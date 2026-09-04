"""Recover durable queued jobs across commit-before-publish process crashes."""

from __future__ import annotations

import logging

from sqlalchemy import select, update

from app.core.config import settings
from app.jobs.dispatcher import JobDispatcher, get_recovery_job_dispatcher
from app.models.processing_job import JobStatus, ProcessingJob


logger = logging.getLogger(__name__)


def reconcile_undispatched_jobs(
    db_session_factory=None,
    dispatcher: JobDispatcher | None = None,
) -> int:
    """Publish ID-only deliveries that may have been lost across process exit.

    Broker-backed delivery uses the nullable confirmation marker. Inline callbacks are
    process memory, so every queued distributed inline job is recovered regardless of
    that marker. A crash after acceptance can publish a duplicate; Task 3's atomic
    claim makes duplicate ID-only deliveries safe.
    """
    if db_session_factory is None:
        from app.services.database import SessionLocal as db_session_factory
    dispatcher = dispatcher or get_recovery_job_dispatcher()

    recover_registered_inline = settings.JOB_QUEUE_PROVIDER == "inline"
    with db_session_factory() as db:
        conditions = [
            ProcessingJob.status == JobStatus.QUEUED.value,
            ProcessingJob.active_key.is_not(None),
        ]
        if not recover_registered_inline:
            conditions.append(ProcessingJob.external_task_id.is_(None))
        rows = db.execute(
            select(ProcessingJob.id, ProcessingJob.queue_name).where(*conditions)
        ).all()

    confirmed = 0
    for job_id, queue_name in rows:
        try:
            external_task_id = dispatcher.enqueue(job_id, queue_name)
            with db_session_factory() as db:
                update_conditions = [
                    ProcessingJob.id == job_id,
                    ProcessingJob.status == JobStatus.QUEUED.value,
                ]
                if not recover_registered_inline:
                    update_conditions.append(
                        ProcessingJob.external_task_id.is_(None)
                    )
                result = db.execute(
                    update(ProcessingJob)
                    .where(*update_conditions)
                    .values(external_task_id=external_task_id)
                )
                db.commit()
                confirmed += int(result.rowcount == 1)
        except Exception:
            logger.exception("Could not reconcile undispatched durable job %s", job_id)
    return confirmed
