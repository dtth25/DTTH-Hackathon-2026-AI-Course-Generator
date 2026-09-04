"""Dispatch durable jobs without exposing a queue provider to API callers."""

from threading import Timer
from typing import Any, Protocol

from fastapi import BackgroundTasks

from app.core.config import settings


_CELERY_TASKS = {
    "ingestion": "hackagen.execute_ingestion_job",
    "generation": "hackagen.execute_generation_job",
    "video": "hackagen.execute_video_job",
}
_INLINE_REDISPATCH_MAX_SECONDS = 300


class JobDispatcher(Protocol):
    """Minimal dispatch contract shared by inline and Celery execution."""

    def enqueue(self, job_id: str, queue_name: str) -> str:
        """Schedule one durable job by id and return the provider task id."""


def execute_job(job_id: str) -> None:
    """Resolve the shared executor lazily so local mode needs no Celery import."""
    from app.jobs.tasks import execute_job as run_job

    delivery = run_job(job_id)
    if delivery is None:
        return
    delay = max(1, min(_INLINE_REDISPATCH_MAX_SECONDS, delivery.countdown))
    timer = Timer(delay, execute_job, args=(job_id,))
    timer.daemon = True
    timer.start()


def _validate_queue_name(queue_name: str) -> None:
    if queue_name not in _CELERY_TASKS:
        raise ValueError(f"Unsupported job queue: {queue_name}")


class InlineJobDispatcher:
    """Schedule ID-only work through the current FastAPI response lifecycle."""

    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._background_tasks = background_tasks

    def enqueue(self, job_id: str, queue_name: str) -> str:
        _validate_queue_name(queue_name)
        self._background_tasks.add_task(execute_job, job_id)
        return f"inline:{job_id}"


class RecoveryInlineJobDispatcher:
    """Redispatch startup work without depending on an HTTP response lifecycle."""

    def enqueue(self, job_id: str, queue_name: str) -> str:
        _validate_queue_name(queue_name)
        timer = Timer(0, execute_job, args=(job_id,))
        timer.daemon = True
        timer.start()
        return f"inline-recovery:{job_id}"


class CeleryJobDispatcher:
    """Send ID-only jobs to their isolated Celery queues."""

    def __init__(self, celery_app: Any) -> None:
        self._celery_app = celery_app

    def enqueue(self, job_id: str, queue_name: str) -> str:
        _validate_queue_name(queue_name)
        result = self._celery_app.send_task(
            _CELERY_TASKS[queue_name],
            args=[job_id],
            queue=queue_name,
            task_id=job_id,
        )
        return str(result.id)


def get_job_dispatcher(
    background_tasks: BackgroundTasks | None = None,
) -> JobDispatcher:
    """Build the configured dispatcher while keeping inline mode broker-free."""
    if settings.JOB_QUEUE_PROVIDER == "inline":
        if background_tasks is None:
            raise ValueError("Inline job dispatch requires BackgroundTasks.")
        return InlineJobDispatcher(background_tasks)

    from app.jobs.celery_app import celery_app

    return CeleryJobDispatcher(celery_app)


def get_recovery_job_dispatcher() -> JobDispatcher:
    """Build a provider dispatcher suitable for process-start reconciliation."""
    if settings.JOB_QUEUE_PROVIDER == "inline":
        return RecoveryInlineJobDispatcher()
    return get_job_dispatcher()
