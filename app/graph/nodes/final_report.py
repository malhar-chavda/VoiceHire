"""
SEVENTH NODE, Inserts one row into the final_report table.
Reads from state:
    interview_id → to fetch context and link report
    per_que_scores  → evaluation results from evaluator node

Writes to state:
    final_report_id → UUID of the inserted final_report row
"""

from __future__ import annotations

import json
import logging
from sqlalchemy import select
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate

from app.graph.state import InterviewState
from app.services.postgres_db import AsyncSessionLocal
from app.services.azure_openai import azure_openai
from app.structure.entities import Answer, FinalReport, Interview, JobDescription, Resume, Recommendation
from app.prompts.interview import FINAL_REPORT_PROMPT

log = logging.getLogger("voicehire.graph.reporter")

def log_step(name: str):
    log.info(f"\n{'*' * 20} NODE: {name.upper()} {'*' * 20}")


class FinalReportResult(BaseModel):
    strengths: list[str]
    weaknesses: list[str]
    topics_covered: list[str]
    topics_not_covered: list[str]
    overall_summary: str
    recommendation: str
    recruiter_notes: str

async def reporter_node(state: InterviewState) -> dict:
    log_step("reporter")
    interview_id   = state["interview_id"]
    log.info(f"Synthesizing final recruiter report for session: {interview_id}")
    per_que_scores = state.get("per_que_scores", [])

    #  Fetch context from DB 
    async with AsyncSessionLocal() as session:

        int_result = await session.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = int_result.scalar_one_or_none()

        jd_result = await session.execute(
            select(JobDescription).where(
                JobDescription.id == interview.jd_id
            )
        )
        jd = jd_result.scalar_one_or_none()

        res_result = await session.execute(
            select(Resume).where(Resume.id == interview.resume_id)
        )
        resume = res_result.scalar_one_or_none()

        # fetch all Q&A for context
        ans_result = await session.execute(
            select(Answer)
            .where(Answer.interview_id == interview_id)
            .order_by(Answer.question_order)
        )
        all_answers = ans_result.scalars().all()

    # ── Build context payload for LLM ─────────
    context = {
        "job_title": jd.title if jd else "Unknown Role",
        "jd_summary": jd.jd_json if jd else {},
        "candidate_name": resume.candidate_name if resume else "Candidate",
        "resume_summary": resume.resume_json if resume else {},
        "match_score": interview.match_score if interview else 0,
        "final_score": interview.final_score if interview else 0,
        "skill_gap": interview.skill_gap_report if interview else {},
        "qa_pairs": [
            {
                "question": a.question_text,
                "answer": a.answer_text or "(no answer)",
                "score": a.per_que_score,
                "is_followup": a.is_followup,
            }
            for a in all_answers
        ],
        "per_question_evaluations": per_que_scores,
    }

    # ── Call LLM for final report ─────────────
    try:
        result = await azure_openai.extract_structured_data(
            raw_text      = json.dumps(context, indent=2),
            prompt_template=FINAL_REPORT_PROMPT,
            response_model=FinalReportResult,
            llm           = azure_openai.smart_llm,
        )
        log.info(f"AI Report Synthesis Success. Rec: {result.recommendation.upper()}")
        
        strengths = result.strengths
        weaknesses = result.weaknesses
        topics_covered = result.topics_covered
        topics_not_covered = result.topics_not_covered
        overall_summary = result.overall_summary
        rec_str = result.recommendation.lower()
        if rec_str not in ("hire", "hold", "reject"):
            rec_str = "hold"
        recommendation = Recommendation(rec_str)
        recruiter_notes = result.recruiter_notes

    except Exception as e:
        log.error(f"Report generation failed: {e}")
        strengths = []
        weaknesses = []
        topics_covered = []
        topics_not_covered = []
        overall_summary = "Report generation failed."
        recommendation = Recommendation.HOLD
        recruiter_notes = str(e)

    # ── Insert final_report row ───────────────
    async with AsyncSessionLocal() as session:

        # check for existing report (idempotency)
        existing = await session.execute(
            select(FinalReport).where(
                FinalReport.interview_id == interview_id
            )
        )
        if existing.scalar_one_or_none():
            log.warning(f"Report already exists for {interview_id}")
            return {"final_report_id": "already_exists"}

        # Build an answer lookup by id for question/answer text enrichment
        answer_lookup = {str(a.id): a for a in all_answers}

        report = FinalReport(
            interview_id = interview_id,
            topics_covered = topics_covered,
            overall_summary = overall_summary,
            recommendation = recommendation,
            per_question_scores = {
                ev["answer_id"]: {
                    "score": ev["score"],
                    "feedback": ev["feedback"],
                    "highlights": ev.get("highlights", []),
                    "question": answer_lookup[ev["answer_id"]].question_text
                               if ev["answer_id"] in answer_lookup else "",
                    "answer": answer_lookup[ev["answer_id"]].answer_text or ""
                               if ev["answer_id"] in answer_lookup else "",
                }
                for ev in per_que_scores
                if "answer_id" in ev
            },
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)

        log.info(
            f"Final report saved: {report.id} — "
            f"recommendation: {recommendation.value}"
        )
        report_id = report.id

    return {"final_report_id": report_id}