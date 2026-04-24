"""
data access layer, responsible for all the database operations.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from sqlalchemy.orm import joinedload
from app.structure.entities import (
    Resume, JobDescription, Interview, InterviewStatus, Answer, FinalReport
)

async def get_resume(db: AsyncSession, resume_id: str):
    res = await db.execute(select(Resume).where(Resume.id == resume_id))
    return res.scalar_one_or_none()

async def get_job_description(db: AsyncSession, jd_id: str):
    res = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    return res.scalar_one_or_none()

async def get_active_interview_for_candidate(db: AsyncSession, resume_id: str, jd_id: str):
    res = await db.execute(
        select(Interview).where(
            Interview.resume_id == resume_id,
            Interview.jd_id == jd_id,
            Interview.status.in_([InterviewStatus.PENDING, InterviewStatus.ACTIVE]),
        )
    )
    return res.scalar_one_or_none()

async def get_interview(db: AsyncSession, interview_id: str):
    return await db.get(Interview, interview_id)

async def get_final_report(db: AsyncSession, interview_id: str):
    res = await db.execute(select(FinalReport).where(FinalReport.interview_id == interview_id))
    return res.scalar_one_or_none()

async def get_answer(db: AsyncSession, answer_id: str):
    return await db.get(Answer, answer_id)

async def get_next_unanswered_question(db: AsyncSession, interview_id: str):
    res = await db.execute(
        select(Answer)
        .where(Answer.interview_id == interview_id, Answer.answer_text == "")
        .order_by(Answer.question_order, Answer.is_followup)
        .limit(1)
    )
    return res.scalar_one_or_none()

async def get_answer_counts(db: AsyncSession, interview_id: str):
    total = (await db.execute(
        select(func.count(Answer.id))
        .where(Answer.interview_id == interview_id, Answer.is_followup == False)
    )).scalar_one()

    answered = (await db.execute(
        select(func.count(Answer.id))
        .where(
            Answer.interview_id == interview_id,
            Answer.is_followup == False,
            Answer.answer_text != "",
        )
    )).scalar_one()
    
    return total, answered

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
