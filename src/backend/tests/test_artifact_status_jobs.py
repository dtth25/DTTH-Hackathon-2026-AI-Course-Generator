"""Ownership and selected/active identity contracts for artifact status envelopes."""

from datetime import datetime, timedelta

from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.database import SessionLocal


def _headers(client, email: str) -> dict[str, str]:
    assert client.post("/api/auth/register", json={"email": email, "password": "password123"}).status_code == 201
    response = client.post("/api/auth/verify-email", json={"email": email, "code": "000000"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class StatusGenerator:
    def artifact_versions(self, course_id, artifact):
        return "v2", [
            {"version_id": "v1", "label": "Old", "options": {}, "status": "ready"},
            {"version_id": "v2", "label": "New", "options": {}, "status": "processing"},
        ]

    def _load_artifact_json(self, *args, **kwargs):
        return {"title": "Book", "summary": "Safe", "chapters": [{"chapter_title": "One", "sections": []}]}

    def get_artifact_status(self, course_id, artifact, version_id=None):
        return {"status": "ready" if version_id == "v1" else "processing", "progress": 100 if version_id == "v1" else 25}


def test_old_selected_version_returns_its_job_and_separate_owned_active_job(client, monkeypatch):
    owner_headers = _headers(client, "artifact-owner@example.com")
    _headers(client, "artifact-other@example.com")
    with SessionLocal() as db:
        owner = db.query(User).filter_by(email="artifact-owner@example.com").one()
        other = db.query(User).filter_by(email="artifact-other@example.com").one()
        db.add(Course(id="artifact-course", user_id=owner.id, filenames=["source.txt"], status="ready"))
        db.flush()
        now = datetime.utcnow()
        db.add_all([
            ProcessingJob(id="selected-job", course_id="artifact-course", user_id=owner.id, job_type="book", status="succeeded", progress=100, payload_json={"artifact": "book", "version_id": "v1"}, created_at=now),
            ProcessingJob(id="other-active-job", course_id="artifact-course", user_id=other.id, job_type="book", status="running", progress=80, payload_json={"artifact": "book", "version_id": "foreign"}, created_at=now + timedelta(seconds=2)),
            ProcessingJob(id="owned-active-job", course_id="artifact-course", user_id=owner.id, job_type="book", status="running", progress=25, payload_json={"artifact": "book", "version_id": "v2"}, created_at=now + timedelta(seconds=1), next_attempt_at=now + timedelta(minutes=2)),
            ProcessingJob(id="deleted-version-job", course_id="artifact-course", user_id=owner.id, job_type="book", status="running", progress=40, payload_json={"artifact": "book", "version_id": "deleted-v3"}, created_at=now + timedelta(seconds=4)),
            ProcessingJob(id="malformed-version-job", course_id="artifact-course", user_id=owner.id, job_type="book", status="running", progress=50, payload_json={"artifact": "book", "version_id": {"bad": True}}, created_at=now + timedelta(seconds=3)),
            ProcessingJob(id="missing-version-job", course_id="artifact-course", user_id=owner.id, job_type="book", status="running", progress=60, payload_json={"artifact": "book"}, created_at=now + timedelta(seconds=2)),
        ])
        db.commit()

    monkeypatch.setattr("app.routers.generation.get_generator", lambda: StatusGenerator())
    response = client.get("/api/course/artifact-course/book?version=v1", headers=owner_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version_id"] == "v1"
    assert body["job_id"] == "selected-job"
    assert body["active_job"] == {"job_id": "owned-active-job", "version_id": "v2"}
    assert "other-active-job" not in response.text
    assert "foreign" not in response.text
    assert "deleted-version-job" not in response.text
    assert "malformed-version-job" not in response.text
    assert "missing-version-job" not in response.text

    job_response = client.get("/api/jobs/owned-active-job", headers=owner_headers)
    assert job_response.status_code == 200
    assert job_response.json()["next_attempt_at"].endswith("Z")


def test_other_user_cannot_read_artifact_job_envelope(client, monkeypatch):
    owner_headers = _headers(client, "private-owner@example.com")
    other_headers = _headers(client, "private-other@example.com")
    with SessionLocal() as db:
        owner = db.query(User).filter_by(email="private-owner@example.com").one()
        db.add(Course(id="private-artifact", user_id=owner.id, filenames=["source.txt"], status="ready"))
        db.commit()
    monkeypatch.setattr("app.routers.generation.get_generator", lambda: StatusGenerator())
    assert client.get("/api/course/private-artifact/book?version=v1", headers=owner_headers).status_code == 200
    response = client.get("/api/course/private-artifact/book?version=v1", headers=other_headers)
    assert response.status_code == 404
    assert "job_id" not in response.text
