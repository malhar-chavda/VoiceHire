from __future__ import annotations

import uuid
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


# Helpers

def _uuid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.utcnow()

# Base

class Base(DeclarativeBase):
    pass


# 1. job_description
#    Exists independently — one JD can be used across many interviews.

class JobDescription(Base):
    __tablename__ = "job_description"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    recruiter_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), nullable=True, index=True
        # nullable for now — add FK when recruiters table is built
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    jd_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False
        # structured extraction: required_skills, experience, responsibilities etc.
    )
    jd_blob_url: Mapped[str | None] = mapped_column(
        Text, nullable=True
        # Azure Blob URL to the original uploaded PDF/DOCX
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    # relationships
    interviews: Mapped[list["Interview"]] = relationship(
        "Interview", back_populates="job_description"
    )


# 2. resume
#    Belongs to a candidate. No direct JD link — that link lives in Interview.

class Resume(Base):
    __tablename__ = "resume"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    resume_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False
        # structured extraction: skills, experience, education, certifications
    )
    resume_blob_url: Mapped[str | None] = mapped_column(
        Text, nullable=True
        # Azure Blob URL to the original uploaded PDF/DOCX
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    # relationships
    interviews: Mapped[list["Interview"]] = relationship(
        "Interview", back_populates="resume"
    )

# 3. interview
#    The join event between a Resume and a JobDescription.
#    Holds pre-interview evaluation results + live session state.

class InterviewStatus(str):
    PENDING = "pending"      # link sent, candidate hasn't joined
    ACTIVE = "active"       # candidate is in the session right now
    COMPLETED = "completed"    # all questions answered, loop exited
    REJECTED = "rejected"     # match_score < threshold, never reached interview
    HIRED = "hired"        # recruiter final decision
    HOLD = "hold"         # recruiter final decision


class Interview(Base):
    __tablename__ = "interview"

    interview_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )

    # --- foreign keys ---
    resume_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("resume.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    jd_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_description.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # --- pre-interview LLM evaluation (moved from questions table) ---
    match_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
        # 0.0 – 100.0, produced by LLM match+gap node before interview starts
    )
    skill_gap_report: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
        # e.g. {"missing": ["Kubernetes", "System Design"], "partial": ["AWS"]}
    )
    eligibility: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
        # True if match_score >= threshold, False if rejected before interview
    )

    # --- session state ---
    session_token: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
        # candidate uses this to rejoin if browser closes mid-interview
        # generate with: secrets.token_urlsafe(64)
    )
    status: Mapped[str] = mapped_column(
        Enum(
            "pending", "active", "completed", "rejected", "hired", "hold",
            name="interview_status_enum"
        ),
        nullable=False, default="pending"
    )

    # --- post-interview results ---
    final_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
        # aggregated score after batch evaluation, 0.0 – 100.0
    )
    transcription_blob_url: Mapped[str | None] = mapped_column(
        Text, nullable=True
        # Azure Blob URL to the full interview audio/transcript file
    )
    notification_sent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
        # prevents duplicate emails on retry
    )

    # --- timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
        # set when candidate joins the session
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
        # set when interview loop exits
    )

    # --- constraints ---
    __table_args__ = (
        CheckConstraint("match_score >= 0 AND match_score <= 100", name="chk_match_score"),
        CheckConstraint("final_score >= 0 AND final_score <= 100",  name="chk_final_score"),
    )

    # relationships
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
#    One row per question asked (root + follow-ups).
#    Follow-ups link back to their root via parent_answer_id.

class Answer(Base):
    __tablename__ = "answer"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    interview_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("interview.interview_id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    parent_answer_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("answer.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_followup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    per_que_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    # --- constraints ---
    __table_args__ = (
        CheckConstraint(
            "per_que_score IS NULL OR (per_que_score >= 0 AND per_que_score <= 10)",
            name="chk_per_que_score"
        ),
    )

    # relationships
    interview: Mapped["Interview"] = relationship(
        "Interview", back_populates="answers"
    )

    follow_ups: Mapped[list["Answer"]] = relationship(
        "Answer",
        back_populates="parent_answer",
        cascade="all, delete-orphan",
        foreign_keys=[parent_answer_id]
    )

    parent_answer: Mapped["Answer | None"] = relationship(
        "Answer",
        back_populates="follow_ups",
        remote_side=[id],
        foreign_keys=[parent_answer_id]
    )

# 5. final_report
#    One row per completed interview. Holds the full recruiter-facing report.

class FinalReport(Base):

    __tablename__ = "final_report"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    interview_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("interview.interview_id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
        # unique=True enforces one report per interview
    )

    # --- structured report sections ---
    topics_covered: Mapped[list | None] = mapped_column(
        JSON, nullable=True
        # e.g. ["Python", "REST APIs", "AWS S3", "SQL"]
    )
    per_question_scores: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
        # {"q_id": {"score": 8.5, "summary": "Good answer, missed edge case"}}
        # aggregated from questions table after batch eval
    )
    overall_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
        # 3–5 sentence plain-English summary for the recruiter
    )
    recommendation: Mapped[str | None] = mapped_column(
        Enum("hire", "hold", "reject", name="recommendation_enum"),
        nullable=True
        # LLM-generated recommendation, recruiter can override
    )
    recruiter_decision: Mapped[str | None] = mapped_column(
        Enum("hire", "hold", "reject", name="recruiter_decision_enum"),
        nullable=True
        # final human decision — may differ from LLM recommendation
    )

    # --- timestamps ---
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    decision_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
        # set when recruiter makes their hire/hold/reject call
    )

    # relationship
    interview: Mapped["Interview"] = relationship(
        "Interview", back_populates="final_report"
    )