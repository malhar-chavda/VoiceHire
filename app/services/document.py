"""
document processing service (parse, upload, extract)
orchestrates the flow (upload, llm call, db save)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Type, TypeVar, Any
from fastapi import UploadFile, HTTPException
from pydantic import BaseModel

from app.services.azure_blob import blob_storage
from app.services.azure_openai import azure_openai
from app.utils.pdf_parser import pdf_parser

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class DocumentService:
    """
    Unified service to handle document processing:
    Validate -> Upload to Blob -> Extract Text -> LLM Structured Extraction
    """
    async def process_document(
        self,
        file: UploadFile,
        folder: str,
        prompt_template: Any,
        response_model: Type[T],
        llm: Any = azure_openai.fast_llm,
    ) -> tuple[T, str]:
        """
        Process a document and return the extracted structured data and the blob URL.
        """
        # 1. Validate (PDF check)
        file_bytes = await pdf_parser.validate(file)
        logger.info("Document validated: %s (%d bytes)", file.filename, len(file_bytes))

        # 2. Upload to Blob Storage
        try:
            blob_url = await blob_storage.upload(
                file_data=file_bytes,
                filename=file.filename,
                folder=folder,
                content_type=file.content_type,
            )
            logger.info("Document uploaded to blob: %s", blob_url)
        except Exception as exc:
            logger.error("Blob upload failed: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="Failed to upload file to storage. Please try again.",
            )

        # 3. Extract Text (pdfplumber is sync → offload to thread)
        try:
            raw_text = await asyncio.to_thread(pdf_parser.extract_text, file_bytes)
            logger.info("Text extracted (%d chars)", len(raw_text))
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Text extraction failed: %s", exc)
            raise HTTPException(
                status_code=422,
                detail="Could not extract text from the uploaded file.",
            )

        # 4. LLM Extraction
        try:
            extracted_data: T = await azure_openai.extract_structured_data(
                raw_text=raw_text,
                prompt_template=prompt_template,
                response_model=response_model,
                llm=llm,
            )
            logger.info("LLM extraction complete for document.")
        except Exception as exc:
            logger.error("LLM extraction failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail="LLM failed to extract structured data from the document.",
            )

        return extracted_data, blob_url

document_service = DocumentService()
