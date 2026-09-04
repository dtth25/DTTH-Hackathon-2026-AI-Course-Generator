"""Keep public course/artifact polling state coherent with terminal jobs."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.services.versioning import migrate_legacy_artifact_metadata


_ARTIFACT_FAILURE_CODES = {
    "book": "BOOK_GENERATION_FAILED",
    "slides": "SLIDE_GENERATION_FAILED",
    "quiz": "QUIZ_GENERATION_FAILED",
    "vid": "VIDEO_GENERATION_FAILED",
}


def synchronize_terminal_resource(
    db: Session,
    job: ProcessingJob,
    *,
    cancelled: bool,
    dispatch_failed: bool = False,
) -> None:
    """Mutate the job's polled resource without committing the caller's transaction."""
    course = db.get(Course, job.course_id)
    if course is None or course.user_id != job.user_id or course.is_deleted:
        return

    if job.job_type == "preprocess":
        if course.status != "processing":
            return
        if cancelled:
            code = "DOCUMENT_PROCESSING_CANCELLED"
            message = "Tài liệu đã bị hủy trước khi xử lý hoàn tất."
            failure_stage = "processing_cancelled"
        else:
            code = "DOCUMENT_SCHEDULING_FAILED"
            message = "Không thể bắt đầu xử lý tài liệu. Vui lòng thử lại."
            failure_stage = "scheduling_failed"
        course.status = "failed"
        course.stage = "failed"
        course.embedding_status = "failed"
        course.error_code = code
        course.error_message = message
        course.failure_stage = failure_stage
        course.can_retry = True
        course.recommended_action = "retry_later"
        course.technical_error = (
            "Durable job dispatch failed." if dispatch_failed else None
        )
        return

    payload = job.payload_json if isinstance(job.payload_json, dict) else {}
    artifact = payload.get("artifact")
    version_id = payload.get("version_id")
    if artifact not in _ARTIFACT_FAILURE_CODES or not isinstance(version_id, str):
        return

    try:
        raw_metadata = json.loads(course.metadata_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raw_metadata = {}
    metadata, _ = migrate_legacy_artifact_metadata(raw_metadata)
    study_pack = dict(metadata.get("study_pack", {}))
    artifacts = dict(study_pack.get("artifacts", {}))
    entry = dict(artifacts.get(artifact, {}))
    versions = dict(entry.get("versions", {}))
    current = versions.get(version_id)
    if not isinstance(current, dict) or current.get("status") != "processing":
        return

    now = datetime.utcnow().isoformat()
    current = dict(current)
    current.update(
        {
            "status": "error",
            "error": (
                "Đã hủy tạo học liệu."
                if cancelled
                else "Không thể bắt đầu tạo học liệu. Vui lòng thử lại."
            ),
            "error_code": _ARTIFACT_FAILURE_CODES[artifact],
            "technical_error": (
                "Durable job dispatch failed." if dispatch_failed else None
            ),
            "finished_at": now,
            "updated_at": now,
        }
    )
    versions[version_id] = current
    entry["versions"] = versions
    artifacts[artifact] = entry
    study_pack["artifacts"] = artifacts
    metadata["study_pack"] = study_pack
    course.metadata_json = json.dumps(metadata, ensure_ascii=False)


def terminalize_dispatch_failure(db: Session, job_id: str) -> bool:
    """Fail an unpublished job and its resource in one database transaction."""
    from sqlalchemy import update

    from app.models.processing_job import JobStatus

    now = datetime.utcnow()
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status == JobStatus.QUEUED.value,
            ProcessingJob.external_task_id.is_(None),
        )
        .values(
            status=JobStatus.FAILED.value,
            active_key=None,
            error_code="JOB_DISPATCH_FAILED",
            error_message="Không thể bắt đầu tác vụ. Vui lòng thử lại.",
            message="Không thể bắt đầu tác vụ. Vui lòng thử lại.",
            completed_at=now,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        return False
    db.expire_all()
    job = db.get(ProcessingJob, job_id)
    if job is not None:
        synchronize_terminal_resource(
            db, job, cancelled=False, dispatch_failed=True
        )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True
