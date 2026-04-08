from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.postgres_db import get_db
from app.services.azure_blob import upload_file
from app.services.azure_openai import azure_openai
from app.utils.pdf_parser import read_and_validate, extract_text
from app.prompts.extraction import RESUME_SYSTEM_INSTRUCTIONS, RESUME_EXTRACTION_PROMPT
from app.structure.entities import Resume
from app.models.resume_model import (
    ResumeUploadResponse,
    ResumeDetailResponse,
    ResumeSummary,
    ResumeSchema
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resumes", tags=["Resumes"])

@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=201,
    summary="Upload a resume and extract structured data",
    description=(
        "Accepts a PDF resume file. "
        "Uploads it to Azure Blob Storage, extracts text, "
        "runs LLM extraction, and stores the result in PostgreSQL."
    ),
)
async def upload_resume(
    file: UploadFile = File(..., description="PDF resume file"),
    db: AsyncSession = Depends(get_db),
) -> ResumeUploadResponse:

    # validate 
    file_bytes = await read_and_validate(file)
    logger.info("Resume validated: %s (%d bytes)", file.filename, len(file_bytes))

    # blob upload 
    try:
        blob_url =await upload_file(
            file_data=file_bytes,
            filename=file.filename,
            folder="resumes",
            content_type=file.content_type,
        )
        logger.info("Resume uploaded to blob: %s", blob_url)
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
        extracted_resume: ResumeSchema = await azure_openai.extract_structured_data(
            raw_text=raw_text,
            prompt_template=RESUME_EXTRACTION_PROMPT,
            response_model=ResumeSchema,
            llm=azure_openai.fast_llm,
        )
    
        logger.info(
            "Extraction complete for: %s",
            extracted_resume.candidate_name,
        )
    except Exception as exc:
        logger.error("LLM extraction failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="LLM failed to extract structured data from the resume.",
        )

    # DB persist 
    # We access attributes directly from the Pydantic object now
    candidate_name = extracted_resume.candidate_name
    candidate_email = extracted_resume.candidate_email

    if not candidate_email:
        raise HTTPException(
        status_code=422,
        detail="Could not extract a valid email address from the resume.",
    )

    # Check for existing email
    query = select(Resume).where(Resume.candidate_email == candidate_email)
    existing = await db.execute(query)
    if existing.scalar_one_or_none():
        raise HTTPException(
        status_code=409,
        detail=f"A resume with email '{candidate_email}' already exists.",
    )

    # Convert Pydantic object to dict for the JSONB column in Postgres
    resume_row = Resume(
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        resume_json=extracted_resume.model_dump(), # Use model_dump()
        resume_blob_url=blob_url,
    )

    db.add(resume_row)
    await db.commit()
    await db.refresh(resume_row)
    logger.info("Resume saved to DB: id=%s", resume_row.id)

    #  response 
    return ResumeUploadResponse(
        resume_id=str(resume_row.id),
        candidate_name=resume_row.candidate_name,
        candidate_email=resume_row.candidate_email,
        resume_blob_url=resume_row.resume_blob_url,
        resume_json=resume_row.resume_json,
        created_at=resume_row.created_at,
    )

@router.get(
    "/{resume_id}",
    response_model=ResumeDetailResponse,
    summary="Fetch a resume by ID",
)
async def get_resume(
    resume_id: str,
    db: AsyncSession = Depends(get_db),
) -> ResumeDetailResponse:

    result = await db.execute(
        select(Resume).where(Resume.id == resume_id)
    )
    row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Resume not found.")

    return ResumeDetailResponse(
        resume_id=str(row.id),
        candidate_name=row.candidate_name,
        candidate_email=row.candidate_email,
        resume_blob_url=row.resume_blob_url,
        resume_json=row.resume_json,
        created_at=row.created_at,
    )

@router.get(
    "/",
    response_model=list[ResumeSummary],
    summary="List all uploaded resumes",
)
async def list_resumes(
    db: AsyncSession = Depends(get_db),
) -> list[ResumeSummary]:

    result = await db.execute(
        select(Resume).order_by(Resume.created_at.desc())
    )
    rows = result.scalars().all()

    return [
        ResumeSummary(
            resume_id=str(row.id),
            candidate_name=row.candidate_name,
            candidate_email=row.candidate_email,
            resume_blob_url=row.resume_blob_url,
            created_at=row.created_at,
        )
        for row in rows
    ]