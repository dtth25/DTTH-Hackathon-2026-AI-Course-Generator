"""Transactional per-user and global admission control for durable jobs."""

from threading import Lock
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.processing_job import JobStatus, ProcessingJob


_ACTIVE_STATUSES = (
    JobStatus.QUEUED.value,
    JobStatus.RETRY_SCHEDULED.value,
    JobStatus.RUNNING.value,
)
_SQLITE_ADMISSION_LOCK = Lock()
_SQLITE_LOCK_HELD_KEY = "hackagen:jobs:sqlite-admission-lock-held"
_SQLITE_LISTENER_KEY = "hackagen:jobs:sqlite-admission-listener-installed"


class UserJobLimitExceeded(HTTPException):
    """Provider-neutral response raised when one user fills their job slots."""

    def __init__(self, retry_after: int = 30) -> None:
        self.retry_after = retry_after
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "USER_JOB_LIMIT_EXCEEDED",
                "message": "Bạn đang có quá nhiều tác vụ chờ xử lý. Vui lòng thử lại sau.",
            },
            headers={"Retry-After": str(retry_after)},
        )


class GlobalJobLimitExceeded(HTTPException):
    """Provider-neutral response raised when the service backlog is full."""

    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "GLOBAL_JOB_LIMIT_EXCEEDED",
                "message": "Hệ thống đang bận. Vui lòng thử lại sau.",
            },
            headers={"Retry-After": str(retry_after)},
        )


def _release_sqlite_admission_lock(
    session: Session, transaction: Any
) -> None:
    """Release only after the outer transaction containing the insert ends."""
    if transaction.parent is not None:
        return
    if session.info.pop(_SQLITE_LOCK_HELD_KEY, False):
        _SQLITE_ADMISSION_LOCK.release()


def _acquire_sqlite_admission_lock(db: Session) -> None:
    if db.info.get(_SQLITE_LOCK_HELD_KEY):
        return
    _SQLITE_ADMISSION_LOCK.acquire()
    db.info[_SQLITE_LOCK_HELD_KEY] = True
    if not db.info.get(_SQLITE_LISTENER_KEY):
        event.listen(db, "after_transaction_end", _release_sqlite_admission_lock)
        db.info[_SQLITE_LISTENER_KEY] = True


def _release_rejected_sqlite_admission(db: Session) -> None:
    if db.info.pop(_SQLITE_LOCK_HELD_KEY, False):
        _SQLITE_ADMISSION_LOCK.release()


def _active_job_count(db: Session, *, user_id: str | None = None) -> int:
    statement = select(func.count()).select_from(ProcessingJob).where(
        ProcessingJob.status.in_(_ACTIVE_STATUSES)
    )
    if user_id is not None:
        statement = statement.where(ProcessingJob.user_id == user_id)
    return int(db.scalar(statement) or 0)


def enforce_job_admission(db: Session, user_id: str) -> None:
    """Reserve capacity until the caller's current DB transaction ends.

    Call this immediately before reservation and ``create_job``. The caller must
    commit both insertions in the same transaction (or roll back on failure).
    PostgreSQL transaction advisory locks and the SQLite session-bound process
    lock keep the count valid until that transaction finishes.
    """
    dialect_name = db.get_bind().dialect.name
    sqlite_lock_acquired = False
    if dialect_name == "postgresql":
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtext('hackagen:jobs:global'))"
            )
        )
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtext('hackagen:jobs:user:' || :user_id))"
            ),
            {"user_id": user_id},
        )
    elif dialect_name == "sqlite":
        _acquire_sqlite_admission_lock(db)
        sqlite_lock_acquired = True

    try:
        if _active_job_count(db) >= settings.MAX_PENDING_JOBS_GLOBAL:
            raise GlobalJobLimitExceeded(retry_after=60)
        if (
            _active_job_count(db, user_id=user_id)
            >= settings.MAX_PENDING_JOBS_PER_USER
        ):
            raise UserJobLimitExceeded(retry_after=30)
    except Exception:
        if sqlite_lock_acquired:
            _release_rejected_sqlite_admission(db)
        raise
