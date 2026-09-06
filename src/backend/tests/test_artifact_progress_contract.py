import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.database import Base
from app.services.generator import Generator
from app.services.job_service import claim_job


@pytest.fixture
def progress_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'progress.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(User(id="progress-user", email="progress@example.com", hashed_password="unused"))
        db.add(Course(id="progress-course", user_id="progress-user", status="ready", metadata_json="{}"))
        for artifact in ("book", "quiz"):
            db.add(ProcessingJob(
                id=f"{artifact}-job", course_id="progress-course", user_id="progress-user",
                job_type=artifact, status="running", progress=0, attempts=1,
                worker_id=f"{artifact}-worker",
                lease_expires_at=datetime.utcnow() + timedelta(minutes=10),
                payload_json={"version_id": f"{artifact}-v1"},
            ))
        db.commit()
    try:
        yield factory
    finally:
        engine.dispose()


def _write(factory, artifact="book", progress=52, **overrides):
    values = {
        "course_id": "progress-course", "artifact": artifact, "status": "processing",
        "progress": progress, "version_id": f"{artifact}-v1", "job_id": f"{artifact}-job",
        "worker_id": f"{artifact}-worker", "attempt_number": 1,
        "db_session_factory": factory,
    }
    values.update(overrides)
    return Generator(None, None)._set_artifact_status(**values)


def _state(factory, artifact="book"):
    with factory() as db:
        course = db.get(Course, "progress-course")
        metadata = json.loads(course.metadata_json)
        entry = metadata.get("study_pack", {}).get("artifacts", {}).get(artifact)
        progress = None if entry is None else entry["versions"][f"{artifact}-v1"]["progress"]
        return db.get(ProcessingJob, f"{artifact}-job").progress, progress


def test_progress_is_committed_to_job_and_artifact_atomically(progress_database):
    written = _write(progress_database)
    job_progress, artifact_progress = _state(progress_database)

    assert written
    assert job_progress == artifact_progress == 52


@pytest.mark.parametrize("mutation", ["expired", "stale", "cancelled"])
def test_stale_claim_changes_neither_representation(progress_database, mutation):
    with progress_database() as db:
        job = db.get(ProcessingJob, "book-job")
        if mutation == "expired":
            job.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        elif mutation == "stale":
            job.attempts = 2
        else:
            job.cancel_requested = True
        db.commit()

    assert not _write(progress_database)
    assert _state(progress_database) == (0, None)


def test_commit_error_rolls_back_both_representations(progress_database, monkeypatch):
    original_commit = progress_database.class_.commit
    monkeypatch.setattr(progress_database.class_, "commit", lambda _self: (_ for _ in ()).throw(RuntimeError("commit failed")))
    try:
        assert not _write(progress_database)
    finally:
        monkeypatch.setattr(progress_database.class_, "commit", original_commit)
    assert _state(progress_database) == (0, None)


def test_regressive_progress_remains_equal_and_monotonic(progress_database):
    assert _write(progress_database, progress=70)
    assert _write(progress_database, progress=52)
    assert _state(progress_database) == (70, 70)


def test_expired_lease_reclaim_resets_progress_for_new_attempt(progress_database):
    assert _write(progress_database, progress=90)
    with progress_database() as db:
        job = db.get(ProcessingJob, "book-job")
        job.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        assert claim_job(db, "book-job", "replacement-worker", 300)
        assert db.get(ProcessingJob, "book-job").progress == 0

    assert not _write(progress_database, progress=95)
    assert _write(
        progress_database,
        progress=5,
        worker_id="replacement-worker",
        attempt_number=2,
    )
    assert _state(progress_database) == (5, 5)


def test_concurrent_artifacts_preserve_both_entries(progress_database):
    barrier = Barrier(2)

    def update_artifact(args):
        artifact, progress = args
        barrier.wait(timeout=10)
        return _write(progress_database, artifact=artifact, progress=progress)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update_artifact, (("book", 41), ("quiz", 67))))

    assert results == [True, True]
    assert _state(progress_database, "book") == (41, 41)
    assert _state(progress_database, "quiz") == (67, 67)
