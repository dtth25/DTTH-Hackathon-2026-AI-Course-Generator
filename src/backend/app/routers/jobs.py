"""Durable job dispatch, polling, cancellation, and safe admin aggregates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.jobs.dispatcher import DefiniteJobDispatchError, get_job_dispatcher
from app.models.processing_job import JobStatus, ProcessingJob
from app.models.user import User
from app.schemas.course import JobResponse
from app.services.job_service import cancel_job
from app.services.job_resource_state import terminalize_dispatch_failure
from app.services.public_errors import public_error


router = APIRouter(prefix="/api", tags=["jobs"])

_TERMINAL_STATUSES = {
    JobStatus.SUCCEEDED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
}
_FAILURE_CODE_BY_TYPE = {
    "preprocess": "DOCUMENT_PROCESSING_FAILED",
    "book": "BOOK_GENERATION_FAILED",
    "slides": "SLIDE_GENERATION_FAILED",
    "quiz": "QUIZ_GENERATION_FAILED",
    "video": "VIDEO_GENERATION_FAILED",
}
_DISPATCH_FAILURE_CODE = "JOB_DISPATCH_FAILED"
_DISPATCH_FAILURE_MESSAGE = "Không thể bắt đầu tác vụ. Vui lòng thử lại."


def dispatch_persisted_job(
    background_tasks: BackgroundTasks,
    db: Session,
    job: ProcessingJob,
) -> None:
    """Publish one already-committed ID-only delivery and retain its provider id."""
    try:
        external_task_id = get_job_dispatcher(background_tasks).enqueue(
            job.id, job.queue_name
        )
    except DefiniteJobDispatchError as exc:
        try:
            terminalize_dispatch_failure(db, job.id)
        except Exception as persistence_exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "JOB_DISPATCH_PERSISTENCE_FAILED",
                    "message": "Không thể lưu trạng thái tác vụ. Vui lòng thử lại.",
                },
            ) from persistence_exc
        response_code = (
            "DOCUMENT_SCHEDULING_FAILED"
            if job.job_type == "preprocess"
            else _DISPATCH_FAILURE_CODE
        )
        response_message = (
            "Không thể bắt đầu xử lý tài liệu. Vui lòng thử lại."
            if job.job_type == "preprocess"
            else _DISPATCH_FAILURE_MESSAGE
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": response_code,
                "message": response_message,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "JOB_DISPATCH_UNCONFIRMED",
                "message": (
                    "Chưa thể xác nhận tác vụ đã bắt đầu. "
                    "Hệ thống sẽ tự động thử lại."
                ),
            },
        ) from exc

    try:
        db.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.id == job.id,
                ProcessingJob.status == JobStatus.QUEUED.value,
                ProcessingJob.external_task_id.is_(None),
            )
            .values(external_task_id=external_task_id)
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "JOB_DISPATCH_PERSISTENCE_FAILED",
                "message": "Không thể lưu trạng thái tác vụ. Vui lòng thử lại.",
            },
        ) from exc


def _owned_job_or_404(db: Session, job_id: str, current_user: User) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if not job or (job.user_id != current_user.id and current_user.role != "admin"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tác vụ không tồn tại.",
        )
    return job


def _queue_position(db: Session, job: ProcessingJob) -> int | None:
    if job.status not in {
        JobStatus.QUEUED.value,
        JobStatus.RETRY_SCHEDULED.value,
        JobStatus.RUNNING.value,
    }:
        return None
    return int(
        db.scalar(
            select(func.count(ProcessingJob.id)).where(
                ProcessingJob.queue_name == job.queue_name,
                ProcessingJob.status.in_(
                    [
                        JobStatus.QUEUED.value,
                        JobStatus.RETRY_SCHEDULED.value,
                        JobStatus.RUNNING.value,
                    ]
                ),
                or_(
                    ProcessingJob.created_at < job.created_at,
                    and_(
                        ProcessingJob.created_at == job.created_at,
                        ProcessingJob.id <= job.id,
                    ),
                ),
            )
        )
        or 0
    )


def job_response(db: Session, job: ProcessingJob) -> dict[str, Any]:
    """Serialize the established Plan A envelope without technical queue data."""
    failed = job.status == JobStatus.FAILED.value
    public_code, public_message = public_error(
        job.error_code,
        _FAILURE_CODE_BY_TYPE.get(job.job_type, "DOCUMENT_PROCESSING_FAILED"),
    )
    return {
        "id": job.id,
        "document_id": job.course_id,
        "user_id": job.user_id,
        "job_type": job.job_type,
        "status": job.status,
        "queue_position": _queue_position(db, job),
        "progress": job.progress,
        "message": public_message if failed else job.message,
        "error": public_message if failed else None,
        "error_code": public_code if failed else None,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
    }


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_processing_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a safe job envelope only to its owner or an administrator."""
    return job_response(db, _owned_job_or_404(db, job_id, current_user))


@router.delete(
    "/jobs/{job_id}",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def cancel_processing_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request cooperative cancellation without revealing cross-user jobs."""
    job = _owned_job_or_404(db, job_id, current_user)
    if job.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "JOB_ALREADY_TERMINAL",
                "message": "Tác vụ đã kết thúc.",
            },
        )
    if not cancel_job(db, job.id):
        refreshed = db.get(ProcessingJob, job.id)
        if refreshed is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tác vụ không tồn tại.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "JOB_ALREADY_TERMINAL",
                "message": "Tác vụ đã kết thúc.",
            },
        )
    db.expire_all()
    return job_response(db, db.get(ProcessingJob, job.id))


@router.get("/admin/jobs/summary")
def get_job_summary(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return queue/status counts and backlog age without job payloads or text."""
    grouped = db.execute(
        select(
            ProcessingJob.queue_name,
            ProcessingJob.status,
            func.count(ProcessingJob.id),
        ).group_by(ProcessingJob.queue_name, ProcessingJob.status)
    ).all()
    counts: dict[str, dict[str, int]] = {}
    for queue_name, job_status, count in grouped:
        counts.setdefault(queue_name, {})[job_status] = int(count)

    oldest_created_at = db.scalar(
        select(func.min(ProcessingJob.created_at)).where(
            ProcessingJob.status == JobStatus.QUEUED.value
        )
    )
    oldest_age = None
    if oldest_created_at is not None:
        oldest_age = max(
            0,
            int((datetime.utcnow() - oldest_created_at).total_seconds()),
        )
    return {
        "counts": counts,
        "oldest_queued_age_seconds": oldest_age,
    }
