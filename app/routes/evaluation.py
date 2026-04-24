import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

import app.crud.interview_crud as crud
from app.services.postgres_db import get_db
from app.services.auth import auth_manager
from app.structure.entities import Interview, InterviewStatus, Answer
from app.models.interview_model import EvaluateRequest, EvaluateResponse
from app.services.comparison import matching_service
from app.services.question_generation import question_service
from app.services.azure_email import azure_email
from app.utils.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

#  1. POST /evaluate  (recruiter) 

@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_match(
    req: EvaluateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    recruiter: str = Depends(auth_manager.get_current_recruiter),
):
    logger.info(f">>> [EVALUATE] Starting match for Resume: {req.resume_id} & JD: {req.jd_id}")
    resume_obj = await crud.get_resume(db, req.resume_id)
    if not resume_obj:
        raise HTTPException(status_code=404, detail="Resume not found")

    jd_obj = await crud.get_job_description(db, req.jd_id)
    if not jd_obj:
        raise HTTPException(status_code=404, detail="Job Description not found")

    # Check for existing active or pending interview for the same resume + JD pair
    existing_iv = await crud.get_active_interview_for_candidate(db, req.resume_id, req.jd_id)
    if existing_iv:
        logger.info("Found existing interview session for this pair, id=%s. Re-sending email.", existing_iv.id)

        # Always refresh the token so the candidate gets a non-expired link
        if existing_iv.eligibility:
            existing_iv.session_token = auth_manager.create_interview_token(existing_iv.id)
            await db.commit()
            await db.refresh(existing_iv)
            logger.info("Refreshed session token for interview %s.", existing_iv.id)

        # Trigger email background task with the fresh token
        background_tasks.add_task(
            azure_email.send_decision_email,
            candidate_email=resume_obj.candidate_email,
            candidate_name=resume_obj.candidate_name,
            is_eligible=existing_iv.eligibility,
            session_token=existing_iv.session_token if existing_iv.eligibility else None,
        )

        return EvaluateResponse(
            eligibility=existing_iv.eligibility,
            match_score=existing_iv.match_score,
            interview_id=existing_iv.id,
            session_token=existing_iv.session_token,
        )



    try:
        eval_result = await matching_service.evaluate(resume_obj.resume_json, jd_obj.jd_json)
        logger.info(f"AI matched score: {eval_result.overall_match_score}")
    except Exception as e:
        logger.error(f"Evaluation failed critically: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}")

    match_score = eval_result.overall_match_score
    skill_gap_report = {
        "matched":        [s.model_dump() for s in eval_result.matched_skills if s.is_matched],
        "unmatched":      [s.model_dump() for s in eval_result.matched_skills if not s.is_matched],
        "missing":        eval_result.missing_critical_skills,
        "experience_gap": eval_result.experience_gap,
    }
    reasoning = eval_result.alignment_summary
    eligibility = float(match_score) >= settings.MATCH_SCORE_THRESHOLD

    interview = Interview(
        resume_id=req.resume_id,
        jd_id=req.jd_id,
        match_score=match_score,
        skill_gap_report=skill_gap_report,
        eligibility=eligibility,
        status=InterviewStatus.PENDING if eligibility else InterviewStatus.REJECTED,
    )
    
    db.add(interview)
    await db.flush()
    
    if eligibility:
        interview.session_token = auth_manager.create_interview_token(interview.id)
        await db.flush()
        try:
            logger.info(f"Generating {req.num_questions} questions for the candidate...")
            generated_questions = await question_service.generate(
                resume_json=resume_obj.resume_json,
                jd_json=jd_obj.jd_json,
                skill_gap_report=skill_gap_report,
                num_questions=req.num_questions,
            )
            logger.info(f"Successfully generated {len(generated_questions)} questions.")

            # ── Q1: Default greeting + self-introduction (always first) ──────
            greeting_text = (
                f"Hello! Welcome to your VoiceHire interview. "
                f"I'm your interviewer today. "
                f"Before we dive into the technical questions, "
                f"could you please start by introducing yourself — "
                f"your background, experience, and what interests you about this role?"
            )
            db.add(Answer(
                interview_id=interview.id,
                question_text=greeting_text,
                question_order=1,
                is_followup=False,
                answer_text="",
            ))

            # ── Q2+: LLM-generated domain-specific questions ─────────────────
            for idx, q in enumerate(generated_questions, start=2):
                db.add(Answer(
                    interview_id=interview.id,
                    question_text=q["question_text"],
                    question_order=idx,
                    is_followup=False,
                    answer_text="",
                ))
        except Exception as e:
            await db.rollback()
            logger.error("Question generation failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Question generation failed: {e}")

    await db.commit()
    await db.refresh(interview)

    logger.info(f"Submitting background task to send decision email to {resume_obj.candidate_email}")
    background_tasks.add_task(
        azure_email.send_decision_email,
        candidate_email=resume_obj.candidate_email,
        candidate_name=resume_obj.candidate_name,
        is_eligible=eligibility,
        session_token=interview.session_token if eligibility else None,
    )

    logger.info(f"<<< [EVALUATE COMPLETE] Eligible: {eligibility} | Match: {match_score}")

    if eligibility:
        return EvaluateResponse(
            eligibility=True,
            match_score=match_score,
            interview_id=interview.id,
            session_token=interview.session_token,
        )
    return EvaluateResponse(eligibility=False, match_score=match_score, reason=reasoning)
