"""
Inserts a new row into the answer table with:
    is_followup = True
    parent_answer_id = current_question_id (root question)
    answer_text = "" (filled when candidate answers)
FOURTH, triggered only if followup threshold is met
Reads from state:
    interview_id → to insert new answer row
    current_question_id → parent_answer_id for the follow-up
    current_question_text → context for generating follow-up
    current_answer_text → weak answer that triggered follow-up
    current_index → to set correct question_order
    followup_count → to increment after generating

Writes to state:
    current_question_id → new follow-up row id
    current_question_text → follow-up question text
    current_answer_text → "" (reset for candidate's new answer)
    current_score → 0.0 (reset)
    followup_count → incremented by 1
    is_followup_pending → True (signals asker to use state id, not questions list)
"""

from __future__ import annotations

import logging
from sqlalchemy import select
from pydantic import BaseModel

from app.graph.state import InterviewState
from app.services.postgres_db import AsyncSessionLocal
from app.services.azure_openai import azure_openai
from app.structure.entities import Answer
from app.prompts.interview import FOLLOW_UP_PROMPT

log = logging.getLogger("voicehire.graph.followup")


class FollowUpResult(BaseModel):
    followup_question: str


async def followup_node(state: InterviewState) -> dict:
    """
    Generates a follow-up question based on the weak answer.
    Inserts it as a new row in the answer table.
    Updates state so the asker presents the follow-up next.
    """
    interview_id = state["interview_id"]
    parent_answer_id = state["current_question_id"]
    original_question = state["current_question_text"]
    weak_answer = state["current_answer_text"]
    current_index = state["current_index"]
    followup_count = state.get("followup_count", 0)

    # ── Generate follow-up via LLM (prompt expects question_text + answer_text) ──
    try:
        llm_chain = FOLLOW_UP_PROMPT | azure_openai.fast_llm.with_structured_output(FollowUpResult)
        result = await llm_chain.ainvoke({
            "question_text": original_question,
            "answer_text":   weak_answer,
        })
        followup_text = result.followup_question
    except Exception as e:
        log.error(f"Follow-up generation failed: {e}")
        followup_text = "Can you explain that in more detail?"

    log.info(f"Follow-up generated: {followup_text[:60]}...")

    # ── Insert follow-up row into answer table ────────────────────
    async with AsyncSessionLocal() as session:

        # get question_order from parent row to match it
        parent_result = await session.execute(
            select(Answer).where(Answer.id == parent_answer_id)
        )
        parent_row = parent_result.scalar_one_or_none()
        order = parent_row.question_order if parent_row else current_index + 1

        followup_row = Answer(
            interview_id     = interview_id,
            parent_answer_id = parent_answer_id,
            question_text    = followup_text,
            question_order   = order,
            is_followup      = True,
            answer_text      = "",
        )
        session.add(followup_row)
        await session.commit()
        await session.refresh(followup_row)

        new_answer_id = followup_row.id
        log.info(f"Follow-up row inserted: {new_answer_id}")

    return {
        "current_question_id":   new_answer_id,
        "current_question_text": followup_text,
        "current_answer_text":   "",
        "current_score":         0.0,
        "followup_count":        followup_count + 1,
        "is_followup_pending":   True,   # tells asker to use state id, not questions list
    }