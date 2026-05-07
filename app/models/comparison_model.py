from __future__ import annotations
from pydantic import BaseModel, Field

class SkillMatch(BaseModel):
    skill_name: str
    is_matched: bool
    candidate_proficiency: str = Field(description="Brief mention of how they used it")
    gap_analysis: str | None = Field(None, description="If not matched, why is it a problem?")

class ComparisonSchema(BaseModel):
    overall_match_score: float = Field(..., ge=0, le=100, description="0 to 100 score")
    alignment_summary: str = Field(..., description="High-level summary of fit")
    matched_skills: list[SkillMatch]
    missing_critical_skills: list[str] = Field(description="Must-have JD skills missing from Resume")
    experience_gap: str | None = Field(None, description="Discrepancy in years or seniority")
    suggested_interview_focus: list[str] = Field(description="3-5 topics for the recruiter to probe")
