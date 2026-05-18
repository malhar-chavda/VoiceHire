from __future__ import annotations
import logging
import asyncio
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from utils.core.data.postgres_db import get_db, AsyncSessionLocal
from utils.core.services.auth import auth_manager
from models.interview_model import (
    InterviewSummary, DashboardStats,
    ReportDetailResponse, DecisionRequest,
)
from constants.config import settings
from utils.helpers.prompts import LIVE_INTERVIEW_SYSTEM_PROMPT
from utils.core.services.live_session_manager import LiveSessionManager
from utils.core.services.azure_email import azure_email
from models.entities import Interview, Resume, JobDescription, InterviewStatus, Answer, FinalReport, Recommendation

logger = logging.getLogger(__name__)
router = APIRouter()

async def get_interview(db: AsyncSession, interview_id: str):
    return await db.get(Interview, interview_id)

async def update_session_resumption_token(db: AsyncSession, interview_id: str, token: str):
    interview = await db.get(Interview, interview_id)
    if interview:
        interview.session_resumption_token = token
        await db.commit()

async def get_final_report(db: AsyncSession, interview_id: str):
    res = await db.execute(select(FinalReport).where(FinalReport.interview_id == interview_id))
    return res.scalar_one_or_none()

async def get_all_interview_summaries(db: AsyncSession):
    result = await db.execute(
        select(Interview, Resume, JobDescription, FinalReport)
        .join(Resume, Interview.resume_id == Resume.id)
        .join(JobDescription, Interview.jd_id == JobDescription.id)
        .outerjoin(FinalReport, FinalReport.interview_id == Interview.id)
        .order_by(Interview.created_at.desc())
    )
    return result.all()

async def get_dashboard_stats(db: AsyncSession):
    iv_stats = (await db.execute(
        select(
            func.count(Interview.id).label("total"),
            func.sum(case((Interview.status == InterviewStatus.PENDING,   1), else_=0)).label("pending"),
            func.sum(case((Interview.status == InterviewStatus.ACTIVE,    1), else_=0)).label("active"),
            func.sum(case((Interview.status == InterviewStatus.COMPLETED, 1), else_=0)).label("completed"),
            func.sum(case((Interview.status == InterviewStatus.REJECTED,  1), else_=0)).label("rejected"),
        )
    )).one()

    res_count = (await db.execute(select(func.count(Resume.id)))).scalar_one()
    jd_count  = (await db.execute(select(func.count(JobDescription.id)))).scalar_one()

    return iv_stats, res_count, jd_count

async def get_interview_report_details(db: AsyncSession, interview_id: str):
    result = await db.execute(
        select(Interview, Resume, JobDescription, FinalReport)
        .join(Resume, Interview.resume_id == Resume.id)
        .join(JobDescription, Interview.jd_id == JobDescription.id)
        .outerjoin(FinalReport, FinalReport.interview_id == Interview.id)
        .where(Interview.id == interview_id)
    )
    return result.first()


@router.get("/all", response_model=list[InterviewSummary])
async def list_all_interviews(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(auth_manager.get_current_recruiter),
):
    rows = await get_all_interview_summaries(db)
    return [
        InterviewSummary(
            interview_id=iv.id,
            candidate_name=res.candidate_name,
            candidate_email=res.candidate_email,
            jd_title=jd.title,
            status=iv.status.value,
            match_score=iv.match_score,
            final_score=iv.final_score,
            recommendation=rpt.recommendation.value if rpt and rpt.recommendation else None,
            overall_summary=rpt.overall_summary if rpt else None,
            eligible=iv.eligibility,
            created_at=iv.created_at,
            started_at=iv.started_at,
            completed_at=iv.completed_at,
        )
        for iv, res, jd, rpt in rows
    ]


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(auth_manager.get_current_recruiter),
):
    iv_stats, res_count, jd_count = await get_dashboard_stats(db)
    return DashboardStats(
        total_resumes=res_count,
        total_jds=jd_count,
        total_interviews=iv_stats.total or 0,
        pending=iv_stats.pending or 0,
        active=iv_stats.active or 0,
        completed=iv_stats.completed or 0,
        rejected=iv_stats.rejected or 0,
    )


@router.get("/{interview_id}/report", response_model=ReportDetailResponse) #gather data related to finished interview
async def get_interview_report(
    interview_id: str,
    db: AsyncSession = Depends(get_db), 
    _: str = Depends(auth_manager.get_current_recruiter), #only logged in recruiters can access
):
    row = await get_interview_report_details(db, interview_id)#joins table to fetch data 
    if not row:
        raise HTTPException(404, "Interview not found")
    iv, res, jd, rpt = row
    return ReportDetailResponse( #data formatting
        interview_id=iv.id,
        candidate_name=res.candidate_name,
        jd_title=jd.title,
        overall_summary=rpt.overall_summary if rpt else None,
        topics_covered=rpt.topics_covered if rpt else None,
        per_question_scores=rpt.per_question_scores if rpt else None,
        ai_recommendation=rpt.recommendation.value if rpt and rpt.recommendation else None,
        recruiter_decision=rpt.recruiter_decision.value if rpt and rpt.recruiter_decision else None,
        candidate_confidence=rpt.candidate_confidence if rpt else None,
    )


@router.post("/{interview_id}/decision") #HITL - override AI's recomentation
async def submit_recruiter_decision( #recruiter makes final decision on whether
    interview_id: str, 
    req: DecisionRequest, #take decision from front end
    db: AsyncSession = Depends(get_db),
    _: str = Depends(auth_manager.get_current_recruiter), #authentication
):
    rpt = await get_final_report(db, interview_id)
    if not rpt:
        raise HTTPException(404, "Final report not generated")
    try:
        decision = Recommendation(req.decision.lower())
    except ValueError:
        raise HTTPException(400, "Invalid decision")
    rpt.recruiter_decision = decision
    rpt.decision_at = datetime.now(timezone.utc)

    iv = await get_interview(db, interview_id)
    if not iv:
        raise HTTPException(404, "Interview not found")

    iv.status = {
        "hire": InterviewStatus.HIRED,
        "hold": InterviewStatus.HOLD,
        "reject": InterviewStatus.COMPLETED
    }.get(req.decision.lower(), iv.status)

    res = await db.get(Resume, iv.resume_id)
    jd = await db.get(JobDescription, iv.jd_id)
    if res: #send email to candidate with decision
        asyncio.create_task(
            azure_email.send_post_interview_decision(
                email=res.candidate_email,
                name=res.candidate_name,
                recommendation=decision.value,
                job_title=jd.title if jd else "the position"
            )
        )
        logger.info(f"Decision email queued for {res.candidate_email}")

    await db.commit()
    return {"status": "success", "decision": decision.value}

# ─── LIVE INTERVIEW WEBSOCKET ──────────────────────────────────────────────────

@router.websocket("/ws/live/{interview_id}")
async def live_interview_websocket(websocket: WebSocket, interview_id: str, token: str):
    await websocket.accept()
    logger.info(f"|-----| Live interview WS accepted for {interview_id} |-----|")

    # ── AUTHORIZATION ──────────────────────────────────────────────────────────
    try:
        verified_id = auth_manager.verify_interview_token(token)
        if verified_id != interview_id:
            logger.warning(f"|-----| Token mismatch: {verified_id} != {interview_id} |-----|")
            await websocket.close(code=1008)
            return
    except Exception as e:
        logger.warning(f"|-----| Auth failed: {e} |-----|")
        await websocket.close(code=1008)
        return

    # ── LOAD DATA ──────────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        interview = await get_interview(db, interview_id)
        if not interview:
            logger.error(f"Interview {interview_id} not found")
            await websocket.close(code=1008)
            return

        result = await db.execute(
            select(Answer)
            .where(Answer.interview_id == interview_id)
            .order_by(Answer.question_order)
        )
        answers = result.scalars().all()

        try:
            total_que = await db.scalar(
                select(func.count(Answer.id))
                .where(Answer.interview_id == interview_id, Answer.is_followup == False)
            )
        except Exception:
            total_que = 0

        if interview.status == InterviewStatus.PENDING:
            interview.status = InterviewStatus.ACTIVE
            interview.started_at = datetime.now(timezone.utc)
            await db.commit()

    questions = [q for q in answers if not q.is_followup]

    if not questions:
        logger.error(f"|-----| No questions found for interview {interview_id} |-----|")
        await websocket.send_json({
            "type": "error",
            "message": "No interview questions are available. Please contact support."
        })
        await websocket.close(code=1011)
        return

    logger.info(f"|-----| Loaded {len(questions)} questions for interview {interview_id} |-----|")

    # ── SESSION STATE ──────────────────────────────────────────────────────────
    current_index = 0
    last_question_text = ""
    closing_done = False            # gates the closing flow to prevent infinite loop
    asked_questions_history = []
    intro_done = False
    evaluated_question_index = 0
    interview_finished = False      # prevents [ANSWER] tags from being sent after finish
    kickoff_sent = False            # ensures the greeting is only sent ONCE ever
    silence_timer: asyncio.Task = None  # tracks silence after AI turn
    just_interrupted = False        # prevents [ANSWER] racing with [INTERRUPT] handling

    logger.info(f"|-----| Starting from Q{current_index + 1} of {len(questions)} |-----|")

    # ── HELPERS ────────────────────────────────────────────────────────────────
    async def send_json(data: dict): #sends json to frontend
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.debug(f"send_json failed: {e}")

    async def send_bytes(data: bytes):
        try:
            await websocket.send_bytes(data)
        except Exception as e:
            logger.debug(f"send_bytes failed: {e}")

    async def save_candidate_text(text: str):
        """
        Append candidate transcription to the current question being evaluated.

        - During intro (intro_done=False) we skip entirely.
        - After intro, we write to questions[evaluated_question_index].
        """
        nonlocal evaluated_question_index

        if not text or not text.strip():
            return

        if not intro_done:
            logger.debug(f"save_candidate_text: intro phase, skipping: {text[:40]}")
            return

        target_index = evaluated_question_index

        async def _save():
            try:
                async with AsyncSessionLocal() as db:
                    if target_index < len(questions):
                        qid = questions[target_index].id
                        db_que = await db.get(Answer, qid)
                        if db_que:
                            existing = db_que.answer_text or ""
                            if existing == "[Asked via Live AI]":
                                existing = ""
                            db_que.answer_text = (existing + " " + text).strip()
                            await db.commit()
                            logger.debug(f"save_candidate_text: saved to Q{target_index + 1} (id={qid})")
                    else:
                        logger.debug(f"save_candidate_text: target_index {target_index} out of range, skipping.")
            except Exception as e:
                logger.error(f"save_candidate_text background task failed: {e}")

        asyncio.create_task(_save())

    async def dispatch_event(event_type: str, text: str = None, data: bytes = None):
        nonlocal silence_timer, just_interrupted
        if event_type == "audio_out":
            await send_bytes(data)
            return
           
        payload = None
        if event_type == "text_out":
            payload = {"type": "transcript_chunk", "speaker": "ai", "text": text}
        elif event_type == "input_transcription": #saves text to db
            if not text or not text.strip(): return
            if silence_timer and not silence_timer.done():
                silence_timer.cancel() # cancel silence timer if candidate speaks
                silence_timer = None
            logger.info(f"👤 Candidate: {text}")
            payload = {"type": "transcript", "speaker": "candidate", "text": text}
            await save_candidate_text(text)
        elif event_type == "output_transcription": #sends to frontend for AI audio
            if not text or not text.strip(): return
            payload = {"type": "transcript", "speaker": "ai", "text": text}
        elif event_type == "turn_started":
            just_interrupted = False # reset flag when AI starts speaking
            payload = {"type": "turn_started"}
        elif event_type == "turn_complete":
            payload = {"type": "turn_complete"}
        elif event_type == "interrupted":
            just_interrupted = True # set flag when interruption detected
            logger.info("|-----| Interruption detected — notifying UI. |-----|")
            payload = {"type": "interrupted"} 

        if payload:
            await send_json(payload)
        #whether the AI stops naturally or is cut off, it always switches back to listening mode
        if event_type == "interrupted": 
            await asyncio.sleep(0.05)
            asyncio.create_task(manager.enqueue_text("[ANSWER]", turn_complete=False)) #listening state
        elif event_type == "turn_complete" and not interview_finished and not just_interrupted:
            asyncio.create_task(manager.enqueue_text("[ANSWER]", turn_complete=False)) #natural end of turn

    async def handle_resumption(token: str = None):
        try:
            async with AsyncSessionLocal() as db:
                await update_session_resumption_token(db, interview_id, token)
        except Exception as e:
            logger.warning(f"Resumption update failed: {e}")

    # ── TOOL: get_question ─────────────────────────────────────────────────────
    async def get_question(action: str = "next", text_content: str = None):
        """
        Fetches the next scripted question, asks a follow-up, or repeats the last question.

        action:
          'next'     — advance to the next pre-generated question (DEFAULT).
          'followup' — ask a targeted follow-up; supply text_content.
          'repeat'   — repeat the last asked question word-for-word.

        IMPORTANT: You MUST call this tool for every question.
        Never invent or paraphrase a question yourself.
        """
        nonlocal current_index, last_question_text, intro_done, evaluated_question_index, closing_done

        # First call to get_question signals intro is over.
        if not intro_done:
            intro_done = True
            logger.info("|-----| Intro phase complete. Technical questions starting. |-----|")

        # ── REPEAT ────────────────────────────────────────────────────────────
        if action == "repeat":
            logger.info("|-----| Repeat requested |-----|")
            return (
                f"REPEAT REQUEST\n"
                f"The last question you asked was: '{last_question_text}'.\n"
                f"Say: 'Of course, the question was...' and then repeat it exactly word-for-word."
            )

        # ── AI-GENERATED FOLLOW-UP ────────────────────────────────────────────
        if action == "followup" and text_content:
            last_question_text = text_content
            asked_questions_history.append({"order": None, "text": text_content, "is_followup": True})

            await send_json({
                "type": "question",
                "text": text_content,
                "order": None,
                "total": total_que,
                "is_followup": True,
                "history": asked_questions_history[:]
            })
            logger.info(f"|-----| Follow-up sent: {text_content[:60]} |-----|")
            return (
                f"FOLLOW-UP: '{text_content}'\n\n"
                f"1. Say 'Here is a follow-up—' then ask exactly: '{text_content}'\n"
                f"2. End your turn immediately and wait for the candidate to answer.\n"
                f"Do not call any other tools right now."
            )

        # ── ALL QUESTIONS DONE ─────────────────────────────────────────────────
        if current_index >= len(questions):
 
            if closing_done:
                logger.warning("|-----| get_question called again after closing — returning finish signal |-----|")
                return (
                    "STATUS: INTERVIEW ALREADY CLOSING.\n"
                    "You already asked if they have questions. "
                    "Call finish_interview() NOW. Do not ask anything else."
                )

            closing_done = True
            logger.info("|-----| All questions exhausted — entering closing phase. |-----|")
            return (
                "STATUS: ALL QUESTIONS EXHAUSTED\n\n"
                "CLOSING — follow these steps EXACTLY:\n"
                "1. Say 3-4 warm, natural sentences to close the interview. Be genuine.\n"
                "   Example: 'And that's all the questions I had for you today. You tackled some\n"
                "   tough ones — I really appreciate your honesty and effort throughout.\n"
                "   It was a genuinely good conversation. Best of luck with the rest of the process!'\n"
                "2. Do NOT ask if they have questions for you.\n"
                "3. Call finish_interview() IMMEDIATELY after saying goodbye.\n"
                "4. Say NOTHING after finish_interview() returns."
            )

        #  NEXT SCRIPTED QUESTION 
        que = questions[current_index]
        evaluated_question_index = current_index   # snapshot BEFORE advancing
        current_index += 1
        last_question_text = que.question_text
        asked_questions_history.append({
            "order": que.question_order,
            "text": que.question_text,
            "is_followup": False
        })

        async def _mark_asked(qid):
            try:
                async with AsyncSessionLocal() as db:
                    db_que = await db.get(Answer, qid)
                    if db_que and (not db_que.answer_text or db_que.answer_text == ""):
                        db_que.answer_text = "[Asked via Live AI]"
                        await db.commit()
            except Exception as e:
                logger.error(f"Background mark_asked failed: {e}")

        asyncio.create_task(_mark_asked(que.id))

        await send_json({
            "type": "question",
            "text": que.question_text,
            "order": que.question_order,
            "total": total_que,
            "is_followup": False,
            "history": asked_questions_history[:]
        })

        logger.info(f"|-----| Returning Q{que.question_order} from RAM cache |-----|")
        return (
            f"QUESTION {que.question_order} of {total_que}: '{que.question_text}'\n\n"
            f"STRICT INSTRUCTIONS:\n"
            f"1. Read this question WORD FOR WORD — do NOT paraphrase or change it.\n"
            f"2. End your turn immediately and wait for the candidate's answer.\n"
            f"Do not call any other tools right now."
        )

    #  TOOL: finish_interview 
    async def finish_interview(
        strengths: list[str] = None,
        weaknesses: list[str] = None,
        recommendation: str = "hold",
        overall_summary: str = "Interview completed.",
        confidence_score: float = 0.0,
        confidence_observations: str = "",
        candidate_feedback: str = "Thank you for taking the time to interview with us today."
    ):
        """
        Finalizes the interview and saves the report.
        Call this after the closing, OR immediately if the candidate wants to quit early.
        Works with partial data — use whatever answers are available.
        IMPORTANT: Strictly use candidate's ACTUAL performance for the report (strengths, weaknesses, etc). Do not say they performed well if they did poorly. Generate the final report purely based on the candidate's performance.
        candidate_feedback MUST be 4-5 sentences of constructive feedback directly for the candidate, without revealing the actual score or recommendation.
        """
        nonlocal interview_finished, silence_timer
        logger.info(f"|-----| finish_interview called: rec={recommendation} |-----|")

        # Set flag FIRST so on_turn_complete stops sending [ANSWER]
        interview_finished = True
        # Cancel any pending silence watchdog
        if silence_timer and not silence_timer.done():
            silence_timer.cancel()
            silence_timer = None

        try:
            async with AsyncSessionLocal() as db:
                rec = recommendation.lower() if recommendation.lower() in ["hire", "hold", "reject"] else "hold"

                existing = await get_final_report(db, interview_id)
                if not existing:
                    report = FinalReport(
                        interview_id=interview_id,
                        overall_summary=overall_summary,
                        recommendation=Recommendation(rec),
                        topics_covered=strengths or [],
                        per_question_scores={"strengths": strengths, "weaknesses": weaknesses},
                        candidate_confidence={
                            "score": confidence_score,
                            "observations": confidence_observations
                        }
                    )
                    db.add(report)

                iv = await get_interview(db, interview_id)
                if iv:
                    iv.status = InterviewStatus.COMPLETED
                    iv.completed_at = datetime.now(timezone.utc)
                    # Scale confidence_score (0-10) to final_score (0-100)
                    iv.final_score = min(max(float(confidence_score or 0) * 10.0, 0.0), 100.0)

                await db.commit()
                if iv:
                    await db.refresh(iv)
                    final_score_val = iv.final_score
                else:
                    final_score_val = confidence_score * 10.0

            await send_json({#display after completion of interview
                "type": "completed",
                "status": "completed",
                "candidate_feedback": candidate_feedback
            })
            return "Interview finalized successfully. Session is now closed."
        except Exception as e:
            logger.error(f"finish_interview failed: {e}", exc_info=True)
            return f"Error finalizing: {str(e)}"

    # AI SESSION SETUP - crash recovery and starting new conversation
    os.environ.pop("GOOGLE_API_KEY", None)
    system_instruction = LIVE_INTERVIEW_SYSTEM_PROMPT
    model_name = settings.GEMINI_MODEL_NAME

    async def on_session_reconnected():
        """Fired by LiveSessionManager when Gemini internally reconnects.
        Send a silent RESUME to prevent the AI from re-greeting or skipping ahead."""
        logger.info("||---|| Internal Gemini reconnect detected — sending RESUME signal. ||---||")
        await asyncio.sleep(0.3)
        await manager.enqueue_text(
            "[SYSTEM - RECONNECT - DO NOT GREET AGAIN]\n"
            "The session reconnected after a brief network interruption. "
            "Do NOT re-introduce yourself. Do NOT greet the candidate again. "
            "Simply wait silently for the candidate to continue speaking. "
            "Do NOT call get_question() unless the candidate has already finished answering.",
            turn_complete=False #ai in listening mode
        )

    manager = LiveSessionManager(
        api_key=settings.GEMINI_API_KEY,
        model=model_name,
        system_instruction=system_instruction,
        initial_resumption_token=None,
        on_audio_out=lambda d: dispatch_event("audio_out", data=d),
        on_text_out=lambda t: dispatch_event("text_out", text=t),
        on_input_transcription=lambda t: dispatch_event("input_transcription", text=t),
        on_output_transcription=lambda t: dispatch_event("output_transcription", text=t),
        on_interrupted=lambda: dispatch_event("interrupted"),
        on_turn_started=lambda: dispatch_event("turn_started"),
        on_turn_complete=lambda: dispatch_event("turn_complete"),
        on_resumption_token=lambda t: handle_resumption(t),
        on_resumption_error=lambda: handle_resumption(None),
        on_session_reconnected=on_session_reconnected,
        tools=[get_question, finish_interview]
    )

    try:
        await manager.connect() #opens live connection to google sesrver
        logger.info("||---|| AI session connected. Sending kickoff trigger. ||---||")

        await asyncio.sleep(0.5)

        # Kickoff — only send ONCE. On reconnects, the session resumption token
        # replays context so Gemini already knows where it is. Sending the intro
        # again causes it to re-greet the candidate.
        if not kickoff_sent: 
            kickoff_sent = True
            # Send ONLY the trigger signal. The system instruction in prompts.py 
            await manager.enqueue_text("[SYSTEM - ONE TIME STARTUP - DO NOT REPEAT]")

        # Main receive loop, hearing and disconnection handling
        while True: #data from user to ai
            try:
                msg = await websocket.receive()#receive data from frontend
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected by client.")
                break

            msg_type = msg.get("type") #captures sound -> raw bytes -> manager -> gemini
            if msg_type == "websocket.disconnect":
                logger.info("WebSocket disconnect frame received.")
                break

            if msg.get("bytes"):
                await manager.enqueue_audio(msg["bytes"])
            elif msg.get("text"):
                logger.debug(f"Client text: {msg['text'][:100]}")

    except WebSocketDisconnect:#handle disconnect
        logger.info("WebSocket disconnected.")
    except Exception as e:
        logger.error(f"Live interview error: {e}", exc_info=True)
    finally:
        try:
            await manager.disconnect()
        except Exception:
            pass
        logger.info(f"📚 Live interview session ended for {interview_id}")