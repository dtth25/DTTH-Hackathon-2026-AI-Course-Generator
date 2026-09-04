"""ID-only Celery entrypoints backed by atomic processing-job leases."""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings
from app.jobs.celery_app import celery_app
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.services import database
from app.services.document_processor import get_document_processor
from app.services.job_service import (
    claim_job,
    mark_job_cancelled,
    mark_job_failed,
    mark_job_succeeded,
    renew_job_lease,
    schedule_job_retry,
)
from sqlalchemy import update


logger = logging.getLogger(__name__)

_ARTIFACT_BY_JOB_TYPE = {
    "book": "book",
    "slides": "slides",
    "quiz": "quiz",
    "video": "vid",
}
_JOB_FAILED_MESSAGE = "Không thể hoàn tất tác vụ. Vui lòng thử lại."
_JOB_TYPE_UNSUPPORTED_MESSAGE = "Loại tác vụ không được hỗ trợ."


@dataclass(frozen=True)
class DeliveryInstruction:
    """Schedule the same ID-only delivery after durable state becomes claimable."""

    queue_name: str
    countdown: int


def _countdown_until(when: datetime | None) -> int:
    if when is None:
        return 1
    return max(1, math.ceil((when - datetime.utcnow()).total_seconds()))


def _delivery_for_unclaimed(job_id: str) -> DeliveryInstruction | None:
    """Keep active work discoverable when a duplicate arrives before its lease is due."""
    with database.SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return None
        if job.status == "running" and job.lease_expires_at is not None:
            return DeliveryInstruction(
                queue_name=job.queue_name,
                countdown=_countdown_until(job.lease_expires_at),
            )
        if job.status == "retry_scheduled":
            return DeliveryInstruction(
                queue_name=job.queue_name,
                countdown=_countdown_until(job.next_attempt_at),
            )
        return None


def get_generator():
    """Build a worker-local generator without importing an API router."""
    from app.services.generator import Generator
    from app.services.llm import LLMService
    from app.services.vector_store import get_vector_store

    default_llm = LLMService()
    overrides = {
        "book": settings.OPENROUTER_BOOK_MODEL,
        "slides": settings.OPENROUTER_SLIDE_MODEL,
        "quiz": settings.OPENROUTER_QUIZ_MODEL,
        "vid": settings.OPENROUTER_VID_MODEL,
    }
    feature_llms = {
        feature: LLMService(model=model) if model else default_llm
        for feature, model in overrides.items()
    }
    return Generator(get_vector_store(), default_llm, feature_llms)


def _payload(job: ProcessingJob) -> dict[str, Any]:
    payload = job.payload_json
    if not isinstance(payload, dict):
        raise ValueError("Job payload must be a JSON object.")
    return dict(payload)


def _artifact_version_is_ready(
    raw_metadata: str | dict[str, Any] | None,
    artifact: str,
    version_id: str,
) -> bool:
    raw_metadata = raw_metadata or "{}"
    try:
        metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(metadata, dict):
        return False
    version = (
        metadata.get("study_pack", {})
        .get("artifacts", {})
        .get(artifact, {})
        .get("versions", {})
        .get(version_id, {})
    )
    return isinstance(version, dict) and version.get("status") == "ready"


def _progress_callback(
    job_id: str, worker_id: str, attempt_number: int
) -> Callable[[], bool]:
    """Renew a live lease, or signal the service to stop after cancellation/claim loss."""

    def report() -> bool:
        with database.SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.worker_id != worker_id or job.status != "running":
                return False
            if job.cancel_requested:
                return False
            return renew_job_lease(
                db,
                job_id,
                worker_id,
                settings.JOB_LEASE_SECONDS,
                expected_attempt=attempt_number,
            )

    return report


def _finalize(
    job_id: str, worker_id: str, attempt_number: int, succeeded: bool
) -> None:
    with database.SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None or job.worker_id != worker_id or job.status != "running":
            return
        if job.cancel_requested:
            mark_job_cancelled(
                db, job_id, worker_id, expected_attempt=attempt_number
            )
        elif succeeded:
            mark_job_succeeded(
                db,
                job_id,
                worker_id=worker_id,
                expected_attempt=attempt_number,
            )
        else:
            mark_job_failed(
                db,
                job_id,
                worker_id=worker_id,
                error_code="JOB_EXECUTION_FAILED",
                message=_JOB_FAILED_MESSAGE,
                expected_attempt=attempt_number,
            )


def _execute_preprocess(
    job_id: str, course_id: str, worker_id: str, attempt_number: int
) -> bool:
    processor = get_document_processor()
    with database.SessionLocal() as db:
        owned = db.get(ProcessingJob, job_id)
        if (
            owned is None
            or owned.worker_id != worker_id
            or owned.attempts != attempt_number
            or owned.status != "running"
            or owned.cancel_requested
        ):
            return False
        db.execute(
            update(Course)
            .where(
                Course.id == course_id,
                Course.user_id == owned.user_id,
                Course.is_deleted.is_(False),
            )
            .values(status="processing")
        )
        db.commit()
    if attempt_number > 1:
        processor.vector_store.delete_job_attempt(
            course_id=course_id,
            job_id=job_id,
            attempt_number=attempt_number - 1,
        )
    file_paths = processor.list_saved_course_files(course_id)
    if not file_paths:
        raise ValueError("No saved course files were found.")
    result = processor.process_course(
        course_id=course_id,
        file_paths=file_paths,
        db_session_factory=database.SessionLocal,
        job_id=job_id,
        worker_id=worker_id,
        attempt_number=attempt_number,
        progress_callback=_progress_callback(job_id, worker_id, attempt_number),
    )
    return result.status == "ready"


def _execute_artifact(
    job_id: str,
    job_type: str,
    course_id: str,
    course_metadata: str | dict[str, Any] | None,
    payload: dict[str, Any],
    worker_id: str,
    attempt_number: int,
) -> bool:
    artifact = _ARTIFACT_BY_JOB_TYPE[job_type]
    version_id = payload.get("version_id")
    if not isinstance(version_id, str) or not version_id:
        raise ValueError("Artifact job payload requires version_id.")
    if _artifact_version_is_ready(course_metadata, artifact, version_id):
        return True

    common = {
        "course_id": course_id,
        "version_id": version_id,
        "db_session_factory": database.SessionLocal,
        "progress_callback": _progress_callback(job_id, worker_id, attempt_number),
        "execution_token": f"{job_id}-{attempt_number}",
        "job_id": job_id,
        "worker_id": worker_id,
        "attempt_number": attempt_number,
    }
    generator = get_generator()
    if job_type == "book":
        result = generator.generate_book(
            detail_level=payload.get("detail_level", "Tiêu chuẩn"),
            user_prompt=payload.get("user_prompt", ""),
            **common,
        )
    elif job_type == "slides":
        result = generator.generate_slides(
            topic=payload.get("topic", "AI Overview"),
            num_slides=payload.get("num_slides", 15),
            focus_prompt=payload.get("focus_prompt", ""),
            **common,
        )
    elif job_type == "quiz":
        result = generator.generate_quiz(
            topic=payload.get("topic", "AI Quiz"),
            quantity=payload.get("quantity", 5),
            difficulty=payload.get("difficulty", "mixed"),
            **common,
        )
    else:
        result = generator.generate_vid(
            topic=payload.get("topic", "AI Video"),
            fmt=payload.get("format", "standard"),
            voice=payload.get("voice", "female"),
            user_prompt=payload.get("user_prompt", ""),
            **common,
        )
    return result is not None


def _retry_or_fail(
    job_id: str, worker_id: str, attempt_number: int
) -> DeliveryInstruction | None:
    with database.SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None or job.worker_id != worker_id or job.attempts != attempt_number:
            return _delivery_for_unclaimed(job_id)
        if job.cancel_requested:
            mark_job_cancelled(
                db, job_id, worker_id, expected_attempt=attempt_number
            )
            return None
        retry_at = datetime.utcnow() + timedelta(
            seconds=min(300, 5 * (2 ** max(0, attempt_number - 1)))
        )
        if schedule_job_retry(
            db,
            job_id,
            worker_id,
            retry_at,
            expected_attempt=attempt_number,
        ):
            return DeliveryInstruction(
                queue_name=job.queue_name,
                countdown=_countdown_until(retry_at),
            )
        mark_job_failed(
            db,
            job_id,
            worker_id=worker_id,
            error_code="JOB_EXECUTION_FAILED",
            message=_JOB_FAILED_MESSAGE,
            expected_attempt=attempt_number,
        )
        return None


def execute_job(
    job_id: str, worker_id: str = "celery-worker"
) -> DeliveryInstruction | None:
    """Claim and execute one persisted job; all durable inputs are loaded by id."""
    with database.SessionLocal() as db:
        if not claim_job(db, job_id, worker_id, settings.JOB_LEASE_SECONDS):
            return _delivery_for_unclaimed(job_id)
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return
        if job.job_type not in {"preprocess", *_ARTIFACT_BY_JOB_TYPE}:
            mark_job_failed(
                db,
                job_id,
                worker_id=worker_id,
                error_code="JOB_TYPE_UNSUPPORTED",
                message=_JOB_TYPE_UNSUPPORTED_MESSAGE,
            )
            return
        course = db.get(Course, job.course_id)
        if course is None or course.is_deleted or course.user_id != job.user_id:
            mark_job_failed(
                db,
                job_id,
                worker_id=worker_id,
                error_code="JOB_COURSE_UNAVAILABLE",
                message=_JOB_FAILED_MESSAGE,
            )
            return
        try:
            payload = _payload(job)
            payload_course_id = payload.get("course_id")
            if payload_course_id is not None and payload_course_id != job.course_id:
                raise ValueError("Job payload course_id does not match its durable owner.")
        except ValueError:
            mark_job_failed(
                db,
                job_id,
                worker_id=worker_id,
                error_code="JOB_PAYLOAD_INVALID",
                message=_JOB_FAILED_MESSAGE,
            )
            return
        job_type = job.job_type
        attempt_number = job.attempts
        course_id = course.id
        course_metadata = course.metadata_json

    try:
        if job_type == "preprocess":
            succeeded = _execute_preprocess(
                job_id, course_id, worker_id, attempt_number
            )
        else:
            succeeded = _execute_artifact(
                job_id,
                job_type,
                course_id,
                course_metadata,
                payload,
                worker_id,
                attempt_number,
            )
    except Exception:
        logger.exception("Durable job %s failed", job_id)
        return _retry_or_fail(job_id, worker_id, attempt_number)
    if not succeeded:
        return _retry_or_fail(job_id, worker_id, attempt_number)
    _finalize(job_id, worker_id, attempt_number, succeeded)
    return None


def _run(self, job_id: str) -> None:
    delivery = execute_job(
        job_id, worker_id=self.request.hostname or "celery-worker"
    )
    if delivery is not None:
        self.apply_async(
            args=[job_id],
            queue=delivery.queue_name,
            countdown=delivery.countdown,
        )


@celery_app.task(
    bind=True,
    name="hackagen.execute_ingestion_job",
    soft_time_limit=900,
    time_limit=1200,
)
def execute_ingestion_job(self, job_id: str) -> None:
    _run(self, job_id)


@celery_app.task(
    bind=True,
    name="hackagen.execute_generation_job",
    soft_time_limit=1200,
    time_limit=1500,
)
def execute_generation_job(self, job_id: str) -> None:
    _run(self, job_id)


@celery_app.task(
    bind=True,
    name="hackagen.execute_video_job",
    soft_time_limit=2700,
    time_limit=3000,
)
def execute_video_job(self, job_id: str) -> None:
    _run(self, job_id)
