"""
Reads all root questions for the interview from the answer table
and loads them into state. Sets the loop counter to 0.
FIRST NODE
Writes to state:
    questions → list of question dicts ordered by question_order
    total_questions → count of root questions
    current_index → 0 (start of loop)
    followup_count → 0
    interview_complete → False
    per_que_scores → [] (empty, filled during loop)
    error → "" (healthy)
"""

from __future__ import annotations

import logging
from sqlalchemy import select

from app.graph.state import InterviewState
from app.services.postgres_db import AsyncSessionLocal
from app.structure.entities import Answer, Interview, InterviewStatus

log = logging.getLogger("voicehire.graph.loader")


async def loader_node(state: InterviewState) -> dict:
    """
    Fetches all root questions for the interview from the DB.
    Validates the interview exists and is eligible.
    Initialises all loop counters.
    """
    interview_id = state["interview_id"]   #reads from the state

    async with AsyncSessionLocal() as session:

        # verify interview exists and is eligible
        result = await session.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = result.scalar_one_or_none()

        if not interview:
            return {"error": f"Interview not found: {interview_id}"}

        if not interview.eligibility:
            return {"error": "Candidate is not eligible for interview"}

        question_result = await session.execute(           # fetch all root questions from db ordered by sequence
            select(Answer)
            .where(
                Answer.interview_id == interview_id,
                Answer.is_followup == False,       #ensures only the parent question is fetched 
            )
            .order_by(Answer.question_order)
        )
        root_questions = question_result.scalars().all()  #converts raw db data to list of python objects

        if not root_questions:
            return {"error": "No questions found. Run question generation first."}

        questions = [   #formatting the questions into dict before pushing into the state
            {
                "id": q.id,
                "question_text": q.question_text,
                "question_order": q.question_order,
                "is_followup": q.is_followup,
                "question_audio_url": q.question_audio_url,
            }
            for q in root_questions
        ]

        # update interview status to active
        interview.status = InterviewStatus.ACTIVE
        await session.commit()

        log.info(
            f"Loader: {len(questions)} questions loaded "
            f"for interview {interview_id}"
        )

    return {      #UPLOADING TO THE STATE, THE LG UPDATES THE STATE
        "questions": questions,
        "total_questions": len(questions),
        "current_index": 0,
        "followup_count": 0,
        "interview_complete": False,
        "per_que_scores": [],
        "error":"",
    }