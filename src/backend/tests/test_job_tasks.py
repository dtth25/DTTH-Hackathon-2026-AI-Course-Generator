"""Contract tests for durable, ID-only Celery job execution."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Barrier, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.database import Base
from app.services.job_service import cancel_job, claim_job, create_job, mark_job_succeeded


@pytest.fixture
def worker_database(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'worker.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("app.services.database.SessionLocal", factory)
    try:
        yield factory
    finally:
        engine.dispose()


def _seed_job(factory, job_type="preprocess", payload=None):
    with factory() as db:
        user = User(
            email=f"{job_type}-{id(factory)}@example.com",
            hashed_password="not-used",
            is_verified=True,
        )
        db.add(user)
        db.flush()
        course = Course(
            user_id=user.id,
            filenames=["source.txt"],
            status="processing" if job_type == "preprocess" else "ready",
        )
        db.add(course)
        db.flush()
        resolved_payload = dict(payload or {})
        resolved_payload.setdefault("course_id", course.id)
        if job_type != "preprocess":
            resolved_payload.setdefault("version_id", f"{job_type}-v1")
        job = create_job(
            db,
            course_id=course.id,
            user_id=user.id,
            job_type=job_type,
            payload_json=resolved_payload,
        )
        return job.id, course.id


def test_celery_routes_and_time_limits_are_queue_specific():
    from app.jobs.celery_app import celery_app
    from app.jobs.tasks import (
        execute_generation_job,
        execute_ingestion_job,
        execute_video_job,
    )

    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_track_started is True
    assert celery_app.conf.broker_connection_retry_on_startup is True
    assert celery_app.conf.task_routes == {
        "hackagen.execute_ingestion_job": {"queue": "ingestion"},
        "hackagen.execute_generation_job": {"queue": "generation"},
        "hackagen.execute_video_job": {"queue": "video"},
    }
    assert (execute_ingestion_job.soft_time_limit, execute_ingestion_job.time_limit) == (900, 1200)
    assert (execute_generation_job.soft_time_limit, execute_generation_job.time_limit) == (1200, 1500)
    assert (execute_video_job.soft_time_limit, execute_video_job.time_limit) == (2700, 3000)


def test_worker_process_discards_inherited_database_connections(monkeypatch):
    from app.jobs.celery_app import _dispose_inherited_connections
    from app.services import database

    dispose = Mock()
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))

    _dispose_inherited_connections()

    dispose.assert_called_once_with(close=False)


def test_succeeded_job_redelivery_does_not_invoke_processor(worker_database, monkeypatch):
    from app.jobs.tasks import execute_job

    job_id, _ = _seed_job(worker_database)
    with worker_database() as db:
        assert claim_job(db, job_id, "first-worker", 300)
        assert mark_job_succeeded(db, job_id, worker_id="first-worker")
    processor = Mock()
    monkeypatch.setattr("app.jobs.tasks.get_document_processor", lambda: processor)

    execute_job(job_id, worker_id="redelivery-worker")
    execute_job(job_id, worker_id="redelivery-worker")

    processor.process_course.assert_not_called()


def test_concurrent_delivery_invokes_processor_exactly_once(worker_database, monkeypatch):
    from app.jobs.tasks import execute_job

    job_id, _ = _seed_job(worker_database)
    processor = Mock()
    processor.list_saved_course_files.return_value = ["saved-source.txt"]
    processor.process_course.return_value = SimpleNamespace(status="ready")
    monkeypatch.setattr("app.jobs.tasks.get_document_processor", lambda: processor)
    delivery_barrier = Barrier(2)

    def deliver(worker_id):
        delivery_barrier.wait(timeout=10)
        execute_job(job_id, worker_id=worker_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(deliver, ("worker-a", "worker-b")))

    processor.process_course.assert_called_once()
    with worker_database() as db:
        job = db.get(ProcessingJob, job_id)
        assert job.status == "succeeded"
        assert job.attempts == 1


def test_preprocess_retry_clears_partial_chunks_before_upsert(worker_database, monkeypatch):
    from app.jobs.tasks import execute_job

    job_id, _ = _seed_job(worker_database)
    with worker_database() as db:
        job = db.get(ProcessingJob, job_id)
        job.attempts = 1
        db.commit()
    processor = Mock()
    processor.list_saved_course_files.return_value = ["saved-source.txt"]
    processor.process_course.return_value = SimpleNamespace(status="ready")
    monkeypatch.setattr("app.jobs.tasks.get_document_processor", lambda: processor)

    execute_job(job_id, worker_id="retry-worker")

    processor.vector_store.delete_course.assert_called_once()
    processor.process_course.assert_called_once()


def test_preprocess_chunk_ids_are_stable_and_course_scoped():
    from app.services.document_processor import DocumentProcessor

    processor = DocumentProcessor(Mock(), chunk_size=100, chunk_overlap=10)
    metadata = {"source_file": "source.txt", "page": 1}

    first = processor.chunk_text("Stable source content", metadata, "course-a")
    redelivery = processor.chunk_text("Stable source content", metadata, "course-a")
    other_course = processor.chunk_text("Stable source content", metadata, "course-b")

    assert [chunk.metadata["chunk_id"] for chunk in first] == [
        chunk.metadata["chunk_id"] for chunk in redelivery
    ]
    assert first[0].metadata["chunk_id"] != other_course[0].metadata["chunk_id"]
    assert first[0].metadata["source_chunk_id"] == first[0].metadata["chunk_id"]


@pytest.mark.parametrize(
    ("job_type", "method_name", "payload", "expected_kwargs"),
    [
        ("book", "generate_book", {"detail_level": "Chuyên sâu"}, {"detail_level": "Chuyên sâu"}),
        (
            "slides",
            "generate_slides",
            {"topic": "Trees", "num_slides": 12, "focus_prompt": "Proofs"},
            {"topic": "Trees", "num_slides": 12, "focus_prompt": "Proofs"},
        ),
        (
            "quiz",
            "generate_quiz",
            {"topic": "Trees", "quantity": 8, "difficulty": "hard"},
            {"topic": "Trees", "quantity": 8, "difficulty": "hard"},
        ),
        (
            "video",
            "generate_vid",
            {"topic": "Trees", "format": "overview", "voice": "male", "user_prompt": "Focus"},
            {"topic": "Trees", "fmt": "overview", "voice": "male", "user_prompt": "Focus"},
        ),
    ],
)
def test_artifact_job_dispatches_to_exact_generator_method(
    worker_database, monkeypatch, job_type, method_name, payload, expected_kwargs
):
    from app.jobs.tasks import execute_job

    job_id, course_id = _seed_job(worker_database, job_type, payload)
    generator = Mock()
    getattr(generator, method_name).return_value = object()
    generator.get_artifact_status.return_value = {"status": "processing"}
    monkeypatch.setattr("app.jobs.tasks.get_generator", lambda: generator)

    execute_job(job_id, worker_id="worker-a")

    call = getattr(generator, method_name).call_args
    assert call.args == ()
    assert call.kwargs["course_id"] == course_id
    assert call.kwargs["version_id"] == f"{job_type}-v1"
    assert call.kwargs["db_session_factory"] is worker_database
    assert callable(call.kwargs["progress_callback"])
    for key, value in expected_kwargs.items():
        assert call.kwargs[key] == value


def test_ready_artifact_version_is_not_regenerated(worker_database, monkeypatch):
    from app.jobs.tasks import execute_job

    version_id = "book-v1"
    job_id, course_id = _seed_job(worker_database, "book", {"version_id": version_id})
    with worker_database() as db:
        course = db.get(Course, course_id)
        course.metadata_json = json.dumps(
            {
                "study_pack": {
                    "artifacts": {
                        "book": {
                            "active": version_id,
                            "versions": {version_id: {"status": "ready"}},
                        }
                    }
                }
            }
        )
        db.commit()
    generator = Mock()
    monkeypatch.setattr("app.jobs.tasks.get_generator", lambda: generator)

    execute_job(job_id, worker_id="worker-a")

    generator.generate_book.assert_not_called()
    with worker_database() as db:
        assert db.get(ProcessingJob, job_id).status == "succeeded"


def test_generator_entrypoint_returns_ready_version_without_rewriting(
    worker_database, monkeypatch, test_upload_dir
):
    from app.services.generator import Generator

    version_id = "book-v1"
    _, course_id = _seed_job(worker_database, "book", {"version_id": version_id})
    with worker_database() as db:
        course = db.get(Course, course_id)
        course.metadata_json = json.dumps(
            {
                "study_pack": {
                    "artifacts": {
                        "book": {
                            "active": version_id,
                            "versions": {version_id: {"status": "ready"}},
                        }
                    }
                }
            }
        )
        db.commit()
    artifact_dir = Path(test_upload_dir) / course_id / "artifacts" / "book" / version_id
    artifact_dir.mkdir(parents=True)
    artifact_file = artifact_dir / "book.json"
    artifact_file.write_text(
        json.dumps({"title": "Existing", "summary": "Published", "chapters": []}),
        encoding="utf-8",
    )
    before = artifact_file.stat().st_mtime_ns
    generator = Generator(Mock(), Mock())
    start_write = Mock(side_effect=AssertionError("ready version must not start a write"))
    monkeypatch.setattr(generator, "_start_version_write", start_write)

    result = generator.generate_book(
        course_id,
        version_id=version_id,
        db_session_factory=worker_database,
    )

    assert result.title == "Existing"
    assert artifact_file.stat().st_mtime_ns == before
    start_write.assert_not_called()


def test_invalid_payload_is_terminal_and_not_retried(worker_database):
    from app.jobs.tasks import execute_job

    job_id, _ = _seed_job(worker_database)
    with worker_database() as db:
        job = db.get(ProcessingJob, job_id)
        job.payload_json = ["not", "an", "object"]
        db.commit()

    execute_job(job_id, worker_id="worker-a")
    execute_job(job_id, worker_id="worker-b")

    with worker_database() as db:
        job = db.get(ProcessingJob, job_id)
        assert job.status == "failed"
        assert job.error_code == "JOB_PAYLOAD_INVALID"
        assert job.attempts == 1


def test_cancelled_running_job_stops_at_progress_checkpoint(worker_database, monkeypatch):
    from app.jobs.tasks import execute_job

    job_id, _ = _seed_job(worker_database, "book")
    callback_seen = Lock()
    generator = Mock()
    generator.get_artifact_status.return_value = {"status": "processing"}

    def generate_book(**kwargs):
        with worker_database() as db:
            assert cancel_job(db, job_id)
        assert kwargs["progress_callback"]() is False
        callback_seen.acquire()
        return None

    generator.generate_book.side_effect = generate_book
    monkeypatch.setattr("app.jobs.tasks.get_generator", lambda: generator)

    execute_job(job_id, worker_id="worker-a")

    assert callback_seen.locked()
    with worker_database() as db:
        assert db.get(ProcessingJob, job_id).status == "cancelled"


def test_unknown_job_type_fails_without_invoking_services(worker_database, monkeypatch):
    from app.jobs.tasks import execute_job

    job_id, _ = _seed_job(worker_database)
    with worker_database() as db:
        job = db.get(ProcessingJob, job_id)
        job.job_type = "other"
        db.commit()
    processor = Mock()
    generator = Mock()
    monkeypatch.setattr("app.jobs.tasks.get_document_processor", lambda: processor)
    monkeypatch.setattr("app.jobs.tasks.get_generator", lambda: generator)

    execute_job(job_id, worker_id="worker-a")

    processor.process_course.assert_not_called()
    assert not generator.method_calls
    with worker_database() as db:
        job = db.get(ProcessingJob, job_id)
        assert job.status == "failed"
        assert job.error_code == "JOB_TYPE_UNSUPPORTED"
