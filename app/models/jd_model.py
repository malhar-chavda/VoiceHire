from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict

class ExperienceSchema(BaseModel):
    model_config = ConfigDict(extra='forbid') # This satisfies Azure's 'false' requirement
    min_years: int
    max_years: int | None

class JDSchema(BaseModel): 
    """The schema the LLM will use to extract data from a JD."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(description="The job title")
    company: str | None = Field(None, description="The company name")
    experience_required: Optional[ExperienceSchema] = Field(default=None, description="Min and Max years of experience")    
    required_skills: list[str] = Field(description="Must-have technical skills")
    preferred_skills: list[str] = Field(description="Nice-to-have skills")
    domain: str = Field(description="Industry domain like FinTech or AI")

class JDUploadResponse(BaseModel):
    jd_id: str = Field(..., description="UUID of the created job_description row")
    title: str
    jd_blob_url: str
    jd_json: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class JDSummary(BaseModel):
    jd_id: str
    title: str
    jd_blob_url: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class JDDetailResponse(BaseModel):  
    jd_id: str
    title: str
    jd_blob_url: str | None
    jd_json: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True

JDSchema.model_rebuild()