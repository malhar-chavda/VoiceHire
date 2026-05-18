from __future__ import annotations
import re
import io
import logging
from typing import Type, TypeVar, Any

from fastapi import UploadFile, HTTPException
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {"application/pdf"}
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class PDFParser:
    """Handles PDF validation and text extraction."""

    async def validate(self, file: UploadFile) -> bytes:
        """Validate content type and size. Returns raw bytes."""
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type '{file.content_type}'. Only PDF files are accepted.",
            )
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' exceeds the {MAX_FILE_SIZE_MB}MB size limit.",
            )
        return contents

    def extract_text(self, file_bytes: bytes) -> str:
        """Extract and clean plain text from PDF bytes."""
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            pages = [page.get_text() for page in doc]
            doc.close()
            text = re.sub(r" +", " ", "\n".join(pages).strip())
            text = re.sub(r"\n{3,}", "\n\n", text)
            if not text:
                raise ValueError("PDF appears to be scanned or image-based.")
            return text
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not extract text from PDF: {exc}")
            
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
        logger.info("EXTRACTING FROM: %s", raw_text[:200])
        res = await chain.ainvoke(invoke_args)
        logger.info("EXTRACTED DATA: %s", res.model_dump_json())
        return res
pdf_parser = PDFParser()