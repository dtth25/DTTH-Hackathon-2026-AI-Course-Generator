"""Persistence tests for document processing jobs and saved-document retries."""

from pathlib import Path

import pytest

from app.core.config import settings
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
