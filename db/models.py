"""
db/models.py
============
SQLAlchemy ORM models for the AI Job Application Agent.
Uses plain string columns for status/platform to avoid enum conflicts.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# ---------------------------------------------------------------------------
# Constants (used instead of enums to keep things simple and portable)
# ---------------------------------------------------------------------------

class JobStatus:
    QUEUED      = "queued"
    IN_PROGRESS = "in_progress"
    SUBMITTED   = "submitted"
    FAILED      = "failed"
    BACKLOG     = "backlog"


class ATSPlatform:
    WORKDAY    = "workday"
    GREENHOUSE = "greenhouse"
    LEVER      = "lever"
    LINKEDIN   = "linkedin"
    UNKNOWN    = "unknown"


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

class Candidate(Base):
    __tablename__ = "candidates"

    id            = Column(Integer, primary_key=True, autoincrement=True)

    full_name     = Column(String(200), nullable=False)
    email         = Column(String(254), nullable=False, unique=True)
    phone         = Column(String(30))
    location      = Column(String(200))
    linkedin_url  = Column(String(500))
    github_url    = Column(String(500))
    portfolio_url = Column(String(500))
    resume_path   = Column(String(500))

    work_history  = Column(JSON, default=list)
    education     = Column(JSON, default=list)
    skills        = Column(JSON, default=list)

    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    custom_answers = relationship("CustomAnswer", back_populates="candidate",
                                  cascade="all, delete-orphan")
    jobs           = relationship("Job", back_populates="candidate",
                                  cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Candidate id={self.id} email={self.email!r}>"


# ---------------------------------------------------------------------------
# CustomAnswer
# ---------------------------------------------------------------------------

class CustomAnswer(Base):
    __tablename__ = "custom_answers"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    key          = Column(String(200), nullable=False)
    value        = Column(Text, nullable=False)
    notes        = Column(Text)

    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate    = relationship("Candidate", back_populates="custom_answers")

    def __repr__(self):
        return f"<CustomAnswer {self.key!r}={self.value!r}>"


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class Job(Base):
    __tablename__ = "jobs"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", ondelete="CASCADE"),
                          nullable=False, index=True)

    url          = Column(String(2000), nullable=False)
    company      = Column(String(300))
    title        = Column(String(300))
    ats_platform = Column(String(50), default=ATSPlatform.UNKNOWN)

    # status is a plain string — one of JobStatus constants
    status       = Column(String(50), default=JobStatus.QUEUED, nullable=False, index=True)

    failure_reason       = Column(Text)
    unanswered_fields    = Column(JSON, default=list)
    tailored_resume_path = Column(String(500))
    cover_letter_path    = Column(String(500))

    queued_at    = Column(DateTime, default=datetime.utcnow)
    started_at   = Column(DateTime)
    submitted_at = Column(DateTime)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate    = relationship("Candidate", back_populates="jobs")

    def __repr__(self):
        return f"<Job id={self.id} status={self.status!r} company={self.company!r}>"
