"""Route coverage for durable upload and study-pack generation jobs."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from time import perf_counter
from typing import Any

import pytest

from app.core.config import settings
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.database import SessionLocal
from app.services.job_dispatch_recovery import reconcile_undispatched_jobs
from app.services.job_resource_state import terminalize_dispatch_failure
from app.services.job_service import cancel_job, claim_job, create_job, mark_job_cancelled


def _headers(client, email: str) -> dict[str, str]:
    registered = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123", "full_name": email},
    )
    assert registered.status_code == 201, registered.text
    verified = client.post(
        "/api/auth/verify-email",
        json={"email": email, "code": "000000"},
    )
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _user_id(email: str) -> str:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        return user.id


def _ready_course(user_id: str, course_id: str = "queued-course") -> Course:
    with SessionLocal() as db:
        course = Course(
            id=course_id,
            user_id=user_id,
            filenames=["source.txt"],
            status="ready",
            stage="completed",
            progress=100,
            chunk_count=1,
            embedding_status="completed",
            quality_score=80,
        )
        db.add(course)
        db.commit()
        db.refresh(course)
        db.expunge(course)
        return course


@dataclass
class RecordingDispatcher:
    deliveries: list[tuple[str, str]] = field(default_factory=list)

    def enqueue(self, job_id: str, queue_name: str) -> str:
        self.deliveries.append((job_id, queue_name))
        return f"recorded:{job_id}"


class FailingDispatcher:
    def enqueue(self, job_id: str, queue_name: str) -> str:
        from app.jobs.dispatcher import DefiniteJobDispatchError

        raise DefiniteJobDispatchError(
            "internal callback registration detail must remain private"
        )


class AcceptedThenErroredDispatcher:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, str]] = []

    def enqueue(self, job_id: str, queue_name: str) -> str:
        self.deliveries.append((job_id, queue_name))
        raise ConnectionError("broker may already have accepted this delivery")


class ReservingOnlyGenerator:
    """A route fake whose generation methods must never be reached by the request."""

    def __init__(self) -> None:
        self.reservations: list[dict[str, Any]] = []
        self.generation_started = Event()

    def prepare_artifact_version(
        self,
        course_id: str,
        artifact: str,
        options: dict[str, Any],
        **kwargs: Any,
    ) -> str:
        self.reservations.append(
            {
                "course_id": course_id,
                "artifact": artifact,
                "options": options,
                **kwargs,
            }
        )
        return f"version-{artifact}"

    def __getattr__(self, name: str):
        if name.startswith("generate_"):
            def blocked_generator(*args, **kwargs):
                self.generation_started.set()
                Event().wait(3)

            return blocked_generator
        raise AttributeError(name)


def _install_recording_dispatcher(monkeypatch) -> RecordingDispatcher:
    dispatcher = RecordingDispatcher()
    monkeypatch.setattr(
        "app.routers.jobs.get_job_dispatcher",
        lambda background_tasks: dispatcher,
    )
    return dispatcher


def _install_failing_dispatcher(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.jobs.get_job_dispatcher",
        lambda background_tasks: FailingDispatcher(),
    )


def test_upload_enqueues_one_id_only_preprocess_job(client, monkeypatch):
    headers = _headers(client, "queued-upload@example.com")
    dispatcher = _install_recording_dispatcher(monkeypatch)
    processor_requested = Event()

    def blocked_processor():
        processor_requested.set()
        Event().wait(3)

    monkeypatch.setattr(
        "app.routers.documents.get_document_processor",
        blocked_processor,
    )

    started_at = perf_counter()
    response = client.post(
        "/api/upload",
        headers=headers,
        files=[("files", ("source.txt", b"grounded source", "text/plain"))],
    )
    elapsed = perf_counter() - started_at

    assert response.status_code == 201, response.text
    assert elapsed < 1.5
    assert not processor_requested.is_set()
    body = response.json()
    assert body["job_id"]
    with SessionLocal() as db:
        jobs = db.query(ProcessingJob).all()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == body["job_id"]
        assert job.job_type == "preprocess"
        assert job.status == "queued"
        assert job.queue_name == "ingestion"
        assert job.payload_json == {"course_id": body["course_id"]}
        assert job.external_task_id == f"recorded:{job.id}"
    assert dispatcher.deliveries == [(body["job_id"], "ingestion")]


GENERATION_CASES = [
    (
        "/api/generate-book",
        {"user_prompt": "Focus", "detail_level": "Chuyên sâu"},
        "book",
        "book",
        "generation",
        {"detail_level": "Chuyên sâu", "user_prompt": "Focus"},
    ),
    (
        "/api/generate-slide",
        {"topic": "Networks", "mode": "summary", "focus_prompt": "Routing"},
        "slides",
        "slides",
        "generation",
        {"topic": "Networks", "num_slides": 8, "focus_prompt": "Routing"},
    ),
    (
        "/api/generate-quiz",
        {"topic": "Networks", "quantity": 7, "difficulty": "hard"},
        "quiz",
        "quiz",
        "generation",
        {"topic": "Networks", "quantity": 7, "difficulty": "hard"},
    ),
    (
        "/api/generate-vid",
        {
            "topic": "Networks",
            "format": "overview",
            "voice": "male",
            "user_prompt": "Concise",
        },
        "video",
        "vid",
        "video",
        {
            "topic": "Networks",
            "format": "overview",
            "voice": "male",
            "user_prompt": "Concise",
        },
    ),
]


@pytest.mark.parametrize(
    "endpoint,options,job_type,artifact,queue_name,worker_options",
    GENERATION_CASES,
)
def test_generation_route_enqueues_one_validated_job_without_running_generator(
    client,
    monkeypatch,
    endpoint,
    options,
    job_type,
    artifact,
    queue_name,
    worker_options,
):
    email = f"queued-{job_type}@example.com"
    headers = _headers(client, email)
    course = _ready_course(_user_id(email), f"course-{job_type}")
    dispatcher = _install_recording_dispatcher(monkeypatch)
    generator = ReservingOnlyGenerator()
    monkeypatch.setattr("app.routers.generation.get_generator", lambda: generator)

    started_at = perf_counter()
    response = client.post(
        endpoint,
        headers=headers,
        json={"course_id": course.id, **options},
    )
    elapsed = perf_counter() - started_at

    assert response.status_code == 200, response.text
    assert elapsed < 1.5
    assert not generator.generation_started.is_set()
    body = response.json()
    assert body["job_id"]
    assert body["version_id"] == f"version-{artifact}"
    with SessionLocal() as db:
        jobs = db.query(ProcessingJob).all()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == body["job_id"]
        assert job.job_type == job_type
        assert job.status == "queued"
        assert job.queue_name == queue_name
        assert job.payload_json == {
            "course_id": course.id,
            "artifact": artifact,
            "version_id": f"version-{artifact}",
            **worker_options,
        }
        assert job.external_task_id == f"recorded:{job.id}"
    assert dispatcher.deliveries == [(body["job_id"], queue_name)]


def test_job_read_and_cancel_are_owner_scoped_and_safe(client, monkeypatch):
    owner_headers = _headers(client, "job-owner@example.com")
    other_headers = _headers(client, "job-other@example.com")
    course = _ready_course(_user_id("job-owner@example.com"), "owner-course")
    _install_recording_dispatcher(monkeypatch)
    monkeypatch.setattr(
        "app.routers.generation.get_generator", lambda: ReservingOnlyGenerator()
    )
    created = client.post(
        "/api/generate-book",
        headers=owner_headers,
        json={"course_id": course.id},
    )
    job_id = created.json()["job_id"]

    assert client.get(f"/api/jobs/{job_id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/jobs/{job_id}", headers=other_headers).status_code == 404

    read = client.get(f"/api/jobs/{job_id}", headers=owner_headers)
    assert read.status_code == 200
    assert set(read.json()).isdisjoint(
        {"payload_json", "worker_id", "lease_expires_at", "external_task_id"}
    )
    cancelled = client.delete(f"/api/jobs/{job_id}", headers=owner_headers)
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancelled"
    assert client.delete(f"/api/jobs/{job_id}", headers=owner_headers).status_code == 409


def test_cancelled_video_job_never_invokes_generator_or_produces_mp4(
    client, monkeypatch
):
    from app.jobs.tasks import execute_job

    email = "cancel-video@example.com"
    headers = _headers(client, email)
    course = _ready_course(_user_id(email), "cancel-video-course")
    _install_recording_dispatcher(monkeypatch)
    monkeypatch.setattr(
        "app.routers.generation.get_generator", lambda: ReservingOnlyGenerator()
    )
    created = client.post(
        "/api/generate-vid",
        headers=headers,
        json={"course_id": course.id},
    )
    assert created.status_code == 200
    job_id = created.json()["job_id"]
    version_id = created.json()["version_id"]
    cancelled = client.delete(f"/api/jobs/{job_id}", headers=headers)
    assert cancelled.status_code == 202

    monkeypatch.setattr(
        "app.jobs.tasks.get_generator",
        lambda: (_ for _ in ()).throw(
            AssertionError("A cancelled video job constructed the generator.")
        ),
    )
    assert execute_job(job_id, worker_id="test-worker") is None
    output = (
        Path(settings.UPLOAD_DIR)
        / course.id
        / "artifacts"
        / "vid"
        / version_id
        / "vid.mp4"
    )
    assert not output.exists()


def test_admission_rejection_does_not_reserve_artifact_or_create_job(
    client, monkeypatch
):
    email = "full-queue@example.com"
    headers = _headers(client, email)
    user_id = _user_id(email)
    course = _ready_course(user_id, "full-queue-course")
    with SessionLocal() as db:
        for index in range(settings.MAX_PENDING_JOBS_PER_USER):
            extra = Course(
                id=f"full-{index}",
                user_id=user_id,
                filenames=["source.txt"],
                status="ready",
                stage="completed",
                progress=100,
                chunk_count=1,
                embedding_status="completed",
                quality_score=80,
            )
            db.add(extra)
            db.flush()
            create_job(
                db,
                course_id=extra.id,
                user_id=user_id,
                job_type="book",
                payload_json={
                    "course_id": extra.id,
                    "artifact": "book",
                    "version_id": f"seed-{index}",
                },
                commit=False,
            )
        db.commit()

    generator = ReservingOnlyGenerator()
    monkeypatch.setattr("app.routers.generation.get_generator", lambda: generator)
    response = client.post(
        "/api/generate-book",
        headers=headers,
        json={"course_id": course.id},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert generator.reservations == []
    with SessionLocal() as db:
        assert db.query(ProcessingJob).count() == settings.MAX_PENDING_JOBS_PER_USER


def test_upload_admission_rejection_leaves_no_course_job_or_files(client):
    email = "full-upload-queue@example.com"
    headers = _headers(client, email)
    user_id = _user_id(email)
    with SessionLocal() as db:
        for index in range(settings.MAX_PENDING_JOBS_PER_USER):
            course = Course(
                id=f"upload-full-{index}",
                user_id=user_id,
                filenames=["source.txt"],
                status="ready",
                stage="completed",
                progress=100,
                chunk_count=1,
                embedding_status="completed",
                quality_score=80,
            )
            db.add(course)
            db.flush()
            create_job(
                db,
                course_id=course.id,
                user_id=user_id,
                job_type="book",
                payload_json={
                    "course_id": course.id,
                    "artifact": "book",
                    "version_id": f"upload-seed-{index}",
                },
                commit=False,
            )
        db.commit()

    response = client.post(
        "/api/upload",
        headers=headers,
        files=[("files", ("rejected.txt", b"content", "text/plain"))],
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    with SessionLocal() as db:
        assert db.query(Course).count() == settings.MAX_PENDING_JOBS_PER_USER
        assert db.query(ProcessingJob).count() == settings.MAX_PENDING_JOBS_PER_USER
    assert list(Path(settings.UPLOAD_DIR).iterdir()) == []


def test_dispatch_failure_terminalizes_upload_course_with_safe_error(client, monkeypatch):
    headers = _headers(client, "upload-dispatch-failure@example.com")
    _install_failing_dispatcher(monkeypatch)

    response = client.post(
        "/api/upload",
        headers=headers,
        files=[("files", ("source.txt", b"content", "text/plain"))],
    )

    assert response.status_code == 503
    assert "broker" not in response.text.lower()
    with SessionLocal() as db:
        course = db.query(Course).one()
        job = db.query(ProcessingJob).one()
        assert course.status == "failed"
        assert course.error_code == "DOCUMENT_SCHEDULING_FAILED"
        assert job.status == "failed"
        assert job.active_key is None


def test_dispatch_failure_terminalizes_reserved_artifact_version(client, monkeypatch):
    email = "generation-dispatch-failure@example.com"
    headers = _headers(client, email)
    course = _ready_course(_user_id(email), "generation-dispatch-failure")
    _install_failing_dispatcher(monkeypatch)

    response = client.post(
        "/api/generate-book",
        headers=headers,
        json={"course_id": course.id},
    )

    assert response.status_code == 503
    assert "broker" not in response.text.lower()
    with SessionLocal() as db:
        job = db.query(ProcessingJob).one()
        assert job.status == "failed"
        assert job.active_key is None
    from app.routers.generation import get_generator

    _, versions = get_generator().artifact_versions(course.id, "book")
    assert len(versions) == 1
    assert versions[0]["status"] == "error"


def test_admin_job_summary_contains_only_aggregate_queue_state(client):
    headers = _headers(client, "jobs-admin@example.com")
    user_id = _user_id("jobs-admin@example.com")
    _ready_course(user_id, "admin-summary-course")
    with SessionLocal() as db:
        user = db.get(User, user_id)
        user.role = "admin"
        create_job(
            db,
            course_id="admin-summary-course",
            user_id=user_id,
            job_type="preprocess",
            payload_json={"course_id": "admin-summary-course"},
            queue_name="ingestion",
            commit=False,
        )
        db.commit()

    response = client.get("/api/admin/jobs/summary", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["counts"]["ingestion"]["queued"] == 1
    assert response.json()["oldest_queued_age_seconds"] >= 0
    serialized = response.text.lower()
    assert "payload" not in serialized
    assert "document" not in serialized


def test_queued_preprocess_cancellation_terminalizes_course_polling(client, monkeypatch):
    headers = _headers(client, "cancel-upload-resource@example.com")
    _install_recording_dispatcher(monkeypatch)
    created = client.post(
        "/api/upload",
        headers=headers,
        files=[("files", ("source.txt", b"content", "text/plain"))],
    )

    cancelled = client.delete(
        f"/api/jobs/{created.json()['job_id']}", headers=headers
    )
    polled = client.get(
        f"/api/courses/{created.json()['course_id']}/status", headers=headers
    )

    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["message"] == "Đã hủy tác vụ"
    assert polled.json()["status"] == "failed"
    assert polled.json()["error_code"] == "DOCUMENT_PROCESSING_CANCELLED"


def test_running_cancellation_terminalizes_artifact_at_worker_checkpoint(
    client, monkeypatch
):
    from app.routers.generation import get_generator

    email = "cancel-running-artifact@example.com"
    headers = _headers(client, email)
    course = _ready_course(_user_id(email), "cancel-running-artifact")
    _install_recording_dispatcher(monkeypatch)
    created = client.post(
        "/api/generate-book", headers=headers, json={"course_id": course.id}
    )
    job_id = created.json()["job_id"]
    version_id = created.json()["version_id"]
    with SessionLocal() as db:
        assert claim_job(db, job_id, "worker-a", 60)
        assert cancel_job(db, job_id)
        active = db.get(ProcessingJob, job_id)
        assert active.status == "running"
        assert active.message == "Đang hủy tác vụ"
        assert mark_job_cancelled(
            db, job_id, "worker-a", expected_attempt=active.attempts
        )

    _, versions = get_generator().artifact_versions(course.id, "book")
    version = next(item for item in versions if item["version_id"] == version_id)
    assert version["status"] == "error"
    polled = client.get(
        f"/api/courses/{course.id}/book?version={version_id}", headers=headers
    )
    assert polled.json()["status"] == "error"


def test_reservation_rolls_back_when_job_creation_fails(client, monkeypatch):
    from app.routers.generation import get_generator

    email = "atomic-reservation@example.com"
    headers = _headers(client, email)
    course = _ready_course(_user_id(email), "atomic-reservation")

    def fail_create_job(*args, **kwargs):
        raise RuntimeError("forced insert failure")

    monkeypatch.setattr("app.routers.generation.create_job", fail_create_job)
    with pytest.raises(RuntimeError, match="forced insert failure"):
        client.post(
            "/api/generate-book", headers=headers, json={"course_id": course.id}
        )
    with SessionLocal() as db:
        assert db.query(ProcessingJob).count() == 0
        persisted = db.get(Course, course.id)
        metadata = json.loads(persisted.metadata_json or "{}")
        assert not metadata.get("study_pack", {}).get("artifacts", {}).get("book")
    assert get_generator().artifact_versions(course.id, "book") == (None, [])


def test_reservation_and_job_roll_back_together_when_outer_commit_fails():
    from app.routers.generation import get_generator

    user = User(
        email="atomic-commit@example.com", hashed_password="unused", is_verified=True
    )
    with SessionLocal() as db:
        db.add(user)
        db.flush()
        course = Course(
            id="atomic-commit", user_id=user.id, filenames=["source.txt"], status="ready"
        )
        course_id = course.id
        db.add(course)
        db.commit()
        version_id = get_generator().prepare_artifact_version(
            course_id,
            "book",
            {"detail_level": "Tiêu chuẩn"},
            db_session=db,
        )
        create_job(
            db,
            course_id=course_id,
            user_id=user.id,
            job_type="book",
            payload_json={
                "course_id": course_id,
                "artifact": "book",
                "version_id": version_id,
            },
            commit=False,
        )

        def fail_commit():
            raise OSError("commit unavailable")

        db.commit = fail_commit
        with pytest.raises(OSError):
            db.commit()
        db.rollback()

    with SessionLocal() as db:
        assert db.query(ProcessingJob).count() == 0
        assert get_generator().artifact_versions(course_id, "book") == (None, [])


def test_startup_reconciles_unconfirmed_generation_and_preprocess_deliveries(
    monkeypatch,
):
    user = User(
        email="recovery@example.com", hashed_password="unused", is_verified=True
    )
    with SessionLocal() as db:
        db.add(user)
        db.flush()
        first = Course(id="recover-upload", user_id=user.id, filenames=["a.txt"])
        second = Course(id="recover-book", user_id=user.id, filenames=["b.txt"])
        db.add_all([first, second])
        db.flush()
        upload_job = create_job(
            db,
            course_id=first.id,
            user_id=user.id,
            job_type="preprocess",
            payload_json={"course_id": first.id},
            queue_name="ingestion",
            commit=False,
        )
        book_job = create_job(
            db,
            course_id=second.id,
            user_id=user.id,
            job_type="book",
            payload_json={
                "course_id": second.id,
                "artifact": "book",
                "version_id": "recover-version",
            },
            queue_name="generation",
            commit=False,
        )
        db.commit()
        ids = {upload_job.id, book_job.id}

    class AcceptedWithoutAck:
        def __init__(self):
            self.deliveries = []

        def enqueue(self, job_id, queue_name):
            self.deliveries.append((job_id, queue_name))
            raise ConnectionError("accepted but acknowledgement lost")

    lost_ack = AcceptedWithoutAck()
    assert reconcile_undispatched_jobs(SessionLocal, lost_ack) == 0
    recovered = RecordingDispatcher()
    assert reconcile_undispatched_jobs(SessionLocal, recovered) == 2
    assert {job_id for job_id, _ in lost_ack.deliveries} == ids
    assert {job_id for job_id, _ in recovered.deliveries} == ids
    with SessionLocal() as db:
        assert all(db.get(ProcessingJob, job_id).external_task_id for job_id in ids)

    startup_called = []
    monkeypatch.setattr("main.seed_default_admin", lambda: None)
    monkeypatch.setattr(
        "main.reconcile_interrupted_inline_preprocess_jobs", lambda: None
    )
    monkeypatch.setattr("main.reconcile_undispatched_jobs", lambda: startup_called.append(True))
    from main import app, lifespan

    async def enter_startup():
        async with lifespan(app):
            pass

    asyncio.run(enter_startup())
    assert startup_called == [True]


def test_dispatch_repair_commit_failure_rolls_back_job_and_artifact_together():
    user = User(
        email="repair-rollback@example.com", hashed_password="unused", is_verified=True
    )
    with SessionLocal() as db:
        db.add(user)
        db.flush()
        course = Course(
            id="repair-rollback",
            user_id=user.id,
            filenames=["a.txt"],
            status="ready",
            metadata_json=json.dumps(
                {
                    "study_pack": {
                        "artifacts": {
                            "book": {
                                "active": None,
                                "versions": {
                                    "v1": {"status": "processing", "progress": 0}
                                },
                            }
                        }
                    }
                }
            ),
        )
        db.add(course)
        db.flush()
        job = create_job(
            db,
            course_id=course.id,
            user_id=user.id,
            job_type="book",
            payload_json={
                "course_id": course.id,
                "artifact": "book",
                "version_id": "v1",
            },
            commit=False,
        )
        db.commit()
        job_id = job.id

    with SessionLocal() as db:
        original_commit = db.commit

        def fail_commit():
            raise OSError("database write lost")

        db.commit = fail_commit
        with pytest.raises(OSError):
            terminalize_dispatch_failure(db, job_id)
        db.commit = original_commit

    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        course = db.get(Course, "repair-rollback")
        version = json.loads(course.metadata_json)["study_pack"]["artifacts"]["book"]["versions"]["v1"]
        assert job.status == "queued"
        assert job.active_key is not None
        assert version["status"] == "processing"


def test_dispatch_repair_persistence_failure_returns_only_safe_error(
    client, monkeypatch
):
    email = "repair-safe-error@example.com"
    headers = _headers(client, email)
    course = _ready_course(_user_id(email), "repair-safe-error")
    _install_failing_dispatcher(monkeypatch)
    monkeypatch.setattr(
        "app.routers.jobs.terminalize_dispatch_failure",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("private db path")),
    )

    response = client.post(
        "/api/generate-book", headers=headers, json={"course_id": course.id}
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "JOB_DISPATCH_PERSISTENCE_FAILED"
    assert "private" not in response.text.lower()


def test_job_queue_position_is_same_queue_active_only(client):
    headers = _headers(client, "queue-position@example.com")
    user_id = _user_id("queue-position@example.com")
    jobs = []
    with SessionLocal() as db:
        for index, queue_name in enumerate(("generation", "video", "generation")):
            course = Course(
                id=f"position-{index}",
                user_id=user_id,
                filenames=["source.txt"],
                status="ready",
            )
            db.add(course)
            db.flush()
            job = create_job(
                db,
                course_id=course.id,
                user_id=user_id,
                job_type="video" if queue_name == "video" else "book",
                payload_json={
                    "course_id": course.id,
                    "artifact": "vid" if queue_name == "video" else "book",
                    "version_id": f"v-{index}",
                },
                queue_name=queue_name,
                commit=False,
            )
            job.created_at = datetime.utcnow() + timedelta(seconds=index)
            jobs.append(job.id)
        db.commit()

    assert client.get(f"/api/jobs/{jobs[0]}", headers=headers).json()["queue_position"] == 1
    assert client.get(f"/api/jobs/{jobs[1]}", headers=headers).json()["queue_position"] == 1
    assert client.get(f"/api/jobs/{jobs[2]}", headers=headers).json()["queue_position"] == 2
    with SessionLocal() as db:
        first = db.get(ProcessingJob, jobs[0])
        first.status = "cancelled"
        first.active_key = None
        first.completed_at = datetime.utcnow()
        db.commit()
    assert client.get(f"/api/jobs/{jobs[0]}", headers=headers).json()["queue_position"] is None
    assert client.get(f"/api/jobs/{jobs[2]}", headers=headers).json()["queue_position"] == 1


def test_inline_startup_recovers_queued_job_even_with_registration_marker():
    user = User(
        email="inline-registration-crash@example.com",
        hashed_password="unused",
        is_verified=True,
    )
    with SessionLocal() as db:
        db.add(user)
        db.flush()
        course = Course(
            id="inline-registration-crash",
            user_id=user.id,
            filenames=["source.txt"],
        )
        db.add(course)
        db.flush()
        job = create_job(
            db,
            course_id=course.id,
            user_id=user.id,
            job_type="preprocess",
            payload_json={"course_id": course.id},
            queue_name="ingestion",
            commit=False,
        )
        job.external_task_id = f"inline:{job.id}"
        db.commit()
        job_id = job.id

    dispatcher = RecordingDispatcher()
    assert reconcile_undispatched_jobs(SessionLocal, dispatcher) == 1
    assert dispatcher.deliveries == [(job_id, "ingestion")]


def test_ambiguous_publish_error_keeps_job_and_resource_recoverable(
    client, monkeypatch
):
    from app.routers.generation import get_generator

    email = "ambiguous-dispatch@example.com"
    headers = _headers(client, email)
    course = _ready_course(_user_id(email), "ambiguous-dispatch")
    ambiguous = AcceptedThenErroredDispatcher()
    monkeypatch.setattr(
        "app.routers.jobs.get_job_dispatcher", lambda background_tasks: ambiguous
    )

    response = client.post(
        "/api/generate-book", headers=headers, json={"course_id": course.id}
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "JOB_DISPATCH_UNCONFIRMED"
    assert "broker" not in response.text.lower()
    with SessionLocal() as db:
        job = db.query(ProcessingJob).one()
        assert job.status == "queued"
        assert job.active_key is not None
        assert job.external_task_id is None
        job_id = job.id
    _, versions = get_generator().artifact_versions(course.id, "book")
    assert versions[0]["status"] == "processing"

    recovered = RecordingDispatcher()
    assert reconcile_undispatched_jobs(SessionLocal, recovered) == 1
    assert recovered.deliveries == [(job_id, "generation")]
