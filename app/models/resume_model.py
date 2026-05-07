from __future__ import annotations
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict

class SkillCategory(BaseModel):
    category_name: str = Field(description="Name of the skill category (e.g., Languages, Frameworks)")
    skills: list[str] = Field(description="List of specific skills in this category")

class ExperienceEntry(BaseModel):
    company: str = Field(description="Name of the organization")
    title: str = Field(description="Job title or role")
    start_date: str = Field(description="Start date (YYYY-MM)")
    end_date: str = Field(description="End date (YYYY-MM or 'Present')")
    duration_months: float = Field(0, description="Calculated duration in months")
    responsibilities: list[str] = Field(default_factory=list, description="List of key responsibilities and achievements")

class EducationEntry(BaseModel):
    institution: str = Field(description="Name of the university or school")
    degree: str = Field(description="Degree or certification obtained")
    graduation_year:float = Field(description="Year of graduation")

class ResumeSchema(BaseModel):    
    """The schema the LLM will use to extract structured data from PDF text."""
    model_config = ConfigDict(from_attributes=True)
    
    candidate_name: str = Field(description="Full name")
    candidate_email: str = Field(description="Email address")
    candidate_phone: Optional[str] = Field(None, description="Phone number")
    total_experience_years: float = Field(0.0, description="Total years of work experience as a number")
    
    skills: list[SkillCategory] = Field(
        default_factory=list, 
        description="List of categorized skills."
    )
    
    work_experience: list[ExperienceEntry] = Field(
        default_factory=list, 
        description="List of professional work experiences."
    )
    
    education: list[EducationEntry] = Field(
        default_factory=list, 
        description="List of educational qualifications."
    )

class ResumeResponse(BaseModel):
    """Unified schema for both listing and detailed view of a resume."""
    model_config = ConfigDict(from_attributes=True)
    
    resume_id: str
    candidate_name: str
    candidate_email: str
    resume_blob_url: Optional[str] = None
    created_at: datetime
    
    # Optional field: only populated when fetching a specific resume
    resume_json: Optional[dict[str, Any]] = Field(None, description="The full extracted structured data")

# Keep model_rebuild for complex forward refs if any were added
ResumeSchema.model_rebuild()
