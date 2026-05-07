from __future__ import annotations
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict

class JDSchema(BaseModel): 
    """The schema the LLM will use to extract structured data from a JD."""
    model_config = ConfigDict(extra="forbid")
    
    title: str = Field(description="The job title")
    company: Optional[str] = Field(None, description="The company name")
    
    # Inlined experience requirement
    experience_required: dict[str, Any] = Field(
        default_factory=lambda: {"min_years": None, "max_years": None},
        description="Min and Max years of experience expected. e.g. {'min_years': 3, 'max_years': 5}"
    )
    
    required_skills: list[str] = Field(description="Must-have technical skills")
    preferred_skills: list[str] = Field(description="Nice-to-have skills")
    domain: str = Field(description="Industry domain like FinTech or AI")

class JDResponse(BaseModel):
    """Unified schema for both listing and detailed view of a job description."""
    model_config = ConfigDict(from_attributes=True)
    
    jd_id: str
    title: str
    jd_blob_url: Optional[str] = None
    created_at: datetime
    
    # Optional field: only populated when fetching a specific JD
    jd_json: Optional[dict[str, Any]] = Field(None, description="The full extracted structured data")

JDSchema.model_rebuild()
