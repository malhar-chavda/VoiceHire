"""
this file handles the scoring of the candidate's answers. quick score generation, follow up generation and batch evaluation.
the scorer node sends the candidate response here for evaluation.
"""
from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from app.services.azure_openai import azure_openai
from app.prompts.interview import ANSWER_SCORING_PROMPT, FOLLOW_UP_PROMPT
from app.utils.settings import settings

logger = logging.getLogger(__name__)

class ScoringResult(BaseModel):  #model used when grading the answer
    score: float = Field(..., ge=0, le=10)
    justification: str
    needs_follow_up: bool


class FollowUpResult(BaseModel):  #model used when generating follow up questions
    follow_up_question: str


class ScoringService:

    """Scores candidate answers and generates follow-up questions,   if any"""

    async def score(self, question_text: str, answer_text: str) -> ScoringResult:#takes que and response
        """Score an answer 0-10. Falls back to 5.0 if the LLM call fails."""
        try:
            result: ScoringResult = await azure_openai.extract_structured_data(
                raw_text=answer_text,
                prompt_template=ANSWER_SCORING_PROMPT,
                response_model=ScoringResult,
                llm=azure_openai.fast_llm,
                question_text=question_text,
                answer_text=answer_text,
                follow_up_threshold=settings.FOLLOW_UP_THRESHOLD,
            )
            logger.info("Score: %.1f | needs_follow_up: %s", result.score, result.needs_follow_up)
            return result  #returns a log if the evaluation is successful

        except Exception as exc:
            logger.error("ScoringService failed to evaluate answer: %s", exc) #gives 5.0 by default if llm fails
            return ScoringResult(score=5.0, justification="Scoring failed", needs_follow_up=False)

    async def follow_up(self, question_text: str, answer_text: str) -> str:
        """Generate a targeted follow-up question for a weak answer."""
        try:
            result: FollowUpResult = await azure_openai.extract_structured_data(
                raw_text=answer_text,
                prompt_template=FOLLOW_UP_PROMPT,
                response_model=FollowUpResult,
                llm=azure_openai.fast_llm,
                question_text=question_text,
                answer_text=answer_text,
            )
            logger.info("Follow-up generated: %s...", result.follow_up_question[:60])
            return result.follow_up_question
        except Exception as exc:
            logger.error("Follow-up generation failed: %s", exc)
            return "Could you please elaborate on your previous answer?"

scoring_service = ScoringService()
