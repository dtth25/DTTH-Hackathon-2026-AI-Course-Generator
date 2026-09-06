"""Private, durable checkpoints for resumable Book generation.

Checkpoint files are deliberately outside published artifact directories.  A render
promotion may replace a version directory, while validated content must survive a
failed attempt and remain available to the next owner of the same logical version.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import update

from app.models.course import Course
from app.models.processing_job import JobStatus, ProcessingJob
from app.models.provider_call import BookBudget
from app.schemas.generator_output import BookChapterContent, BookChapterPlan, BookOutline
from app.services.versioning import migrate_legacy_artifact_metadata


CHECKPOINT_SCHEMA_REVISION = "book-checkpoint-v1"
BOOK_PROMPT_REVISION = "book-outline-chapter-v1"
ALLOCATION_REVISION = "evidence-allocation-v1"
RENDER_REVISION = "book-pdf-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
logger = logging.getLogger(__name__)


class CheckpointRejected(ValueError):
    """A checkpoint exists but belongs to a different immutable identity."""


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def options_digest(options: dict[str, Any]) -> str:
    return canonical_digest(options)


def checkpoint_key(
    source_digest: str,
    version_id: str,
    model: str,
    options_digest: str,
    prompt_revision: str,
    policy_revision: str = "",
) -> str:
    """Return a stable, opaque key for content reusable by one owned version."""

    return canonical_digest(
        {
            "schema_revision": CHECKPOINT_SCHEMA_REVISION,
            "source_digest": source_digest,
            "version_id": version_id,
            "model": model,
            "options_digest": options_digest,
            "prompt_revision": prompt_revision,
            "policy_revision": policy_revision,
        }
    )


def plan_digest(plan: BookChapterPlan) -> str:
    return canonical_digest(plan.model_dump(mode="json"))


class CheckpointIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_revision: str = CHECKPOINT_SCHEMA_REVISION
    course_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_revision: int = Field(ge=1)
    model: str = Field(min_length=1)
    options_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_revision: str = Field(min_length=1)
    policy_revision: str = Field(min_length=1)
    budget_id: str = Field(min_length=1)

    @property
    def key(self) -> str:
        return checkpoint_key(
            self.source_digest,
            self.version_id,
            self.model,
            self.options_digest,
            self.prompt_revision,
            self.policy_revision,
        )


class CheckpointRecord(BaseModel):
    """Serialized record with a unique token for cross-transaction recovery."""

    promotion_token: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        pattern=r"^[0-9a-f]{32}$",
    )


class OutlineRecord(CheckpointRecord):
    identity: CheckpointIdentity
    evidence_ids: list[str] = Field(min_length=1)
    outline_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    outline: BookOutline

    @model_validator(mode="after")
    def digest_matches(self):
        if canonical_digest(self.outline.model_dump(mode="json")) != self.outline_digest:
            raise ValueError("Outline digest mismatch")
        return self


class ManifestRecord(CheckpointRecord):
    identity: CheckpointIdentity
    outline_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    allocation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    allocation_revision: str = Field(min_length=1)
    plan_digests: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    render_revision: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_plan_digests(self):
        if any(not _SHA256.fullmatch(item) for item in self.plan_digests):
            raise ValueError("Invalid chapter plan digest")
        return self


class ChapterRecord(CheckpointRecord):
    identity: CheckpointIdentity
    outline_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    allocation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    chapter_index: int = Field(ge=0)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_ids: list[str] = Field(min_length=1)
    chapter: BookChapterContent


class BookCheckpointStore:
    """Typed checkpoint IO with exact identity and evidence validation."""

    def __init__(self, upload_dir: str, identity: CheckpointIdentity):
        self.identity = identity
        safe_version = _safe_component(identity.version_id)
        directory = (
            Path(upload_dir)
            / identity.course_id
            / "artifacts"
            / "book"
            / ".checkpoints"
            / safe_version
            / identity.key
        )
        if os.name == "nt" and len(str(directory.resolve())) >= 220:
            directory = Path("\\\\?\\" + str(directory.resolve()))
        self.directory = directory

    def _load(self, name: str, model_type, *, reject_incompatible: bool = False):
        path = self.directory / name
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            record = model_type.model_validate(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, TypeError):
            return None
        if record.identity != self.identity:
            if reject_incompatible:
                raise CheckpointRejected("Checkpoint identity does not match this Book version")
            return None
        return record

    def load_outline(self, valid_evidence_ids: Iterable[str]) -> BookOutline | None:
        record = self._load("outline.json", OutlineRecord)
        if record is None or not _evidence_is_valid(record.evidence_ids, valid_evidence_ids):
            return None
        return record.outline

    def load_manifest(
        self,
        *,
        outline_digest: str,
        allocation_digest: str,
        plan_digests: list[str],
        valid_evidence_ids: Iterable[str],
    ) -> ManifestRecord | None:
        record = self._load("manifest.json", ManifestRecord, reject_incompatible=True)
        if record is None:
            return None
        if (
            record.outline_digest != outline_digest
            or record.allocation_digest != allocation_digest
            or record.allocation_revision != ALLOCATION_REVISION
            or record.plan_digests != plan_digests
            or not _evidence_is_valid(record.evidence_ids, valid_evidence_ids)
        ):
            return None
        return record

    def ready_manifest(
        self, allocation_digest: str, valid_evidence_ids: Iterable[str]
    ) -> ManifestRecord | None:
        """Validate the complete private identity used by an owned ready-cache hit."""

        outline_record = self._load("outline.json", OutlineRecord)
        manifest = self._load("manifest.json", ManifestRecord)
        if outline_record is None or manifest is None:
            return None
        if (
            manifest.outline_digest != outline_record.outline_digest
            or manifest.allocation_digest != allocation_digest
            or manifest.allocation_revision != ALLOCATION_REVISION
            or manifest.render_revision != RENDER_REVISION
            or manifest.plan_digests
            != [plan_digest(plan) for plan in outline_record.outline.chapters]
            or not _evidence_is_valid(outline_record.evidence_ids, valid_evidence_ids)
            or not _evidence_is_valid(manifest.evidence_ids, valid_evidence_ids)
        ):
            return None
        return manifest

    def load_chapter(
        self,
        index: int,
        *,
        outline_digest: str,
        allocation_digest: str,
        expected_plan_digest: str,
        valid_evidence_ids: Iterable[str],
        validator: Callable[[BookChapterContent], None] | None = None,
    ) -> BookChapterContent | None:
        record = self._load(f"chapter-{index + 1}.json", ChapterRecord)
        if record is None:
            return None
        if (
            record.chapter_index != index
            or record.outline_digest != outline_digest
            or record.allocation_digest != allocation_digest
            or record.plan_digest != expected_plan_digest
            or not _evidence_is_valid(record.evidence_ids, valid_evidence_ids)
            or not set(record.chapter.source_chunk_ids).issubset(set(record.evidence_ids))
        ):
            return None
        try:
            if validator:
                validator(record.chapter)
        except Exception:
            return None
        return record.chapter

    def save_outline(self, outline: BookOutline, evidence_ids: list[str], fence) -> bool:
        record = OutlineRecord(
            identity=self.identity,
            evidence_ids=_normalized_evidence(evidence_ids),
            outline_digest=canonical_digest(outline.model_dump(mode="json")),
            outline=outline,
        )
        return self._save("outline.json", record, fence)

    def save_manifest(
        self,
        *,
        outline_digest: str,
        allocation_digest: str,
        plans: list[BookChapterPlan],
        evidence_ids: list[str],
        fence,
    ) -> bool:
        record = ManifestRecord(
            identity=self.identity,
            outline_digest=outline_digest,
            allocation_digest=allocation_digest,
            allocation_revision=ALLOCATION_REVISION,
            plan_digests=[plan_digest(item) for item in plans],
            evidence_ids=_normalized_evidence(evidence_ids),
            render_revision=RENDER_REVISION,
        )
        return self._save("manifest.json", record, fence)

    def save_chapter(
        self,
        index: int,
        chapter: BookChapterContent,
        *,
        outline_digest: str,
        allocation_digest: str,
        expected_plan_digest: str,
        evidence_ids: list[str],
        fence,
    ) -> bool:
        evidence = _normalized_evidence(evidence_ids)
        if not set(chapter.source_chunk_ids).issubset(set(evidence)):
            raise ValueError("Chapter cites evidence outside its checkpoint envelope")
        record = ChapterRecord(
            identity=self.identity,
            outline_digest=outline_digest,
            allocation_digest=allocation_digest,
            chapter_index=index,
            plan_digest=expected_plan_digest,
            evidence_ids=evidence,
            chapter=chapter,
        )
        return self._save(f"chapter-{index + 1}.json", record, fence)

    def _save(self, name: str, record: BaseModel, fence) -> bool:
        payload = record.model_dump(mode="json")
        # Revalidate the exact JSON shape before it reaches durable storage.
        type(record).model_validate(payload)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / name
        # Keep the same-directory temporary name short enough for Windows' common
        # MAX_PATH configuration; the directory already carries two SHA-256 identities.
        tmp = self.directory / f".{uuid.uuid4().hex[:8]}.tmp"
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            return bool(fence(tmp, path))
        finally:
            tmp.unlink(missing_ok=True)


def checkpoint_write_fence(
    db_session_factory,
    identity: CheckpointIdentity,
    *,
    job_id: str | None,
    worker_id: str | None,
    attempt_number: int | None,
):
    """Build a J→C fenced replacement callback for one worker attempt."""

    def lock_current_owner(db) -> bool:
        now = datetime.utcnow()
        if db.bind is not None and db.bind.dialect.name == "sqlite":
            from sqlalchemy import text

            db.execute(text("BEGIN IMMEDIATE"))
        job = None
        if job_id:
            guarded = db.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.id == job_id,
                    ProcessingJob.course_id == identity.course_id,
                    ProcessingJob.status == JobStatus.RUNNING.value,
                    ProcessingJob.worker_id == worker_id,
                    ProcessingJob.attempts == attempt_number,
                    ProcessingJob.cancel_requested.is_(False),
                    ProcessingJob.lease_expires_at > now,
                )
                .values(updated_at=ProcessingJob.updated_at)
            )
            if guarded.rowcount != 1:
                return False
            job = db.get(ProcessingJob, job_id)
            payload = job.payload_json if job and isinstance(job.payload_json, dict) else {}
            if (
                job is None
                or payload.get("version_id") != identity.version_id
                or payload.get("budget_id") != identity.budget_id
            ):
                return False
        query = db.query(Course).filter(Course.id == identity.course_id)
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        course = query.first()
        budget = db.get(BookBudget, identity.budget_id)
        if (
            course is None
            or course.is_deleted
            or budget is None
            or budget.course_id != identity.course_id
            or budget.version_id != identity.version_id
            or budget.user_id != course.user_id
            or (job_id and job.user_id != course.user_id)
        ):
            return False
        meta, _ = migrate_legacy_artifact_metadata(_metadata(course))
        version = (
            meta.get("study_pack", {})
            .get("artifacts", {})
            .get("book", {})
            .get("versions", {})
            .get(identity.version_id)
        )
        return isinstance(version, dict) and version.get("status") == "processing"

    def recover_failed_promotion(
        target: Path, backup: Path, promotion_token: str
    ) -> None:
        """Restore only while holding a fresh fence and still owning our bytes."""

        recovery = db_session_factory()
        try:
            if not lock_current_owner(recovery):
                recovery.rollback()
                return
            try:
                current_token = json.loads(
                    target.read_text(encoding="utf-8")
                ).get("promotion_token")
            except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
                current_token = None
            if current_token == promotion_token:
                if backup.exists():
                    os.replace(backup, target)
                else:
                    target.unlink(missing_ok=True)
            recovery.commit()
        except Exception:
            recovery.rollback()
            logger.exception("Checkpoint recovery failed after database commit error")
        finally:
            recovery.close()

    def replace(tmp: Path, target: Path) -> bool:
        db = db_session_factory()
        backup = target.with_name(f".{uuid.uuid4().hex[:8]}.bak")
        promoted = False
        promotion_token = json.loads(tmp.read_text(encoding="utf-8")).get(
            "promotion_token"
        )
        if not isinstance(promotion_token, str):
            raise ValueError("Checkpoint promotion token is missing")
        try:
            if not lock_current_owner(db):
                db.rollback()
                return False
            if target.exists():
                os.replace(target, backup)
            os.replace(tmp, target)
            promoted = True
            try:
                db.commit()
            except Exception:
                db.rollback()
                recover_failed_promotion(target, backup, promotion_token)
                try:
                    backup.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Unable to remove failed checkpoint backup %s", backup.name
                    )
                raise
        except Exception:
            if not promoted:
                try:
                    if backup.exists():
                        os.replace(backup, target)
                finally:
                    db.rollback()
            raise
        finally:
            db.close()
        try:
            backup.unlink(missing_ok=True)
        except OSError:
            logger.warning("Unable to remove committed checkpoint backup %s", backup.name)
        return True

    return replace


def remove_book_checkpoints(upload_dir: str, course_id: str, version_id: str) -> None:
    import shutil

    root = Path(upload_dir) / course_id / "artifacts" / "book" / ".checkpoints"
    shutil.rmtree(root / _safe_component(version_id), ignore_errors=True)


def _safe_component(value: str) -> str:
    if not value or Path(value).name != value or value in {".", ".."}:
        raise ValueError("Invalid checkpoint path component")
    return re.sub(r"[^A-Za-z0-9._-]", "-", value)


def _metadata(course: Course) -> dict[str, Any]:
    raw = course.metadata_json or "{}"
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _normalized_evidence(values: Iterable[str]) -> list[str]:
    result = list(dict.fromkeys(item for item in values if isinstance(item, str) and item))
    if not result:
        raise ValueError("Checkpoint evidence must not be empty")
    return result


def _evidence_is_valid(saved: Iterable[str], current: Iterable[str]) -> bool:
    saved_set = set(saved)
    return bool(saved_set) and saved_set.issubset(set(current))
