from __future__ import annotations
from app.app import App

class AzureOpenAIManager:
    @property
    def smart_llm(self):
        return App.smart_llm
    
    @property
    def fast_llm(self):
        return App.fast_llm

    async def extract_structured_data(self, *args, **kwargs):
        from utils.helpers.parsers import pdf_parser
        return await pdf_parser.extract_structured_data(*args, **kwargs)

azure_openai = AzureOpenAIManager()