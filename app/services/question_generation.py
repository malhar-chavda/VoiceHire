from __future__ import annotations

import json
import logging  
from typing import Any

from app.services.azure_openai import azure_openai
from app.prompts.questions import QUESTION_GENERATION_PROMPT

from app.models.interview_model import GeneratedQuestions

logger = logging.getLogger(__name__)

async def generate_interview_questions(
    resume_json: dict[str, Any],
    jd_json: dict[str, Any],
    skill_gap_report: dict[str, Any],
    num_questions: int = 8
) -> list[str]:
    """
    Generates technical and behavioral questions for the candidate based
    on their skill gaps from the Resume vs Job Description.
    """
    # Enforce bounds between 6 and 10 based on user requirements
    num_questions = max(6, min(10, num_questions))

    prompt = QUESTION_GENERATION_PROMPT

    # Combine the context into a single readable string for the user prompt
    combined_payload = {
        "resume": resume_json,
        "job_description": jd_json,
        "skill_gap_report": skill_gap_report
    }
    
    raw_payload_str = json.dumps(combined_payload, indent=2) # converts the dict to a string for llm understnding
    
    logger.info(f"Generating {num_questions} questions via Azure OpenAI.")
    
    try:
        evaluation_result = await azure_openai.extract_structured_data(
            raw_text=raw_payload_str,
            prompt_template=prompt,
            llm=azure_openai.smart_llm,
            response_model=GeneratedQuestions,
            num_questions=num_questions
        )
        
        questions = [q.model_dump() for q in evaluation_result.questions]
        if not questions:    # safe guard, if llm crashed. Still the candidate would not see a server error and interview will proceed with these 2 ques
            logger.warning("LLM returned empty questions list. Falling back to defaults.")
            return [
                {"question_order": 1, "question_text": "Can you tell me about your background?", "skill_area": "General", "difficulty": "basic"},
                {"question_order": 2, "question_text": "What was your most challenging project?", "skill_area": "Experience", "difficulty": "intermediate"}
            ]

        return questions[:num_questions] # returns the questions in the order they were generated
        
    except Exception as exc:
        logger.error(f"Failed to generate questions: {exc}")
        raise
