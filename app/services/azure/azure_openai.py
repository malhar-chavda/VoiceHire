from __future__ import annotations
from typing import Type, TypeVar, Any
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI
from app.utils.settings import settings

T = TypeVar("T", bound=BaseModel) # type variable- handles multiple pydantic models in one function

class AzureOpenAIManager:
    def __init__(self):
        self.smart_llm = AzureChatOpenAI(  
            azure_deployment=settings.AZURE_DEPLOYMENT_SMART,
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version="2024-08-01-preview",
            temperature=0.2,
            timeout=60,
        )
        
        self.fast_llm = AzureChatOpenAI(
            azure_deployment=settings.AZURE_DEPLOYMENT_FAST,
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version="2024-08-01-preview",
            temperature=0.2,
            timeout=60,
        )

    async def extract_structured_data(
        self,
        raw_text: str,
        prompt_template: ChatPromptTemplate,
        response_model: Type[T], 
        llm: AzureChatOpenAI,
        **kwargs: Any,
    ) -> T:  # type variable
        structured_llm = llm.with_structured_output(
            response_model,
            method="function_calling"  
        )
        chain = prompt_template | structured_llm
        invoke_args = {"raw_text": raw_text}
        invoke_args.update(kwargs)
        # logger.info("EXTRACTING FROM: %s", raw_text[:200])
        res = await chain.ainvoke(invoke_args)
        # logger.info("EXTRACTED DATA: %s", res.model_dump_json())
        return res

azure_openai = AzureOpenAIManager()


