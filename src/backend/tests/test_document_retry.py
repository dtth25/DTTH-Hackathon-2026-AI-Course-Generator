"""Persistence tests for document processing jobs."""

from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.database import SessionLocal
from app.services.job_service import create_job, mark_job_failed, mark_job_running


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
        mark_job_running(db, job.id, "Đang phân tích tài liệu")
        db.refresh(job)
        assert job.status == "running"
        mark_job_failed(
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
