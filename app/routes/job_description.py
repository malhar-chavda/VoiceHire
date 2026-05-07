from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.postgres_db import get_db
from app.structure.entities import JobDescription
from app.models.interview_model import JDResponse
from app.services.auth import auth_manager

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/job-descriptions",
    tags=["Job Descriptions"],
    dependencies=[Depends(auth_manager.get_current_recruiter)],
)


@router.get("/{jd_id}", response_model=JDResponse, summary="Fetch a job description by ID")
async def get_jd(jd_id: str, db: AsyncSession = Depends(get_db)) -> JDResponse:
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Job description not found.")
    return JDResponse(
        jd_id=str(row.id),
        title=row.title,
        jd_blob_url=row.jd_blob_url,
        jd_json=row.jd_json,
        created_at=row.created_at,
    )


@router.get("/", response_model=list[JDResponse], summary="List all job descriptions")
async def list_jds(db: AsyncSession = Depends(get_db)) -> list[JDResponse]:
    result = await db.execute(select(JobDescription).order_by(JobDescription.created_at.desc()))
    rows = result.scalars().all()
    return [
        JDResponse(
            jd_id=str(row.id),
            title=row.title,
            jd_blob_url=row.jd_blob_url,
            created_at=row.created_at,
        )
        for row in rows
    ]


