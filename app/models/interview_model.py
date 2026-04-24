from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


#  Recruiter: Evaluate 

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


#  Candidate: Single turn 

class QuestionResponse(BaseModel):
    """Embedded in TurnResponse when the interview is still active."""
    answer_id: str
    question_order: int
    question_text: str
    total_questions: int = 0
    questions_remaining: int = 0
    is_follow_up: bool = False

class TurnRequest(BaseModel):
    """
    Drives one turn of the interview.

    **First call** — send only `session_token` (no answer fields).
    The server joins/inits the interview and returns the first question.

    **Every next call** — send `session_token` + `answer_id` (from the
    previous response) + `answer_text`.
    """
    model_config = {"json_schema_extra": {
        "examples": [
            {
                "summary": "First call — join interview, get Q1",
                "value": {
                    "session_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                }
            },
            {
                "summary": "Subsequent call — submit text answer",
                "value": {
                    "session_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "answer_id": "uuid-from-previous-turn-response",
                    "answer_text": "I would use EXPLAIN ANALYZE to identify slow queries..."
                }
            }
        ]
    }}

    session_token: str
    answer_id: Optional[str] = None
    answer_text: str = ""

class TurnResponse(BaseModel):
    """
    status = "active"    → question is populated with the next question.
    status = "completed" → final_score / recommendation / overall_summary
                           are populated; question is None.
    score is the per-question score for the answer just submitted
    (None on the first call when no answer yet).
    """
    interview_id: str
    status: str
    score: Optional[float] = None
    question: Optional[QuestionResponse] = None
    final_score: Optional[float] = None
    recommendation: Optional[str] = None
    overall_summary: Optional[str] = None


# Speech token 

class SpeechTokenResponse(BaseModel):
    """Short-lived Azure Speech token for frontend SDK use."""
    token: str
    region: str


# Dashboard (recruiter) 

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
    """Full detail of the final report for manual recruiter analysis."""
    interview_id: str
    candidate_name: str
    jd_title: str
    overall_summary: Optional[str] = None
    topics_covered: Optional[list] = None
    per_question_scores: Optional[dict] = None
    ai_recommendation: Optional[str] = None
    recruiter_decision: Optional[str] = None

class DecisionRequest(BaseModel):
    """Request to log the recruiter's final decision."""
    decision: str  # hire, hold, reject
