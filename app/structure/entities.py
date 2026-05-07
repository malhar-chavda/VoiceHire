from __future__ import annotations
import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class InterviewStatus(str, enum.Enum):
    PENDING = "pending"      # link sent, candidate hasn't joined
    ACTIVE = "active"       # candidate is in the session right now
    COMPLETED = "completed"    # all questions answered, loop exited
    REJECTED = "rejected"     # match_score < threshold, never reached interview
    HIRED = "hire"           # recruiter final decision
    HOLD = "hold"            # recruiter final decision


class Recommendation(str, enum.Enum):
    HIRE = "hire"
    HOLD = "hold"
    REJECT = "reject"


# --- Helpers ---

def _uuid() -> str:   # generates a random uuid
    return str(uuid.uuid4())

def _now() -> datetime: # returns the current time
    return datetime.utcnow()

# --- Base ---

class Base(DeclarativeBase): # base class for all entities
    pass


# 1. job_description
class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    recruiter_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    jd_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    jd_blob_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    interviews: Mapped[list["Interview"]] = relationship(
        "Interview", back_populates="job_description"
    )


# 2. resume
class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    resume_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resume_blob_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    interviews: Mapped[list["Interview"]] = relationship(
        "Interview", back_populates="resume"
    )


# 3. interview
class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )

    resume_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    jd_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    skill_gap_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    eligibility: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    session_token: Mapped[str | None] = mapped_column(   # JWT token for interview
        String(512), nullable=True, unique=True, index=True # 24h expiry
    )
    session_resumption_token: Mapped[str | None] = mapped_column( # Token for Live API
        String(512), nullable=True
    )
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus, name="interview_status_enum"),
        nullable=False, default=InterviewStatus.PENDING
    )
    # session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    transcription_blob_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_sent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("match_score >= 0 AND match_score <= 100", name="chk_match_score"),
        CheckConstraint("final_score >= 0 AND final_score <= 100",  name="chk_final_score"),
    )

    resume: Mapped["Resume"] = relationship("Resume", back_populates="interviews")
    job_description: Mapped["JobDescription"] = relationship(
        "JobDescription", back_populates="interviews"
    )
    answers: Mapped[list["Answer"]] = relationship(
        "Answer", back_populates="interview", cascade="all, delete-orphan"
    )
    final_report: Mapped["FinalReport | None"] = relationship(
        "FinalReport", back_populates="interview", uselist=False
    )


# 4. answer
class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    interview_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    parent_answer_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("answers.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_followup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    answer_audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    per_que_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "per_que_score IS NULL OR (per_que_score >= 0 AND per_que_score <= 10)",
            name="chk_per_que_score"
        ),
    )

    interview: Mapped["Interview"] = relationship("Interview", back_populates="answers")
    follow_ups: Mapped[list["Answer"]] = relationship(
        "Answer", back_populates="parent_answer", cascade="all, delete-orphan", foreign_keys=[parent_answer_id]
    )
    parent_answer: Mapped["Answer | None"] = relationship(
        "Answer", back_populates="follow_ups", remote_side=[id], foreign_keys=[parent_answer_id]
    )


# 5. final_report
class FinalReport(Base):
    __tablename__ = "final_reports"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    interview_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )

    topics_covered: Mapped[list | None] = mapped_column(JSON, nullable=True)
    per_question_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    overall_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    recommendation: Mapped[Recommendation | None] = mapped_column(
        Enum(Recommendation, name="recommendation_enum"), nullable=True
    )
    recruiter_decision: Mapped[Recommendation | None] = mapped_column(
        Enum(Recommendation, name="recruiter_decision_enum"), nullable=True
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    decision_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    interview: Mapped["Interview"] = relationship("Interview", back_populates="final_report")


