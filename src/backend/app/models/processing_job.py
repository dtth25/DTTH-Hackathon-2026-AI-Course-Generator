"""SQLAlchemy model for durable document and generation processing jobs."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

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
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    completed_at = Column(DateTime, nullable=True)
