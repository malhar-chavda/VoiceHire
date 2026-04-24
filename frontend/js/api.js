// any changes
// API Client
const API = '/api'
//error handling, server error to js error, converts backend json response to js object
async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, opts)
  const body = await res.json().catch(() => ({ detail: res.statusText }))
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`)
  return body
}
// handles the recruiter login flow 
export async function login(username, password) {
  const fd = new FormData() //sends credentials to backend OAuth2 endpoint
  fd.append('username', username)
  fd.append('password', password)
  return apiFetch('/auth/login', { method: 'POST', body: fd })
}
// interview flow starts
export async function uploadDocuments(resumeFile, jdFile, accessToken) {
  const fd = new FormData()
  fd.append('resume_file', resumeFile)
  fd.append('jd_file', jdFile)
  return apiFetch('/documents/upload', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: fd,
  })
}
// handles the evaluation logic (LLM)
export async function evaluate(resumeId, jdId, numQuestions, accessToken) {
  return apiFetch('/interview/evaluate', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ resume_id: resumeId, jd_id: jdId, num_questions: numQuestions }),
  })
}
// interview loop management. Sends candidate's ans and gets the next que in return
export async function turn(sessionToken, answerId = null, answerText = '') {
  const body = { session_token: sessionToken }
  if (answerId)   body.answer_id   = answerId
  if (answerText) body.answer_text = answerText
  return apiFetch('/interview/turn', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
// speech token for azure speech services- requests an access token from azure speech service
// allowing the frontend to use the STT and TTS services
export async function getSpeechToken(sessionToken) {
  return apiFetch('/interview/speech-token', {
    headers: { Authorization: `Bearer ${sessionToken}` },
  })
}

export function health() {
  return apiFetch('/health').catch(() => null)
}

// Dashboard (recruiter)
function authHdr(token) { return { Authorization: `Bearer ${token}` } }

export function listResumes(token){ return apiFetch('/resumes/', { headers: authHdr(token) }) }

export function listJDs(token){ return apiFetch('/job-descriptions/', { headers: authHdr(token) }) }

export function listInterviews(token){ return apiFetch('/interview/all', { headers: authHdr(token) }) }
// retrieves the dashboard stats (counts the no of events)
export function getDashboardStats(token){ return apiFetch('/interview/stats', { headers: authHdr(token) }) }

export function getInterviewReport(id, token){ return apiFetch(`/interview/${id}/report`, { headers: authHdr(token) }) }

export function submitDecision(id, decision, token) {
  return apiFetch(`/interview/${id}/decision`, {
    method: 'POST',
    headers: { ...authHdr(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision }),
  })
}
