from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Optional, List, Dict
from pydantic import BaseModel, Field, ConfigDict

# --- Evaluation & Matching Models ---

class SkillMatch(BaseModel):
    skill_name: str 
    is_matched: bool
    candidate_proficiency: str = Field(description="Brief mention of how they used it")
    gap_analysis: Optional[str] = Field(None, description="If not matched, why is it a problem?")

class ComparisonSchema(BaseModel):
    overall_match_score: float = Field(..., ge=0, le=100, description="0 to 100 score")
    alignment_summary: str = Field(..., description="High-level summary of fit")
    matched_skills: List[SkillMatch]
    missing_critical_skills: List[str] = Field(description="Must-have JD skills missing from Resume")
    experience_gap: Optional[str] = Field(None, description="Discrepancy in years or seniority")
    suggested_interview_focus: List[str] = Field(description="3-5 topics for the recruiter to probe")

class EvaluateRequest(BaseModel):
    resume_id: str
    jd_id: str
    num_questions: int = Field(default=8, ge=1, le=10, description="Number of interview questions to generate")

class EvaluateResponse(BaseModel):
    eligibility: bool
    match_score: float
    reason: Optional[str] = None
    interview_id: Optional[str] = None
    session_token: Optional[str] = None

# --- Interview Session Models ---

class QuestionResponse(BaseModel):
    """Embedded in TurnResponse when the interview is still active."""
    answer_id: str
    question_order: int
    question_text: str
    total_questions: int = 0
    questions_remaining: int = 0
    is_follow_up: bool = False

class TurnRequest(BaseModel):
    session_token: str
    answer_id: Optional[str] = None
    answer_text: str = ""

class TurnResponse(BaseModel):
    interview_id: str
    status: str
    score: Optional[float] = None
    question: Optional[QuestionResponse] = None
    final_score: Optional[float] = None
    recommendation: Optional[str] = None
    overall_summary: Optional[str] = None

# --- Dashboard & Reports ---

class InterviewSummary(BaseModel):
    """One row in the recruiter dashboard interview list."""
    interview_id: str
    candidate_name: str
    candidate_email: str
    jd_title: str
    status: str
    match_score: Optional[float] = None
    final_score: Optional[float] = None
    recommendation: Optional[str] = None
    overall_summary: Optional[str] = None # Added for visibility
    eligible: Optional[bool] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class DashboardStats(BaseModel):
    """Aggregate counts for the overview cards."""
    total_resumes: int
    total_jds: int
    total_interviews: int
    pending: int
    active: int
    completed: int
    rejected: int

class ReportDetailResponse(BaseModel):
    """Full detail of the final report."""
    interview_id: str
    candidate_name: str
    jd_title: str
    overall_summary: Optional[str] = None
    topics_covered: Optional[List] = None
    per_question_scores: Optional[Dict] = None
    ai_recommendation: Optional[str] = None
    recruiter_decision: Optional[str] = None

class DecisionRequest(BaseModel):
    decision: str  # hire, hold, reject

# --- JD & Resume Extraction Models ---

class JDSchema(BaseModel): 
    """The schema the LLM will use to extract structured data from a JD."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(description="The job title")
    company: Optional[str] = Field(None, description="The company name")
    experience_required: Dict[str, Any] = Field(
        default_factory=lambda: {"min_years": None, "max_years": None}
    )
    required_skills: List[str] = Field(description="Must-have technical skills")
    preferred_skills: List[str] = Field(description="Nice-to-have skills")
    domain: str = Field(description="Industry domain")

class JDResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    jd_id: str
    title: str
    jd_blob_url: Optional[str] = None
    created_at: datetime
    jd_json: Optional[Dict[str, Any]] = None

class ResumeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    resume_id: str
    candidate_name: str
    candidate_email: str
    resume_blob_url: Optional[str] = None
    created_at: datetime
    resume_json: Optional[Dict[str, Any]] = None

class SkillCategory(BaseModel):
    category_name: str
    skills: List[str]

class ExperienceEntry(BaseModel):
    company: str
    title: str
    start_date: str
    end_date: str
    duration_months: float = 0.0
    responsibilities: List[str] = Field(default_factory=list)

class EducationEntry(BaseModel):
    institution: str
    degree: str
    graduation_year: float

class ResumeSchema(BaseModel):    
    model_config = ConfigDict(from_attributes=True)
    candidate_name: str
    candidate_email: str
    candidate_phone: Optional[str] = None
    total_experience_years: float = 0.0
    skills: List[SkillCategory] = Field(default_factory=list)
    work_experience: List[ExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)

# Rebuild models
JDSchema.model_rebuild()
ResumeSchema.model_rebuild()

