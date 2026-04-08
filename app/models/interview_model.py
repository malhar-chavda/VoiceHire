from typing import Optional
from pydantic import BaseModel, Field

class QuestionSchema(BaseModel):
    question_order: int
    question_text: str
    skill_area: str = Field(description="General area of the skill being evaluated")
    difficulty: str = Field(description="basic | intermediate | advanced")

class GeneratedQuestions(BaseModel):
    questions: list[QuestionSchema]

class EvaluateMatchRequest(BaseModel):
    resume_id: str
    jd_id: str

class EvaluateMatchResponse(BaseModel):
    eligibility: bool
    match_score: float
    reason: Optional[str] = None
    interview_id: Optional[str] = None
    session_token: Optional[str] = None
