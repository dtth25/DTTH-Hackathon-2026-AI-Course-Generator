"""Dispatch durable jobs without exposing a queue provider to API callers."""

from typing import Any, Protocol

from fastapi import BackgroundTasks

from app.core.config import settings


_CELERY_TASKS = {
    "ingestion": "hackagen.execute_ingestion_job",
    "generation": "hackagen.execute_generation_job",
    "video": "hackagen.execute_video_job",
}


class JobDispatcher(Protocol):
    """Minimal dispatch contract shared by inline and Celery execution."""

    def enqueue(self, job_id: str, queue_name: str) -> str:
        """Schedule one durable job by id and return the provider task id."""


def execute_job(job_id: str) -> None:
    """Resolve the shared executor lazily so local mode needs no Celery import."""
    from app.jobs.tasks import execute_job as run_job

    run_job(job_id)


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
