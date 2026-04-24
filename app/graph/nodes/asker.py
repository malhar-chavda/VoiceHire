"""
picks the question, uses the TTS to ask the question
Reads from state:
    questions → full question list
    current_index → which question we're on
Writes to state:
    current_question_id → answer table row id
    current_question_text → the question string to show/speak
    current_answer_text → reset to "" for new answer
    current_score → reset to 0.0
SECOND NODE, pauses for the candidate ans
"""
from __future__ import annotations

import logging
from app.graph.state import InterviewState
from app.services.postgres_db import AsyncSessionLocal
from app.structure.entities import Answer

log = logging.getLogger("voicehire-graph-asker")

async def asker_node(state: InterviewState) -> dict:
    """
    Presents the next question to the candidate.
    - Normal turn : picks questions[current_index]
    - Followup turn: uses current_question_id/text already set by followup_node
    Generates TTS audio and uploads to Azure Blob.
    """
    is_followup = state.get("is_followup_pending", False)
    if is_followup:
        # State already has the followup's id/text set by followup_node
        question_id   = state["current_question_id"]
        question_text = state["current_question_text"]
        log.info(f"Asker (followup): queueing question {question_id}")

        return {
            "current_question_id": question_id,
            "current_question_text": question_text,
            "current_question_audio_url": "",
            "current_answer_text": "",
            "current_answer_audio_url": "",
            "current_score": 0.0,
            "is_followup_pending": False,   # clear flag
        }

    # Normal (non-followup) question path 
    questions = state.get("questions", [])
    current_index = state.get("current_index", 0)

    if current_index >= len(questions):
        log.warning("Asker called but no more questions remain")
        return {"interview_complete": True}

    question      = questions[current_index]
    question_text = question["question_text"]
    question_id   = question["id"]

    log.info(f"Asking Q{current_index + 1}/{len(questions)}: {question_text[:60]}...")

    audio_url = ""

    return {
        "current_question_id": question_id,
        "current_question_text": question_text,
        "current_question_audio_url": audio_url,
        "current_answer_text": "",
        "current_answer_audio_url": "",
        "current_score": 0.0,
        "is_followup_pending": False, #asker uses new followup from state instead of repeating parent que
    }