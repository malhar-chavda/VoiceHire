"""
THIRD NODE, scores the answer and updates the DB (Question loop till next_question_node)
Conditional follow-up questions triggered 
"""
from __future__ import annotations

import logging
from sqlalchemy import select
from app.graph.state import InterviewState
from app.services.postgres_db import AsyncSessionLocal
from app.services.scoring import scoring_service
from app.structure.entities import Answer

log = logging.getLogger("voicehire.graph.scorer")

# ── LOG HELPERS ──────────────────────────────────────────────────
def log_step(name: str):
    log.info(f"\n{'='*20} NODE: {name.upper()} {'='*20}")

async def scorer_node(state: InterviewState) -> dict:
    """
    1. Saves answer_text to the DB answer row
    2. Calls LLM to score 0.0–10.0
    3. Returns current_score to state
    """
    answer_id = state["current_question_id"]
    question = state["current_question_text"]
    answer_text = state["current_answer_text"]

    log_step("scorer")
    log.info(f"Processing Q{state['current_index'] + 1} | Answer Length: {len(answer_text)} chars")
    
    # ── 1. Quick score via centralised service ──
    try:
        result = await scoring_service.score(
            question_text=question,
            answer_text=answer_text
        )
        score = float(result.score)
        log.info(f"LLM Result -> Score: {score}/10 | Feedback: {result.reason[:60]}...")
    except Exception as e:
        log.error(f"Scoring failed: {e} — defaulting to 5.0")
        score = 5.0

    # ── 2. Save answer and score to DB ─────────
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Answer).where(Answer.id == answer_id)
        )
        answer_row = result.scalar_one_or_none()

        if answer_row:
            answer_row.answer_text = answer_text
            answer_row.per_que_score = score
            answer_row.answer_audio_url = ""
            await session.commit()
            log.info(f"Saved answer and score for row {answer_id}")
        else:
            log.warning(f"Answer row not found: {answer_id}")

    return {"current_score": score}