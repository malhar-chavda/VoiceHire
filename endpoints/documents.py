from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Optional, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from utils.core.data.postgres_db import get_db
from utils.core.services.document import document_service
from app.app import App
from utils.helpers.prompts import RESUME_EXTRACTION_PROMPT, JD_EXTRACTION_PROMPT
from models.entities import Resume, JobDescription
from models.interview_model import ResumeSchema
from models.interview_model import JDSchema
from utils.core.services.auth import auth_manager

logger = logging.getLogger(__name__)

# Initialize the APIRouter for document-related endpoints.
# This router uses a dependency to make sure only authenticated recruiters can access these endpoints.
router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
    dependencies=[Depends(auth_manager.get_current_recruiter)],
)


class UploadResponse(BaseModel):
    """
    Pydantic model representing the response payload for a successful document upload.
    It contains identifiers, extracted metadata, and blob URLs for both the resume and the job description.
    """
    model_config = ConfigDict(from_attributes=True)

    resume_id: str
    candidate_name: str
    candidate_email: str
    resume_blob_url: Optional[str] = None
    resume_created_at: datetime

    jd_id: str
    jd_title: str
    jd_blob_url: Optional[str] = None
    jd_created_at: datetime


@router.post("/upload", response_model=UploadResponse, status_code=201,
             summary="Upload resume and job description together")
async def upload_documents(
    resume_file: UploadFile = File(..., description="PDF resume file"),
    jd_file: UploadFile = File(..., description="PDF job description file"),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """
    Endpoint to process and store both a candidate's resume and a job description in a single transaction.
    It extracts structural data from both PDFs concurrently using LLMs and saves the details into the database.
    """
    logger.info(f">>> [UPLOAD] Received Resume: {resume_file.filename} and JD: {jd_file.filename}")

    try:
        # Concurrently process both documents: extract text, parse via LLMs into structured schemas,
        # and upload raw PDFs to configured blob storage.
        (extracted_resume, resume_blob_url), (extracted_jd, jd_blob_url) = await asyncio.gather(
            document_service.process_document(
                file=resume_file,
                folder="resumes",
                prompt_template=RESUME_EXTRACTION_PROMPT,
                response_model=ResumeSchema,
                llm=App.smart_llm,
            ),
            document_service.process_document(
                file=jd_file,
                folder="jds",
                prompt_template=JD_EXTRACTION_PROMPT,
                response_model=JDSchema,
                llm=App.fast_llm,
            ),
        )
        logger.info(f"AI Extraction complete: Candidate={extracted_resume.candidate_name}, Job={extracted_jd.title}")
    except HTTPException:
        # Re-raise HTTPExceptions spawned during extraction directly (e.g. invalid file types)
        raise
    except Exception as e:
        logger.error("Document processing failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Document processing failed: {e}")

    # Ensure a valid candidate email was extracted; it's a critical uniqueness identifier.
    if not extracted_resume.candidate_email:
        raise HTTPException(status_code=422, detail="Could not extract a valid email from the resume.")

    # Check database for existing resume (based on email).
    existing_res = await db.execute(
        select(Resume).where(Resume.candidate_email == extracted_resume.candidate_email)
    )
    resume_row = existing_res.scalar_one_or_none()
    
    if not resume_row:
        # Create new resume if not exists
        resume_row = Resume(
            candidate_name=extracted_resume.candidate_name,
            candidate_email=extracted_resume.candidate_email,
            resume_json=extracted_resume.model_dump(),
            resume_blob_url=resume_blob_url,
        )
        db.add(resume_row)
        logger.info("New resume created for %s", extracted_resume.candidate_email)
    else:
        logger.info("Found existing resume for %s, id=%s", extracted_resume.candidate_email, resume_row.id)

    # Check database for existing JD (based on title).
    jd_title = extracted_jd.title or "Untitled Position"
    existing_jd = await db.execute(
        select(JobDescription).where(JobDescription.title == jd_title)
    )
    jd_row = existing_jd.scalar_one_or_none()

    if not jd_row:
        # Create new JD if not exists
        jd_row = JobDescription(
            title=jd_title,
            jd_json=extracted_jd.model_dump(),
            jd_blob_url=jd_blob_url,
        )
        db.add(jd_row)
        logger.info("New JD created: %s", jd_title)
    else:
        logger.info("Found existing JD: %s, id=%s", jd_title, jd_row.id)

    try:
        await db.commit()
        await db.refresh(resume_row)
        await db.refresh(jd_row)
    except Exception as e:
        logger.error("Database sync failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to sync documents to database.")


    logger.info(f"<<< [UPLOAD COMPLETE] Resume ID: {resume_row.id} | JD ID: {jd_row.id}")

    return UploadResponse(
        resume_id=str(resume_row.id),
        candidate_name=resume_row.candidate_name,
        candidate_email=resume_row.candidate_email,
        resume_blob_url=resume_row.resume_blob_url,
        resume_created_at=resume_row.created_at,
        jd_id=str(jd_row.id),
        jd_title=jd_row.title,
        jd_blob_url=jd_row.jd_blob_url,
        jd_created_at=jd_row.created_at,
    )