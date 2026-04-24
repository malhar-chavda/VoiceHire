from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Header, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import os
from sqlalchemy import select
import app.crud.interview_crud as crud

from app.services.postgres_db import get_db, AsyncSessionLocal
from app.services.auth import auth_manager
from app.structure.entities import (
    Resume, JobDescription, Interview, InterviewStatus, Answer, FinalReport,
)
from app.models.interview_model import (
    EvaluateRequest, EvaluateResponse,
    TurnRequest, TurnResponse,
    QuestionResponse, SpeechTokenResponse,
    InterviewSummary, DashboardStats,
    ReportDetailResponse, DecisionRequest,
)
from app.services.comparison import matching_service
from app.services.question_generation import question_service
from app.services.azure_email import azure_email
from app.services.speech import stt_service
from app.utils.settings import settings
from app.graph.workflow import GraphManager

logger = logging.getLogger(__name__)
router = APIRouter()


#  2. POST /turn  (candidate — entire interview loop) 

@router.post("/turn", response_model=TurnResponse)
async def interview_turn(
    req: TurnRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Single endpoint that drives the full candidate-side interview loop.

    First call  (no answer_id) → joins/inits the session, returns Q1.
    Every next call (answer_id) → scores the answer, advances the graph,
                                   returns the next question OR final result.
    """
    # 1. Verify interview JWT
    int_id = auth_manager.verify_interview_token(req.session_token)
    logger.info(f"--- [TURN REQUEST] Interview: {int_id[:8]}... ---")

    # 2. Fetch & validate interview
    interview = await crud.get_interview(db, int_id)
    if not interview or interview.session_token != req.session_token:
        raise HTTPException(status_code=404, detail="Invalid, expired or revoked session token.")
    if interview.status == InterviewStatus.REJECTED:
        raise HTTPException(status_code=403, detail="This candidate was not eligible for an interview.")

    # 3. Already completed — return existing report (idempotent)
    if interview.status == InterviewStatus.COMPLETED:
        report = await crud.get_final_report(db, interview.id)
        return TurnResponse(
            interview_id=interview.id,
            status="completed",
            final_score=interview.final_score or 0.0,
            recommendation=report.recommendation.value if report and report.recommendation else "hold",
            overall_summary=report.overall_summary if report else "",
        )

    score = None

    # a. First call — join/init graph
    if not req.answer_id:
        logger.info(f"[INIT] Candidate joined the room. Initializing graph...")
        if interview.status == InterviewStatus.PENDING:
            config = {"configurable": {"thread_id": interview.id}}
            try:
                ig = GraphManager.get_graph()
                await ig.ainvoke({"interview_id": interview.id}, config=config)
                interview.started_at = datetime.now(tz=timezone.utc)
                await db.commit()
                await db.refresh(interview)
            except Exception as exc:
                logger.error("Graph init failed: %s", exc)
                raise HTTPException(status_code=500, detail="Failed to initialize interview.")

    # b. Subsequent calls — process the submitted answer
    else:
        logger.info(f"[ANSWER] Candidate submitted answer for {req.answer_id}")
        answer_row = await crud.get_answer(db, req.answer_id)
        if not answer_row:
            raise HTTPException(status_code=404, detail="Answer row not found.")
        if answer_row.interview_id != interview.id:
            raise HTTPException(status_code=403, detail="Answer does not belong to this interview.")
        if answer_row.answer_text:
            raise HTTPException(status_code=409, detail="This question has already been answered.")

        if not req.answer_text.strip():
            raise HTTPException(
                status_code=422,
                detail="Provide answer_text — cannot be empty.",
            )

        final_text = req.answer_text

        await db.close()

        config = {"configurable": {"thread_id": interview.id}}
        ig = GraphManager.get_graph()
        try:
            await ig.aupdate_state(config, {
                "current_answer_text": final_text,
                "current_answer_audio_url": "",
                "current_question_id": req.answer_id,
            })
            final_state = await ig.ainvoke(None, config=config)
        except Exception as exc:
            logger.error("Graph invocation failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Interview processing failed: {exc}")

        is_complete = final_state.get("interview_complete", False)

        async with AsyncSessionLocal() as sess:
            updated = await crud.get_answer(sess, req.answer_id)
            score = (updated.per_que_score or 0.0) if updated else 0.0
            logger.info(f"[SCORED] Answer scored: {score}/10")

            if is_complete:
                logger.info(f"[COMPLETE] Interview {interview.id} is finished.")
                report = await crud.get_final_report(sess, interview.id)
                iv = await crud.get_interview(sess, interview.id)
                return TurnResponse(
                    interview_id=interview.id,
                    status="completed",
                    score=score,
                    final_score=iv.final_score or 0.0,
                    recommendation=report.recommendation.value if report and report.recommendation else "hold",
                    overall_summary=report.overall_summary if report else "",
                )

    # 5. Return next unanswered question
    async with AsyncSessionLocal() as sess:
        next_q = await crud.get_next_unanswered_question(sess, interview.id)

        if not next_q:
            return TurnResponse(interview_id=interview.id, status="completed", score=score)

        total, answered = await crud.get_answer_counts(sess, interview.id)

    logger.info(f"[NEXT] Returning next question {next_q.question_order}. Status: {interview.status.value}")
    return TurnResponse(
        interview_id=interview.id,
        status="active",
        score=score,
        question=QuestionResponse(
            answer_id=next_q.id,
            question_order=next_q.question_order,
            question_text=next_q.question_text,
            total_questions=total,
            questions_remaining=total - answered,
            is_follow_up=next_q.is_followup,
        ),
    )


#  4. GET /all  (recruiter) — interview list for dashboard 

@router.get("/all", response_model=list[InterviewSummary], tags=["Dashboard"])
async def list_all_interviews(
    db: AsyncSession = Depends(get_db),
    recruiter: str = Depends(auth_manager.get_current_recruiter),
):
    """Return every interview joined with candidate name, JD title, and recommendation."""
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
            eligible=iv.eligibility,
            created_at=iv.created_at,
            started_at=iv.started_at,
            completed_at=iv.completed_at,
        )
        for iv, res, jd, rpt in rows
    ]


#  5. GET /stats  (recruiter) — aggregate counts for overview cards 

@router.get("/stats", response_model=DashboardStats, tags=["Dashboard"])
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    recruiter: str = Depends(auth_manager.get_current_recruiter),
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


@router.get("/speech-token", response_model=SpeechTokenResponse)
async def get_speech_token(authorization: str = Header(...)):
    """
    Returns a short-lived Azure Speech access token for the frontend SDK.
    The token lets the browser call TTS/STT directly without exposing the
    subscription key.

    Requires a valid interview JWT:  Authorization: Bearer <session_token>
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must be: Bearer <token>")

    token = authorization.split(" ", 1)[1]
    auth_manager.verify_interview_token(token)  # raises 401 if invalid/expired

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://{settings.AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
                headers={"Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY},
            )
            resp.raise_for_status()
            azure_token = resp.text
    except Exception as e:
        logger.error("Failed to fetch Azure speech token: %s", e)
        raise HTTPException(status_code=502, detail="Failed to obtain speech token from Azure.")

    return SpeechTokenResponse(token=azure_token, region=settings.AZURE_SPEECH_REGION)

@router.get("/{interview_id}/report", response_model=ReportDetailResponse, tags=["Dashboard"])
async def get_interview_report(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
    recruiter: str = Depends(auth_manager.get_current_recruiter),
):
    """Fetch the detailed final report for recruiter analysis."""
    row = await crud.get_interview_report_details(db, interview_id)
    if not row:
        raise HTTPException(status_code=404, detail="Interview not found")
        
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

@router.post("/{interview_id}/decision", tags=["Dashboard"])
async def submit_recruiter_decision(
    interview_id: str,
    req: DecisionRequest,
    db: AsyncSession = Depends(get_db),
    recruiter: str = Depends(auth_manager.get_current_recruiter),
):
    """Submit manual manual decision for candidate."""
    rpt = await crud.get_final_report(db, interview_id)
    
    if not rpt:
        raise HTTPException(status_code=404, detail="Final report not generated yet.")
        
    try:
        from app.structure.entities import Recommendation
        decision_enum = Recommendation(req.decision.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid decision. Must be hire, hold, or reject.")
        
    rpt.recruiter_decision = decision_enum
    rpt.decision_at = datetime.now(tz=timezone.utc)
    
    # Also update interview status based on decision if needed
    iv = await crud.get_interview(db, interview_id)
    from app.structure.entities import InterviewStatus
    
    if req.decision.lower() == "hire":
         iv.status = InterviewStatus.HIRED
    elif req.decision.lower() == "hold":
         iv.status = InterviewStatus.HOLD
    elif req.decision.lower() == "reject":
         pass # Could update logically but maybe not required
         
    await db.commit()
    
    return {"status": "success", "decision": decision_enum.value}
