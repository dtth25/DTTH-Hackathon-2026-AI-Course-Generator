"""Lifecycle helpers for durable processing jobs."""

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.processing_job import JobStatus, ProcessingJob


def create_job(
    db: Session, *, course_id: str, user_id: str, job_type: str
) -> ProcessingJob:
    """Persist and return a queued job for the specified course operation."""
    course = db.get(Course, course_id)
    if course is None or course.user_id != user_id:
        raise ValueError("Course does not belong to the specified user.")

    job = ProcessingJob(course_id=course_id, user_id=user_id, job_type=job_type)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_running(db: Session, job_id: str, message: str) -> bool:
    """Transition a queued job to running, returning whether the transition occurred."""
    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status == JobStatus.QUEUED.value,
        )
        .values(status=JobStatus.RUNNING.value, message=message, updated_at=now)
    )
    db.commit()
    return result.rowcount == 1


def mark_job_failed(
    db: Session, job_id: str, *, error_code: str, message: str
) -> bool:
    """Transition a running job to a terminal, user-safe failure."""
    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status == JobStatus.RUNNING.value,
        )
        .values(
            status=JobStatus.FAILED.value,
            error_code=error_code,
            error_message=message,
            message=message,
            updated_at=now,
            completed_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1


def mark_job_succeeded(db: Session, job_id: str) -> bool:
    """Transition a running job to success and clear any prior job error."""
    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status == JobStatus.RUNNING.value,
        )
        .values(
            status=JobStatus.SUCCEEDED.value,
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
