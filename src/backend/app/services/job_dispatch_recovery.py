"""Recover durable queued jobs across commit-before-publish process crashes."""

from __future__ import annotations

import logging

from sqlalchemy import select, update

from app.jobs.dispatcher import JobDispatcher, get_recovery_job_dispatcher
from app.models.processing_job import JobStatus, ProcessingJob


logger = logging.getLogger(__name__)


def reconcile_undispatched_jobs(
    db_session_factory=None,
    dispatcher: JobDispatcher | None = None,
) -> int:
    """Publish ID-only deliveries for distributed jobs lacking confirmation.

    A crash after broker acceptance but before storing the returned id can publish a
    duplicate. That is intentional: Task 3's atomic claim makes duplicate ID-only
    deliveries safe, while silently losing the only delivery is not recoverable.
    """
    if db_session_factory is None:
        from app.services.database import SessionLocal as db_session_factory
    dispatcher = dispatcher or get_recovery_job_dispatcher()

    with db_session_factory() as db:
        rows = db.execute(
            select(ProcessingJob.id, ProcessingJob.queue_name).where(
                ProcessingJob.status == JobStatus.QUEUED.value,
                ProcessingJob.external_task_id.is_(None),
                ProcessingJob.active_key.is_not(None),
            )
        ).all()

    confirmed = 0
    for job_id, queue_name in rows:
        try:
            external_task_id = dispatcher.enqueue(job_id, queue_name)
            with db_session_factory() as db:
                result = db.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.status == JobStatus.QUEUED.value,
                        ProcessingJob.external_task_id.is_(None),
                    )
                    .values(external_task_id=external_task_id)
                )
                db.commit()
                confirmed += int(result.rowcount == 1)
        except Exception:
            logger.exception("Could not reconcile undispatched durable job %s", job_id)
    return confirmed
