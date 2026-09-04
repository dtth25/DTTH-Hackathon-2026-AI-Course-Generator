"""SQLAlchemy model for durable document and generation processing jobs."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text

from app.services.database import Base


class JobType(StrEnum):
    """The product operation represented by a processing job."""

    PREPROCESS = "preprocess"
    BOOK = "book"
    SLIDES = "slides"
    QUIZ = "quiz"
    VIDEO = "video"


class JobStatus(StrEnum):
    """The lifecycle states persisted for a processing job."""

    QUEUED = "queued"
    RETRY_SCHEDULED = "retry_scheduled"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingJob(Base):
    """A durable record of asynchronous document or artifact processing."""

    __tablename__ = "processing_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(
        String, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type = Column(String(32), nullable=False)
    status = Column(
        String(32), nullable=False, default=JobStatus.QUEUED.value, index=True
    )
    progress = Column(Integer, nullable=False, default=0)
    message = Column(Text, nullable=False, default="Đang chờ xử lý")
    error_code = Column(String(80), nullable=True)
    error_message = Column(Text, nullable=True)
    external_task_id = Column(String(100), nullable=True, index=True)
    payload_json = Column(JSON, nullable=False, default=dict)
    active_key = Column(String(180), nullable=True, unique=True, index=True)
    queue_name = Column(String(32), nullable=False, default="ingestion")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    worker_id = Column(String(120), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    completed_at = Column(DateTime, nullable=True)
