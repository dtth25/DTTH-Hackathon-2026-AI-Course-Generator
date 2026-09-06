"""Document processing service for extracting, cleaning, chunking, and embedding documents."""

import logging
import os
import re
import time
from collections import Counter
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from pydantic import BaseModel
import fitz  # PyMuPDF
from sqlalchemy import select, update
from app.models.course import Course
from app.models.processing_job import JobStatus, ProcessingJob
from app.services.job_service import mark_job_running
from app.services.provider_errors import (
    ProviderErrorCode,
    ProviderFailure,
    ProviderRequestError,
)
from app.services.provider_health import get_openrouter_health
from app.services.provider_guard import ProviderCircuitOpen
from app.services.vector_store import Document, VectorStore
from app.schemas.source_document import ExtractionReport, SourceBlock
from app.services.extraction_quality import OCRResult, extract_source

logger = logging.getLogger(__name__)

_PREFLIGHT_MAX_ATTEMPTS = 3
_PREFLIGHT_INITIAL_DELAY_SECONDS = 0.25
_PREFLIGHT_MAX_DELAY_SECONDS = 1.0
PERSISTENCE_FAILURE_CODE = "DOCUMENT_PROCESSING_PERSISTENCE_FAILED"
PERSISTENCE_FAILURE_MESSAGE = "Không thể lưu trạng thái xử lý tài liệu. Vui lòng thử lại."

_SENTENCE_BOUNDARY_RE = re.compile(r"[.?!][ \n]")
_FRONT_MATTER_MARKERS = (
    "isbn", "nhà xuất bản", "nxb", "bản quyền", "tái bản", "ấn bản", "thẩm định",
    "được thẩm định", "approval", "approved by", "publisher", "copyright", "all rights reserved",
    "edition", "出版社", "出版", "审定", "批准", "版权", "isbn",
)


def _is_front_matter(text: str) -> bool:
    """Identify colophon/publishing pages so they cannot dominate RAG on thin scans."""
    normalized = " ".join(text.lower().split())
    matches = sum(marker in normalized for marker in _FRONT_MATTER_MARKERS)
    # A strong colophon marker is enough; a generic edition/publisher hint needs a second
    # signal to avoid discarding an academic discussion that happens to mention publishing.
    return matches >= 2 or any(marker in normalized for marker in ("isbn", "thẩm định", "审定", "出版社", "版权"))


def _legacy_extraction_compatibility_score(reports: List[ExtractionReport]) -> int:
    """Binary legacy field: extraction completion only, independent of chunk count."""

    return 100 if reports and all(report.complete for report in reports) else 0


def _evenly_spaced_indices(indices: List[int], limit: int) -> List[int]:
    """Choose up to ``limit`` source-page indices across the entire document."""
    if limit <= 0 or not indices:
        return []
    if len(indices) <= limit:
        return indices
    if limit == 1:
        return [indices[len(indices) // 2]]
    return [indices[round(i * (len(indices) - 1) / (limit - 1))] for i in range(limit)]


def _find_split_position(text: str, start: int, end: int, chunk_size: int) -> int:
    """Find the best position to end a chunk at, preferring a sentence boundary, then a
    newline, then a plain space — only within the back half of the window so a chunk
    never ends up drastically shorter than requested. Returns -1 for a hard cut at `end`
    when no good boundary is found."""
    half = start + chunk_size // 2

    best = -1
    for m in _SENTENCE_BOUNDARY_RE.finditer(text, start, end):
        pos = m.start() + 1  # right after the punctuation, before the trailing whitespace
        if pos > half:
            best = pos
    if best != -1:
        return best

    split_pos = text.rfind("\n", start, end)
    if split_pos == -1 or split_pos <= half:
        split_pos = text.rfind(" ", start, end)
    if split_pos != -1 and split_pos > half:
        return split_pos

    return -1


def _extraction_failure_details(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, UnicodeDecodeError):
        return (
            "Không thể đọc tệp văn bản. Vui lòng lưu lại tệp ở định dạng UTF-8 rồi tải lên lại.",
            "DOCUMENT_TEXT_ENCODING_UNSUPPORTED",
            "resave_utf8",
        )
    return (
        "Không thể đọc tài liệu. Vui lòng tải lên bản PDF rõ hơn.",
        "DOCUMENT_TEXT_EXTRACTION_FAILED",
        "upload_clearer_pdf",
    )


class ProcessingResult(BaseModel):
    """Result of processing documents for a course."""

    course_id: str
    status: str
    chunk_count: int
    quality_score: int
    error: Optional[str] = None


class TerminalPersistenceOutcome(StrEnum):
    """A terminal write either committed, lost ownership, or hit durable storage."""

    PERSISTED = "persisted"
    LOST_CLAIM = "lost_claim"
    ERROR = "error"


class _TerminalCommitAcknowledgementUncertain(Exception):
    """The database may have committed even though the driver raised from commit()."""


def _provider_failure_from_health(error_code: Optional[str]) -> ProviderFailure:
    """Convert the redacted health result into the same typed provider failure used by calls."""
    try:
        code = ProviderErrorCode(error_code or ProviderErrorCode.REQUEST_FAILED)
    except ValueError:
        code = ProviderErrorCode.REQUEST_FAILED
    messages = {
        ProviderErrorCode.KEY_INVALID: ("Dịch vụ AI chưa được cấu hình hợp lệ.", "contact_admin"),
        ProviderErrorCode.KEY_LIMIT_EXCEEDED: (
            "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
            "restore_provider_quota",
        ),
        ProviderErrorCode.CREDITS_EXHAUSTED: (
            "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
            "restore_provider_quota",
        ),
        ProviderErrorCode.ACCESS_DENIED: ("Dịch vụ AI không có quyền thực hiện yêu cầu này.", "contact_admin"),
        ProviderErrorCode.RATE_LIMITED: ("Dịch vụ AI đang bận. Tác vụ có thể thử lại sau.", "retry_later"),
        ProviderErrorCode.TIMEOUT: ("Kết nối dịch vụ AI quá thời gian chờ.", "retry_later"),
        ProviderErrorCode.UNAVAILABLE: ("Dịch vụ AI tạm thời không khả dụng.", "retry_later"),
        ProviderErrorCode.REQUEST_FAILED: ("Không thể hoàn tất yêu cầu AI.", "retry_later"),
    }
    user_message, recommended_action = messages[code]
    automatic_retry = code in {
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.UNAVAILABLE,
        ProviderErrorCode.TIMEOUT,
    }
    return ProviderFailure(
        code=code,
        user_message=user_message,
        can_retry=True,
        automatic_retry=automatic_retry,
        recommended_action=recommended_action,
        http_status=None,
        technical_message=f"OpenRouter preflight unavailable: {code}",
    )


def _require_provider_preflight() -> None:
    """Fail fast on permanent provider errors, retrying transient cached preflight failures."""
    from app.core.config import settings

    for attempt in range(_PREFLIGHT_MAX_ATTEMPTS):
        # A transient cached failure must be refreshed; otherwise retrying would merely
        # reread the same TTL entry without probing whether the provider recovered.
        health = get_openrouter_health(force=attempt > 0)
        if health.available:
            return
        failure = _provider_failure_from_health(health.error_code)
        if not failure.automatic_retry or attempt == _PREFLIGHT_MAX_ATTEMPTS - 1:
            raise ProviderRequestError(failure)
        if settings.JOB_QUEUE_PROVIDER == "celery":
            raise ProviderCircuitOpen(
                settings.OPENROUTER_CIRCUIT_OPEN_SECONDS,
                reason="preflight",
                error_code="AI_UNAVAILABLE",
            )
        delay = min(
            _PREFLIGHT_INITIAL_DELAY_SECONDS * (2**attempt),
            _PREFLIGHT_MAX_DELAY_SECONDS,
        )
        time.sleep(delay)


class DocumentProcessor:
    """Processes course documents: extraction, cleaning, chunking, embedding, and vector storage."""

    def __init__(
        self,
        vector_store: VectorStore,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        from app.core.config import settings

        self.vector_store = vector_store
        self.chunk_size = chunk_size if chunk_size is not None else settings.DOCUMENT_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.DOCUMENT_CHUNK_OVERLAP

    def _update_course_db(
        self,
        course_id: str,
        status: str,
        stage: str,
        progress: int,
        chunk_count: int = 0,
        quality_score: int = 0,
        embedding_status: str = "pending",
        name: Optional[str] = None,
        error_message: Optional[str] = None,
        embedding_provider: Optional[str] = None,
        failure_stage: Optional[str] = None,
        error_code: Optional[str] = None,
        can_retry: bool = False,
        recommended_action: Optional[str] = None,
        technical_error: Optional[str] = None,
        job_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
        db_session_factory=None,
    ) -> bool:
        """Persist course progress and deliberately propagate persistence failures."""
        if db_session_factory is None:
            from app.services.database import SessionLocal as factory
        else:
            factory = db_session_factory
        with factory() as db:
            if worker_id is not None:
                if not job_id or attempt_number is None:
                    return False
                now = datetime.utcnow()
                live_claim = (
                    select(ProcessingJob.id)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.course_id == Course.id,
                        ProcessingJob.user_id == Course.user_id,
                        ProcessingJob.worker_id == worker_id,
                        ProcessingJob.attempts == attempt_number,
                        ProcessingJob.status == JobStatus.RUNNING.value,
                        ProcessingJob.cancel_requested.is_(False),
                        ProcessingJob.lease_expires_at > now,
                    )
                    .correlate(Course)
                    .exists()
                )
                course_values = self._terminal_course_values(
                    status=status,
                    stage=stage,
                    progress=progress,
                    embedding_status=embedding_status,
                    course_fields={
                        "chunk_count": chunk_count,
                        "quality_score": quality_score,
                        "name": name,
                        "error_message": error_message,
                        "embedding_provider": embedding_provider,
                        "failure_stage": failure_stage,
                        "error_code": error_code,
                        "can_retry": can_retry,
                        "recommended_action": recommended_action,
                        "technical_error": technical_error,
                    },
                )
                result = db.execute(
                    update(Course)
                    .where(
                        Course.id == course_id,
                        Course.is_deleted.is_(False),
                        live_claim,
                    )
                    .values(**course_values)
                )
                db.commit()
                return result.rowcount == 1
            course = (
                db.query(Course)
                .filter(Course.id == course_id, Course.is_deleted == False)  # noqa: E712
                .first()
            )
            if course is None:
                raise RuntimeError(f"Course {course_id} was not found while persisting processing state.")
            self._apply_course_state(
                course,
                status=status,
                stage=stage,
                progress=progress,
                chunk_count=chunk_count,
                quality_score=quality_score,
                embedding_status=embedding_status,
                name=name,
                error_message=error_message,
                embedding_provider=embedding_provider,
                failure_stage=failure_stage,
                error_code=error_code,
                can_retry=can_retry,
                recommended_action=recommended_action,
                technical_error=technical_error,
            )
            db.commit()
            return True

    @staticmethod
    def _apply_course_state(
        course: Course,
        *,
        status: str,
        stage: str,
        progress: int,
        chunk_count: int = 0,
        quality_score: int = 0,
        embedding_status: str = "pending",
        name: Optional[str] = None,
        error_message: Optional[str] = None,
        embedding_provider: Optional[str] = None,
        failure_stage: Optional[str] = None,
        error_code: Optional[str] = None,
        can_retry: bool = False,
        recommended_action: Optional[str] = None,
        technical_error: Optional[str] = None,
    ) -> None:
        course.status = status
        course.stage = stage
        course.progress = progress
        if chunk_count > 0:
            course.chunk_count = chunk_count
        if quality_score > 0:
            course.quality_score = quality_score
        if name:
            course.name = name
        if embedding_provider:
            course.embedding_provider = embedding_provider
        course.embedding_status = embedding_status
        course.error_message = error_message
        course.failure_stage = failure_stage
        course.error_code = error_code
        course.can_retry = can_retry
        course.recommended_action = recommended_action
        course.technical_error = technical_error

    @staticmethod
    def _terminal_course_values(
        *, status: str, stage: str, progress: int, embedding_status: str, course_fields: dict
    ) -> dict:
        """Build only the course columns intended for a terminal state transition."""
        course_values = {
            "status": status,
            "stage": stage,
            "progress": progress,
            "embedding_status": embedding_status,
            "error_message": course_fields.get("error_message"),
            "failure_stage": course_fields.get("failure_stage"),
            "error_code": course_fields.get("error_code"),
            "can_retry": course_fields.get("can_retry", False),
            "recommended_action": course_fields.get("recommended_action"),
            "technical_error": course_fields.get("technical_error"),
        }
        for field in ("chunk_count", "quality_score"):
            if course_fields.get(field, 0) > 0:
                course_values[field] = course_fields[field]
        for field in ("name", "embedding_provider", "extraction_coverage_json"):
            if course_fields.get(field):
                course_values[field] = course_fields[field]
        return course_values

    @staticmethod
    def _guarded_terminal_update(
        db,
        *,
        course_id: str,
        job_id: Optional[str],
        job_values: Optional[dict],
        course_values: dict,
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
    ) -> TerminalPersistenceOutcome:
        """Commit a terminal job/course pair only while this attempt still owns both."""
        if job_id:
            active_course_owner = (
                select(Course.user_id)
                .where(
                    Course.id == course_id,
                    Course.is_deleted == False,  # noqa: E712
                    Course.status == "processing",
                )
                .scalar_subquery()
            )
            latest_job_id = (
                select(ProcessingJob.id)
                .where(
                    ProcessingJob.course_id == course_id,
                    ProcessingJob.job_type == "preprocess",
                )
                .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
                .limit(1)
                .scalar_subquery()
            )
            job_conditions = [
                ProcessingJob.id == job_id,
                ProcessingJob.course_id == course_id,
                ProcessingJob.status == JobStatus.RUNNING.value,
                ProcessingJob.user_id == active_course_owner,
                ProcessingJob.id == latest_job_id,
            ]
            if worker_id is not None:
                job_conditions.extend(
                    [
                        ProcessingJob.worker_id == worker_id,
                        ProcessingJob.attempts == attempt_number,
                        ProcessingJob.cancel_requested.is_(False),
                        ProcessingJob.lease_expires_at > datetime.utcnow(),
                    ]
                )
            if job_values is None:
                owns_job = db.scalar(
                    select(ProcessingJob.id)
                    .where(*job_conditions)
                    .with_for_update()
                )
                job_rowcount = 1 if owns_job is not None else 0
            else:
                job_result = db.execute(
                    update(ProcessingJob)
                    .where(*job_conditions)
                    .values(**job_values)
                )
                job_rowcount = job_result.rowcount
            if job_rowcount != 1:
                db.rollback()
                return TerminalPersistenceOutcome.LOST_CLAIM
        course_result = db.execute(
            update(Course)
            .where(
                Course.id == course_id,
                Course.is_deleted == False,  # noqa: E712
                Course.status == "processing",
            )
            .values(**course_values)
        )
        if course_result.rowcount != 1:
            db.rollback()
            return TerminalPersistenceOutcome.LOST_CLAIM
        try:
            db.commit()
        except Exception as exc:
            raise _TerminalCommitAcknowledgementUncertain from exc
        return TerminalPersistenceOutcome.PERSISTED

    @staticmethod
    def _terminal_state_is_durable(
        factory,
        *,
        course_id: str,
        job_id: Optional[str],
        course_values: dict,
        job_values: Optional[dict],
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
    ) -> bool:
        """Read a fresh session after an uncertain commit acknowledgement.

        This is intentionally narrow: it accepts only the exact course terminal state
        and, when present, the current owner-matched job terminal state requested by
        this worker. It never exposes database exception details to a client.
        """
        try:
            with factory() as db:
                course = db.get(Course, course_id)
                if (
                    course is None
                    or course.is_deleted
                    or course.status != course_values["status"]
                    or course.stage != course_values["stage"]
                    or course.embedding_status != course_values["embedding_status"]
                    or course.error_code != course_values.get("error_code")
                ):
                    return False
                if not job_id:
                    return True
                job = db.get(ProcessingJob, job_id)
                latest_job = (
                    db.query(ProcessingJob)
                    .filter(
                        ProcessingJob.course_id == course_id,
                        ProcessingJob.job_type == "preprocess",
                    )
                    .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
                    .first()
                )
                if job_values is None:
                    return bool(
                        job
                        and latest_job
                        and latest_job.id == job_id
                        and job.status == JobStatus.RUNNING.value
                        and job.worker_id == worker_id
                        and job.attempts == attempt_number
                    )
                return bool(
                    job
                    and latest_job
                    and latest_job.id == job_id
                    and job.course_id == course_id
                    and job.user_id == course.user_id
                    and job.status == job_values["status"]
                    and job.error_code == job_values.get("error_code")
                )
        except Exception:
            logger.warning(
                "Could not verify uncertain terminal commit acknowledgement for course %s",
                course_id,
            )
            return False

    def _persist_terminal_state(
        self,
        course_id: str,
        *,
        status: str,
        stage: str,
        progress: int,
        embedding_status: str,
        job_id: Optional[str],
        job_succeeded: bool,
        job_error_code: Optional[str] = None,
        job_message: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
        db_session_factory=None,
        **course_fields,
    ) -> TerminalPersistenceOutcome:
        """Atomically publish a terminal state only for the still-live attempt.

        The job claim occurs before the course update. Course deletion cancels active
        jobs before marking the course deleted, so either deletion wins (this claim
        updates zero rows) or this transaction wins and deletion follows it. This works
        with SQLite's writer lock and databases that lock the updated job row.
        """
        if db_session_factory is None:
            from app.services.database import SessionLocal as factory
        else:
            factory = db_session_factory
        now = datetime.utcnow()
        course_values = self._terminal_course_values(
            status=status,
            stage=stage,
            progress=progress,
            embedding_status=embedding_status,
            course_fields=course_fields,
        )
        job_values: Optional[dict] = {
            "status": JobStatus.SUCCEEDED.value if job_succeeded else JobStatus.FAILED.value,
            "active_key": None,
            "worker_id": None,
            "lease_expires_at": None,
            "next_attempt_at": None,
            "updated_at": now,
            "completed_at": now,
        }
        if job_succeeded:
            job_values.update(
                progress=100,
                message="Hoàn thành",
                error_code=None,
                error_message=None,
            )
        else:
            job_values.update(
                error_code=job_error_code,
                error_message=job_message,
                message=job_message or "Xử lý tài liệu thất bại.",
            )
            if worker_id is not None:
                # The durable worker owns retry/final-failure policy. Keep this
                # attempt running while atomically fencing the course failure write.
                job_values = None
        with factory() as db:
            try:
                return self._guarded_terminal_update(
                    db,
                    course_id=course_id,
                    job_id=job_id,
                    job_values=job_values,
                    course_values=course_values,
                    worker_id=worker_id,
                    attempt_number=attempt_number,
                )
            except _TerminalCommitAcknowledgementUncertain:
                try:
                    db.rollback()
                except Exception:
                    pass
                if self._terminal_state_is_durable(
                    factory,
                    course_id=course_id,
                    job_id=job_id,
                    course_values=course_values,
                    job_values=job_values,
                    worker_id=worker_id,
                    attempt_number=attempt_number,
                ):
                    return TerminalPersistenceOutcome.PERSISTED
                logger.warning(
                    "Terminal commit acknowledgement was uncertain for course %s", course_id
                )
                return TerminalPersistenceOutcome.ERROR
            except Exception:
                db.rollback()
                logger.exception("Terminal processing-state persistence failed for course %s", course_id)
                return TerminalPersistenceOutcome.ERROR

    def _persist_persistence_failure(
        self,
        course_id: str,
        job_id: Optional[str],
        db_session_factory,
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
    ) -> TerminalPersistenceOutcome:
        """Fresh-session fallback for a real terminal write failure, never job-only."""
        now = datetime.utcnow()
        course_values = self._terminal_course_values(
            status="failed",
            stage="failed",
            progress=0,
            embedding_status="failed",
            course_fields={
                "error_message": PERSISTENCE_FAILURE_MESSAGE,
                "failure_stage": "persistence_failed",
                "error_code": PERSISTENCE_FAILURE_CODE,
                "can_retry": True,
                "recommended_action": "retry_later",
                "technical_error": "The terminal processing transaction could not be persisted.",
            },
        )
        job_values = {
            "status": JobStatus.FAILED.value,
            "error_code": PERSISTENCE_FAILURE_CODE,
            "error_message": PERSISTENCE_FAILURE_MESSAGE,
            "message": PERSISTENCE_FAILURE_MESSAGE,
            "updated_at": now,
            "completed_at": now,
        }
        with db_session_factory() as db:
            try:
                return self._guarded_terminal_update(
                    db,
                    course_id=course_id,
                    job_id=job_id,
                    job_values=job_values,
                    course_values=course_values,
                    worker_id=worker_id,
                    attempt_number=attempt_number,
                )
            except Exception:
                db.rollback()
                logger.exception("Fallback terminal persistence failed for course %s", course_id)
                return TerminalPersistenceOutcome.ERROR

    @staticmethod
    def _attempt_is_active(
        course_id: str,
        job_id: Optional[str],
        db_session_factory,
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
    ) -> bool:
        """Ensure this worker still owns the live, non-deleted preprocessing attempt."""
        with db_session_factory() as db:
            course = (
                db.query(Course)
                .filter(
                    Course.id == course_id,
                    Course.is_deleted == False,  # noqa: E712
                    Course.status == "processing",
                )
                .first()
            )
            if course is None:
                return False
            if not job_id:
                return True
            job = db.get(ProcessingJob, job_id)
            latest_job = (
                db.query(ProcessingJob)
                .filter(
                    ProcessingJob.course_id == course_id,
                    ProcessingJob.job_type == "preprocess",
                )
                .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
                .first()
            )
            durable_fence = (
                worker_id is None
                or (
                    job is not None
                    and job.worker_id == worker_id
                    and job.attempts == attempt_number
                    and not job.cancel_requested
                    and job.lease_expires_at is not None
                    and job.lease_expires_at > datetime.utcnow()
                )
            )
            return bool(
                job
                and job.status == JobStatus.RUNNING.value
                and job.user_id == course.user_id
                and latest_job
                and latest_job.id == job_id
                and durable_fence
            )

    @staticmethod
    def _course_is_deleted(course_id: str, db_session_factory) -> bool:
        with db_session_factory() as db:
            course = db.get(Course, course_id)
            return course is None or course.is_deleted

    def _resolve_inactive_attempt(
        self, course_id: str, job_id: Optional[str], db_session_factory, vectors_written: bool
    ) -> ProcessingResult:
        """Avoid resurrecting deleted/stale work and clean vectors created by a delete race.

        A worker that lost its claim must not terminalize an old job by itself: the
        current attempt or startup reconciliation owns the coherent course/job repair.
        """
        if vectors_written and self._course_is_deleted(course_id, db_session_factory):
            self.vector_store.delete_course(course_id)
        return ProcessingResult(course_id=course_id, status="failed", chunk_count=0, quality_score=0)

    def _resolve_terminal_outcome(
        self,
        outcome: TerminalPersistenceOutcome,
        *,
        course_id: str,
        job_id: Optional[str],
        db_session_factory,
        vectors_written: bool,
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
    ) -> ProcessingResult:
        """Resolve a failed terminal write without turning a storage error into claim loss."""
        if outcome == TerminalPersistenceOutcome.LOST_CLAIM:
            return self._resolve_inactive_attempt(
                course_id, job_id, db_session_factory, vectors_written
            )

        # The worker did write vectors, but its terminal transaction hit storage. Remove
        # those vectors before the fresh-session fallback so an uncommitted course never
        # appears ready through retrieval.
        if vectors_written:
            if job_id and attempt_number is not None:
                self.vector_store.delete_job_attempt(
                    course_id=course_id,
                    job_id=job_id,
                    attempt_number=attempt_number,
                )
            else:
                self.vector_store.delete_course(course_id)
        fallback = self._persist_persistence_failure(
            course_id,
            job_id,
            db_session_factory,
            worker_id=worker_id,
            attempt_number=attempt_number,
        )
        if fallback == TerminalPersistenceOutcome.PERSISTED:
            return ProcessingResult(
                course_id=course_id,
                status="failed",
                chunk_count=0,
                quality_score=0,
                error=PERSISTENCE_FAILURE_MESSAGE,
            )
        # Do not fail just the job if the fallback storage operation also fails. The
        # retained running attempt is intentionally recoverable by inline startup
        # reconciliation (when explicitly enabled) or the future durable queue.
        return ProcessingResult(
            course_id=course_id,
            status="failed",
            chunk_count=0,
            quality_score=0,
            error=PERSISTENCE_FAILURE_MESSAGE,
        )

    def _generate_course_title(self, all_documents: List[Document]) -> Optional[str]:
        """Best-effort AI-generated short course title from a sample of extracted text.
        Tried exactly once per course (from process_course) — on any failure the caller
        falls back to the document's own filename, like how chat UIs name a conversation
        once and leave the rest to manual rename."""
        try:
            from app.services.llm import LLMService

            sample = "\n\n".join(doc.content for doc in all_documents[:5])[:4000]
            if not sample.strip():
                return None
            result = LLMService().generate_course_title(sample)
            title = (result.title or "").strip()
            return title or None
        except Exception as e:
            logger.error(f"Course title generation failed, falling back to filename: {e}", exc_info=True)
            return None

    @staticmethod
    def _filename_fallback_title(file_path: str) -> str:
        """Clean a filename into a presentable course title: drop the upload-time timestamp
        prefix and the extension (e.g. '1730000000_Virtual Tree.pdf' -> 'Virtual Tree')."""
        filename = os.path.basename(file_path)
        parts = filename.split("_", 1)
        if len(parts) == 2 and parts[0].isdigit():
            filename = parts[1]
        return os.path.splitext(filename)[0].strip() or filename

    def purge_course_storage(self, course_id: str) -> None:
        """Remove on-disk uploads and vector store chunks for a course. Shared by
        single-course delete and full-account deletion so the cleanup logic lives in
        exactly one place."""
        import shutil
        from app.core.config import settings

        upload_dir = os.path.join(settings.UPLOAD_DIR, course_id)
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir, ignore_errors=True)
        self.vector_store.delete_course(course_id)

    def list_saved_course_files(self, course_id: str) -> List[str]:
        """Return regular saved source files without following symlinks outside the course."""
        from app.core.config import settings

        upload_root = Path(settings.UPLOAD_DIR).resolve()
        course_dir = upload_root / course_id
        try:
            resolved_course_dir = course_dir.resolve(strict=True)
        except (FileNotFoundError, OSError):
            return []
        if (
            not resolved_course_dir.is_dir()
            or resolved_course_dir.parent != upload_root
            or course_dir.is_symlink()
        ):
            return []

        file_paths = []
        for entry in sorted(resolved_course_dir.iterdir(), key=lambda item: item.name):
            if entry.is_symlink() or not entry.is_file():
                continue
            try:
                resolved_entry = entry.resolve(strict=True)
            except (FileNotFoundError, OSError):
                continue
            if resolved_entry.parent == resolved_course_dir:
                file_paths.append(str(resolved_entry))
        return file_paths

    def extract_text_from_file(self, file_path: str) -> List[dict]:
        """Compatibility projection of canonical source blocks for legacy callers."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        blocks, _ = self.extract_source(file_path)
        return [
            {
                "content": block.math_latex or block.text or "",
                **({"page": block.page} if block.page is not None else {}),
                "source_file": block.source_file,
                "block_kind": block.kind,
                "document_location": block.location,
                **({"math_latex": block.math_latex} if block.math_latex else {}),
            }
            for block in blocks
            if block.math_latex or block.text
        ]

    def extract_source(self, file_path: str) -> tuple[List[SourceBlock], ExtractionReport]:
        from app.core.config import settings

        ocr = None
        if Path(file_path).suffix.lower() == ".pdf" and settings.PDF_ENABLE_OCR:
            def ocr(image: bytes, page_number: int) -> OCRResult:
                result = self._ocr_image(image)
                return result if isinstance(result, OCRResult) else OCRResult(text=result or "", complete=True)
        return extract_source(
            Path(file_path), ocr_page=ocr,
            ocr_max_pages=settings.PDF_OCR_MAX_PAGES,
            ocr_dpi=settings.PDF_OCR_DPI,
            min_chars=settings.PDF_TEXT_MIN_CHARS_PER_PAGE,
        )

    def _ocr_image(self, image_bytes: bytes) -> OCRResult:
        from app.services.llm import LLMService

        return LLMService().ocr_page_image(image_bytes)

    def _ocr_page(self, doc: "fitz.Document", page_index: int, dpi: int) -> Optional[str]:
        """Render a PDF page to an image and ask OpenRouter vision to transcribe its text.
        Rendering failures remain best-effort, but provider request failures propagate so
        scanned pages cannot silently disappear from an otherwise-ready document."""
        try:
            page = doc[page_index]
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            image_bytes = pix.tobytes("png")

            from app.services.llm import LLMService

            result = LLMService().ocr_page_image(image_bytes)
            return result.text or None
        except (ProviderRequestError, ProviderCircuitOpen):
            raise
        except Exception as e:
            logger.warning(f"OCR fallback failed for page {page_index + 1}: {e}")
            return None

    def clean_text(self, text: str) -> str:
        """Clean extracted text: remove repetitive noise, extra whitespace, Table of Contents leaders."""
        if not text:
            return ""

        # Remove TOC dot leaders (e.g. "Chapter 1 ................ 5")
        text = re.sub(r"\.{4,}\s*\d*", " ", text)
        # Remove repetitive dashes or underscores
        text = re.sub(r"[-_]{4,}", " ", text)
        # Normalize whitespace and newlines
        lines = [line.strip() for line in text.split("\n")]
        # Filter out very short noisy lines (like page numbers standing alone)
        cleaned_lines = [line for line in lines if len(line) > 1 or not line.isdigit()]

        return "\n".join(cleaned_lines).strip()

    def chunk_text(
        self,
        text: str,
        metadata: dict,
        course_id: str,
        page_offsets: Optional[List[Tuple[int, int, int]]] = None,
    ) -> List[Document]:
        """Chunk text with overlap and attach required metadata.

        When `page_offsets` (list of (start, end, page_number) covering `text`) is given —
        used when `text` is the concatenation of every page of one document, so ideas
        split across a page boundary don't get fragmented — each chunk's `page` is derived
        from the offset range it starts in instead of the single `metadata["page"]` value.
        Without it, behaves exactly as a single-page chunk call (`metadata["page"]` for all
        chunks), which is what direct single-page callers still rely on.
        """
        if not text:
            return []

        chunks = []
        source_file = metadata.get("source_file", "unknown")
        default_page = metadata.get("page", 1)

        def _page_for_offset(pos: int) -> int:
            if not page_offsets:
                return default_page
            for p_start, p_end, page_num in page_offsets:
                if p_start <= pos < p_end:
                    return page_num
            return page_offsets[-1][2]

        # Character-boundary chunking with overlap, preferring sentence/newline/space breaks
        start = 0
        text_len = len(text)
        idx = 0

        while start < text_len:
            end = start + self.chunk_size
            if end < text_len:
                split_pos = _find_split_position(text, start, end, self.chunk_size)
                if split_pos != -1:
                    end = split_pos

            chunk_content = text[start:end].strip()
            if chunk_content:
                page = _page_for_offset(start)
                # Chroma ids are collection-global, so include the course while
                # retaining a deterministic source/page/ordinal identity for upsert.
                chunk_id = f"{course_id}_{source_file}_p{page}_c{idx}"
                source_chunk_id = chunk_id

                doc = Document(
                    content=chunk_content,
                    metadata={
                        "page": page,
                        "source_file": source_file,
                        "chunk_id": chunk_id,
                        "source_chunk_id": source_chunk_id,
                        "course_id": course_id,
                    },
                )
                chunks.append(doc)
                idx += 1

            if end >= text_len:
                break
            start = max(end - self.chunk_overlap, start + 1)

        return chunks

    def _strip_repeated_headers_footers(self, pages: List[dict]) -> List[dict]:
        """Detect lines that repeat identically across >=3 pages of the same document
        (running headers/footers) and strip them before chunking. Needs the full page
        list at once (unlike clean_text, which only ever sees one page)."""
        if len(pages) < 3:
            return pages

        line_counts: Counter = Counter()
        for p in pages:
            lines = {line.strip() for line in p["content"].split("\n") if line.strip()}
            for line in lines:
                if len(line) >= 3:
                    line_counts[line] += 1

        repeated = {line for line, count in line_counts.items() if count >= 3}
        if not repeated:
            return pages

        result = []
        for p in pages:
            kept = [line for line in p["content"].split("\n") if line.strip() not in repeated]
            result.append({**p, "content": "\n".join(kept)})
        return result

    def _is_low_information(self, text: str) -> bool:
        """A chunk is noise if it's too short or mostly non-alphanumeric (leftover
        table borders, decorative characters, stray symbols)."""
        stripped = text.strip()
        if len(stripped.split()) < 15:
            return True
        alnum_count = sum(1 for c in stripped if c.isalnum())
        return len(stripped) > 0 and (alnum_count / len(stripped)) < 0.5

    def extract_and_chunk_file(
        self, path: str, course_id: str, report_sink: Optional[List[ExtractionReport]] = None
    ) -> List[Document]:
        """Extract canonical blocks, remove repeated page noise, and create grounded chunks."""
        blocks, report = self.extract_source(path)
        if report_sink is not None:
            report_sink.append(report)
        pdf_paragraphs = [block for block in blocks if block.page is not None and block.kind == "paragraph"]
        if pdf_paragraphs:
            page_rows = [
                {"content": block.text or "", "page": block.page, "source_file": block.source_file}
                for block in pdf_paragraphs
            ]
            cleaned_by_page = {
                row["page"]: row["content"] for row in self._strip_repeated_headers_footers(page_rows)
            }
            blocks = [
                block.model_copy(update={"text": cleaned_by_page.get(block.page, block.text)})
                if block.page is not None and block.kind == "paragraph"
                else block
                for block in blocks
            ]
        cleaned_content = {
            id(block): self.clean_text(block.math_latex or block.text or "") for block in blocks
        }
        inline_math_roots = {
            block.location.split("/fragment[", 1)[0]
            for block in blocks
            if block.kind == "math" and "/fragment[" in block.location
        }
        ordinary_usable = [
            content for block in blocks
            if block.kind == "paragraph"
            and (content := cleaned_content[id(block)])
            and (not self._is_low_information(content) or len(content.split()) >= 5)
        ]
        has_structured = any(block.kind in {"table", "math"} for block in blocks)
        documents: List[Document] = []
        import hashlib
        for block_order, block in enumerate(blocks):
            content = cleaned_content[id(block)]
            if not content:
                continue
            paragraph_root = block.location.split("/fragment[", 1)[0]
            weak_paragraph = (
                block.kind == "paragraph"
                and self._is_low_information(content)
                and len(content.split()) < 5
                and paragraph_root not in inline_math_roots
            )
            if weak_paragraph and (ordinary_usable or has_structured):
                continue
            metadata = {
                "source_file": block.source_file,
                "block_kind": block.kind,
                "document_location": block.location,
                "block_order": block_order,
            }
            if block.page is not None:
                metadata["page"] = block.page
            if block.math_latex:
                metadata["math_latex"] = block.math_latex
            chunks = self.chunk_text(content, metadata, course_id)
            digest = hashlib.sha256(block.location.encode("utf-8")).hexdigest()[:12]
            for ordinal, chunk in enumerate(chunks):
                chunk_id = f"{course_id}_{block.source_file}_{digest}_c{ordinal}"
                chunk.metadata.update(metadata)
                chunk.metadata["is_front_matter"] = _is_front_matter(content)
                chunk.metadata["within_block_order"] = ordinal
                if block.page is None:
                    chunk.metadata.pop("page", None)
                chunk.metadata["chunk_id"] = chunk_id
                chunk.metadata["source_chunk_id"] = chunk_id
            documents.extend(chunks)
        return documents

    def process_course(
        self,
        course_id: str,
        file_paths: List[str],
        db_session_factory=None,
        job_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
        progress_callback: Optional[Callable[[], bool]] = None,
    ) -> ProcessingResult:
        """
        1. Extract text từ files (PDF/DOCX/TXT)
        2. Clean text: remove headers, footers, TOC noise
        3. Chunk text với overlap
        4. Generate embeddings
        5. Store in Chroma
        """
        logger.info("Starting document processing pipeline for course %s", course_id)
        if db_session_factory is None:
            from app.services.database import SessionLocal as db_session_factory

        if job_id and worker_id is None:
            with db_session_factory() as db:
                if not mark_job_running(db, job_id, "Đang phân tích tài liệu"):
                    return ProcessingResult(course_id=course_id, status="failed", chunk_count=0, quality_score=0)

        if not self._attempt_is_active(
            course_id,
            job_id,
            db_session_factory,
            worker_id=worker_id,
            attempt_number=attempt_number,
        ):
            return self._resolve_inactive_attempt(course_id, job_id, db_session_factory, False)

        try:
            if not self._update_course_db(
                course_id, status="processing", stage="extracting", progress=20,
                job_id=job_id, worker_id=worker_id, attempt_number=attempt_number,
                db_session_factory=db_session_factory,
            ):
                return self._resolve_inactive_attempt(
                    course_id, job_id, db_session_factory, False
                )
            if progress_callback and not progress_callback():
                return ProcessingResult(
                    course_id=course_id, status="cancelled", chunk_count=0, quality_score=0
                )
            _require_provider_preflight()
            all_documents: List[Document] = []
            extraction_reports: List[ExtractionReport] = []
            try:
                for path in file_paths:
                    all_documents.extend(self.extract_and_chunk_file(path, course_id, extraction_reports))
                if not all_documents:
                    raise ValueError("No valid text could be extracted from uploaded files.")
            except (ProviderRequestError, ProviderCircuitOpen):
                raise
            except Exception as exc:
                user_message, extraction_code, recommended_action = _extraction_failure_details(exc)
                terminal_outcome = self._persist_terminal_state(
                    course_id, status="failed", stage="failed", progress=0, embedding_status="failed",
                    job_id=job_id, job_succeeded=False,
                    job_error_code=extraction_code, job_message=user_message,
                    worker_id=worker_id, attempt_number=attempt_number,
                    error_message=user_message, failure_stage="extraction_failed",
                    error_code=extraction_code, can_retry=True,
                    recommended_action=recommended_action,
                    technical_error=str(exc)[:1000],
                    db_session_factory=db_session_factory,
                )
                if terminal_outcome != TerminalPersistenceOutcome.PERSISTED:
                    return self._resolve_terminal_outcome(
                        terminal_outcome,
                        course_id=course_id,
                        job_id=job_id,
                        db_session_factory=db_session_factory,
                        vectors_written=False,
                        worker_id=worker_id,
                        attempt_number=attempt_number,
                    )
                logger.error("Document extraction failed for course %s: %s", course_id, exc)
                return ProcessingResult(course_id=course_id, status="failed", chunk_count=0, quality_score=0, error=user_message)

            if not self._update_course_db(
                course_id, status="processing", stage="chunking", progress=50,
                job_id=job_id, worker_id=worker_id, attempt_number=attempt_number,
                db_session_factory=db_session_factory,
            ):
                return self._resolve_inactive_attempt(
                    course_id, job_id, db_session_factory, False
                )
            if progress_callback and not progress_callback():
                return ProcessingResult(
                    course_id=course_id, status="cancelled", chunk_count=0, quality_score=0
                )
            if not self._update_course_db(
                course_id, status="processing", stage="embedding", progress=75,
                job_id=job_id, worker_id=worker_id, attempt_number=attempt_number,
                db_session_factory=db_session_factory,
            ):
                return self._resolve_inactive_attempt(
                    course_id, job_id, db_session_factory, False
                )
            if progress_callback and not progress_callback():
                return ProcessingResult(
                    course_id=course_id, status="cancelled", chunk_count=0, quality_score=0
                )
            if not self._attempt_is_active(
                course_id,
                job_id,
                db_session_factory,
                worker_id=worker_id,
                attempt_number=attempt_number,
            ):
                return self._resolve_inactive_attempt(course_id, job_id, db_session_factory, False)
            embedding_provider = "openrouter"
            if job_id and attempt_number is not None:
                for document in all_documents:
                    document.metadata["processing_job_id"] = job_id
                    document.metadata["processing_attempt"] = attempt_number
            self.vector_store.add_documents(all_documents, course_id=course_id, provider=embedding_provider)
            if progress_callback and not progress_callback():
                return ProcessingResult(
                    course_id=course_id, status="cancelled", chunk_count=0, quality_score=0
                )
            if not self._attempt_is_active(
                course_id,
                job_id,
                db_session_factory,
                worker_id=worker_id,
                attempt_number=attempt_number,
            ):
                return self._resolve_inactive_attempt(course_id, job_id, db_session_factory, True)
            course_title = self._generate_course_title(all_documents) or self._filename_fallback_title(file_paths[0])
            import json
            aggregate_total = (
                sum(report.total_pages for report in extraction_reports)
                if extraction_reports and all(report.total_pages is not None for report in extraction_reports)
                else None
            )
            extraction_coverage = {
                "version": 2,
                "document_count": len(extraction_reports),
                "total_pages": aggregate_total,
                "extracted_pages": sum(len(report.extracted_pages) for report in extraction_reports),
                "ocr_pages": sum(len(report.ocr_pages) for report in extraction_reports),
                "skipped_pages": sum(len(report.skipped_pages) for report in extraction_reports),
                "damaged_pages": sum(len(report.damaged_pages) for report in extraction_reports),
                "blank_pages": sum(len(report.blank_pages) for report in extraction_reports),
                "warning_count": sum(len(report.warnings) for report in extraction_reports),
                "complete": all(report.complete for report in extraction_reports),
                "extraction_complete": all(report.complete for report in extraction_reports),
                "indexed_chunk_count": len(all_documents),
                "faithfulness": None,
                "faithfulness_status": "not_evaluated",
                "legacy_quality_score_label": "extraction completeness compatibility",
            }
            # Compatibility only: this binary value reflects extraction completion, never factual accuracy.
            quality_score = _legacy_extraction_compatibility_score(extraction_reports)
            terminal_outcome = self._persist_terminal_state(
                course_id, status="ready", stage="completed", progress=100, embedding_status="completed",
                job_id=job_id, job_succeeded=True, chunk_count=len(all_documents), quality_score=quality_score,
                worker_id=worker_id, attempt_number=attempt_number,
                name=course_title, embedding_provider=embedding_provider,
                extraction_coverage_json=json.dumps(extraction_coverage), db_session_factory=db_session_factory,
            )
            if terminal_outcome != TerminalPersistenceOutcome.PERSISTED:
                return self._resolve_terminal_outcome(
                    terminal_outcome,
                    course_id=course_id,
                    job_id=job_id,
                    db_session_factory=db_session_factory,
                    vectors_written=True,
                    worker_id=worker_id,
                    attempt_number=attempt_number,
                )
            logger.info("Successfully processed course %s: %s chunks created.", course_id, len(all_documents))
            return ProcessingResult(course_id=course_id, status="ready", chunk_count=len(all_documents), quality_score=quality_score)

        except ProviderCircuitOpen:
            raise
        except ProviderRequestError as exc:
            failure = exc.failure
            failure_status = "paused_due_to_quota" if failure.code in {
                ProviderErrorCode.KEY_LIMIT_EXCEEDED, ProviderErrorCode.CREDITS_EXHAUSTED,
            } else "failed"
            terminal_outcome = self._persist_terminal_state(
                course_id, status=failure_status, stage="failed", progress=0, embedding_status="failed",
                job_id=job_id, job_succeeded=False, job_error_code=str(failure.code), job_message=failure.user_message,
                worker_id=worker_id, attempt_number=attempt_number,
                error_message=failure.user_message, failure_stage="embedding_failed", error_code=str(failure.code),
                can_retry=failure.can_retry, recommended_action=failure.recommended_action,
                technical_error=failure.technical_message, db_session_factory=db_session_factory,
            )
            if terminal_outcome != TerminalPersistenceOutcome.PERSISTED:
                return self._resolve_terminal_outcome(
                    terminal_outcome,
                    course_id=course_id,
                    job_id=job_id,
                    db_session_factory=db_session_factory,
                    vectors_written=False,
                    worker_id=worker_id,
                    attempt_number=attempt_number,
                )
            logger.error("Provider failure processing course %s: %s", course_id, failure.code)
            return ProcessingResult(course_id=course_id, status=failure_status, chunk_count=0, quality_score=0, error=failure.user_message)
        except Exception as exc:
            user_message = "Không thể hoàn tất xử lý tài liệu. Vui lòng thử lại sau."
            terminal_outcome = self._persist_terminal_state(
                course_id, status="failed", stage="failed", progress=0, embedding_status="failed",
                job_id=job_id, job_succeeded=False, job_error_code="DOCUMENT_PROCESSING_FAILED", job_message=user_message,
                worker_id=worker_id, attempt_number=attempt_number,
                error_message=user_message, failure_stage="embedding_failed", error_code="DOCUMENT_PROCESSING_FAILED",
                can_retry=True, recommended_action="retry_later", technical_error=str(exc)[:1000],
                db_session_factory=db_session_factory,
            )
            if terminal_outcome != TerminalPersistenceOutcome.PERSISTED:
                return self._resolve_terminal_outcome(
                    terminal_outcome,
                    course_id=course_id,
                    job_id=job_id,
                    db_session_factory=db_session_factory,
                    vectors_written=False,
                    worker_id=worker_id,
                    attempt_number=attempt_number,
                )
            logger.error("Document processing failed for course %s: %s", course_id, exc)
            return ProcessingResult(course_id=course_id, status="failed", chunk_count=0, quality_score=0, error=user_message)


def get_document_processor() -> DocumentProcessor:
    """Get DocumentProcessor instance initialized with singleton VectorStore."""
    from app.services.vector_store import get_vector_store
    return DocumentProcessor(vector_store=get_vector_store())
