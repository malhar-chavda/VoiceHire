from __future__ import annotations
import logging
import asyncio
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.services.postgres_db import get_db, AsyncSessionLocal
from app.services.auth import auth_manager
from app.models.interview_model import (
    InterviewSummary, DashboardStats,
    ReportDetailResponse, DecisionRequest,
)
from app.utils.settings import settings
from app.services.live_session_manager import LiveSessionManager
from app.services.azure_email import azure_email
import app.crud.interview_crud as crud
from app.structure.entities import InterviewStatus, Answer, FinalReport, Recommendation, Resume
from sqlalchemy import select, func, desc, desc as desc_alias # just in case

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/all", response_model=list[InterviewSummary])
async def list_all_interviews(
    db: AsyncSession = Depends(get_db),  #dependency 
    _: str = Depends(auth_manager.get_current_recruiter), #authorization
):
    rows = await crud.get_all_interview_summaries(db)
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
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(auth_manager.get_current_recruiter),
):
    iv_stats, res_count, jd_count = await crud.get_dashboard_stats(db)
    return DashboardStats(
        total_resumes=res_count,
        total_jds=jd_count,
        total_interviews=iv_stats.total or 0,
        pending=iv_stats.pending or 0,
        active=iv_stats.active or 0,
        completed=iv_stats.completed or 0,
        rejected=iv_stats.rejected or 0,
    )


@router.get("/{interview_id}/report", response_model=ReportDetailResponse)
async def get_interview_report(
    interview_id: str,# extract the interview id from the path(url) and pass in to the func as string
    db: AsyncSession = Depends(get_db),
    _: str = Depends(auth_manager.get_current_recruiter),
):
    row = await crud.get_interview_report_details(db, interview_id)
    if not row:
        raise HTTPException(404, "Interview not found")
    iv, res, jd, rpt = row
    return ReportDetailResponse(
        interview_id=iv.id,
        candidate_name=res.candidate_name,
        jd_title=jd.title,
        overall_summary=rpt.overall_summary if rpt else None,
        topics_covered=rpt.topics_covered if rpt else None,
        per_question_scores=rpt.per_question_scores if rpt else None,
        ai_recommendation=rpt.recommendation.value if rpt and rpt.recommendation else None,
        recruiter_decision=rpt.recruiter_decision.value if rpt and rpt.recruiter_decision else None,
    )


@router.post("/{interview_id}/decision")
async def submit_recruiter_decision(
    interview_id: str,
    req: DecisionRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(auth_manager.get_current_recruiter),
):
    rpt = await crud.get_final_report(db, interview_id)
    if not rpt:
        raise HTTPException(404, "Final report not generated")
    try:
        decision = Recommendation(req.decision.lower())
    except ValueError:
        raise HTTPException(400, "Invalid decision")
    rpt.recruiter_decision = decision
    rpt.decision_at = datetime.now(timezone.utc)
    
    iv = await crud.get_interview(db, interview_id)
    if not iv:
        raise HTTPException(404, "Interview not found")
        
    iv.status = {
        "hire": InterviewStatus.HIRED,
        "hold": InterviewStatus.HOLD,
        "reject": InterviewStatus.COMPLETED # Keep completed but decision is made
    }.get(req.decision.lower(), iv.status)

    # Fetch candidate info for email
    res = await db.get(Resume, iv.resume_id)
    if res:
        # Fire and forget email
        asyncio.create_task(
            azure_email.send_post_interview_decision(
                email=res.candidate_email,
                name=res.candidate_name,
                recommendation=decision.value
            )
        )
        logger.info(f"Decision email queued for {res.candidate_email}")

    await db.commit()
    return {"status": "success", "decision": decision.value}

# LIVE INTERVIEW WEBSOCKET

@router.websocket("/ws/live/{interview_id}")#persistent bi-directional connection bw client and server
async def live_interview_websocket(websocket: WebSocket, interview_id: str, token: str):
    await websocket.accept()#accepts the client connection HTTP -> persistent ws
    logger.info(f"|-----| Live interview WS accepted for {interview_id} |-----|")

    #AUTHORIZATION
    try:
        verified_id = auth_manager.verify_interview_token(token)
        if verified_id != interview_id:
            logger.warning(f"|-----| Token mismatch: {verified_id} != {interview_id} |-----|")
            await websocket.close(code=1008)
            return
    except Exception as e:
        logger.warning(f"|-----|Auth failed: {e} |-----|")
        await websocket.close(code=1008)
        return

    #LOAD DATA
    async with AsyncSessionLocal() as db: #async db connection context manager
        interview = await crud.get_interview(db, interview_id)
        if not interview:
            logger.error(f"Interview {interview_id} not found")
            await websocket.close(code=1008)
            return

        result = await db.execute( #execute sql query 
            select(Answer)
            .where(Answer.interview_id == interview_id)
            .order_by(Answer.question_order)
        )
        answers = result.scalars().all() #structuring query 
        #all generated questions are stored here
        try:
            total_que = await db.scalar(
                select(func.count(Answer.id))
                .where(Answer.interview_id == interview_id, Answer.is_followup == False)
            )
        except Exception:
            total_que = 0

        # Mark interview as active
        if interview.status == InterviewStatus.PENDING: #if interview is pending, it will be marked as active and started time will be set
            interview.status = InterviewStatus.ACTIVE
            interview.started_at = datetime.now(timezone.utc)
            await db.commit()

    questions = [q for q in answers if not q.is_followup]
    
    if not questions:
        logger.error(f"|-----|No questions found for interview {interview_id}|-----|")
        await websocket.send_json({
            "type": "error",
            "message": "No interview questions are available. Please contact support."
        })
        await websocket.close(code=1011)
        return

    logger.info(f"|-----| Loaded {len(questions)} questions for interview {interview_id}|-----|")

    # Always start from Q0  "Asked via Live AI" marks are cleaned during the session.
    # Resuming mid-interview via index skipping caused questions to be skipped.
    current_index = 0
    last_question_text = ""   # for repeat_question tool
    closing_done = False    # prevents re-entering closing loop
    asked_questions_history = []  # list of {order, text, is_followup} for UI history
    last_ai_utterance = "" # short-term memory to be used in interruptions
    logger.info(f"|-----| Starting from Q{current_index + 1} of {len(questions)}|-----|")

    
    async def send_json(data: dict): #send data to client in json format
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.debug(f"send_json failed: {e}") 

    async def send_bytes(data: bytes): #send data in bytes format
        try:
            await websocket.send_bytes(data)
        except Exception as e:
            logger.debug(f"send_bytes failed: {e}")

    async def save_candidate_text(text: str):
        """Append candidate transcription to most recently asked question (Background)."""
        if not text or not text.strip():
            return

        async def _save(): #bg execution 
            try:
                async with AsyncSessionLocal() as db:
                    res = await db.execute(
                        select(Answer)
                        .where(Answer.interview_id == interview_id)
                        .order_by(Answer.asked_at.desc())
                        .limit(1)
                    )
                    last = res.scalars().first()
                    if last:
                        existing = last.answer_text or ""
                        if existing == "[Asked via Live AI]":
                            existing = ""
                        last.answer_text = (existing + " " + text).strip()
                        await db.commit()
            except Exception as e:
                logger.error(f"save_candidate_text background task failed: {e}")

        # Fire and forget to avoid blocking the live session
        asyncio.create_task(_save())


    async def on_audio_out(data: bytes): #send audio data to the client
        await send_bytes(data)

    async def on_text_out(text: str): #send text data to the client
        await send_json({"type": "transcript_chunk", "speaker": "ai", "text": text})

    async def on_input_transcription(text: str):
        """Called when Gemini transcribes the candidate's speech."""
        if not text or not text.strip():
            return

        logger.info(f"👤 Candidate: {text}")
        await send_json({"type": "transcript", "speaker": "candidate", "text": text})
        await save_candidate_text(text)

    async def on_output_transcription(text: str):
        nonlocal last_ai_utterance
        if text and text.strip():
            last_ai_utterance = text.strip()   # remember for repeat requests
            await send_json({"type": "transcript", "speaker": "ai", "text": text})

    async def on_interrupted(): 
        logger.info("|-----|Interruption detected notifying client.|-----|")
        await send_json({"type": "interrupted"})
        # Tag the user's speech as an interruption
        asyncio.create_task(manager.enqueue_text("[INTERRUPT]"))
  
        # The audio already buffered is the user's speech that caused the
        # interruption. Purging it would make Gemini deaf to what they said.

    async def on_turn_started(): #notfiy client about the turn started, triggered the moment ai begins speaking 
        await send_json({"type": "turn_started"})

    async def on_turn_complete(): #turn completed, triggered when ai finishes speaking
        await send_json({"type": "turn_complete"})
        # Tag the upcoming user's speech as a normal answer
        asyncio.create_task(manager.enqueue_text("[ANSWER]"))


    async def on_resumption_token(new_token: str): #resuming the session
        try:
            async with AsyncSessionLocal() as db:
                await crud.update_session_resumption_token(db, interview_id, new_token)
        except Exception as e:
            logger.warning(f"Failed to save resumption token: {e}")

    async def on_resumption_error(): #resumption error
        try:
            async with AsyncSessionLocal() as db:
                await crud.update_session_resumption_token(db, interview_id, None)
        except Exception as e:
            logger.warning(f"|-----| Failed to clear resumption token: {e} |-----|")

    
    async def get_question(action: str = "next", text_content: str = None):
        """
        Fetches the next planned question, asks a custom follow-up, or repeats the last question.
        - action: 'next' (default) to get the next scripted question.
        - action: 'followup' to ask a targeted follow-up. Provide 'text_content'.
        - action: 'repeat' to repeat the last asked question exactly.
        """
        nonlocal current_index, last_question_text

        if action == "repeat":
            logger.info(f"|-----| Repeat requested |-----|")
            return (
                f"REPEAT REQUEST\n"
                f"The last question you asked was: '{last_question_text}'.\n"
                f"Say: 'Of course! The question was...' and then repeat it exactly word-for-word."
            )

        # CASE 1 AI-GENERATED FOLLOW-UP
        if action == "followup" and text_content:
            last_question_text = text_content
            asked_questions_history.append({"order": None, "text": text_content, "is_followup": True})

            # Notify UI
            await send_json({ 
                "type": "question",
                "text": text_content,
                "order": None,
                "total": total_que,
                "is_followup": True,
                "history": asked_questions_history[:] #appends follow-up to history 
            })
            logger.info(f"|-----| Follow-up sent: {text_content[:60]} |-----|")
            return (
                f"FOLLOW-UP QUESTION: '{text_content}'\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Say: 'Ummm, here's a follow-up question ' then ask: '{text_content}'\n"
                f"2. Stay silent and wait for their complete answer.\n"
                f"3. After they answer: give 1-2 sentences of specific feedback.\n"
                f"4. Then call get_question(action='next') to move forward to the next scripted question."
            )

        # CASE 2 PRE-LOADED SCRIPTED QUESTION
        if current_index >= len(questions):
            logger.info("All questions completed.")
            return (
                "STATUS: ALL QUESTIONS EXHAUSTED  do NOT ask any more interview questions.\n"
                "1. Say warmly: 'That wraps up all my questions great job getting through them all!'\n"
                "2. Ask ONCE: 'Do you have any questions for me about the role or the team?'\n"
                "3. Answer their question using your general knowledge about the industry (2-3 sentences).\n"
                "4. Say a warm goodbye, then call finish_interview immediately."
            )

        que = questions[current_index]
        current_index += 1
        last_question_text = que.question_text
        asked_questions_history.append({"order": que.question_order, "text": que.question_text, "is_followup": False})

        # Mark as asked in background
        async def _mark_asked(qid):
            try:
                async with AsyncSessionLocal() as db:
                    db_que = await db.get(Answer, qid)
                    if db_que and (not db_que.answer_text or db_que.answer_text == ""):
                        db_que.answer_text = "[Asked via Live AI]"
                        await db.commit()
            except Exception as e:
                logger.error(f"Background mark_asked failed: {e}")

        asyncio.create_task(_mark_asked(que.id)) #update database in background to avoid duplicate questions 

        # Inform UI, what to be displayed on the UI side
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
            f"1. Read this question WORD FOR WORD  do NOT paraphrase or change it.\n"
            f"2. Wait silently for the candidate's full answer.\n"
            f"3. After they answer: give 1-2 sentences of specific feedback or response referencing what they JUST said, regardless of whether it was a technical answer, introduction, or general speech.\n"
            f"4. Then call get_question(action='next') to move to the next scripted question, OR call get_question(action='followup', text_content='...') to dig deeper."
        )


    async def finish_interview(
        strengths: list[str],
        weaknesses: list[str],
        recommendation: str,
        overall_summary: str
    ):
        """Finalizes the interview with the AI's evaluation summary. Generating final report for the candidate"""
        logger.info(f"|-----|Finishing interview: rec={recommendation}|-----|")
        try:
            async with AsyncSessionLocal() as db:
                rec = recommendation.lower() if recommendation.lower() in ["hire", "hold", "reject"] else "hold"

                existing = await crud.get_final_report(db, interview_id)
                if not existing:
                    report = FinalReport(
                        interview_id=interview_id,
                        overall_summary=overall_summary,
                        recommendation=Recommendation(rec),
                        topics_covered=strengths or [],
                        per_question_scores={"strengths": strengths, "weaknesses": weaknesses}
                    )
                    db.add(report)

                iv = await crud.get_interview(db, interview_id)
                if iv:
                    iv.status = InterviewStatus.COMPLETED
                    iv.completed_at = datetime.now(timezone.utc)

                await db.commit()

            await send_json({
                "type": "completed",
                "status": "completed",
                "recommendation": rec,
                "overall_summary": overall_summary,
                "final_score": None,
            })
            return "Interview finalized successfully."
        except Exception as e:
            logger.error(f"finish_interview failed: {e}", exc_info=True)
            return f"Error finalizing: {str(e)}"

    #AI SESSION
    os.environ.pop("GOOGLE_API_KEY", None)

    system_instruction = """
You are Aaspas, a warm, professional human technical interviewer. Be natural and conversational—never robotic or scripted.

=== QUESTION RULE (ABSOLUTE NEVER BREAK THIS) ===
- You MUST call get_question(action='next') to fetch EVERY new interview question from the predefined list.
- You MUST call get_question(action='followup', text_content='...') for every follow-up probe. Never ask a follow-up question without calling the tool.
- You MUST call get_question(action='repeat') if the candidate asks you to repeat the question.
- If get_question() says 'ALL QUESTIONS EXHAUSTED', move to closing.

=== CORE BEHAVIOURS ===
1. Always follow the INSTRUCTIONS block inside every tool response exactly.
2. The system will tag user speech with one of:
     [ANSWER]       — the candidate is answering the current technical question.
     [INTERRUPT]    — the candidate interrupted while you were speaking.
     [SILENCE]      — the candidate didn't respond (be encouraging).

=== WHEN YOU RECEIVE A TURN TAGGED [INTERRUPT] ===
1. IMMEDIATELY stop and acknowledge what the candidate just said.
2. Respond to the interruption content directly and naturally.
3. Do NOT provide interview feedback. Just answer them or clarify.
4. After resolving the interruption, return to the interview flow if appropriate.

=== WHEN YOU RECEIVE A TURN TAGGED [ANSWER] ===
1. Respond to and evaluate ONLY that answer.
2. Give brief feedback or response (1-2 sentences max) acknowledging what they said, whether it is a technical answer, an introduction, or general speech.
3. Then move to the next question by calling get_question(action='next').

=== HANDLING OUT-OF-CONTEXT REQUESTS (Natural Intelligence) ===
- 'Can you repeat the question?' → Call get_question(action='repeat'). 
- 'Tell me about the company' → Answer in 2 sentences using your own knowledge, then: 'Anyway, back to you...'
- 'How am I doing?' → Give a brief, encouraging assessment, then move on.
- 'Can you speak slower / clarify?' → Accommodate it immediately and naturally.
- Small talk or off-topic → Respond warmly in 1 sentence, then: 'Anyway, let's keep going...'
- Technical term clarification → Explain naturally, then restate the original question.

=== FOLLOW-UP LOGIC ===
- Vague/buzzword answer (no substance) → call get_question(action='followup', text_content='...').
- Strong and complete answer → give specific positive feedback, then call get_question(action='next').
- Weak answer → probe with get_question(action='followup', text_content='...'), NOT next.

=== TONE ===
- Use natural filler phrases: 'Right', 'Got it', 'Interesting', 'Fair enough', 'I see'.
- Be warm and encouraging but honest. Never sycophantic.
"""

    model_name = "gemini-3.1-flash-live-preview"
 
    manager = LiveSessionManager(
        api_key=settings.GEMINI_API_KEY,
        model=model_name, 
        system_instruction=system_instruction,
        initial_resumption_token=None,
        on_audio_out=on_audio_out,
        on_text_out=on_text_out,
        on_input_transcription=on_input_transcription,
        on_output_transcription=on_output_transcription,
        on_interrupted=on_interrupted,
        on_turn_started=on_turn_started,
        on_turn_complete=on_turn_complete,
        on_resumption_token=on_resumption_token,
        on_resumption_error=on_resumption_error,
        tools=[get_question, finish_interview]
    )

    try:
        await manager.connect()
        logger.info(" ||---||  AI session connected. Sending kickoff trigger. ||---|| ")

        await asyncio.sleep(0.5)
        await manager.enqueue_text(
            "The interview is now starting. You are Aaspas, a warm human technical interviewer. "
            "Greet the candidate naturally in 1-2 sentences, then immediately call get_question(). "
            "ABSOLUTE RULES: "
            "(1) NEVER make up or improvise questions  always call get_question(). "
            "(2) Give 1-2 sentences of specific feedback or response after each candidate answer (whether technical, introduction, or general speech) BEFORE calling any tool. "
            "(3) If interrupted or asked an off-topic question, skip interview feedback entirely and respond to what they said directly. "
            "(4) 'Repeat' requests: repeat the last question or your last sentence immediately without using tools."
        )

        # Main receive loop
        while True:
            try:
                msg = await websocket.receive() # recive text or audio from browser
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected by client.")                                                                                      
                break

            msg_type = msg.get("type") # get the type of message
            if msg_type == "websocket.disconnect":
                logger.info("WebSocket disconnect frame received.")
                break

            # Forward audio bytes from browser → Gemini
            if msg.get("bytes"):
                await manager.enqueue_audio(msg["bytes"]) #send audio to gemini 
            elif msg.get("text"):
                logger.debug(f"Client text: {msg['text'][:100]}")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected.")
    except Exception as e: #prevents the fastapi server from crashing
        logger.error(f"Live interview error: {e}", exc_info=True)
    finally:
        try:
            await manager.disconnect()
        except Exception:
            pass
        logger.info(f"ðŸ”š Live interview session ended for {interview_id}")

