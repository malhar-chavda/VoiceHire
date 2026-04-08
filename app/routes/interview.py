from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.services.postgres_db import get_db
from app.structure.entities import Resume, JobDescription, Interview, InterviewStatus, Answer
from app.models.interview_model import EvaluateMatchRequest, EvaluateMatchResponse
from app.services.comparison import evaluate_candidate_match
from app.services.question_generation import generate_interview_questions
from app.services.azure_email import send_decision_email
from app.utils.settings import settings
import secrets

router = APIRouter()

@router.post("/evaluate", response_model=EvaluateMatchResponse)
async def evaluate_match(
    req: EvaluateMatchRequest, # model
    background_tasks: BackgroundTasks,  # background tasks
    db: AsyncSession = Depends(get_db)  # database session
):
    # fetch resume
    res_db = await db.execute(select(Resume).where(Resume.id == req.resume_id))
    resume_obj = res_db.scalar_one_or_none()
    if not resume_obj:
        raise HTTPException(status_code=404, detail="Resume not found")


    # fetch job description
    jd_db = await db.execute(select(JobDescription).where(JobDescription.id == req.jd_id))
    jd_obj = jd_db.scalar_one_or_none()
    if not jd_obj:
        raise HTTPException(status_code=404, detail="Job Description not found")

    # match resume and jd 
    try:
        eval_result = await evaluate_candidate_match(resume_obj.resume_json, jd_obj.jd_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}")

    match_score = eval_result.overall_match_score
    #pydantic model 
    skill_gap_report = {  
        "matched": [s.model_dump() for s in eval_result.matched_skills if s.is_matched], # only actual matched skills
        "unmatched": [s.model_dump() for s in eval_result.matched_skills if not s.is_matched],
        "missing": eval_result.missing_critical_skills,
        "experience_gap": eval_result.experience_gap
    }    
    reasoning = eval_result.alignment_summary
    
    eligibility = float(match_score) >= settings.MATCH_SCORE_THRESHOLD

    # Create Interview Record
    interview = Interview(   # to db
        resume_id=req.resume_id,
        jd_id=req.jd_id,
        match_score=match_score,
        skill_gap_report=skill_gap_report,
        eligibility=eligibility
    )

    if eligibility:
        interview.session_token = secrets.token_urlsafe(64)
        interview.status = InterviewStatus.PENDING
    else:
        interview.status = InterviewStatus.REJECTED

    db.add(interview)

    if eligibility:
        await db.flush()  # ensure interview has an ID
        
        try:
            generated_questions = await generate_interview_questions(
                resume_json=resume_obj.resume_json,
                jd_json=jd_obj.jd_json,
                skill_gap_report=skill_gap_report,
                num_questions=8  # defaults to 8 to stay within 6-10 range
            )
            
            for idx, q in enumerate(generated_questions, start=1):
                ans = Answer(
                    interview_id  = interview.interview_id,
                    question_text = q["question_text"],
                    question_order= idx,
                    # skill_area    = q.get("skill_area", "General"),
                    # difficulty    = q.get("difficulty", "intermediate"),
                    is_followup   = False,
                    answer_text   = "",
                )
                db.add(ans)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            await db.rollback()
            print(f"Exception traceback:\n{tb}")
            raise HTTPException(status_code=500, detail=f"Question generation failed: {e}\n{tb}")

    await db.commit()  
    await db.refresh(interview)  # to get the interview_id

    # Return Result
    if eligibility:  # if eligible send interview invite email
        background_tasks.add_task(
            send_decision_email,
            candidate_email=resume_obj.candidate_email,
            candidate_name=resume_obj.candidate_name,
            is_eligible=True,
            session_token=interview.session_token
        )
        
        return EvaluateMatchResponse(
            eligibility=True,
            match_score=match_score,
            interview_id=interview.interview_id,
            session_token=interview.session_token
        )
    else:  # if not eligible send rejection email
        background_tasks.add_task(
            send_decision_email,
            candidate_email=resume_obj.candidate_email,
            candidate_name=resume_obj.candidate_name,
            is_eligible=False
        )

        return EvaluateMatchResponse(
            eligibility=False,
            match_score=match_score,
            reason=reasoning
        )
