"""Recovery policy for the current single-process BackgroundTasks execution mode.

This module is intentionally isolated: a future durable queue (for example Celery) must
not call this reconciliation because its queued/running tasks can survive a web restart.
"""

from datetime import datetime

from app.models.course import Course
from app.models.processing_job import JobStatus, ProcessingJob

INLINE_INTERRUPTED_CODE = "INLINE_PROCESSING_INTERRUPTED"
INLINE_INTERRUPTED_MESSAGE = "Tác vụ xử lý trước đó bị gián đoạn. Vui lòng thử lại."


def reconcile_interrupted_inline_preprocess_jobs(db_session_factory=None) -> int:
    """Fail stranded inline preprocessing jobs before this process starts serving."""
    from app.core.config import settings

    if (
        settings.PROCESSING_EXECUTION_MODE != "inline"
        or not settings.INLINE_PROCESSING_RECOVERY_ENABLED
    ):
        return 0
    if db_session_factory is None:
        from app.services.database import SessionLocal as db_session_factory

    now = datetime.utcnow()
    with db_session_factory() as db:
        jobs = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.job_type == "preprocess",
                ProcessingJob.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
            )
            .all()
        )
        for job in jobs:
            course = db.get(Course, job.course_id)
            latest_job = (
                db.query(ProcessingJob)
                .filter(
                    ProcessingJob.course_id == job.course_id,
                    ProcessingJob.job_type == "preprocess",
                )
                .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
                .first()
            )
            if (
                course is None
                or course.is_deleted
                or course.status != "processing"
                or job.user_id != course.user_id
                or latest_job is None
                or latest_job.id != job.id
            ):
                continue
            job.status = JobStatus.FAILED.value
            job.error_code = INLINE_INTERRUPTED_CODE
            job.error_message = INLINE_INTERRUPTED_MESSAGE
            job.message = INLINE_INTERRUPTED_MESSAGE
            job.completed_at = now
            job.updated_at = now
            course.status = "failed"
            course.stage = "failed"
            course.progress = 0
            course.embedding_status = "failed"
            course.error_message = INLINE_INTERRUPTED_MESSAGE
            course.failure_stage = "processing_interrupted"
            course.error_code = INLINE_INTERRUPTED_CODE
            course.can_retry = True
            course.recommended_action = "retry_later"
            course.technical_error = "Inline processing did not complete before process restart."
        db.commit()
        return sum(job.status == JobStatus.FAILED.value for job in jobs)
