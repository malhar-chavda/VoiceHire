"""
EIGHTH NODE, Sends the automated post-interview decision email to the candidate.
This node is the final step in the pipeline after report generation.
"""

from __future__ import annotations

import logging
from sqlalchemy import select

from app.graph.state import InterviewState
from app.services.postgres_db import AsyncSessionLocal
from app.services.azure_email import azure_email
from app.structure.entities import Interview, Resume, FinalReport

log = logging.getLogger("voicehire.graph.notifier")

async def notifier_node(state: InterviewState) -> dict:
    interview_id = state["interview_id"]
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Interview, Resume, FinalReport)
            .join(Resume, Interview.resume_id == Resume.id)
            .join(FinalReport, Interview.id == FinalReport.interview_id)
            .where(Interview.id == interview_id)
        )
        row = result.first()
        if not row: return {}
            
        interview, resume, report = row
        if interview.notification_sent: return {}

        rec = report.recommendation.value if report.recommendation else "hold"
        success = await azure_email.send_post_interview_decision(resume.candidate_email, resume.candidate_name, rec)
        
        if success:
            interview.notification_sent = True
            await session.commit()

    return {}
