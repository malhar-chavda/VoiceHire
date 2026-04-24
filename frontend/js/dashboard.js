import { listResumes, listJDs, listInterviews, getInterviewReport, submitDecision } from './api.js'
// Imports API wrappers to cleanly interact with backend endpoints.

//  Auth guard (proactive: validate JWT structure before any request) 
function isTokenLikelyValid(token) {
  if (!token) return false
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return false
    const payload = JSON.parse(atob(parts[1]))
    // Check expiry if present
    if (payload.exp && payload.exp * 1000 < Date.now()) return false
    return true
  } catch {
    return false
  }
}
// Checks if the JWT is superficially valid and not expired, skipping redundant API requests if already unauthorized.

const token = sessionStorage.getItem('access_token')
// Grabs the current access token from the session memory to power authenticated actions.

if (!isTokenLikelyValid(token)) {
  sessionStorage.removeItem('access_token')
  location.replace('index.html')
}
// Serves as an early auth-guard, immediately kicking un-tokened or expired sessions back to the login page.

//   Helpers 
const $ = id => document.getElementById(id)
// Shorthand function to make interacting with DOM elements faster and the code cleaner.

function fmt(dt) {
  if (!dt) return '—'
  const d = new Date(dt)
  return isNaN(d) ? '—' : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}
// Normalizes raw timestamp properties into a compact formatting readable by humans (e.g., 21 Apr 2026).
function fmtTime(dt) {
  if (!dt) return '—'
  const d = new Date(dt)
  return isNaN(d) ? '—' : d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}
// Like above, but tailored to show both date and time for interactions needing higher precision like completed interviews.
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
// Mitigates script injection attacks by sanitizing potentially malicious text outputs in the UI structure.

/** Safely get first character of a string, returning '?' as fallback */
function initial(name) {
  const s = String(name ?? '').trim()
  return s.length > 0 ? s[0].toUpperCase() : '?'
}
// Pulls the first letter of an email or name to drop into avatar circles automatically, degrading safely.

/** Safe string field — returns '' if null/undefined */
function safeStr(v) { return String(v ?? '') }
// Forces any loosely typed javascript values (including null/undefined) into flat empty strings to avoid runtime crashes.

function statusBadge(s) {
  const map = {
    pending:   ['badge-warn', '⏳ Pending'],
    active:    ['badge-primary', '🎙️ Active'],
    completed: ['badge-success', '✅ Completed'],
    rejected:  ['badge-error', '✗ Not Eligible'],
    hire:      ['badge-success', '🟢 Hire'],
    hold:      ['badge-warn', '🟡 Hold'],
  }
  const key = safeStr(s).toLowerCase()
  const [cls, label] = map[key] ?? ['badge-warn', s ?? '—']
  return `<span class="badge ${cls}">${label}</span>`
}
// Constructs consistent, styled badge components based on unified pipeline status strings.

function recBadge(r) {
  if (!r) return '<span class="muted-text">—</span>'
  return statusBadge(r)
}
// Generates recruiter status badges with fallback handling for unassigned scenarios.
// Wraps statusBadge to handle null/undefined recruitment statuses gracefully with a muted placeholder.

function scoreBar(val, max = 10) {
  if (val === null || val === undefined) return '<span class="muted-text">—</span>'
  const pct = Math.min((val / max) * 100, 100)
  const colorClass = val >= 7 ? 'bar-success' : val >= 4 ? 'bar-warn' : 'bar-error'
  return `<div class="score-bar-wrap">
    <div class="score-bar-track">
      <div class="score-bar-fill ${colorClass}" style="width:${pct}%"></div>
    </div>
    <span class="score-bar-label">${Number(val).toFixed(1)}</span>
  </div>`
}
// Converts integer scores into colored progress bar HTML injectables natively grading candidates.

//  Toast notifications 
function toast(msg, type = 'info') {
  const el = document.createElement('div')
  el.className = `toast ${type}`
  el.textContent = msg
  $('toast-area').appendChild(el)
  setTimeout(() => el.remove(), 4000)
}
// Spawns brief context notifications for users without halting the screen visually via native DOM element pushes.

//  Debounce utility 
function debounce(fn, delay = 250) {
  let timer
  return (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), delay)
  }
}
// Function throttler discarding intermediate event triggers preventing heavy recomputation on rapid typing.

//  Navigation 
const navItems = document.querySelectorAll('.nav-item[data-section]')
const sections = document.querySelectorAll('.dash-section')

const sectionTitles = {
  overview: 'Dashboard Overview',
  candidates: 'Candidates',
  jds: 'Job Descriptions',
  interviews: 'All Interviews',
  reports: 'Reports',
}

function showSection(id) {
  navItems.forEach(n => n.classList.toggle('active', n.dataset.section === id))
  sections.forEach(s => s.classList.toggle('active', s.id === 'sec-' + id))
  const titleEl = $('topbar-title')
  if (titleEl) titleEl.textContent = sectionTitles[id] ?? 'Dashboard'
}
// Traverses elements linking visible section IDs logically toggling tab DOM contents and title tracking simultaneously.

navItems.forEach(n => n.addEventListener('click', () => showSection(n.dataset.section)))

//  State 
let resumes = [], jds = [], interviews = []

//  Section-level loading indicators 
function setSectionLoading(tableId, colspan, message = 'Loading…') {
  const el = $(tableId)
  if (el) el.innerHTML = `<tr><td colspan="${colspan}" class="empty-row">${message}</td></tr>`
}
// Generates loading states within empty interface structures natively communicating latency when API loads block.

//  Load data with granular error handling 
async function loadAll() {
  setRefreshing(true)

  // Show per-section loading skeletons immediately
  setSectionLoading('recent-table', 5, 'Loading…')
  setSectionLoading('resumes-table', 4, 'Loading…')
  setSectionLoading('jds-table', 3, 'Loading…')
  setSectionLoading('iv-table', 7, 'Loading…')

  const [resumesResult, jdsResult, interviewsResult] = await Promise.allSettled([
    listResumes(token),
    listJDs(token),
    listInterviews(token),
  ])

  // Handle each result independently — partial data still renders
  let hasAuthFailure = false

  if (resumesResult.status === 'fulfilled') {
    resumes = Array.isArray(resumesResult.value) ? resumesResult.value : []
  } else {
    resumes = []
    const err = resumesResult.reason
    if (isAuthError(err)) { hasAuthFailure = true } else {
      toast('Could not load candidates: ' + err.message, 'error')
      setSectionLoading('resumes-table', 4, '⚠️ Failed to load candidates.')
    }
  }

  if (jdsResult.status === 'fulfilled') {
    jds = Array.isArray(jdsResult.value) ? jdsResult.value : []
  } else {
    jds = []
    const err = jdsResult.reason
    if (isAuthError(err)) { hasAuthFailure = true } else {
      toast('Could not load job descriptions: ' + err.message, 'error')
      setSectionLoading('jds-table', 3, '⚠️ Failed to load job descriptions.')
    }
  }

  if (interviewsResult.status === 'fulfilled') {
    interviews = Array.isArray(interviewsResult.value) ? interviewsResult.value : []
  } else {
    interviews = []
    const err = interviewsResult.reason
    if (isAuthError(err)) { hasAuthFailure = true } else {
      toast('Could not load interviews: ' + err.message, 'error')
      setSectionLoading('recent-table', 5, '⚠️ Failed to load interviews.')
      setSectionLoading('iv-table', 7, '⚠️ Failed to load interviews.')
    }
  }

  // Handle auth failure once — redirect after collecting all results
  if (hasAuthFailure) {
    sessionStorage.removeItem('access_token')
    toast('Session expired. Redirecting to login…', 'error')
    setTimeout(() => location.replace('index.html'), 1500)
    setRefreshing(false)
    return
  }

  renderStats()
  renderResumes()
  renderJDs()
  renderInterviews()
  renderReports()
  updateLastRefresh()
  setRefreshing(false)
}
// Broad asynchronous initiator orchestrating total UI dataset fetching handling simultaneous loading queues.

function isAuthError(err) {
  return err?.message?.includes('401') || err?.message?.includes('credentials') || err?.message?.includes('Unauthorized')
}
// Checks error bodies textually tracking predictable server side responses relating to authorization expiration.

function setRefreshing(v) {
  $('global-loader')?.classList.toggle('hidden', !v)
  const btn = $('refresh-btn')
  if (btn) {
    btn.disabled = v
    btn.innerHTML = v ? '<span class="spinner spinner-sm"></span> Refreshing…' : '<span>🔄</span> Refresh'
  }
}
// Blocks interacting with API refresh workflows managing native states preventing race conditions natively.

function updateLastRefresh() {
  const el = $('last-refresh')
  if (el) el.textContent = 'Last updated: ' + new Date().toLocaleTimeString()
}
// Adjusts contextual local time labels establishing system trust visually without needing exact synchronization.

//  Overview Stats 
function renderStats() {
  const pending = interviews.filter(i => safeStr(i.status) === 'pending').length
  const active = interviews.filter(i => safeStr(i.status) === 'active').length
  const completed = interviews.filter(i => safeStr(i.status) === 'completed').length
  const rejected = interviews.filter(i => safeStr(i.status) === 'rejected').length

  const set = (id, val) => { const el = $(id); if (el) el.textContent = val }
  set('stat-resumes', resumes.length)
  set('stat-jds', jds.length)
  set('stat-interviews', interviews.length)
  set('stat-completed', completed)
  set('stat-active', active)
  set('stat-rejected', rejected)

  // Recent activity — most recent 8
  const recent = interviews.slice(0, 8)
  const tbody = $('recent-table')
  if (!tbody) return

  if (recent.length === 0) {
    tbody.innerHTML = emptyRow(5, '📭 No interviews yet. Send your first evaluation to get started.')
    return
  }

  tbody.innerHTML = recent.map(i => {
    const isCompleted = safeStr(i.status).toLowerCase() === 'completed'
    const reportBtn = isCompleted
      ? `<button class="btn btn-sm btn-secondary view-report-btn" data-id="${i.interview_id}" style="white-space:nowrap">📊 Report</button>`
      : `<span class="muted-text" style="font-size:0.8rem">—</span>`
    return `<tr>
      <td><strong>${esc(i.candidate_name)}</strong><div class="sub-text">${esc(i.candidate_email)}</div></td>
      <td>${esc(i.jd_title)}</td>
      <td>${statusBadge(i.status)}</td>
      <td>${i.match_score != null ? `<span class="score-text">${Number(i.match_score).toFixed(1)}%</span>` : '—'}</td>
      <td class="muted-text">${fmtTime(i.created_at)}</td>
      <td>${reportBtn}</td>
    </tr>`
  }).join('')
}
// Unpacks raw stat objects logically compiling overview numbers dynamically formatting brief widget rows directly in dashboard.

//  Shared empty-row builder 
function emptyRow(colspan, message) {
  return `<tr><td colspan="${colspan}" class="empty-row">${message}</td></tr>`
}
// Provides formatted, reliable placeholder strings standardizing missing list data rows logically.

//  Delegate click on "View Report" buttons inside recent activity table 
$('recent-table')?.addEventListener('click', async (e) => {
  const btn = e.target.closest('.view-report-btn')
  if (!btn) return
  await openReportModal(btn.dataset.id)
})

//  Resumes table 
function renderResumes(filter = '') {
  const f = filter.toLowerCase()
  const rows = f
    ? resumes.filter(r =>
        safeStr(r.candidate_name).toLowerCase().includes(f) ||
        safeStr(r.candidate_email).toLowerCase().includes(f))
    : resumes

  const tbody = $('resumes-table')
  if (!tbody) return

  tbody.innerHTML = rows.length === 0
    ? emptyRow(4, resumes.length === 0
        ? '📭 No candidates found. Upload a resume to get started.'
        : '🔍 No candidates match your search.')
    : rows.map(r => `
      <tr>
        <td>
          <div class="avatar-cell">
            <div class="avatar">${esc(initial(r.candidate_name))}</div>
            <div>
              <strong>${esc(r.candidate_name)}</strong>
              <div class="sub-text">${esc(r.candidate_email)}</div>
            </div>
          </div>
        </td>
        <td class="muted-text">${fmt(r.created_at)}</td>
        <td><code class="id-code">${esc(safeStr(r.resume_id).slice(0, 8))}…</code></td>
        <td>
          ${r.resume_blob_url
            ? `<a href="${esc(r.resume_blob_url)}" target="_blank" rel="noopener" class="btn btn-sm btn-secondary">📄 View PDF</a>`
            : '<span class="muted-text">No file</span>'}
        </td>
      </tr>`).join('')

  const cnt = $('resume-count')
  if (cnt) cnt.textContent = rows.length
}
// Iterates and natively rebuilds graphical resume sets supporting textual filters displaying candidate resources interactively.

$('resume-search').addEventListener('input', debounce(e => renderResumes(e.target.value), 250))

//  JD table 
function renderJDs(filter = '') {
  const f = filter.toLowerCase()
  const rows = f
    ? jds.filter(j => safeStr(j.title).toLowerCase().includes(f))
    : jds

  const tbody = $('jds-table')
  if (!tbody) return

  tbody.innerHTML = rows.length === 0
    ? emptyRow(3, jds.length === 0
        ? '📭 No job descriptions found. Upload a JD to get started.'
        : '🔍 No job descriptions match your search.')
    : rows.map(j => `
      <tr>
        <td><strong>${esc(j.title)}</strong></td>
        <td class="muted-text">${fmt(j.created_at)}</td>
        <td>
          ${j.jd_blob_url
            ? `<a href="${esc(j.jd_blob_url)}" target="_blank" rel="noopener" class="btn btn-sm btn-secondary">📄 View JD</a>`
            : '<span class="muted-text">No file</span>'}
        </td>
      </tr>`).join('')

  const cnt = $('jd-count')
  if (cnt) cnt.textContent = rows.length
}
// Extracts description items populating tabular structures letting users parse JD blob file strings swiftly.

$('jd-search').addEventListener('input', debounce(e => renderJDs(e.target.value), 250))

//  Interviews table 
let ivFilter = 'all'

function renderInterviews(search = '') {
  const s = search.toLowerCase()
  let rows = interviews

  if (ivFilter !== 'all') {
    rows = rows.filter(i => safeStr(i.status).toLowerCase() === ivFilter)
  }
  if (s) {
    rows = rows.filter(i =>
      safeStr(i.candidate_name).toLowerCase().includes(s) ||
      safeStr(i.jd_title).toLowerCase().includes(s))
  }

  const tbody = $('iv-table')
  if (!tbody) return

  tbody.innerHTML = rows.length === 0
    ? emptyRow(8, interviews.length === 0
        ? '📭 No interviews found. Evaluate a candidate to get started.'
        : '🔍 No interviews match this filter.')
    : rows.map(i => {
      const isCompleted = safeStr(i.status).toLowerCase() === 'completed'
      const reportBtn = isCompleted
        ? `<button class="btn btn-sm btn-secondary view-report-btn" data-id="${i.interview_id}" style="white-space:nowrap">📊 View Report</button>`
        : `<span class="muted-text" style="font-size:0.8rem">—</span>`
      return `<tr>
        <td>
          <div class="avatar-cell">
            <div class="avatar">${esc(initial(i.candidate_name))}</div>
            <div>
              <strong>${esc(i.candidate_name)}</strong>
              <div class="sub-text">${esc(i.candidate_email)}</div>
            </div>
          </div>
        </td>
        <td>${esc(i.jd_title)}</td>
        <td>${statusBadge(i.status)}</td>
        <td>${i.match_score != null ? `<span class="score-text">${Number(i.match_score).toFixed(1)}%</span>` : '—'}</td>
        <td>${i.final_score != null ? scoreBar(i.final_score) : '—'}</td>
        <td>${recBadge(i.recommendation)}</td>
        <td class="muted-text">${fmt(i.created_at)}</td>
        <td>${reportBtn}</td>
      </tr>`
    }).join('')

  const cnt = $('iv-count')
  if (cnt) cnt.textContent = rows.length
}
// Computes table lines handling layered active filter strings structurally rendering completed pipeline evaluations securely.

//  Delegate click on "View Report" buttons inside interviews table 
$('iv-table')?.addEventListener('click', async (e) => {
  const btn = e.target.closest('.view-report-btn')
  if (!btn) return
  await openReportModal(btn.dataset.id)
})

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'))
    btn.classList.add('active')
    ivFilter = btn.dataset.filter
    renderInterviews($('iv-search')?.value?.toLowerCase() ?? '')
  })
})
$('iv-search').addEventListener('input', debounce(e => renderInterviews(e.target.value), 250))

//  Reports 
function renderReports() {
  const completed = interviews.filter(i => safeStr(i.status) === 'completed')
  const grid = $('reports-grid')
  if (!grid) return

  if (completed.length === 0) {
    grid.innerHTML = `<div class="empty-state">
      <div style="font-size:2.5rem">🗂️</div>
      <p>No completed interviews yet.<br>Reports will appear here once a candidate finishes their session.</p>
    </div>`
    return
  }

  const recColors = { hire: '#10b981', reject: '#ef4444', hold: '#f59e0b' }

  grid.innerHTML = completed.map(i => {
    const rec = safeStr(i.recommendation).toLowerCase()
    const col = recColors[rec] ?? '#94a3b8'
    return `
    <div class="report-card glass-card" data-id="${i.interview_id}" style="cursor:pointer">
      <div class="report-header">
        <div class="avatar avatar-lg">${esc(initial(i.candidate_name))}</div>
        <div class="report-meta">
          <div class="report-name">${esc(i.candidate_name)}</div>
          <div class="sub-text">${esc(i.jd_title)}</div>
          <div class="sub-text">${fmtTime(i.completed_at)}</div>
        </div>
      </div>
      <div class="report-scores">
        <div class="report-score-item">
          <div class="rs-label">Match</div>
          <div class="rs-val">${i.match_score != null ? Number(i.match_score).toFixed(1) + '%' : '—'}</div>
        </div>
        <div class="report-score-item">
          <div class="rs-label">Interview</div>
          <div class="rs-val">${i.final_score != null ? Number(i.final_score).toFixed(1) + '/10' : '—'}</div>
        </div>
      </div>
      <div class="report-rec" style="color:${col}">${(rec || 'pending').toUpperCase()}</div>
    </div>`
  }).join('')
}
// Gathers isolated interview datasets dynamically building fully responsive review card components cleanly formatted for dashboard browsing.

//  Report Modal 
$('reports-grid')?.addEventListener('click', async (e) => {
  const card = e.target.closest('.report-card')
  if (!card) return
  await openReportModal(card.dataset.id)
})

let currentReportId = null

async function openReportModal(id) {
  currentReportId = id
  const modal = $('report-modal')
  const content = $('modal-report-content')
  modal.classList.remove('hidden')
  content.innerHTML = `<div style="text-align:center;padding:2rem;"><span class="spinner spinner-sm" style="display:inline-block"></span> Loading report...</div>`
  
  try {
    const report = await getInterviewReport(id, token)
    
    // Topics covered list
    const topicsHtml = (report.topics_covered || []).map(t => `<span class="badge badge-primary">${esc(t)}</span>`).join(' ')
    
    // Per question scores — now includes candidate answer
    const scoresHtml = report.per_question_scores
      ? Object.entries(report.per_question_scores).map(([k, res]) => {
          const scoreVal = Number(res.score ?? 0)
          const scoreColor = scoreVal >= 7 ? 'var(--success)' : scoreVal >= 4 ? 'var(--warn)' : 'var(--error)'
          const answerHtml = res.answer
            ? `<div style="background:rgba(255,255,255,0.04);border-left:3px solid var(--primary);padding:0.5rem 0.75rem;border-radius:0 6px 6px 0;font-size:0.85rem;color:var(--accent);margin:0.5rem 0;">
                <span style="font-size:0.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.8px;display:block;margin-bottom:0.25rem;">Candidate's Answer</span>
                ${esc(res.answer)}
               </div>`
            : ''
          return `
          <div style="margin-bottom:1rem; padding-bottom:1rem; border-bottom: 1px dashed var(--border)">
            <div style="font-weight:600; font-size:0.95rem; line-height:1.4;">Q: ${esc(res.question || k)}</div>
            ${answerHtml}
            <div style="display:flex; gap:0.5rem; align-items:center; margin-top:0.3rem;">
              <span class="badge badge-primary" style="border-color:${scoreColor};color:${scoreColor};">Score: ${scoreVal}/10</span>
            </div>
            <div style="color:var(--muted);font-size:0.85rem; margin-top:0.4rem;line-height:1.5;">${esc(res.feedback)}</div>
          </div>`
        }).join('')
      : '<em class="muted-text">No question scores available</em>'
      
    content.innerHTML = `
      <div class="report-section">
        <h4 style="margin-bottom: 0.5rem;">Overview</h4>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.5rem;">
          <div><span class="muted-text">Candidate:</span> <strong>${esc(report.candidate_name)}</strong></div>
          <div><span class="muted-text">Position:</span> <strong>${esc(report.jd_title)}</strong></div>
        </div>
        <div style="display:flex;gap:1.5rem; margin-top: 0.75rem;">
          <div><span class="muted-text">AI Recommendation:</span> ${statusBadge(report.ai_recommendation)}</div>
          <div><span class="muted-text">Recruiter Decision:</span> ${statusBadge(report.recruiter_decision || 'pending')}</div>
        </div>
      </div>
      
      <div class="report-section">
        <h4>Summary</h4>
        <p>${esc(report.overall_summary || 'No summary available.')}</p>
      </div>

      <div class="report-section">
        <h4>Topics Covered</h4>
        <div style="display:flex;gap:0.4rem;flex-wrap:wrap; margin-top: 0.5rem;">${topicsHtml || '<em class="muted-text">No topics</em>'}</div>
      </div>

      <div class="report-section" style="max-height:300px;overflow-y:auto; border: 1px solid var(--border);">
        <h4 style="position:sticky; top:0; background:var(--surface-2); z-index:1; padding: 0.5rem 0;">Answer Analysis</h4>
        ${scoresHtml}
      </div>
    `
  } catch (err) {
    content.innerHTML = `<div class="empty-state">⚠️ Error loading report: ${esc(err.message)}</div>`
  }
}
// Initiates remote fetches retrieving detailed AI report breakdowns layering parsed JSON inside stylized modal components.

$('close-modal')?.addEventListener('click', () => {
  $('report-modal').classList.add('hidden')
  currentReportId = null
})

// Click outside to close
$('report-modal')?.addEventListener('click', (e) => {
  if (e.target.id === 'report-modal') {
    $('report-modal').classList.add('hidden')
    currentReportId = null
  }
})

async function handleDecision(decision) {
  if (!currentReportId) return
  setRefreshing(true)
  try {
    await submitDecision(currentReportId, decision, token)
    toast(`Decision saved: ${decision.toUpperCase()}`, 'success')
    $('report-modal').classList.add('hidden')
    await loadAll() // refresh data
  } catch (err) {
    toast(`Failed to save decision: ${err.message}`, 'error')
    setRefreshing(false)
  }
}
// Fires mutation calls mapping client decisions toward API structures effectively refreshing global sets automatically locking workflows properly.

$('btn-hire')?.addEventListener('click', () => handleDecision('hire'))
$('btn-hold')?.addEventListener('click', () => handleDecision('hold'))
$('btn-reject')?.addEventListener('click', () => handleDecision('reject'))

//  Logout 
$('logout-btn').addEventListener('click', () => {
  sessionStorage.removeItem('access_token')
  location.replace('index.html')
})

//  Refresh button 
$('refresh-btn').addEventListener('click', loadAll)

//  Main portal link 
$('portal-btn')?.addEventListener('click', () => location.replace('index.html'))

//  Init 
showSection('overview')
loadAll()
