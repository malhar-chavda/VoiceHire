"""
Reads from state:
    current_index → to increment
    current_question_id → to save score against
    current_question_text → to include in scores record
    current_score → to save
    per_que_scores → to append to
FIFTH NODE increments the index and resets the followup count
Writes to state:
    current_index → incremented by 1
    followup_count → reset to 0
    per_que_scores → appended with completed question score
"""

from __future__ import annotations

import logging
from sqlalchemy import select

from app.graph.state import InterviewState
from app.services.postgres_db import AsyncSessionLocal
from app.structure.entities import Answer

log = logging.getLogger("voicehire.graph.next_question")


async def next_question_node(state: InterviewState) -> dict:
    """
    Finalises the current question:
        1. Updates per_que_score on the answer row in DB
        2. Appends score to per_que_scores in state
        3. Increments current_index, resets followup_count
    """
    answer_id     = state["current_question_id"]
    question_text = state["current_question_text"]
    score         = state.get("current_score", 0.0)
    per_que_scores = list(state.get("per_que_scores", []))
    current_index  = state["current_index"]

    # ── Save final score to DB answer row ─────
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Answer).where(Answer.id == answer_id)
        )
        answer_row = result.scalar_one_or_none()
        if answer_row:
            answer_row.per_que_score = score
            await session.commit()
            log.info(
                f"Score saved: Q{current_index + 1} → "
                f"{score}/10 (row {answer_id})"
            )

    # ── Append to running scores list ─────────
    per_que_scores.append({
        "answer_id":     answer_id,
        "question_text": question_text,
        "score":         score,
    })

    return {
        "current_index":  current_index + 1,
        "followup_count": 0,
        "per_que_scores": per_que_scores,
    }