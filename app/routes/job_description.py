from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.postgres_db import get_db
from app.services.azure_blob import upload_file
from app.services.azure_openai import azure_openai
from app.utils.pdf_parser import read_and_validate, extract_text
from app.prompts.extraction import JD_SYSTEM_INSTRUCTIONS, JD_EXTRACTION_PROMPT
from app.structure.entities import JobDescription
from app.models.jd_model import (
    JDUploadResponse,
    JDDetailResponse,
    JDSummary,
    JDSchema
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/job-descriptions", tags=["Job Descriptions"])

@router.post(
    "/upload",
    response_model=JDUploadResponse,
    status_code=201,
    summary="Upload a job description and extract structured data",
    description=(
        "Accepts a PDF job description file. "
        "Uploads it to Azure Blob Storage, extracts text, "
        "runs LLM extraction, and stores the result in PostgreSQL."
    ),
)
async def upload_jd(
    file: UploadFile = File(..., description="PDF job description file"),
    db: AsyncSession = Depends(get_db),
) -> JDUploadResponse:

    # validate 
    file_bytes = await read_and_validate(file)
    logger.info("JD validated: %s (%d bytes)", file.filename, len(file_bytes))

    # blob upload 
    try:
        blob_url = await upload_file(
            file_data=file_bytes,
            filename=file.filename,
            folder="job_descriptions",
            content_type=file.content_type,
        )
        logger.info("JD uploaded to blob: %s", blob_url)
    except Exception as exc:
        logger.error("Blob upload failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to upload file to storage. Please try again.",
        )

    # text extraction 
    try:
        raw_text = extract_text(file_bytes, file.content_type)
        logger.info("Text extracted (%d chars)", len(raw_text))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Text extraction failed: %s", exc)
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from the uploaded file.",
        )

    # LLM extraction 
    try:
        extracted_jd: JDSchema = await azure_openai.extract_structured_data(
            raw_text=raw_text,
            prompt_template=JD_EXTRACTION_PROMPT,
            response_model=JDSchema,
            llm=azure_openai.fast_llm,
        )
    
        logger.info(
            "Extraction complete for role: %s",
            extracted_jd.title,
        )
    except Exception as exc:
        logger.error("LLM extraction failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="LLM failed to extract structured data from the job description.",
        )

    # DB persist 
    title = extracted_jd.title or "Untitled Position"

    jd_row = JobDescription(
        title=title,
        jd_json=extracted_jd.model_dump(),
        jd_blob_url=blob_url,
    )

    try:
        db.add(jd_row)
        await db.commit()
        await db.refresh(jd_row)
        logger.info("JD saved to DB: id=%s", jd_row.id)
    except Exception as e:
        logger.error("Database save failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save JD to database.")

    # response 
    return JDUploadResponse(
        jd_id=str(jd_row.id),
        title=jd_row.title,
        jd_blob_url=jd_row.jd_blob_url,
        jd_json=jd_row.jd_json,
        created_at=jd_row.created_at,
    )

@router.get(
    "/{jd_id}",
    response_model=JDDetailResponse,
    summary="Fetch a job description by ID",
)
async def get_jd(
    jd_id: str,
    db: AsyncSession = Depends(get_db),
) -> JDDetailResponse:

    result = await db.execute(
        select(JobDescription).where(JobDescription.id == jd_id)
    )
    row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Job description not found.")

    return JDDetailResponse(
        jd_id=str(row.id),
        title=row.title,
        jd_blob_url=row.jd_blob_url,
        jd_json=row.jd_json,
        created_at=row.created_at,
    )

@router.get(
    "/",
    response_model=list[JDSummary],
    summary="List all uploaded job descriptions",
)
async def list_jds(
    db: AsyncSession = Depends(get_db),
) -> list[JDSummary]:

    result = await db.execute(
        select(JobDescription).order_by(JobDescription.created_at.desc())
    )
    rows = result.scalars().all()

    return [
        JDSummary(
            jd_id=str(row.id),
            title=row.title,
            jd_blob_url=row.jd_blob_url,
            created_at=row.created_at,
        )
        for row in rows
    ]