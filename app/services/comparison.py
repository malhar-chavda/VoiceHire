from __future__ import annotations

import logging
from typing import Any

from app.services.azure_openai import azure_openai
from app.prompts.matching import COMPARISON_PROMPT  # The ChatPromptTemplate we created
from app.models.comparison_model import ComparisonSchema  # The Pydantic model

logger = logging.getLogger(__name__)

async def evaluate_candidate_match( 
    resume_json: dict[str, Any], 
    jd_json: dict[str, Any]
) -> ComparisonSchema:
    """
    Takes structured JSONs, compares them using LangChain AzureChatOpenAI,
    and returns a validated ComparisonSchema object.
    """
    logger.info("Initializing Azure OpenAI (Smart) for Match & Gap analysis")
    
    try:
        #Get the langchain LLM (using smart for high-reasoning comparison)
        llm = azure_openai.smart_llm
        
        #Bind the pydantic schema for structured output
        structured_llm = llm.with_structured_output(ComparisonSchema)
        
        #Create the langchain chain (prompt -> LLM)
        chain = COMPARISON_PROMPT | structured_llm
        
        #Execute the chain
        #pass the dicts directly; langchain handles the string injection into the template
        evaluation_result = await chain.ainvoke({    #non-streaming!
            "resume_json": resume_json,
            "jd_json": jd_json
        })
        
        logger.info(f"Analysis complete. Match Score: {evaluation_result.overall_match_score}%")
        
        return evaluation_result
        
    except Exception as exc:
        logger.error(f"Failed to evaluate candidate match: {exc}")
        raise