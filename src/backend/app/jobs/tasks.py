"""ID-only Celery entrypoints backed by atomic processing-job leases."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
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
)


logger = logging.getLogger(__name__)

_ARTIFACT_BY_JOB_TYPE = {
    "book": "book",
    "slides": "slides",
    "quiz": "quiz",
    "video": "vid",
}
_JOB_FAILED_MESSAGE = "Không thể hoàn tất tác vụ. Vui lòng thử lại."
_JOB_TYPE_UNSUPPORTED_MESSAGE = "Loại tác vụ không được hỗ trợ."


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


def _progress_callback(job_id: str, worker_id: str) -> Callable[[], bool]:
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
            )

    return report


def _finalize(job_id: str, worker_id: str, succeeded: bool) -> None:
    with database.SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None or job.worker_id != worker_id or job.status != "running":
            return
        if job.cancel_requested:
            mark_job_cancelled(db, job_id, worker_id)
        elif succeeded:
            mark_job_succeeded(db, job_id, worker_id=worker_id)
        else:
            mark_job_failed(
                db,
                job_id,
                worker_id=worker_id,
                error_code="JOB_EXECUTION_FAILED",
                message=_JOB_FAILED_MESSAGE,
            )


def _execute_preprocess(job_id: str, course_id: str, worker_id: str) -> bool:
    processor = get_document_processor()
    with database.SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        is_reclaimed_attempt = bool(job and job.attempts > 1)
    if is_reclaimed_attempt:
        # A reclaimed attempt can have upserted only part of its stable chunk set.
        # Terminal predecessor jobs start a new job id and never enter this branch.
        processor.vector_store.delete_course(course_id)
    file_paths = processor.list_saved_course_files(course_id)
    if not file_paths:
        raise ValueError("No saved course files were found.")
    result = processor.process_course(
        course_id=course_id,
        file_paths=file_paths,
        db_session_factory=database.SessionLocal,
        progress_callback=_progress_callback(job_id, worker_id),
    )
    return result.status == "ready"


def _execute_artifact(
    job_id: str,
    job_type: str,
    course_id: str,
    course_metadata: str | dict[str, Any] | None,
    payload: dict[str, Any],
    worker_id: str,
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
        "progress_callback": _progress_callback(job_id, worker_id),
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


def execute_job(job_id: str, worker_id: str = "celery-worker") -> None:
    """Claim and execute one persisted job; all durable inputs are loaded by id."""
    with database.SessionLocal() as db:
        if not claim_job(db, job_id, worker_id, settings.JOB_LEASE_SECONDS):
            return
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
        course_id = course.id
        course_metadata = course.metadata_json

    try:
        if job_type == "preprocess":
            succeeded = _execute_preprocess(job_id, course_id, worker_id)
        else:
            succeeded = _execute_artifact(
                job_id,
                job_type,
                course_id,
                course_metadata,
                payload,
                worker_id,
            )
    except Exception:
        logger.exception("Durable job %s failed", job_id)
        succeeded = False
    _finalize(job_id, worker_id, succeeded)


def _run(self, job_id: str) -> None:
    execute_job(job_id, worker_id=self.request.hostname or "celery-worker")


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
