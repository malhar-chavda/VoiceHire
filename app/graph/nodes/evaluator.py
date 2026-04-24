"""
SIXTH NODE, evaluates all the answers and updates the DB(evaluation phase)
"""
from __future__ import annotations

import json
import logging 
from sqlalchemy import select
from pydantic import BaseModel

from app.graph.state import InterviewState
from app.services.postgres_db import AsyncSessionLocal
from app.services.azure_openai import azure_openai
from app.structure.entities import Answer, Interview, InterviewStatus
from app.prompts.interview import BATCH_EVALUATION_PROMPT

log = logging.getLogger("voicehire.graph.evaluator")

def log_step(name: str):
    log.info(f"\n{'#'*20} NODE: {name.upper()} {'#'*20}")


class EvaluationItem(BaseModel):
    answer_id: str
    score: float
    feedback: str
    evidence_highlights: list[str] = []
    follow_up_considered: bool

class BatchEvaluationResult(BaseModel):
    evaluations: list[EvaluationItem]
    overall_score: float
    overall_feedback: str


async def evaluator_node(state: InterviewState) -> dict:
    log_step("evaluator")
    interview_id = state["interview_id"]
    log.info(f"Analyzing all answers for session {interview_id}")

    # ── Fetch all answers from DB ─────────────
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Answer)
            .where(Answer.interview_id == interview_id)
            .order_by(Answer.question_order, Answer.is_followup)
        )
        all_answers = result.scalars().all()

        # build QA payload for LLM
        qa_pairs = []
        for a in all_answers:
            qa_pairs.append({
                "answer_id":    a.id,
                "question":     a.question_text,
                "answer":       a.answer_text or "(no answer given)",
                "is_followup":  a.is_followup,
                "parent_id":    a.parent_answer_id,
            })

    if not qa_pairs:
        log.warning("No answers found for evaluation")
        return {"per_que_scores": [], "error": "No answers to evaluate"}

    # ── Call LLM for batch evaluation ─────────
    user_content = json.dumps(qa_pairs, indent=2)

    try:
        result = await azure_openai.extract_structured_data(
            raw_text      = user_content,
            prompt_template=BATCH_EVALUATION_PROMPT,
            response_model=BatchEvaluationResult,
            llm           = azure_openai.smart_llm,
        )
        log.info(f"AI Batch Evaluation Success. Calculated Overall Score: {result.overall_score}")
        
        evaluations  = [
            {
                "answer_id": ev.answer_id, 
                "score": ev.score, 
                "feedback": ev.feedback,
                "highlights": ev.evidence_highlights
            } 
            for ev in result.evaluations
        ]
        overall_score = float(result.overall_score)
        overall_score = max(0.0, min(100.0, overall_score))

    except Exception as e:
        log.error(f"Batch evaluation failed: {e}")
        evaluations   = []
        overall_score = 0.0

    # ── Update per_que_score on each answer row ─
    async with AsyncSessionLocal() as session:
        for ev in evaluations:
            ans_result = await session.execute(
                select(Answer).where(Answer.id == ev.get("answer_id"))
            )
            ans_row = ans_result.scalar_one_or_none()
            if ans_row:
                ans_row.per_que_score = ev.get("score", 0.0)

        # update interview final_score
        int_result = await session.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = int_result.scalar_one_or_none()
        if interview:
            interview.final_score = overall_score
            interview.status      = InterviewStatus.COMPLETED

        await session.commit()
        log.info(
            f"Evaluation complete — "
            f"overall score: {overall_score}/100"
        )

    per_que_scores = [
        {
            "answer_id": ev.get("answer_id"),
            "score":     ev.get("score", 0.0),
            "feedback":  ev.get("feedback", ""),
            "highlights": ev.get("highlights", []),
        }
        for ev in evaluations
    ]

    return {
        "per_que_scores": per_que_scores,
    }