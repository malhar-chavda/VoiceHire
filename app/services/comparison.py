from __future__ import annotations
import json
import logging
from typing import Any

from app.services.azure.azure_openai import azure_openai
from app.utils.helpers.prompts import COMPARISON_PROMPT
from app.models.interview_model import ComparisonSchema

logger = logging.getLogger(__name__)


class MatchingService:
    """Compares a candidate's resume against a job description using the LLM."""

    async def evaluate(
        self,
        resume_json: dict[str, Any],
        jd_json: dict[str, Any],
    ) -> ComparisonSchema:
        """Run LLM match and return a structured ComparisonSchema result."""
        resume_str = json.dumps(resume_json, indent=2)
        jd_str = json.dumps(jd_json, indent=2)

        structured_llm = azure_openai.smart_llm.with_structured_output(ComparisonSchema)
        chain = COMPARISON_PROMPT | structured_llm

        try:
            result = await chain.ainvoke({"resume_json": resume_str, "jd_json": jd_str})
            logger.info("Match score: %.1f", result.overall_match_score)
            return result
        except Exception as exc:
            logger.error("MatchingService.evaluate failed: %s", exc)
            raise
        
matching_service = MatchingService()


