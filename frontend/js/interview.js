import { turn, getSpeechToken } from './api.js'

// Globals
const params = new URLSearchParams(location.search)
const SESSION_TOKEN = params.get('token')

let recognizer = null  // Azure SpeechRecognizer
let speechToken = null
let isListening = false   // accumulate transcript only when true
let fullTranscript = ''
let currentAnswerId = null
let interviewId = null
let silenceTimeout = null
let initialWaitTimeout = null
let mediaStream = null

// DOM refs
const viewPerm     = document.getElementById('view-permission')
const viewRoom     = document.getElementById('view-room')
const viewComplete = document.getElementById('view-complete')
const startBtn     = document.getElementById('start-btn')
const submitBtn    = document.getElementById('submit-btn')
const cameraFeed   = document.getElementById('camera-feed')
const cameraWrap   = document.getElementById('camera-wrap')
const transcriptEl = document.getElementById('transcript')
const questionEl   = document.getElementById('question-text')
const qTag         = document.getElementById('q-tag')
const qCounterEl   = document.getElementById('q-counter')
const progressFill = document.getElementById('progress-fill')
const sdot         = document.getElementById('sdot')
const statusText   = document.getElementById('status-text')
const waveCanvas   = document.getElementById('waveform-canvas')
const scoreFeedback = document.getElementById('score-feedback')

function toast(msg, type = 'info') {
  const el = document.createElement('div')
  el.className = `toast ${type}`
  el.textContent = msg
  document.getElementById('toast-area').appendChild(el)
  setTimeout(() => el.remove(), 4000)
}

function showView(view) {
  ;[viewPerm, viewRoom, viewComplete].forEach(v => v.classList.remove('active'))
  view.classList.add('active')
}

function setStatus(state) {
  const labels = { idle: 'Ready', playing: 'AI Speaking…', listening: 'Listening…', thinking: 'Processing…' }
  sdot.className = `sdot ${state}`
  statusText.textContent = labels[state] || state
  cameraWrap.classList.toggle('listening', state === 'listening')
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

// ── Waveform ───────────────────────────────────────────────────
function startWaveform(stream) {
  const audioCtx = new AudioContext({ sampleRate: 16000 })
  const analyser = audioCtx.createAnalyser()
  analyser.fftSize = 128

  const source = audioCtx.createMediaStreamSource(stream)
  source.connect(analyser)

  const data = new Uint8Array(analyser.freqBinCount)
  const ctx  = waveCanvas.getContext('2d')

  function draw() {
    requestAnimationFrame(draw)
    analyser.getByteFrequencyData(data)

    const W = waveCanvas.offsetWidth || 0
    const H = waveCanvas.offsetHeight || 0

    // Avoid non-finite errors if container is hidden/zero-sized
    if (H <= 0 || W <= 0) return

    waveCanvas.width = W; waveCanvas.height = H
    ctx.clearRect(0, 0, W, H)

    const bars  = 48
    const space = 1.5
    const bw    = (W / bars) - space

    for (let i = 0; i < bars; i++) {
      const freqIdx = Math.floor(i * data.length / bars)
      const val = (data[freqIdx] || 0) / 255
      const bh  = Math.max(4, val * H) // min height 4px
      const x   = i * (bw + space)
      const y   = (H - bh) / 2

      // Robust check before creating gradient
      if (!isFinite(y) || !isFinite(bh)) continue

      const g = ctx.createLinearGradient(0, y, 0, y + bh)
      g.addColorStop(0, '#6c63ff')
      g.addColorStop(1, '#3ecfcf')
      ctx.fillStyle = g
      ctx.beginPath()
      ctx.roundRect(x, y, Math.max(1, bw), bh, 2)
      ctx.fill()
    }
  }
  draw()
}

// ── Azure Speech Recognition (continuous STT) ─────────────────
function initSTT() {
  if (!window.SpeechSDK || !speechToken) return
  const cfg = SpeechSDK.SpeechConfig.fromAuthorizationToken(speechToken.token, speechToken.region)
  cfg.speechRecognitionLanguage = 'en-US'
  const audio = SpeechSDK.AudioConfig.fromDefaultMicrophoneInput()
  recognizer = new SpeechSDK.SpeechRecognizer(cfg, audio)

  recognizer.recognizing = (_, e) => {
    if (!isListening) return
    clearTimeout(silenceTimeout)
    clearTimeout(initialWaitTimeout)

    transcriptEl.innerHTML =
      escHtml(fullTranscript) + `<span class="partial">${escHtml(e.result.text)}</span>`
    transcriptEl.scrollTop = transcriptEl.scrollHeight
  }

  recognizer.recognized = (_, e) => {
    if (!isListening) return
    if (e.result.reason === SpeechSDK.ResultReason.RecognizedSpeech && e.result.text) {
      fullTranscript += e.result.text + ' '
      transcriptEl.textContent = fullTranscript
      transcriptEl.scrollTop   = transcriptEl.scrollHeight

      clearTimeout(silenceTimeout)
      clearTimeout(initialWaitTimeout)

      silenceTimeout = setTimeout(() => {
        if (isListening) submitAnswer()
      }, 5000)
    }
  }

  recognizer.canceled = (_, e) => {
    console.warn('STT canceled:', e.errorDetails)
  }

  recognizer.startContinuousRecognitionAsync(
    () => console.log('[STT] Continuous recognition started'),
    (err) => console.error('[STT] Start error:', err)
  )
}

// ── Azure TTS playback ─────────────────────────────────────────
function playQuestion(questionText, onDone) {
  setStatus('playing')
  isListening = false
  if (window.SpeechSDK && speechToken && questionText) {
    const speechConfig = SpeechSDK.SpeechConfig.fromAuthorizationToken(speechToken.token, speechToken.region)
    speechConfig.speechSynthesisLanguage = 'en-US'
    speechConfig.speechSynthesisVoiceName = 'en-US-AvaMultilingualNeural'

    const audioConfig = SpeechSDK.AudioConfig.fromDefaultSpeakerOutput()
    const synthesizer = new SpeechSDK.SpeechSynthesizer(speechConfig, audioConfig)

    synthesizer.speakTextAsync(
      questionText,
      result => {
        synthesizer.close()
        onDone()
      },
      error => {
        console.error('TTS Error:', error)
        synthesizer.close()
        onDone()
      }
    )
    return
  }

  // Browser TTS fallback
  if ('speechSynthesis' in window && questionText) {
    const utterance = new SpeechSynthesisUtterance(questionText)
    utterance.lang = 'en-US'
    utterance.onend  = () => onDone()
    utterance.onerror = () => onDone()
    window.speechSynthesis.speak(utterance)
    return
  }

  onDone()
}

// ── Handle turn response ───────────────────────────────────────
function handleTurn(data, prevScore = null) {
  interviewId = data.interview_id

  if (prevScore !== null && prevScore !== undefined) {
    scoreFeedback.hidden = false
    scoreFeedback.querySelector('.score-pill').textContent = `${prevScore}/10`
    scoreFeedback.querySelector('.score-msg').textContent  =
      prevScore >= 7 ? 'Great answer!' : 'Noted — moving on.'
  } else {
    scoreFeedback.hidden = true
  }

  if (data.status === 'completed') {
    showCompletion(data)
    return
  }

  const q = data.question
  currentAnswerId = q.answer_id
  const pct = q.total_questions > 0 ? (q.question_order / q.total_questions) * 100 : 0
  progressFill.style.width = `${pct}%`
  qCounterEl.textContent   = `Q${q.question_order} of ${q.total_questions}`

  qTag.innerHTML = q.is_follow_up
    ? 'Follow-up <span class="followup-chip">↳</span>'
    : `Question ${q.question_order}`
  questionEl.textContent = q.question_text

  fullTranscript = ''
  transcriptEl.innerHTML = '<em class="transcript-empty">Speak your answer after the question plays…</em>'
  setStatus('playing')

  playQuestion(q.question_text, () => {
    setStatus('listening')
    isListening = true
    transcriptEl.innerHTML = '<em class="transcript-empty">Listening…</em>'

    clearTimeout(silenceTimeout)
    clearTimeout(initialWaitTimeout)

    initialWaitTimeout = setTimeout(() => {
      if (isListening && fullTranscript.trim() === '') {
        fullTranscript = '[The candidate did not respond. Request them to answer the question or ask for clarification.]'
        submitAnswer()
      }
    }, 12000)
  })
}

// ── Submit answer ──────────────────────────────────────────────
async function submitAnswer() {
  const answer = fullTranscript.trim()
  if (!answer) return
  if (!currentAnswerId) return

  clearTimeout(silenceTimeout)
  clearTimeout(initialWaitTimeout)
  isListening = false

  setStatus('thinking')

  try {
    const data = await turn(SESSION_TOKEN, currentAnswerId, answer)
    handleTurn(data, data.score)
  } catch (err) {
    toast(err.message, 'error')
    setStatus('listening')
    isListening = true
  }
}

// ── Completion screen ──────────────────────────────────────────
function showCompletion(data) {
  if (recognizer) {
    recognizer.stopContinuousRecognitionAsync()
    recognizer.close()
    recognizer = null
  }
  if (mediaStream) mediaStream.getTracks().forEach(t => t.stop())

  // Hide room completely
  cameraWrap.style.display = 'none'

  document.getElementById('c-score').textContent   = data.final_score?.toFixed(1) ?? '—'
  document.getElementById('c-rec').textContent     = (data.recommendation || 'hold').toUpperCase()
  document.getElementById('c-summary').textContent = data.overall_summary || 'Interview concluded.'

  showView(viewComplete)
}

// ── Start interview ────────────────────────────────────────────
startBtn?.addEventListener('click', async () => {
  startBtn.disabled = true
  startBtn.innerHTML = '<span class="spinner spinner-sm"></span> Starting…'

  try {
    // 1. Fetch Azure Speech token
    speechToken = await getSpeechToken(SESSION_TOKEN)

    // 2. Request camera + mic
    let videoEnabled = true
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
    } catch (camErr) {
      videoEnabled = false
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ video: false, audio: true })
      } catch (micErr) {
        throw new Error('Microphone access denied.')
      }
    }

    if (videoEnabled) {
      cameraFeed.srcObject = mediaStream
      await cameraFeed.play()
    } else {
      cameraFeed.style.display = 'none'
    }

    startWaveform(mediaStream)
    showView(viewRoom)

    // 3. Start Azure continuous STT
    if (window.SpeechSDK) initSTT()

    // 4. Fetch first question from backend
    const data = await turn(SESSION_TOKEN)
    handleTurn(data)

  } catch (err) {
    startBtn.disabled = false
    startBtn.textContent = 'Start Interview'
    let msg = err.message
    document.getElementById('perm-error').textContent = msg
    toast(msg, 'error')
  }
})

if (!SESSION_TOKEN) {
  document.getElementById('perm-error').textContent = 'No interview token found.'
  startBtn.disabled = true
}

showView(viewPerm)
setStatus('idle')
