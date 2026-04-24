import { login, uploadDocuments, evaluate } from './api.js'

// State 
// Migrate legacy localStorage token to sessionStorage (one-time)
// This ensures that authentication sessions expire properly when the browser tab is closed.
const _legacy = localStorage.getItem('vh_token')
if (_legacy) {
  sessionStorage.setItem('access_token', _legacy)
  localStorage.removeItem('vh_token')
}
// Application-level variables storing current authentication headers and uploaded document references.
let accessToken = sessionStorage.getItem('access_token') || null
let resumeId = null
let jdId = null
let resumeFile = null
let jdFile = null
// Controls which screen of the pipeline the recruiter is actively viewing 
let currentStep = accessToken ? 1 : 0   // 0=login, 1=upload, 2=review, 3=result

// DOM refs 
const screens = document.querySelectorAll('.screen')
const stepDots = document.querySelectorAll('.step')
const loginForm = document.getElementById('login-form')
const loginError = document.getElementById('login-error')
const uploadBtn = document.getElementById('upload-btn')
const evaluateBtn = document.getElementById('evaluate-btn')
const numQSelect = document.getElementById('num-questions')
const resumeDrop = document.getElementById('resume-drop')
const jdDrop = document.getElementById('jd-drop')
const resumeInput = document.getElementById('resume-input')
const jdInput = document.getElementById('jd-input')

// Screen management 
// Transition wrapper handling visual UI paging between different states of the upload pipeline.
// Syncs the active screen index and correspondingly updates the progress dot UI components.
function showScreen(n) {
  currentStep = n
  screens.forEach((s, i) => s.classList.toggle('active', i === n))
  stepDots.forEach((d, i) => {
    d.classList.toggle('active', i === n)
    d.classList.toggle('done', i < n)
  })
}

function toast(msg, type = 'info') {
  const el = document.createElement('div')
  el.className = `toast ${type}`
  el.textContent = msg
  document.getElementById('toast-area').appendChild(el)
  setTimeout(() => el.remove(), 4000)
}

function setLoading(btn, loading, label) {
  btn.disabled = loading
  btn.innerHTML = loading
    ? `<span class="spinner spinner-sm"></span> ${label}`
    : label
}

// Login 
loginForm?.addEventListener('submit', async (e) => {
  e.preventDefault()
  loginError.textContent = ''
  const username = e.target.username.value.trim()
  const password = e.target.password.value

  setLoading(e.target.querySelector('button'), true, 'Signing in...')
  try {
    const { access_token } = await login(username, password)
    accessToken = access_token
    sessionStorage.setItem('access_token', access_token)
    showScreen(1)
  } catch (err) {
    loginError.textContent = err.message
  } finally {
    setLoading(e.target.querySelector('button'), false, 'Sign In →')
  }
})

document.getElementById('logout-btn')?.addEventListener('click', () => {
  sessionStorage.removeItem('access_token')
  accessToken = null
  showScreen(0)
})

// File upload zones 
// Generalized drag-and-drop handler for intuitive PDF inputs.
function setupDrop(zone, input, type) {
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over') })
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'))
  zone.addEventListener('drop', (e) => {
    e.preventDefault()
    zone.classList.remove('drag-over')
    const file = e.dataTransfer.files[0]
    if (file && file.type === 'application/pdf') handleFile(zone, type, file)
    else toast('Only PDF files are accepted', 'error')
  })
  input.addEventListener('change', () => {
    if (input.files[0]) handleFile(zone, type, input.files[0])
  })
}

function handleFile(zone, type, file) {
  if (type === 'resume') resumeFile = file
  else jdFile = file
  zone.classList.add('has-file')
  zone.querySelector('.drag-filename').textContent = `✓ ${file.name}`
  checkUploadReady()
}

function checkUploadReady() {
  uploadBtn.disabled = !(resumeFile && jdFile)
}

setupDrop(resumeDrop, resumeInput, 'resume')
setupDrop(jdDrop, jdInput, 'jd')

// Upload & Extract 
// Fires after valid files are placed. Uploads documents, hits extraction API, and displays results in the review screen.
uploadBtn?.addEventListener('click', async () => {
  if (!resumeFile || !jdFile) return
  setLoading(uploadBtn, true, 'Uploading & extracting...')
  try {
    const data = await uploadDocuments(resumeFile, jdFile, accessToken)
    resumeId = data.resume_id
    jdId     = data.jd_id

    // Populate review screen
    document.getElementById('info-name').textContent  = data.candidate_name  || '—'
    document.getElementById('info-email').textContent = data.candidate_email || '—'
    document.getElementById('info-title').textContent = data.jd_title        || '—'
    showScreen(2)
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    setLoading(uploadBtn, false, 'Upload & Analyze →')
  }
})

// Evaluate 
// Submits paired documents for final AI matching verification and kicks off the background eval mechanism.
evaluateBtn?.addEventListener('click', async () => {
  const numQ = parseInt(numQSelect?.value || '8')
  setLoading(evaluateBtn, true, 'Evaluating match...')
  try {
    const data = await evaluate(resumeId, jdId, numQ, accessToken)
    renderResult(data)
    showScreen(3)
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    setLoading(evaluateBtn, false, 'Evaluate Match →')
  }
})

function renderResult(data) {
  // Score ring animation
  // Uses stroke-offset properties on SVG elements to create a smooth circular loading animation to the match percentage.
  const circumference = 2 * Math.PI * 54
  const fill = document.getElementById('score-ring-fill')
  const offset = circumference - (data.match_score / 100) * circumference
  fill.style.strokeDasharray  = circumference
  fill.style.strokeDashoffset = circumference
  requestAnimationFrame(() => requestAnimationFrame(() => {
    fill.style.strokeDashoffset = offset
  }))
  document.getElementById('score-num').textContent = Math.round(data.match_score)

  // Eligibility badge
  const el = document.getElementById('eligibility-badge')
  if (data.eligibility) {
    el.className = 'badge badge-success'
    el.innerHTML = 'Eligible — Interview invite sent'
  } else {
    el.className = 'badge badge-error'
    el.innerHTML = 'Not eligible — Rejection email sent'
  }

  // Reason
  const reasonEl = document.getElementById('result-reason')
  if (reasonEl) reasonEl.textContent = data.reason || ''
}

//Back buttons 
document.getElementById('back-to-upload')?.addEventListener('click', () => showScreen(1))
document.getElementById('back-to-review')?.addEventListener('click', () => showScreen(2))

//Init 
showScreen(currentStep)
