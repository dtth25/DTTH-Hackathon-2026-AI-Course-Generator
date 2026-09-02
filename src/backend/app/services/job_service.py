"""Lifecycle helpers for durable processing jobs."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.processing_job import JobStatus, ProcessingJob


def create_job(
    db: Session, *, course_id: str, user_id: str, job_type: str
) -> ProcessingJob:
    """Persist and return a queued job for the specified course operation."""
    job = ProcessingJob(course_id=course_id, user_id=user_id, job_type=job_type)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_running(db: Session, job_id: str, message: str) -> None:
    """Mark a job as running, doing nothing when it has already been removed."""
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = JobStatus.RUNNING.value
    job.message = message
    job.updated_at = datetime.utcnow()
    db.commit()


def mark_job_failed(
    db: Session, job_id: str, *, error_code: str, message: str
) -> None:
    """Record a terminal, user-safe processing failure."""
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = JobStatus.FAILED.value
    job.error_code = error_code
    job.error_message = message
    job.message = message
    job.completed_at = datetime.utcnow()
    db.commit()


def mark_job_succeeded(db: Session, job_id: str) -> None:
    """Record successful completion and clear a previous job error, if any."""
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = JobStatus.SUCCEEDED.value
    job.progress = 100
    job.message = "Hoàn thành"
    job.error_code = None
    job.error_message = None
    job.completed_at = datetime.utcnow()
    db.commit()
