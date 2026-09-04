"""Celery application for durable study-pack work."""

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings


celery_app = Celery(
    "hackagen",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.jobs.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_routes={
        "hackagen.execute_ingestion_job": {"queue": "ingestion"},
        "hackagen.execute_generation_job": {"queue": "generation"},
        "hackagen.execute_video_job": {"queue": "video"},
    },
)


@worker_process_init.connect
def _dispose_inherited_connections(**_kwargs) -> None:
    """A forked worker must not reuse database connections from its parent."""
    from app.services.database import engine

    engine.dispose(close=False)
