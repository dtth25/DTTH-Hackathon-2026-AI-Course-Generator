"""Lifecycle helpers for durable processing jobs."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.processing_job import JobStatus, ProcessingJob


_AUTO_ACTIVE_KEY = object()
_ACTIVE_STATUSES = (
    JobStatus.QUEUED.value,
    JobStatus.RETRY_SCHEDULED.value,
    JobStatus.RUNNING.value,
)


def _queue_for_job_type(job_type: str) -> str:
    if job_type == "preprocess":
        return "ingestion"
    if job_type == "video":
        return "video"
    return "generation"


def _active_key_for(
    *, course_id: str, job_type: str, payload_json: dict[str, Any]
) -> str:
    if job_type == "preprocess":
        return f"preprocess:{course_id}"
    version_id = payload_json.get("version_id")
    if not isinstance(version_id, str) or not version_id:
        raise ValueError("Artifact jobs require payload_json.version_id.")
    return f"{job_type}:{course_id}:{version_id}"


def create_job(
    db: Session,
    *,
    course_id: str,
    user_id: str,
    job_type: str,
    payload_json: dict[str, Any] | None = None,
    active_key: str | None | object = _AUTO_ACTIVE_KEY,
    queue_name: str | None = None,
    max_attempts: int = 3,
    commit: bool = True,
) -> ProcessingJob:
    """Create or return the one active job for an operation.

    Plan A callers omit all queue-specific arguments. Those legacy calls retain a
    nullable ``active_key`` until their inline lifecycle is replaced, while queue
    callers opt into durable deduplication by supplying ``payload_json``,
    ``queue_name``, or an explicit ``active_key``.

    ``commit=False`` lets controllers atomically pair another state transition and
    job creation in one transaction. A savepoint contains unique-key races so an
    outer admission/reservation transaction is not rolled back.
    """
    course = db.get(Course, course_id)
    if course is None or course.user_id != user_id:
        raise ValueError("Course does not belong to the specified user.")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    payload = dict(payload_json or {})
    uses_distributed_contract = (
        payload_json is not None
        or queue_name is not None
        or active_key is not _AUTO_ACTIVE_KEY
    )
    resolved_active_key: str | None
    if active_key is _AUTO_ACTIVE_KEY:
        resolved_active_key = (
            _active_key_for(
                course_id=course_id, job_type=job_type, payload_json=payload
            )
            if uses_distributed_contract
            else None
        )
    else:
        resolved_active_key = active_key  # type: ignore[assignment]

    if resolved_active_key is not None:
        existing = db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.active_key == resolved_active_key,
                ProcessingJob.status.in_(_ACTIVE_STATUSES),
            )
        )
        if existing is not None:
            return existing

    job = ProcessingJob(
        course_id=course_id,
        user_id=user_id,
        job_type=job_type,
        payload_json=payload,
        active_key=resolved_active_key,
        queue_name=queue_name or _queue_for_job_type(job_type),
        max_attempts=max_attempts,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        if resolved_active_key is None:
            raise
        existing = db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.active_key == resolved_active_key,
                ProcessingJob.status.in_(_ACTIVE_STATUSES),
            )
        )
        if existing is None:
            raise
        if commit:
            db.commit()
        return existing

    if commit:
        db.commit()
    db.refresh(job)
    return job


def claim_job(db: Session, job_id: str, worker_id: str, lease_seconds: int) -> bool:
    """Atomically claim a queued job or reclaim one whose lease expired."""
    if not worker_id:
        raise ValueError("worker_id must not be empty.")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive.")
    now = datetime.utcnow()
    claimable = or_(
        ProcessingJob.status.in_(
            [JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value]
        ),
        and_(
            ProcessingJob.status == JobStatus.RUNNING.value,
            ProcessingJob.lease_expires_at < now,
        ),
    )
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            claimable,
            ProcessingJob.cancel_requested.is_(False),
            ProcessingJob.attempts < ProcessingJob.max_attempts,
        )
        .values(
            status=JobStatus.RUNNING.value,
            attempts=ProcessingJob.attempts + 1,
            worker_id=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            next_attempt_at=None,
            updated_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1


def renew_job_lease(
    db: Session, job_id: str, worker_id: str, lease_seconds: int
) -> bool:
    """Extend the lease only while the same worker still owns a running job."""
    if not worker_id:
        raise ValueError("worker_id must not be empty.")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive.")
    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.worker_id == worker_id,
            ProcessingJob.status == JobStatus.RUNNING.value,
        )
        .values(
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1


def schedule_job_retry(
    db: Session,
    job_id: str,
    worker_id: str,
    next_attempt_at: datetime,
    message: str = "Đang chờ thử lại",
) -> bool:
    """Release a running attempt for a delayed retry when attempts remain."""
    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.worker_id == worker_id,
            ProcessingJob.status == JobStatus.RUNNING.value,
            ProcessingJob.cancel_requested.is_(False),
            ProcessingJob.attempts < ProcessingJob.max_attempts,
        )
        .values(
            status=JobStatus.RETRY_SCHEDULED.value,
            worker_id=None,
            lease_expires_at=None,
            next_attempt_at=next_attempt_at,
            message=message,
            updated_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1


def cancel_job(db: Session, job_id: str) -> bool:
    """Request cooperative cancellation, terminalizing work that is not running."""
    now = datetime.utcnow()
    immediately_cancelled = ProcessingJob.status.in_(
        [JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value]
    )
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status.in_(_ACTIVE_STATUSES),
            ProcessingJob.cancel_requested.is_(False),
        )
        .values(
            cancel_requested=True,
            status=case(
                (immediately_cancelled, JobStatus.CANCELLED.value),
                else_=ProcessingJob.status,
            ),
            active_key=case(
                (immediately_cancelled, None), else_=ProcessingJob.active_key
            ),
            worker_id=case(
                (immediately_cancelled, None), else_=ProcessingJob.worker_id
            ),
            lease_expires_at=case(
                (immediately_cancelled, None),
                else_=ProcessingJob.lease_expires_at,
            ),
            completed_at=case(
                (immediately_cancelled, now), else_=ProcessingJob.completed_at
            ),
            updated_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1


def mark_job_cancelled(db: Session, job_id: str, worker_id: str) -> bool:
    """Finish a cancellation only for the worker that owns the running job."""
    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.worker_id == worker_id,
            ProcessingJob.status == JobStatus.RUNNING.value,
            ProcessingJob.cancel_requested.is_(True),
        )
        .values(
            status=JobStatus.CANCELLED.value,
            active_key=None,
            worker_id=None,
            lease_expires_at=None,
            updated_at=now,
            completed_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1


def mark_job_running(db: Session, job_id: str, message: str) -> bool:
    """Plan A compatibility transition for its unleased inline processor."""
    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status == JobStatus.QUEUED.value,
            ProcessingJob.worker_id.is_(None),
        )
        .values(status=JobStatus.RUNNING.value, message=message, updated_at=now)
    )
    db.commit()
    return result.rowcount == 1


def mark_job_failed(
    db: Session,
    job_id: str,
    *,
    error_code: str,
    message: str,
    worker_id: str | None = None,
) -> bool:
    """Transition the current running attempt to a user-safe final failure."""
    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status == JobStatus.RUNNING.value,
            ProcessingJob.worker_id == worker_id,
            ProcessingJob.cancel_requested.is_(False),
        )
        .values(
            status=JobStatus.FAILED.value,
            active_key=None,
            worker_id=None,
            lease_expires_at=None,
            error_code=error_code,
            error_message=message,
            message=message,
            updated_at=now,
            completed_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1


def mark_job_succeeded(
    db: Session, job_id: str, *, worker_id: str | None = None
) -> bool:
    """Transition the current running attempt to success."""
    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status == JobStatus.RUNNING.value,
            ProcessingJob.worker_id == worker_id,
            ProcessingJob.cancel_requested.is_(False),
        )
        .values(
            status=JobStatus.SUCCEEDED.value,
            active_key=None,
            worker_id=None,
            lease_expires_at=None,
            progress=100,
            message="Hoàn thành",
            error_code=None,
            error_message=None,
            updated_at=now,
            completed_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1
