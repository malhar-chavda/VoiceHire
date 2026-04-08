from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ConfigDict
    
class ResumeSchema(BaseModel):    # to LLM, with the system prompt
    """The schema the LLM will use to extract data."""
    model_config = ConfigDict(from_attributes=True)
    candidate_name: str = Field(description="Full name")
    candidate_email: str = Field(description="Email address")
    candidate_phone: str | None = Field(None, description="Phone number")
    total_experience_years: float = Field(0.0, description="Total years of work experience") # 
    skills: dict[str, list[str]] = Field(default_factory = dict, description="Categorized skills: technical, soft, tools, languages")
    work_experience: list[dict[str, Any]] = Field(default_factory = list, description="List of previous roles with company, title, and dates")
    education: list[dict[str, Any]] = Field(default_factory = list, description="List of degrees and institutions")

class ResumeUploadResponse(BaseModel): # used in POST method to confirm that file is saved
    resume_id: str = Field(..., description="UUID of the created resume row")
    candidate_name: str
    candidate_email: str
    resume_blob_url: str
    resume_json: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class ResumeSummary(BaseModel):  # used in GET method to pass only the defined parameters instead of the whole json to view the list
    resume_id: str
    candidate_name: str
    candidate_email: str
    resume_blob_url: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ResumeDetailResponse(BaseModel):  # used in GET resume(id) so that whole resume is visible to the recruiter 
    resume_id: str
    candidate_name: str
    candidate_email: str
    resume_blob_url: str | None
    resume_json: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True

ResumeSchema.model_rebuild()