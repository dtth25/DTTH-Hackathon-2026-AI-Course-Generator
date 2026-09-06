"""Durable database model for ingestion and artifact generation work."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.services.database import Base


def utc_now() -> datetime:
    """Return an aware UTC timestamp for job lifecycle fields."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Keep timestamps UTC-aware even when SQLite drops timezone information."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Generation job timestamps must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class ArtifactType(StrEnum):
    INGESTION = "ingestion"
    BOOK = "book"
    SLIDES = "slides"
    QUIZ = "quiz"
    VID = "vid"


class JobQueue(StrEnum):
    INGESTION = "ingestion"
    GENERATION = "generation"
    VIDEO = "video"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_JOB_STATES = (
    JobState.QUEUED.value,
    JobState.RUNNING.value,
    JobState.RETRYING.value,
)
_ACTIVE_JOB_SQL = "state IN ('queued', 'running', 'retrying')"


class GenerationJob(Base):
    """PostgreSQL-backed source of truth for replayable background work."""

    __tablename__ = "generation_jobs"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN ('ingestion', 'book', 'slides', 'quiz', 'vid')",
            name="ck_generation_jobs_artifact_type",
        ),
        CheckConstraint(
            "queue_name IN ('ingestion', 'generation', 'video')",
            name="ck_generation_jobs_queue_name",
        ),
        CheckConstraint(
            "state IN ('queued', 'running', 'retrying', 'succeeded', 'failed', 'cancelled')",
            name="ck_generation_jobs_state",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_generation_jobs_progress",
        ),
        CheckConstraint("attempt >= 0", name="ck_generation_jobs_attempt"),
        CheckConstraint("max_attempts > 0", name="ck_generation_jobs_max_attempts"),
        Index(
            "uq_generation_jobs_active_course_artifact",
            "course_id",
            "artifact_type",
            unique=True,
            postgresql_where=text(_ACTIVE_JOB_SQL),
            sqlite_where=text(_ACTIVE_JOB_SQL),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    version_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    queue_name: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=JobState.QUEUED.value, index=True
    )
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    celery_task_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )

    dispatched_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dispatch_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_dispatch_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )

    queued_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )


@event.listens_for(GenerationJob, "before_insert")
def _assign_deterministic_task_id(_mapper, _connection, job: GenerationJob) -> None:
    """Use one identifier for the durable row and every broker delivery."""
    if not job.id:
        job.id = str(uuid.uuid4())
    if not job.celery_task_id:
        job.celery_task_id = job.id
