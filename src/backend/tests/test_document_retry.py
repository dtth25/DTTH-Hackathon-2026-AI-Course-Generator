"""Persistence tests for document processing jobs and saved-document retries."""

import os
from pathlib import Path
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.database import SessionLocal
from app.services.job_service import (
    create_job,
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
)
from app.services.provider_errors import ProviderErrorCode
from app.services.provider_health import ProviderHealth


def _auth_headers(client, email: str) -> dict[str, str]:
    register = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123", "full_name": "Retry Test"},
    )
    assert register.status_code == 201
    verified = client.post(
        "/api/auth/verify-email",
        json={"email": email, "code": "000000"},
    )
    assert verified.status_code == 200
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


@pytest.fixture
def owner_headers(client):
    return _auth_headers(client, "retry-owner@example.com")


@pytest.fixture
def other_headers(client):
    return _auth_headers(client, "retry-other@example.com")


def _course_for(client, headers, *, status: str, with_file: bool) -> Course:
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        course = Course(
            user_id=user_id,
            filenames=["source.txt"],
            status=status,
            stage="failed" if status == "failed" else "ready",
            error_message="Dịch vụ AI đang tạm dừng vì hạn mức sử dụng."
            if status == "failed"
            else None,
        )
        db.add(course)
        db.commit()
        db.refresh(course)
        db.expunge(course)
    if with_file:
        course_dir = Path(settings.UPLOAD_DIR) / course.id
        course_dir.mkdir(parents=True, exist_ok=True)
        (course_dir / "source.txt").write_text(
            "Grounded retry fixture", encoding="utf-8"
        )
    return course


@pytest.fixture
def failed_course_with_file(client, owner_headers):
    return _course_for(client, owner_headers, status="failed", with_file=True)


@pytest.fixture
def failed_course_without_file(client, owner_headers):
    return _course_for(client, owner_headers, status="failed", with_file=False)


@pytest.fixture
def ready_course(client, owner_headers):
    return _course_for(client, owner_headers, status="ready", with_file=True)


def test_owner_can_retry_failed_course_from_saved_file(
    client, failed_course_with_file, owner_headers, monkeypatch
):
    scheduled = []
    monkeypatch.setattr(
        "app.routers.documents._schedule_processing",
        lambda *args: scheduled.append(args),
    )
    response = client.post(
        f"/api/documents/{failed_course_with_file.id}/retry", headers=owner_headers
    )
    assert response.status_code == 202
    body = response.json()
    assert body["document_id"] == failed_course_with_file.id
    assert body["status"] == "processing"
    assert body["job_id"]
    assert len(scheduled) == 1


def test_other_user_cannot_retry_course(client, failed_course_with_file, other_headers):
    response = client.post(
        f"/api/documents/{failed_course_with_file.id}/retry", headers=other_headers
    )
    assert response.status_code == 404


def test_processing_or_ready_course_rejects_retry(client, ready_course, owner_headers):
    response = client.post(
        f"/api/documents/{ready_course.id}/retry", headers=owner_headers
    )
    assert response.status_code == 409


def test_retry_requires_saved_source_file(
    client, failed_course_without_file, owner_headers
):
    response = client.post(
        f"/api/documents/{failed_course_without_file.id}/retry", headers=owner_headers
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SOURCE_FILE_MISSING"


def test_job_status_is_visible_only_to_its_owner(
    client, failed_course_with_file, owner_headers, other_headers, monkeypatch
):
    monkeypatch.setattr("app.routers.documents._schedule_processing", lambda *args: None)
    retry = client.post(
        f"/api/documents/{failed_course_with_file.id}/retry", headers=owner_headers
    )
    assert retry.status_code == 202
    job_id = retry.json()["job_id"]

    owner_response = client.get(f"/api/jobs/{job_id}", headers=owner_headers)
    assert owner_response.status_code == 200
    assert owner_response.json()["document_id"] == failed_course_with_file.id
    assert "technical_error" not in owner_response.json()

    other_response = client.get(f"/api/jobs/{job_id}", headers=other_headers)
    assert other_response.status_code == 404


def test_admin_retry_keeps_job_owned_by_course_owner(
    client, failed_course_with_file, owner_headers, monkeypatch
):
    admin_headers = _auth_headers(client, "retry-admin@example.com")
    admin_id = client.get("/api/auth/me", headers=admin_headers).json()["id"]
    with SessionLocal() as db:
        admin = db.get(User, admin_id)
        admin.role = "admin"
        db.commit()

    monkeypatch.setattr("app.routers.documents._schedule_processing", lambda *args: None)
    response = client.post(
        f"/api/documents/{failed_course_with_file.id}/retry", headers=admin_headers
    )
    assert response.status_code == 202
    with SessionLocal() as db:
        job = db.get(ProcessingJob, response.json()["job_id"])
        course = db.get(Course, failed_course_with_file.id)
        assert job.user_id == course.user_id
        assert course.status == "processing"


def test_scheduling_failure_marks_course_and_job_retryable(
    client, failed_course_with_file, owner_headers, monkeypatch
):
    def scheduling_failure(*args):
        raise RuntimeError("background registration failed")

    monkeypatch.setattr("app.routers.documents._schedule_processing", scheduling_failure)
    response = client.post(
        f"/api/documents/{failed_course_with_file.id}/retry", headers=owner_headers
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DOCUMENT_SCHEDULING_FAILED"
    with SessionLocal() as db:
        course = db.get(Course, failed_course_with_file.id)
        job = (
            db.query(ProcessingJob)
            .filter_by(course_id=failed_course_with_file.id)
            .one()
        )
        assert course.status == "failed"
        assert course.can_retry is True
        assert job.status == "failed"


def test_retry_compare_and_swap_schedules_exactly_one_preprocess_job(
    client, failed_course_with_file, owner_headers, monkeypatch
):
    scheduled = []
    monkeypatch.setattr(
        "app.routers.documents._schedule_processing", lambda *args: scheduled.append(args)
    )

    first = client.post(
        f"/api/documents/{failed_course_with_file.id}/retry", headers=owner_headers
    )
    second = client.post(
        f"/api/documents/{failed_course_with_file.id}/retry", headers=owner_headers
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert len(scheduled) == 1
    with SessionLocal() as db:
        active_jobs = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.course_id == failed_course_with_file.id,
                ProcessingJob.status.in_(["queued", "running"]),
            )
            .count()
        )
        assert active_jobs == 1


def _health(*, available: bool, code: str | None = None) -> ProviderHealth:
    return ProviderHealth(
        available=available,
        error_code=code,
        checked_at=datetime.now(UTC),
        limit=None,
        limit_remaining=None,
        limit_reset=None,
        content_model_available=available,
        embedding_model_available=available,
    )


def _processor_course() -> tuple[Course, str]:
    db = SessionLocal()
    try:
        user = User(email="processor-owner@example.com", hashed_password="not-used")
        db.add(user)
        db.flush()
        course = Course(user_id=user.id, filenames=["source.txt"])
        db.add(course)
        db.commit()
        db.refresh(course)
        return course, user.id
    finally:
        db.close()


def test_preflight_retries_transient_failure_without_sleep(monkeypatch):
    from app.services.document_processor import DocumentProcessor

    course, _ = _processor_course()
    calls = []
    states = iter(
        [
            _health(available=False, code=ProviderErrorCode.RATE_LIMITED),
            _health(available=False, code=ProviderErrorCode.TIMEOUT),
            _health(available=True),
        ]
    )
    monkeypatch.setattr(
        "app.services.document_processor.get_openrouter_health",
        lambda **_: (calls.append(True), next(states))[1],
    )
    sleeps = []
    monkeypatch.setattr("app.services.document_processor.time.sleep", sleeps.append)
    processor = DocumentProcessor(vector_store=None)
    monkeypatch.setattr(processor, "extract_and_chunk_file", lambda *args: [])

    result = processor.process_course(course.id, ["source.txt"], SessionLocal)

    assert len(calls) == 3
    assert sleeps == [0.25, 0.5]
    assert result.status == "failed"
    with SessionLocal() as db:
        persisted = db.get(Course, course.id)
        assert persisted.error_code == "DOCUMENT_TEXT_EXTRACTION_FAILED"


def test_quota_preflight_runs_once_and_returns_paused_status(monkeypatch):
    from app.services.document_processor import DocumentProcessor

    course, _ = _processor_course()
    calls = []
    monkeypatch.setattr(
        "app.services.document_processor.get_openrouter_health",
        lambda **_: (calls.append(True), _health(available=False, code=ProviderErrorCode.KEY_LIMIT_EXCEEDED))[1],
    )
    monkeypatch.setattr("app.services.document_processor.time.sleep", lambda _: pytest.fail("no retry"))

    result = DocumentProcessor(vector_store=None).process_course(course.id, ["source.txt"], SessionLocal)

    assert len(calls) == 1
    assert result.status == "paused_due_to_quota"
    with SessionLocal() as db:
        assert db.get(Course, course.id).status == "paused_due_to_quota"


def test_empty_extraction_is_an_extraction_failure(monkeypatch):
    from app.services.document_processor import DocumentProcessor

    course, _ = _processor_course()
    processor = DocumentProcessor(vector_store=None)
    monkeypatch.setattr(processor, "extract_and_chunk_file", lambda *args: [])

    result = processor.process_course(course.id, ["source.txt"], SessionLocal)

    assert result.status == "failed"
    with SessionLocal() as db:
        persisted = db.get(Course, course.id)
        assert persisted.failure_stage == "extraction_failed"
        assert persisted.error_code == "DOCUMENT_TEXT_EXTRACTION_FAILED"
        assert persisted.recommended_action == "upload_clearer_pdf"


def test_saved_file_discovery_rejects_symlinked_source(tmp_path, monkeypatch):
    from app.services.document_processor import DocumentProcessor

    upload_root = tmp_path / "uploads"
    course_dir = upload_root / "course-1"
    course_dir.mkdir(parents=True)
    safe_file = course_dir / "safe.txt"
    safe_file.write_text("safe", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    linked_file = course_dir / "linked.txt"
    try:
        os.symlink(outside, linked_file)
    except OSError as exc:
        pytest.skip(f"Symlink creation unavailable: {exc}")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_root))

    files = DocumentProcessor(vector_store=None).list_saved_course_files("course-1")

    assert files == [str(safe_file.resolve())]


def test_terminal_execute_failure_purges_vectors_and_falls_back_atomically(monkeypatch):
    from app.services.document_processor import DocumentProcessor
    from app.services.vector_store import Document

    class VectorStoreStub:
        deleted_courses = []

        def add_documents(self, *args, **kwargs):
            return None

        def delete_course(self, course_id):
            self.deleted_courses.append(course_id)

    course, user_id = _processor_course()
    with SessionLocal() as db:
        job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
        job_id = job.id
    processor = DocumentProcessor(vector_store=VectorStoreStub())
    monkeypatch.setattr(
        processor,
        "extract_and_chunk_file",
        lambda *args: [Document(content="enough grounded content", metadata={"page": 1})],
    )
    monkeypatch.setattr(processor, "_generate_course_title", lambda *args: None)
    from sqlalchemy.orm import Session

    original_execute = Session.execute
    failures = 0

    def fail_terminal_course_update(session, statement, *args, **kwargs):
        nonlocal failures
        if (
            getattr(getattr(statement, "table", None), "name", None) == "courses"
            and failures == 0
        ):
            failures += 1
            raise RuntimeError("simulated course persistence failure")
        return original_execute(session, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", fail_terminal_course_update)
    result = processor.process_course(course.id, ["source.txt"], SessionLocal, job_id)

    assert result.status == "failed"
    with SessionLocal() as db:
        persisted_course = db.get(Course, course.id)
        persisted_job = db.get(ProcessingJob, job.id)
        assert persisted_course.status == "failed"
        assert persisted_course.error_code == "DOCUMENT_PROCESSING_PERSISTENCE_FAILED"
        assert persisted_course.can_retry is True
        assert persisted_job.status == "failed"
        assert persisted_job.error_code == "DOCUMENT_PROCESSING_PERSISTENCE_FAILED"
    assert processor.vector_store.deleted_courses == [course.id]


def test_terminal_commit_failure_falls_back_atomically(monkeypatch):
    from app.services.document_processor import DocumentProcessor
    from app.services.vector_store import Document
    from sqlalchemy.orm import Session

    class VectorStoreStub:
        deleted_courses = []

        def add_documents(self, *args, **kwargs):
            return None

        def delete_course(self, course_id):
            self.deleted_courses.append(course_id)

    course, user_id = _processor_course()
    with SessionLocal() as db:
        job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
    processor = DocumentProcessor(vector_store=VectorStoreStub())
    monkeypatch.setattr(
        processor,
        "extract_and_chunk_file",
        lambda *args: [Document(content="enough grounded content", metadata={"page": 1})],
    )
    fail_next_commit = False

    def arm_terminal_commit_failure(*args, **kwargs):
        nonlocal fail_next_commit
        fail_next_commit = True
        return None

    monkeypatch.setattr(processor, "_generate_course_title", arm_terminal_commit_failure)
    original_commit = Session.commit

    def fail_only_terminal_commit(session):
        nonlocal fail_next_commit
        if fail_next_commit:
            fail_next_commit = False
            raise RuntimeError("simulated terminal commit failure")
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_only_terminal_commit)
    result = processor.process_course(course.id, ["source.txt"], SessionLocal, job.id)

    assert result.status == "failed"
    assert processor.vector_store.deleted_courses == [course.id]
    with SessionLocal() as db:
        assert db.get(Course, course.id).status == "failed"
        assert db.get(ProcessingJob, job.id).status == "failed"


def test_terminal_commit_then_raise_acknowledges_durable_success(monkeypatch):
    from app.services.document_processor import DocumentProcessor
    from app.services.vector_store import Document
    from sqlalchemy.orm import Session

    class VectorStoreStub:
        deleted_courses = []

        def add_documents(self, *args, **kwargs):
            return None

        def delete_course(self, course_id):
            self.deleted_courses.append(course_id)

    course, user_id = _processor_course()
    with SessionLocal() as db:
        job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
    processor = DocumentProcessor(vector_store=VectorStoreStub())
    monkeypatch.setattr(
        processor,
        "extract_and_chunk_file",
        lambda *args: [Document(content="enough grounded content", metadata={"page": 1})],
    )
    raise_after_commit = False

    def arm_uncertain_commit(*args, **kwargs):
        nonlocal raise_after_commit
        raise_after_commit = True
        return None

    monkeypatch.setattr(processor, "_generate_course_title", arm_uncertain_commit)
    original_commit = Session.commit

    def commit_then_raise(session):
        nonlocal raise_after_commit
        if raise_after_commit:
            raise_after_commit = False
            original_commit(session)
            raise RuntimeError("simulated acknowledgement loss after commit")
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", commit_then_raise)
    result = processor.process_course(course.id, ["source.txt"], SessionLocal, job.id)

    assert result.status == "ready"
    assert processor.vector_store.deleted_courses == []
    with SessionLocal() as db:
        assert db.get(Course, course.id).status == "ready"
        assert db.get(ProcessingJob, job.id).status == "succeeded"


def test_terminal_commit_then_raise_acknowledges_durable_failure(monkeypatch):
    from app.services.document_processor import DocumentProcessor
    from sqlalchemy.orm import Session

    class VectorStoreStub:
        def delete_course(self, *args, **kwargs):
            return None

    course, user_id = _processor_course()
    with SessionLocal() as db:
        job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
    processor = DocumentProcessor(vector_store=VectorStoreStub())
    raise_after_commit = False

    def fail_extraction_and_arm_commit(*args, **kwargs):
        nonlocal raise_after_commit
        raise_after_commit = True
        raise ValueError("bad source")

    monkeypatch.setattr(processor, "extract_and_chunk_file", fail_extraction_and_arm_commit)
    original_commit = Session.commit

    def commit_then_raise(session):
        nonlocal raise_after_commit
        if raise_after_commit:
            raise_after_commit = False
            original_commit(session)
            raise RuntimeError("simulated acknowledgement loss after commit")
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", commit_then_raise)
    result = processor.process_course(course.id, ["source.txt"], SessionLocal, job.id)

    assert result.status == "failed"
    with SessionLocal() as db:
        assert db.get(Course, course.id).status == "failed"
        assert db.get(Course, course.id).error_code == "DOCUMENT_TEXT_EXTRACTION_FAILED"
        assert db.get(ProcessingJob, job.id).status == "failed"
        assert db.get(ProcessingJob, job.id).error_code == "DOCUMENT_TEXT_EXTRACTION_FAILED"


def test_startup_reconciliation_fails_interrupted_inline_preprocess_job(monkeypatch):
    from app.services.inline_job_recovery import reconcile_interrupted_inline_preprocess_jobs

    monkeypatch.setattr(settings, "INLINE_PROCESSING_RECOVERY_ENABLED", True)
    course, user_id = _processor_course()
    with SessionLocal() as db:
        job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
    assert reconcile_interrupted_inline_preprocess_jobs(SessionLocal) == 1
    with SessionLocal() as db:
        persisted_course = db.get(Course, course.id)
        persisted_job = db.get(ProcessingJob, job.id)
        assert persisted_course.status == "failed"
        assert persisted_course.can_retry is True
        assert persisted_job.status == "failed"


def test_upload_rolls_back_course_when_preprocess_job_creation_fails(
    client, owner_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.upload.create_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced job flush failure")),
    )
    response = client.post(
        "/api/upload",
        headers=owner_headers,
        files=[("files", ("atomic.txt", b"grounded content", "text/plain"))],
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DOCUMENT_UPLOAD_UNAVAILABLE"
    with SessionLocal() as db:
        assert db.query(Course).count() == 0
        assert db.query(ProcessingJob).count() == 0
    assert list(Path(settings.UPLOAD_DIR).iterdir()) == []


def test_upload_cleans_partial_directory_when_second_file_write_fails(
    client, owner_headers, monkeypatch
):
    import builtins

    original_open = builtins.open
    write_count = 0

    def fail_second_upload_write(path, mode="r", *args, **kwargs):
        nonlocal write_count
        if mode == "wb":
            write_count += 1
            if write_count == 2:
                raise OSError("forced second upload write failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("app.routers.upload.open", fail_second_upload_write, raising=False)
    response = client.post(
        "/api/upload",
        headers=owner_headers,
        files=[
            ("files", ("first.txt", b"one", "text/plain")),
            ("files", ("second.txt", b"two", "text/plain")),
        ],
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DOCUMENT_UPLOAD_UNAVAILABLE"
    assert list(Path(settings.UPLOAD_DIR).iterdir()) == []
    with SessionLocal() as db:
        assert db.query(Course).count() == 0
        assert db.query(ProcessingJob).count() == 0


def test_upload_directory_collision_preserves_existing_contents(client, owner_headers, monkeypatch):
    from types import SimpleNamespace

    course_id = "collision123"
    collision_dir = Path(settings.UPLOAD_DIR) / course_id
    collision_dir.mkdir()
    sentinel = collision_dir / "keep.txt"
    sentinel.write_text("do not remove", encoding="utf-8")
    monkeypatch.setattr(
        "app.routers.upload.uuid.uuid4",
        lambda: SimpleNamespace(hex=f"{course_id}deadbeef"),
    )

    response = client.post(
        "/api/upload",
        headers=owner_headers,
        files=[("files", ("collision.txt", b"content", "text/plain"))],
    )

    assert response.status_code == 500
    assert sentinel.read_text(encoding="utf-8") == "do not remove"


def test_upload_rejects_filename_that_would_exceed_component_limit(client, owner_headers):
    response = client.post(
        "/api/upload",
        headers=owner_headers,
        files=[("files", (f"{'a' * 250}.txt", b"content", "text/plain"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Tên file quá dài."
    assert list(Path(settings.UPLOAD_DIR).iterdir()) == []


def test_deleted_course_is_revalidated_before_vector_write(monkeypatch):
    from app.services.document_processor import DocumentProcessor
    from app.services.vector_store import Document

    class VectorStoreStub:
        add_calls = 0

        def add_documents(self, *args, **kwargs):
            self.add_calls += 1

        def delete_course(self, *args, **kwargs):
            pytest.fail("No vectors should exist to clean up")

    course, user_id = _processor_course()
    with SessionLocal() as db:
        job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
        job_id = job.id
        persisted_course = db.get(Course, course.id)
        persisted_course.is_deleted = True
        persisted_course.status = "deleted"
        db.commit()
    vector_store = VectorStoreStub()
    processor = DocumentProcessor(vector_store=vector_store)
    monkeypatch.setattr(
        processor,
        "extract_and_chunk_file",
        lambda *args: [Document(content="grounded content", metadata={"page": 1})],
    )

    result = processor.process_course(course.id, ["source.txt"], SessionLocal, job_id)

    assert result.status == "failed"
    assert vector_store.add_calls == 0


def test_delete_after_vector_write_cleans_vectors_without_resurrecting_course(monkeypatch):
    from app.services.document_processor import DocumentProcessor
    from app.services.vector_store import Document

    course, user_id = _processor_course()
    with SessionLocal() as db:
        job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")

    class VectorStoreStub:
        deleted_courses = []

        def add_documents(self, *args, **kwargs):
            with SessionLocal() as db:
                persisted_course = db.get(Course, course.id)
                persisted_course.is_deleted = True
                persisted_course.status = "deleted"
                persisted_job = db.get(ProcessingJob, job.id)
                persisted_job.status = "failed"
                db.commit()

        def delete_course(self, course_id):
            self.deleted_courses.append(course_id)

    vector_store = VectorStoreStub()
    processor = DocumentProcessor(vector_store=vector_store)
    monkeypatch.setattr(
        processor,
        "extract_and_chunk_file",
        lambda *args: [Document(content="grounded content", metadata={"page": 1})],
    )
    monkeypatch.setattr(processor, "_generate_course_title", lambda *args: None)

    result = processor.process_course(course.id, ["source.txt"], SessionLocal, job.id)

    assert result.status == "failed"
    assert vector_store.deleted_courses == [course.id]
    with SessionLocal() as db:
        assert db.get(Course, course.id).status == "deleted"
        assert db.get(Course, course.id).is_deleted is True


def test_delete_between_post_vector_check_and_terminal_claim_keeps_course_deleted(monkeypatch):
    from app.services.document_processor import DocumentProcessor
    from app.services.vector_store import Document

    course, user_id = _processor_course()
    with SessionLocal() as db:
        job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")

    class VectorStoreStub:
        deleted_courses = []

        def add_documents(self, *args, **kwargs):
            return None

        def delete_course(self, course_id):
            self.deleted_courses.append(course_id)

    vector_store = VectorStoreStub()
    processor = DocumentProcessor(vector_store=vector_store)
    monkeypatch.setattr(
        processor,
        "extract_and_chunk_file",
        lambda *args: [Document(content="grounded content", metadata={"page": 1})],
    )
    monkeypatch.setattr(processor, "_generate_course_title", lambda *args: None)
    persist_terminal = processor._persist_terminal_state

    def delete_immediately_before_terminal(*args, **kwargs):
        if kwargs["status"] == "ready":
            with SessionLocal() as db:
                active_job = db.get(ProcessingJob, job.id)
                active_job.status = "failed"
                active_job.error_code = "DOCUMENT_PROCESSING_CANCELLED"
                current_course = db.get(Course, course.id)
                current_course.is_deleted = True
                current_course.status = "deleted"
                db.commit()
        return persist_terminal(*args, **kwargs)

    monkeypatch.setattr(processor, "_persist_terminal_state", delete_immediately_before_terminal)
    result = processor.process_course(course.id, ["source.txt"], SessionLocal, job.id)

    assert result.status == "failed"
    assert vector_store.deleted_courses == [course.id]
    with SessionLocal() as db:
        assert db.get(Course, course.id).status == "deleted"
        assert db.get(Course, course.id).is_deleted is True
        assert db.get(ProcessingJob, job.id).status == "failed"


def test_failed_terminal_claim_cannot_resurrect_deleted_course(monkeypatch):
    from app.services.document_processor import DocumentProcessor

    class VectorStoreStub:
        def delete_course(self, *args, **kwargs):
            return None

    course, user_id = _processor_course()
    with SessionLocal() as db:
        job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
    processor = DocumentProcessor(vector_store=VectorStoreStub())
    monkeypatch.setattr(
        processor,
        "extract_and_chunk_file",
        lambda *args: (_ for _ in ()).throw(ValueError("bad source")),
    )
    persist_terminal = processor._persist_terminal_state

    def delete_immediately_before_failure(*args, **kwargs):
        if kwargs["status"] == "failed":
            with SessionLocal() as db:
                active_job = db.get(ProcessingJob, job.id)
                active_job.status = "failed"
                current_course = db.get(Course, course.id)
                current_course.is_deleted = True
                current_course.status = "deleted"
                db.commit()
        return persist_terminal(*args, **kwargs)

    monkeypatch.setattr(processor, "_persist_terminal_state", delete_immediately_before_failure)
    result = processor.process_course(course.id, ["source.txt"], SessionLocal, job.id)

    assert result.status == "failed"
    with SessionLocal() as db:
        assert db.get(Course, course.id).status == "deleted"
        assert db.get(Course, course.id).is_deleted is True
        assert db.get(ProcessingJob, job.id).status == "failed"


def test_inline_reconciliation_terminalizes_invalid_jobs_and_repairs_stuck_courses(monkeypatch):
    from app.services.inline_job_recovery import reconcile_interrupted_inline_preprocess_jobs

    course, user_id = _processor_course()
    with SessionLocal() as db:
        ready_course = db.get(Course, course.id)
        ready_course.status = "ready"
        ready_job = create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
    monkeypatch.setattr(settings, "PROCESSING_EXECUTION_MODE", "distributed", raising=False)
    assert reconcile_interrupted_inline_preprocess_jobs(SessionLocal) == 0
    with SessionLocal() as db:
        assert db.get(ProcessingJob, ready_job.id).status == "queued"
        assert db.get(Course, course.id).status == "ready"

    monkeypatch.setattr(settings, "PROCESSING_EXECUTION_MODE", "inline", raising=False)
    monkeypatch.setattr(settings, "INLINE_PROCESSING_RECOVERY_ENABLED", True)
    assert reconcile_interrupted_inline_preprocess_jobs(SessionLocal) == 1
    with SessionLocal() as db:
        assert db.get(ProcessingJob, ready_job.id).status == "failed"
        assert db.get(Course, course.id).status == "ready"

    with SessionLocal() as db:
        mismatched = User(email="mismatched-job@example.com", hashed_password="not-used")
        db.add(mismatched)
        db.flush()
        stale_course = Course(user_id=user_id, filenames=["source.txt"], status="processing")
        db.add(stale_course)
        db.commit()
        stale_course_id = stale_course.id
        stale_job = ProcessingJob(
            course_id=stale_course_id,
            user_id=mismatched.id,
            job_type="preprocess",
            status="running",
        )
        db.add(stale_job)
        db.commit()
        stale_job_id = stale_job.id
    assert reconcile_interrupted_inline_preprocess_jobs(SessionLocal) == 1
    with SessionLocal() as db:
        assert db.get(ProcessingJob, stale_job_id).status == "failed"
        stale_course = db.get(Course, stale_course_id)
        assert stale_course.status == "failed"
        assert stale_course.can_retry is True

    with SessionLocal() as db:
        stale_attempt_course = Course(user_id=user_id, filenames=["source.txt"], status="processing")
        db.add(stale_attempt_course)
        db.commit()
        old_job = ProcessingJob(
            course_id=stale_attempt_course.id,
            user_id=user_id,
            job_type="preprocess",
            status="running",
        )
        db.add(old_job)
        db.commit()
        newer_terminal_job = ProcessingJob(
            course_id=stale_attempt_course.id,
            user_id=user_id,
            job_type="preprocess",
            status="succeeded",
        )
        db.add(newer_terminal_job)
        db.commit()
        old_job_id = old_job.id
        stale_attempt_course_id = stale_attempt_course.id
    assert reconcile_interrupted_inline_preprocess_jobs(SessionLocal) == 1
    with SessionLocal() as db:
        assert db.get(ProcessingJob, old_job_id).status == "failed"
        stale_attempt_course = db.get(Course, stale_attempt_course_id)
        assert stale_attempt_course.status == "failed"
        assert stale_attempt_course.can_retry is True


def test_inline_reconciliation_terminalizes_deleted_and_missing_course_jobs(monkeypatch):
    from app.services.inline_job_recovery import reconcile_interrupted_inline_preprocess_jobs

    monkeypatch.setattr(settings, "PROCESSING_EXECUTION_MODE", "inline")
    monkeypatch.setattr(settings, "INLINE_PROCESSING_RECOVERY_ENABLED", True)
    course, user_id = _processor_course()
    with SessionLocal() as db:
        deleted_course = db.get(Course, course.id)
        deleted_course.is_deleted = True
        deleted_course.status = "deleted"
        deleted_job = ProcessingJob(
            course_id=course.id, user_id=user_id, job_type="preprocess", status="running"
        )
        missing_job = ProcessingJob(
            course_id="missing-course", user_id=user_id, job_type="preprocess", status="queued"
        )
        db.add_all([deleted_job, missing_job])
        db.commit()
        deleted_job_id = deleted_job.id
        missing_job_id = missing_job.id

    assert reconcile_interrupted_inline_preprocess_jobs(SessionLocal) == 2
    with SessionLocal() as db:
        assert db.get(ProcessingJob, deleted_job_id).status == "failed"
        assert db.get(ProcessingJob, missing_job_id).status == "failed"
        persisted_course = db.get(Course, course.id)
        assert persisted_course.status == "deleted"
        assert persisted_course.is_deleted is True


def test_processing_execution_mode_is_validated_and_recovery_defaults_off():
    values = {
        "DATABASE_URL": "sqlite:///./test.db",
        "JWT_SECRET": "test-secret",
        "OPENROUTER_API_KEY": "test-key",
    }
    assert Settings(**values).INLINE_PROCESSING_RECOVERY_ENABLED is False
    with pytest.raises(ValidationError, match="PROCESSING_EXECUTION_MODE"):
        Settings(**values, PROCESSING_EXECUTION_MODE="inlien")


def test_single_process_inline_recovery_is_documented_in_shipped_env_surface():
    repo_root = Path(__file__).resolve().parents[3]
    env_example = (repo_root / ".env.example").read_text(encoding="utf-8")
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert "PROCESSING_EXECUTION_MODE=inline" in env_example
    assert "INLINE_PROCESSING_RECOVERY_ENABLED=true" in env_example
    assert "PROCESSING_EXECUTION_MODE=distributed" in readme
    assert "INLINE_PROCESSING_RECOVERY_ENABLED=false" in readme


def test_delete_cancels_active_preprocess_job(client, failed_course_with_file, owner_headers):
    with SessionLocal() as db:
        course = db.get(Course, failed_course_with_file.id)
        course.status = "processing"
        job = create_job(
            db,
            course_id=course.id,
            user_id=course.user_id,
            job_type="preprocess",
        )
        job_id = job.id

    response = client.delete(
        f"/api/courses/{failed_course_with_file.id}", headers=owner_headers
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.get(Course, failed_course_with_file.id).is_deleted is True
        assert db.get(ProcessingJob, job_id).status == "failed"
        assert db.get(ProcessingJob, job_id).error_code == "DOCUMENT_PROCESSING_CANCELLED"


def test_processing_job_lifecycle():
    db = SessionLocal()
    try:
        user = User(
            email="job-owner@example.com",
            hashed_password="not-used-by-this-test",
            is_verified=True,
        )
        db.add(user)
        db.flush()
        course = Course(user_id=user.id, filenames=["source.txt"])
        db.add(course)
        db.commit()
        job = create_job(
            db,
            course_id=course.id,
            user_id=user.id,
            job_type="preprocess",
        )
        assert job.status == "queued"
        assert mark_job_running(db, job.id, "Đang phân tích tài liệu")
        db.refresh(job)
        assert job.status == "running"
        assert mark_job_failed(
            db,
            job.id,
            error_code="OPENROUTER_KEY_LIMIT_EXCEEDED",
            message="Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
        )
        db.refresh(job)
        assert job.status == "failed"
        assert job.completed_at is not None
    finally:
        db.close()


def test_account_cleanup_deletes_processing_jobs(client):
    headers = _auth_headers(client, "delete-job-owner@example.com")
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        course = Course(user_id=user_id, filenames=["source.txt"])
        db.add(course)
        db.commit()
        create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
    deleted = client.request(
        "DELETE",
        "/api/auth/me",
        headers=headers,
        json={"password": "password123"},
    )
    assert deleted.status_code == 200
    with SessionLocal() as db:
        assert db.query(ProcessingJob).filter_by(user_id=user_id).count() == 0


def test_create_job_rejects_course_owned_by_different_user():
    db = SessionLocal()
    try:
        owner = User(email="course-owner@example.com", hashed_password="not-used")
        other_user = User(email="other-owner@example.com", hashed_password="not-used")
        db.add_all([owner, other_user])
        db.flush()
        course = Course(user_id=owner.id, filenames=["source.txt"])
        db.add(course)
        db.commit()

        with pytest.raises(ValueError, match="Course does not belong"):
            create_job(
                db,
                course_id=course.id,
                user_id=other_user.id,
                job_type="preprocess",
            )
    finally:
        db.close()


def test_account_cleanup_deletes_legacy_cross_owner_processing_jobs(client):
    headers = _auth_headers(client, "delete-malformed-job-owner@example.com")
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        course = Course(user_id=user_id, filenames=["source.txt"])
        malformed_owner = User(
            email="legacy-malformed-job-owner@example.com", hashed_password="not-used"
        )
        db.add_all([course, malformed_owner])
        db.flush()
        legacy_job = ProcessingJob(
            course_id=course.id,
            user_id=malformed_owner.id,
            job_type="preprocess",
        )
        db.add(legacy_job)
        db.commit()
        legacy_job_id = legacy_job.id

    deleted = client.request(
        "DELETE",
        "/api/auth/me",
        headers=headers,
        json={"password": "password123"},
    )
    assert deleted.status_code == 200
    with SessionLocal() as db:
        assert db.get(ProcessingJob, legacy_job_id) is None


def test_processing_job_lifecycle_rejects_missing_and_stale_transitions():
    db = SessionLocal()
    try:
        user = User(email="job-guard-owner@example.com", hashed_password="not-used")
        db.add(user)
        db.flush()
        course = Course(user_id=user.id, filenames=["source.txt"])
        db.add(course)
        db.commit()

        assert not mark_job_running(db, "missing-job", "Đang phân tích tài liệu")
        assert not mark_job_failed(
            db,
            "missing-job",
            error_code="DOCUMENT_TEXT_EXTRACTION_FAILED",
            message="Không thể đọc tài liệu.",
        )
        assert not mark_job_succeeded(db, "missing-job")

        successful_job = create_job(
            db, course_id=course.id, user_id=user.id, job_type="preprocess"
        )
        assert mark_job_running(db, successful_job.id, "Đang phân tích tài liệu")
        assert mark_job_succeeded(db, successful_job.id)
        db.refresh(successful_job)
        successful_completed_at = successful_job.completed_at
        assert successful_job.status == "succeeded"
        assert successful_job.progress == 100
        assert successful_job.error_code is None
        assert successful_job.error_message is None
        assert successful_completed_at is not None
        assert not mark_job_running(db, successful_job.id, "Không được chạy lại")
        db.refresh(successful_job)
        assert successful_job.completed_at == successful_completed_at

        failed_job = create_job(
            db, course_id=course.id, user_id=user.id, job_type="preprocess"
        )
        assert mark_job_running(db, failed_job.id, "Đang phân tích tài liệu")
        assert mark_job_failed(
            db,
            failed_job.id,
            error_code="DOCUMENT_TEXT_EXTRACTION_FAILED",
            message="Không thể đọc tài liệu.",
        )
        db.refresh(failed_job)
        failed_completed_at = failed_job.completed_at
        failed_error_code = failed_job.error_code
        assert not mark_job_succeeded(db, failed_job.id)
        db.refresh(failed_job)
        assert failed_job.status == "failed"
        assert failed_job.completed_at == failed_completed_at
        assert failed_job.error_code == failed_error_code
    finally:
        db.close()
