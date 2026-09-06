"""Transactional admission and lifecycle rules for durable generation jobs."""

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Callable

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.course import Course
from app.models.generation_job import (
    ACTIVE_JOB_STATES,
    ArtifactType,
    GenerationJob,
    JobQueue,
    JobState,
)
from app.schemas.job import JobSummary


class JobServiceError(Exception):
    code = "job_error"
    public_message = "Không thể xử lý tác vụ lúc này."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.public_message)


class JobCapacityError(JobServiceError):
    def __init__(self, code: str) -> None:
        self.code = code
        message = (
            "Hàng đợi video đang đầy. Hãy thử lại sau."
            if code == "video_capacity_reached"
            else "Hàng đợi tạo học liệu đang đầy. Hãy thử lại sau."
        )
        super().__init__(message)


class DuplicateActiveJobError(JobServiceError):
    code = "generation_in_flight"
    public_message = "Học liệu này đang được tạo."


class InvalidJobTransition(JobServiceError):
    code = "invalid_job_transition"
    public_message = "Trạng thái tác vụ không cho phép thao tác này."


class JobCancelled(JobServiceError):
    code = "job_cancelled"
    public_message = "Tác vụ đã được yêu cầu hủy."


class JobNotFound(JobServiceError):
    code = "job_not_found"
    public_message = "Không tìm thấy tác vụ."


ALLOWED_TRANSITIONS = {
    JobState.QUEUED: {JobState.RUNNING, JobState.CANCELLED},
    JobState.RUNNING: {
        JobState.RETRYING,
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.RETRYING: {
        JobState.QUEUED,
        JobState.FAILED,
        JobState.CANCELLED,
    },
}
TERMINAL_STATES = {
    JobState.SUCCEEDED.value,
    JobState.FAILED.value,
    JobState.CANCELLED.value,
}
_ADMISSION_LOCK_KEY = 448_225_191
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _safe_error(value: object) -> str:
    """Bound persisted errors and remove terminal-control characters."""
    cleaned = _CONTROL_CHARACTERS.sub("", str(value)).strip()
    return cleaned[:500]


class JobService:
    """Manage durable jobs inside the caller's database transaction."""

    def __init__(
        self,
        db: Session,
        app_settings: Settings = settings,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.settings = app_settings
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("JobService clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    def _lock_admission(self) -> None:
        bind = self.db.get_bind()
        if bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _ADMISSION_LOCK_KEY},
            )

    def _owned_course(self, course: Course | str, user_id: str | None) -> Course:
        course_id = course.id if isinstance(course, Course) else course
        owner_id = user_id or (course.user_id if isinstance(course, Course) else None)
        if not owner_id:
            raise JobNotFound()
        statement = (
            select(Course)
            .where(
                Course.id == course_id,
                Course.user_id == owner_id,
                Course.is_deleted.is_(False),
            )
            .with_for_update()
        )
        owned = self.db.execute(statement).scalar_one_or_none()
        if owned is None:
            raise JobNotFound()
        return owned

    @staticmethod
    def _queue_for(artifact_type: str) -> str:
        if artifact_type == ArtifactType.INGESTION.value:
            return JobQueue.INGESTION.value
        if artifact_type == ArtifactType.VID.value:
            return JobQueue.VIDEO.value
        return JobQueue.GENERATION.value

    def enqueue(
        self,
        course: Course | str,
        artifact_type: str,
        payload: dict,
        *,
        user_id: str | None = None,
        version_id: str | None = None,
        max_attempts: int = 3,
    ) -> GenerationJob:
        """Validate ownership/capacity and stage one replayable job atomically."""
        valid_artifacts = {kind.value for kind in ArtifactType}
        if artifact_type not in valid_artifacts:
            raise ValueError(f"Unsupported artifact type: {artifact_type}")
        if not isinstance(payload, dict):
            raise ValueError("Job payload must be an object")
        try:
            json.dumps(payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("Job payload must be JSON serializable") from exc
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")

        self._lock_admission()
        owned_course = self._owned_course(course, user_id)

        duplicate = self.db.scalar(
            select(func.count(GenerationJob.id)).where(
                GenerationJob.course_id == owned_course.id,
                GenerationJob.artifact_type == artifact_type,
                GenerationJob.state.in_(ACTIVE_JOB_STATES),
            )
        )
        if duplicate:
            raise DuplicateActiveJobError()

        active_total = self.db.scalar(
            select(func.count(GenerationJob.id)).where(
                GenerationJob.state.in_(ACTIVE_JOB_STATES)
            )
        )
        if (active_total or 0) >= self.settings.MAX_ACTIVE_JOBS:
            raise JobCapacityError("artifact_capacity_reached")

        if artifact_type == ArtifactType.VID.value:
            active_videos = self.db.scalar(
                select(func.count(GenerationJob.id)).where(
                    GenerationJob.artifact_type == ArtifactType.VID.value,
                    GenerationJob.state.in_(ACTIVE_JOB_STATES),
                )
            )
            if (active_videos or 0) >= self.settings.MAX_ACTIVE_VIDEO_JOBS:
                raise JobCapacityError("video_capacity_reached")

        if artifact_type == ArtifactType.INGESTION.value:
            if version_id is not None:
                raise ValueError("Ingestion jobs cannot have an artifact version")
        else:
            version_id = version_id or str(uuid.uuid4())

        now = self._now()
        job = GenerationJob(
            course_id=owned_course.id,
            user_id=owned_course.user_id,
            artifact_type=artifact_type,
            version_id=version_id,
            queue_name=self._queue_for(artifact_type),
            payload_json=dict(payload),
            max_attempts=max_attempts,
            queued_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            with self.db.begin_nested():
                self.db.add(job)
                self.db.flush()
        except IntegrityError as exc:
            raise DuplicateActiveJobError() from exc
        return job

    def _job(self, job_id: str) -> GenerationJob:
        job = self.db.get(GenerationJob, job_id)
        if job is None:
            raise JobNotFound()
        return job

    def _owned_job(self, job_id: str, user_id: str) -> GenerationJob:
        job = self.db.execute(
            select(GenerationJob).where(
                GenerationJob.id == job_id,
                GenerationJob.user_id == user_id,
            )
        ).scalar_one_or_none()
        if job is None:
            raise JobNotFound()
        return job

    @staticmethod
    def _transition(job: GenerationJob, target: JobState) -> None:
        current = JobState(job.state)
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            raise InvalidJobTransition()
        job.state = target.value

    def queue_position(self, job: GenerationJob) -> int:
        """Return a best-effort position; cancellation/retry may reorder the queue."""
        if job.state not in {JobState.QUEUED.value, JobState.RETRYING.value}:
            return 0
        earlier = self.db.scalar(
            select(func.count(GenerationJob.id)).where(
                GenerationJob.queue_name == job.queue_name,
                GenerationJob.state.in_(ACTIVE_JOB_STATES),
                or_(
                    GenerationJob.queued_at < job.queued_at,
                    (
                        (GenerationJob.queued_at == job.queued_at)
                        & (GenerationJob.id < job.id)
                    ),
                ),
            )
        )
        return int(earlier or 0) + 1

    def _summary(self, job: GenerationJob) -> JobSummary:
        return JobSummary(
            job_id=job.id,
            state=job.state,
            stage=job.stage,
            progress=job.progress,
            queue_position=self.queue_position(job),
            attempt=job.attempt,
            can_cancel=job.state not in TERMINAL_STATES
            and job.cancel_requested_at is None,
            queued_at=job.queued_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error_code=job.error_code,
            error_message=job.error_message,
        )

    def get_summary(self, job_id: str, user_id: str) -> JobSummary:
        return self._summary(self._owned_job(job_id, user_id))

    def request_cancel(self, job_id: str, user_id: str) -> JobSummary:
        job = self._owned_job(job_id, user_id)
        if job.state in TERMINAL_STATES:
            raise InvalidJobTransition()
        now = self._now()
        if job.cancel_requested_at is None:
            job.cancel_requested_at = now
        if job.state in {JobState.QUEUED.value, JobState.RETRYING.value}:
            self._transition(job, JobState.CANCELLED)
            job.stage = "cancelled"
            job.finished_at = now
        job.updated_at = now
        self.db.flush()
        return self._summary(job)

    def start(self, job_id: str, celery_task_id: str) -> GenerationJob:
        job = self._job(job_id)
        if job.celery_task_id != celery_task_id:
            raise JobNotFound()
        if job.cancel_requested_at is not None:
            if job.state == JobState.QUEUED.value:
                self._transition(job, JobState.CANCELLED)
                job.finished_at = self._now()
                job.stage = "cancelled"
                self.db.flush()
            raise JobCancelled()
        self._transition(job, JobState.RUNNING)
        now = self._now()
        job.attempt += 1
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.updated_at = now
        job.stage = "starting"
        self.db.flush()
        return job

    def heartbeat(
        self,
        job_id: str,
        *,
        stage: str,
        progress: int,
        force: bool = False,
    ) -> bool:
        job = self._job(job_id)
        if job.state != JobState.RUNNING.value:
            raise InvalidJobTransition()
        if job.cancel_requested_at is not None:
            raise JobCancelled()
        if not 0 <= progress <= 100:
            raise ValueError("progress must be between 0 and 100")
        now = self._now()
        recently_reported = (
            job.heartbeat_at is not None
            and now - job.heartbeat_at < timedelta(seconds=2)
        )
        if not force and recently_reported and stage == job.stage and progress < 100:
            return False
        job.stage = stage
        job.progress = progress
        job.heartbeat_at = now
        job.updated_at = now
        self.db.flush()
        return True

    def succeed(self, job_id: str) -> GenerationJob:
        job = self._job(job_id)
        if job.state == JobState.SUCCEEDED.value:
            return job
        self._transition(job, JobState.SUCCEEDED)
        now = self._now()
        job.progress = 100
        job.stage = "completed"
        job.heartbeat_at = now
        job.finished_at = now
        job.updated_at = now
        job.error_code = None
        job.error_message = None
        self.db.flush()
        return job

    def fail(self, job_id: str, code: str, message: object) -> GenerationJob:
        job = self._job(job_id)
        self._transition(job, JobState.FAILED)
        now = self._now()
        job.stage = "failed"
        job.error_code = _safe_error(code)[:64]
        job.error_message = _safe_error(message)
        job.heartbeat_at = now
        job.finished_at = now
        job.updated_at = now
        self.db.flush()
        return job

    def record_dispatch(
        self, job_id: str, error: object | None = None
    ) -> GenerationJob:
        job = self._job(job_id)
        if job.state != JobState.QUEUED.value:
            raise InvalidJobTransition()
        now = self._now()
        job.dispatch_attempts += 1
        job.last_dispatch_error = _safe_error(error) if error is not None else None
        if error is None:
            job.dispatched_at = now
        job.updated_at = now
        self.db.flush()
        return job

    def find_pending_dispatches(
        self, *, limit: int = 100, redispatch_after_seconds: int = 10
    ) -> list[GenerationJob]:
        cutoff = self._now() - timedelta(seconds=redispatch_after_seconds)
        return list(
            self.db.scalars(
                select(GenerationJob)
                .where(
                    GenerationJob.state == JobState.QUEUED.value,
                    or_(
                        GenerationJob.dispatched_at.is_(None),
                        GenerationJob.dispatched_at <= cutoff,
                    ),
                )
                .order_by(GenerationJob.queued_at, GenerationJob.id)
                .limit(limit)
            )
        )

    def recover_stale_jobs(self) -> list[GenerationJob]:
        cutoff = self._now() - timedelta(
            seconds=self.settings.JOB_HEARTBEAT_STALE_SECONDS
        )
        last_activity = func.coalesce(
            GenerationJob.heartbeat_at,
            GenerationJob.started_at,
            GenerationJob.queued_at,
        )
        stale_jobs = list(
            self.db.scalars(
                select(GenerationJob)
                .where(
                    GenerationJob.state == JobState.RUNNING.value,
                    last_activity <= cutoff,
                )
                .order_by(GenerationJob.queued_at, GenerationJob.id)
                .with_for_update()
            )
        )
        now = self._now()
        for job in stale_jobs:
            if job.attempt < job.max_attempts:
                self._transition(job, JobState.RETRYING)
                job.stage = "retrying"
            else:
                self._transition(job, JobState.FAILED)
                job.stage = "failed"
                job.error_code = "worker_lost"
                job.error_message = "Tác vụ bị gián đoạn và đã hết số lần thử lại."
                job.finished_at = now
            job.updated_at = now
        self.db.flush()
        return stale_jobs
