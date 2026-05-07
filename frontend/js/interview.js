// ─────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────
const params        = new URLSearchParams(location.search);
const SESSION_TOKEN = params.get('token');
let interviewId     = params.get('interview_id');

// Recovery: If interview_id is missing but token is present, try to extract it from the JWT 'sub' claim
if (!interviewId && SESSION_TOKEN) {
    try {
        const payload = JSON.parse(atob(SESSION_TOKEN.split('.')[1]));
        if (payload && payload.sub) {
            interviewId = payload.sub;
            console.log("Recovered interviewId from token:", interviewId);
        }
    } catch (e) {
        console.error("Failed to decode token for recovery:", e);
    }
}

// ─────────────────────────────────────────────────────────────
// DOM refs
// ─────────────────────────────────────────────────────────────
const viewPerm     = document.getElementById('view-permission');
const viewRoom     = document.getElementById('view-room');
const viewComplete = document.getElementById('view-complete');

const startBtn    = document.getElementById('start-btn');
const permError   = document.getElementById('perm-error');

const cameraFeed  = document.getElementById('camera-feed');
const cameraWrap  = document.getElementById('camera-wrap');
const camHolder   = document.getElementById('camera-placeholder');
const waveCanvas  = document.getElementById('waveform-canvas');

const sdot        = document.getElementById('sdot');
const statusText  = document.getElementById('status-text');
const qCounterEl  = document.getElementById('q-counter');
const progressFill= document.getElementById('progress-fill');
const followupBanner = document.getElementById('followup-banner');
const qTag        = document.getElementById('q-tag');
const qText       = document.getElementById('question-text');
const transcriptEl= document.getElementById('transcript');

const prevBtn     = document.getElementById('prev-q-btn');
const nextBtn     = document.getElementById('next-q-btn');
const openHistBtn = document.getElementById('open-history-btn');
const closeHistBtn= document.getElementById('close-history-btn');
const historyDrawer  = document.getElementById('history-drawer');
const historyOverlay = document.getElementById('history-overlay');
const historyList    = document.getElementById('history-list');
const toastArea      = document.getElementById('toast-area');

// ─────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────
let socket          = null;
let manualClose     = false;
let isStarted       = false;

// Audio playback
let playbackCtx     = null;
let nextStartTime   = 0;
let activeSourceNodes = [];
let isAIPlaying     = false;

// Microphone / uplink
let micStream       = null;
let audioCtx        = null;
let processorNode   = null;

// Waveform
let analyser        = null;
let waveAnimId      = null;

// Question history
let questionsHistory  = [];   // [{order, text, is_followup}]
let currentLiveQuestion = null;
let historyViewIndex  = -1;   // -1 = showing live

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────
function setStatus(s) {
    const labels = {
        live: 'Live',
        playing: 'AI Speaking',
        listening: 'Listening',
        thinking: 'Processing…',
        reconnecting: 'Reconnecting…',
        interrupted: 'Interrupted',
    };
    sdot.className = `sdot ${s}`;
    statusText.textContent = labels[s] || s;
}

function toast(msg, type = 'info', ms = 3500) {
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.textContent = msg;
    toastArea.appendChild(t);
    setTimeout(() => t.remove(), ms);
}

function updateTranscript(text, speaker, isTemp = false) {
    // Remove placeholder
    const empty = transcriptEl.querySelector('.transcript-empty');
    if (empty) empty.remove();

    // Update streaming temp line
    if (isTemp) {
        let last = transcriptEl.querySelector('.transcript-line.temp');
        if (!last) {
            last = document.createElement('div');
            last.className = `transcript-line ${speaker} temp`;
            transcriptEl.appendChild(last);
        }
        last.textContent = text;
    } else {
        // Remove old temp for this speaker
        transcriptEl.querySelectorAll('.transcript-line.temp').forEach(el => el.remove());
        const line = document.createElement('div');
        line.className = `transcript-line ${speaker}`;
        line.textContent = text;
        transcriptEl.appendChild(line);
    }
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function displayQuestion(q, isLive) {
    if (q.is_followup) {
        followupBanner.classList.add('visible');
        qTag.innerHTML = 'Follow-up <span class="followup-chip">↩</span>';
    } else {
        followupBanner.classList.remove('visible');
        qTag.innerHTML = q.order != null ? `Question ${q.order}` : 'Question';
    }
    qText.textContent = q.text;
    updateNavButtons();
}

function updateNavButtons() {
    const count = questionsHistory.length;
    if (count === 0) {
        prevBtn.disabled = true;
        nextBtn.disabled = true;
        return;
    }

    if (historyViewIndex === -1) {
        // Showing live question
        nextBtn.disabled = true;
        prevBtn.disabled = count < 2;
    } else {
        prevBtn.disabled = historyViewIndex === 0;
        nextBtn.disabled = historyViewIndex >= count - 1 && currentLiveQuestion === questionsHistory[count - 1];
    }
}

function buildHistoryList() {
    if (questionsHistory.length === 0) {
        historyList.innerHTML = '<p style="color:var(--muted);font-size:.82rem;text-align:center;padding:2rem 0;">No questions asked yet.</p>';
        return;
    }
    historyList.innerHTML = '';
    questionsHistory.forEach((q, i) => {
        const item = document.createElement('div');
        item.className = 'history-item' + (historyViewIndex === i ? ' active-q' : '');
        item.innerHTML = `
            <div class="history-item-meta">
                <span class="history-item-num">${q.is_followup ? 'Follow-up' : `Q${q.order}`}</span>
                ${q.is_followup ? '<span class="history-followup-tag">↩</span>' : ''}
            </div>
            <div class="history-item-text">${q.text}</div>
        `;
        item.addEventListener('click', () => {
            historyViewIndex = i;
            displayQuestion(q, false);
            buildHistoryList();
        });
        historyList.appendChild(item);
    });
}

// History drawer
openHistBtn.addEventListener('click', () => {
    buildHistoryList();
    historyDrawer.classList.add('open');
    historyOverlay.classList.add('open');
});
closeHistBtn.addEventListener('click', closeHistoryDrawer);
historyOverlay.addEventListener('click', closeHistoryDrawer);
function closeHistoryDrawer() {
    historyDrawer.classList.remove('open');
    historyOverlay.classList.remove('open');
}

// Prev / Next navigation
prevBtn.addEventListener('click', () => {
    if (historyViewIndex === -1) {
        // Go to second-to-last
        historyViewIndex = questionsHistory.length - 2;
    } else if (historyViewIndex > 0) {
        historyViewIndex--;
    }
    if (historyViewIndex >= 0 && historyViewIndex < questionsHistory.length) {
        displayQuestion(questionsHistory[historyViewIndex], false);
        updateNavButtons();
    }
});

nextBtn.addEventListener('click', () => {
    if (historyViewIndex === -1) return;
    if (historyViewIndex < questionsHistory.length - 1) {
        historyViewIndex++;
        displayQuestion(questionsHistory[historyViewIndex], false);
    } else {
        // Return to live
        historyViewIndex = -1;
        if (currentLiveQuestion) displayQuestion(currentLiveQuestion, true);
    }
    updateNavButtons();
});

// ─────────────────────────────────────────────────────────────
// Completion
// ─────────────────────────────────────────────────────────────
function showCompletion(msg) {
    closeWebSocket();
    stopMic();
    viewRoom.classList.remove('active');
    viewComplete.classList.add('active');

    document.getElementById('c-score').textContent = msg.final_score != null ? msg.final_score : '—';
    const recMap = { hire: '✅ Hire', hold: '⏸ Hold', reject: '❌ Reject' };
    document.getElementById('c-rec').textContent = recMap[msg.recommendation] || msg.recommendation || '—';
    document.getElementById('c-summary').textContent = msg.overall_summary || '';
}

// ─────────────────────────────────────────────────────────────
// Camera
// ─────────────────────────────────────────────────────────────
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        cameraFeed.srcObject = stream;
        cameraFeed.style.display = 'block';
        camHolder.style.display  = 'none';
    } catch {
        cameraFeed.style.display = 'none';
        camHolder.style.display  = 'flex';
    }
}

// ─────────────────────────────────────────────────────────────
// Waveform
// ─────────────────────────────────────────────────────────────
function startWaveform(stream) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaStreamSource(stream);
    analyser  = ctx.createAnalyser();
    analyser.fftSize = 64;
    src.connect(analyser);

    const buf = new Uint8Array(analyser.frequencyBinCount);
    const canvas = waveCanvas;
    const dctx   = canvas.getContext('2d');

    function draw() {
        waveAnimId = requestAnimationFrame(draw);
        analyser.getByteFrequencyData(buf);
        const W = canvas.offsetWidth;
        const H = canvas.offsetHeight;
        canvas.width  = W;
        canvas.height = H;
        dctx.clearRect(0, 0, W, H);

        const barW = W / buf.length * 2.2;
        let x = 0;
        buf.forEach(v => {
            const h = (v / 255) * H * 0.85;
            dctx.fillStyle = `rgba(163,177,138,${0.4 + (v/255)*0.6})`;
            dctx.fillRect(x, H - h, barW - 1, h);
            x += barW;
        });
    }
    draw();
}

// ─────────────────────────────────────────────────────────────
// Microphone uplink (16kHz PCM → WebSocket)
// ─────────────────────────────────────────────────────────────
async function startUplink() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true }
        });
        micStream = stream;
        startWaveform(stream);

        audioCtx = new AudioContext({ sampleRate: 16000 });
        await audioCtx.audioWorklet.addModule('js/pcm-processor.js').catch(() => {});

        const source = audioCtx.createMediaStreamSource(stream);

        try {
            processorNode = new AudioWorkletNode(audioCtx, 'pcm-processor');
            processorNode.port.onmessage = (e) => {
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(e.data);
                }
            };
            source.connect(processorNode);
            processorNode.connect(audioCtx.destination);
        } catch {
            // Fallback: ScriptProcessor
            const sp = audioCtx.createScriptProcessor(4096, 1, 1);
            sp.onaudioprocess = (e) => {
                if (socket && socket.readyState !== WebSocket.OPEN) return;
                const f32 = e.inputBuffer.getChannelData(0);
                const i16 = new Int16Array(f32.length);
                f32.forEach((s, i) => { i16[i] = Math.max(-32768, Math.min(32767, s * 32767)); });
                if (socket) socket.send(i16.buffer);
            };
            source.connect(sp);
            sp.connect(audioCtx.destination);
            processorNode = sp;
        }
    } catch (err) {
        console.error('Mic uplink failed:', err);
        toast('Microphone access failed.', 'error');
    }
}

function stopMic() {
    if (processorNode) { try { processorNode.disconnect(); } catch {} processorNode = null; }
    if (audioCtx)      { try { audioCtx.close(); }          catch {} audioCtx = null; }
    if (micStream)     { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    if (waveAnimId)    { cancelAnimationFrame(waveAnimId); waveAnimId = null; }
}

// ─────────────────────────────────────────────────────────────
// Audio playback (24kHz PCM from Gemini)
// ─────────────────────────────────────────────────────────────
function playAudioChunk(arrayBuf) {
    if (!playbackCtx) {
        playbackCtx  = new AudioContext({ sampleRate: 24000 });
        nextStartTime = playbackCtx.currentTime;
    }

    const i16    = new Int16Array(arrayBuf);
    const f32    = new Float32Array(i16.length);
    i16.forEach((v, i) => { f32[i] = v / 32768; });

    const abuf   = playbackCtx.createBuffer(1, f32.length, 24000);
    abuf.copyToChannel(f32, 0);

    const source = playbackCtx.createBufferSource();
    source.buffer = abuf;
    source.connect(playbackCtx.destination);

    const startAt = Math.max(nextStartTime, playbackCtx.currentTime + 0.01);
    source.start(startAt);
    nextStartTime = startAt + abuf.duration;

    activeSourceNodes.push(source);
    isAIPlaying = true;
    setStatus('playing');

    source.onended = () => {
        activeSourceNodes = activeSourceNodes.filter(n => n !== source);
        // Only reset status if this node ended naturally (not force-stopped)
        if (!source._manualStop && activeSourceNodes.length === 0) {
            isAIPlaying = false;
            setStatus('listening');
        }
    };
}

function stopAllPlayback() {
    // Mark nodes as intentionally stopped so their onended doesn't reset status
    activeSourceNodes.forEach(node => {
        node._manualStop = true;
        try { node.stop(); } catch (e) {}
    });
    activeSourceNodes = [];
    if (playbackCtx) nextStartTime = playbackCtx.currentTime;
    isAIPlaying = false;
}

// ─────────────────────────────────────────────────────────────
// WebSocket
// ─────────────────────────────────────────────────────────────
function connectWebSocket() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        manualClose = false;
        socket.close();
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/api/interview/ws/live/${interviewId}?token=${SESSION_TOKEN}`;

    console.log(`[WS] Connecting to ${url}`);
    socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';

    socket.onopen = () => {
        console.log('[WS] ✅ Connected');
        manualClose = false;
        setStatus('live');
        if (!processorNode) startUplink();
    };

    socket.onmessage = async (event) => {
        if (event.data instanceof ArrayBuffer) {
            if (window.ignoreAudioUntil && Date.now() < window.ignoreAudioUntil) return;
            try {
                playAudioChunk(event.data);
            } catch (err) {
                console.error("Audio playback error:", err);
            }
            return;
        }
        try {
            const msg = JSON.parse(event.data);
            handleServerEvent(msg);
        } catch (e) {
            console.warn('[WS] Non-JSON text:', event.data);
        }
    };

    socket.onclose = (e) => {
        console.warn(`[WS] Closed — code: ${e.code}, reason: ${e.reason}`);
        if (isStarted && !manualClose && !viewComplete.classList.contains('active')) {
            setStatus('reconnecting');
            toast('Connection lost. Reconnecting…', 'warn');
            setTimeout(connectWebSocket, 2000);
        }
    };

    socket.onerror = (err) => {
        console.error('[WS] Error:', err);
    };
}

function closeWebSocket() {
    manualClose = true;
    if (socket) {
        socket.close();
        socket = null;
    }
}

// ─────────────────────────────────────────────────────────────
// Server Events
// ─────────────────────────────────────────────────────────────
function handleServerEvent(msg) {
    // ── Interruption ──
    if (msg.event === 'interrupted' || msg.type === 'interrupted') {
        console.log('[WS] ⚡ Interruption — stopping playback.');
        stopAllPlayback();

        setStatus('interrupted');
        cameraWrap.classList.add('listening');

        const qPanel = document.querySelector('.question-panel');
        if (qPanel) {
            qPanel.classList.add('interrupt-flash');
            setTimeout(() => qPanel.classList.remove('interrupt-flash'), 400);
        }

        toast('You interrupted — AI is listening…', 'info');

        // Extended ignore window to flush stale AI audio tail
        window.ignoreAudioUntil = Date.now() + 800;

        // Settle into listening after brief pause (only if still interrupted)
        setTimeout(() => {
            if (sdot && sdot.className.includes('interrupted')) {
                setStatus('listening');
            }
        }, 900);
        return;
    }

    // ── Turn started ──
    if (msg.type === 'turn_started') {
        setStatus('playing');
        const spinner = document.getElementById('loading-overlay');
        if (spinner) spinner.style.display = 'none';
        return;
    }

    // ── Turn complete ──
    if (msg.type === 'turn_complete') {
        setStatus('listening');
        return;
    }

    // ── Transcript ──
    if (msg.type === 'transcript' || msg.type === 'transcript_chunk') {
        updateTranscript(msg.text, msg.speaker, msg.type === 'transcript_chunk');
        // Only update status for candidate speech — AI transcript arrives alongside audio
        if (msg.speaker === 'candidate') {
            if (msg.type === 'transcript') {
                setStatus('thinking');   // Final transcription = Gemini processing
            } else {
                setStatus('listening');  // Streaming partial = still listening
            }
        }
        return;
    }

    // ── Question (new or follow-up) ──
    if (msg.type === 'question') {
        const spinner = document.getElementById('loading-overlay');
        if (spinner) spinner.style.display = 'none';

        const q = {
            order: msg.order,
            text: msg.text,
            is_followup: msg.is_followup || false
        };

        // Update history from server if provided
        if (msg.history && Array.isArray(msg.history)) {
            questionsHistory = msg.history;
        } else if (!questionsHistory.find(h => h.text === q.text)) {
            questionsHistory.push(q);
        }

        // Set as current live question and reset nav to live view
        currentLiveQuestion = q;
        historyViewIndex = -1;

        // Update question counter
        if (q.order != null && msg.total) {
            qCounterEl.textContent = `Q${q.order} of ${msg.total}`;
            const pct = (q.order / msg.total) * 100;
            progressFill.style.width = `${pct}%`;
        } else if (q.is_followup) {
            qCounterEl.textContent = `Follow-up`;
        }

        displayQuestion(q, true);
        buildHistoryList();

        if (q.is_followup) {
            updateTranscript(`[Follow-up] ${q.text}`, 'ai', false);
        }
        return;
    }

    // ── Completion ──
    if (msg.type === 'completed' || msg.status === 'completed') {
        showCompletion(msg);
        return;
    }

    // ── Error ──
    if (msg.type === 'error') {
        toast(msg.message || 'An error occurred.', 'error', 6000);
        return;
    }
}

// ─────────────────────────────────────────────────────────────
// Entry — Permission screen
// ─────────────────────────────────────────────────────────────
if (!SESSION_TOKEN || !interviewId) {
    document.body.innerHTML = '<p style="color:#f87171;padding:2rem;text-align:center;">Invalid interview link. Please check the URL and try again.</p>';
} else {
    viewPerm.classList.add('active');

    startBtn.addEventListener('click', async () => {
        permError.textContent = '';
        startBtn.disabled = true;
        startBtn.textContent = 'Starting…';

        try {
            await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
        } catch {
            try {
                await navigator.mediaDevices.getUserMedia({ audio: true });
            } catch (e) {
                permError.textContent = 'Microphone access is required. Please allow and retry.';
                startBtn.disabled = false;
                startBtn.textContent = 'Grant Access & Start';
                return;
            }
        }

        isStarted = true;
        viewPerm.classList.remove('active');
        viewRoom.classList.add('active');

        await startCamera();
        connectWebSocket();
    });
}
