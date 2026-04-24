from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.postgres_db import get_db
from app.structure.entities import Resume
from app.models.resume_model import ResumeResponse
from app.services.auth import auth_manager

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/resumes",
    tags=["Resumes"],
    dependencies=[Depends(auth_manager.get_current_recruiter)],
)


@router.get("/{resume_id}", response_model=ResumeResponse, summary="Fetch a resume by ID")
async def get_resume(resume_id: str, db: AsyncSession = Depends(get_db)) -> ResumeResponse:
    result = await db.execute(select(Resume).where(Resume.id == resume_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return ResumeResponse(
        resume_id=str(row.id),
        candidate_name=row.candidate_name,
        candidate_email=row.candidate_email,
        resume_blob_url=row.resume_blob_url,
        resume_json=row.resume_json,
        created_at=row.created_at,
    )


@router.get("/", response_model=list[ResumeResponse], summary="List all resumes")
async def list_resumes(db: AsyncSession = Depends(get_db)) -> list[ResumeResponse]:
    result = await db.execute(select(Resume).order_by(Resume.created_at.desc()))
    rows = result.scalars().all()
    return [
        ResumeResponse(
            resume_id=str(row.id),
            candidate_name=row.candidate_name,
            candidate_email=row.candidate_email,
            resume_blob_url=row.resume_blob_url,
            created_at=row.created_at,
        )
        for row in rows
    ]
