"""Idempotency tests for distributed processing-job claims."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.database import Base
from app.services.job_service import (
    cancel_job,
    claim_job,
    create_job,
    dead_letter_exhausted_job,
    mark_job_cancelled,
    mark_job_failed,
    mark_job_succeeded,
    renew_job_lease,
    schedule_job_retry,
)


_external_database_url = os.getenv("TEST_DATABASE_URL")
_external_engine = (
    create_engine(_external_database_url, pool_pre_ping=True)
    if _external_database_url
    else None
)
if _external_engine is None:
    # conftest replaces this with its isolated in-memory SQLite session factory.
    from app.services.database import SessionLocal
else:
    SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=_external_engine
    )


@pytest.fixture(autouse=True)
def external_database_schema():
    """Use PostgreSQL when the task's explicit verification URL is supplied."""
    if _external_engine is None:
        yield
        return
    Base.metadata.drop_all(bind=_external_engine)
    Base.metadata.create_all(bind=_external_engine)
    yield
    Base.metadata.drop_all(bind=_external_engine)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def job_owner_and_course(db_session):
    user = User(
        email="distributed-job-owner@example.com",
        hashed_password="not-used-by-this-test",
        is_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    course = Course(user_id=user.id, filenames=["source.txt"])
    db_session.add(course)
    db_session.commit()
    return user, course


@pytest.fixture
def queued_job(db_session, job_owner_and_course):
    user, course = job_owner_and_course
    return create_job(
        db_session,
        course_id=course.id,
        user_id=user.id,
        job_type="preprocess",
    )


@pytest.fixture
def running_job(db_session, job_owner_and_course):
    user, course = job_owner_and_course
    job = create_job(
        db_session,
        course_id=course.id,
        user_id=user.id,
        job_type="preprocess",
    )
    assert claim_job(db_session, job.id, "worker-a", 300)
    db_session.refresh(job)
    return job


@pytest.fixture
def succeeded_job(db_session, job_owner_and_course):
    user, course = job_owner_and_course
    job = create_job(
        db_session,
        course_id=course.id,
        user_id=user.id,
        job_type="preprocess",
    )
    job.status = "succeeded"
    job.completed_at = datetime.utcnow()
    db_session.commit()
    db_session.refresh(job)
    return job


def test_only_one_worker_claims_a_queued_job(db_session, queued_job):
    assert claim_job(db_session, queued_job.id, "worker-a", 300) is True
    assert claim_job(db_session, queued_job.id, "worker-b", 300) is False


def test_expired_lease_allows_redelivery(db_session, running_job):
    running_job.worker_id = "dead-worker"
    running_job.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert claim_job(db_session, running_job.id, "worker-b", 300) is True
    db_session.refresh(running_job)
    assert running_job.attempts == 2


def test_expired_final_attempt_is_dead_lettered_without_rerunning(
    db_session, job_owner_and_course
):
    user, course = job_owner_and_course
    job = _distributed_job(db_session, user, course, max_attempts=1)
    assert claim_job(db_session, job.id, "worker-a", 300)
    assert not claim_job(db_session, job.id, "worker-b", 300)
    assert not dead_letter_exhausted_job(db_session, job.id)
    db_session.refresh(job)
    assert job.status == "running"
    assert job.active_key == f"preprocess:{course.id}"

    job.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    assert not claim_job(db_session, job.id, "worker-b", 300)
    db_session.refresh(job)
    assert job.status == "failed"
    assert job.attempts == 1
    assert job.worker_id is None
    assert job.lease_expires_at is None
    assert job.active_key is None
    assert job.error_code == "JOB_ATTEMPTS_EXHAUSTED"

    replacement = _distributed_job(db_session, user, course, max_attempts=1)
    assert replacement.id != job.id


def test_expired_cancelled_final_attempt_finishes_cancelled_without_rerunning(
    db_session, job_owner_and_course
):
    user, course = job_owner_and_course
    job = _distributed_job(db_session, user, course, max_attempts=1)
    assert claim_job(db_session, job.id, "worker-a", 300)
    assert cancel_job(db_session, job.id)
    job.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    assert not claim_job(db_session, job.id, "worker-b", 300)
    db_session.refresh(job)
    assert job.status == "cancelled"
    assert job.cancel_requested is True
    assert job.attempts == 1
    assert job.worker_id is None
    assert job.lease_expires_at is None
    assert job.active_key is None
    assert job.error_code is None

    replacement = _distributed_job(db_session, user, course, max_attempts=1)
    assert replacement.id != job.id


def test_succeeded_job_ignores_redelivery(db_session, succeeded_job):
    assert claim_job(db_session, succeeded_job.id, "worker-b", 300) is False


def test_claiming_sets_worker_lease_and_running_state(db_session, queued_job):
    before = datetime.utcnow()
    assert claim_job(db_session, queued_job.id, "worker-a", 300) is True
    db_session.refresh(queued_job)
    assert queued_job.status == "running"
    assert queued_job.worker_id == "worker-a"
    assert queued_job.attempts == 1
    assert queued_job.lease_expires_at >= before + timedelta(seconds=299)


def _distributed_job(db_session, user, course, **overrides):
    options = {
        "course_id": course.id,
        "user_id": user.id,
        "job_type": "preprocess",
        "payload_json": {"course_id": course.id},
    }
    options.update(overrides)
    return create_job(db_session, **options)


def test_distributed_create_deduplicates_active_operation(
    db_session, job_owner_and_course
):
    user, course = job_owner_and_course
    first = _distributed_job(db_session, user, course)
    duplicate = _distributed_job(db_session, user, course)

    assert duplicate.id == first.id
    assert first.active_key == f"preprocess:{course.id}"
    assert first.payload_json == {"course_id": course.id}
    assert first.queue_name == "ingestion"


def test_unique_insert_race_recovers_existing_job_via_savepoint(
    db_session, job_owner_and_course, monkeypatch
):
    user, course = job_owner_and_course
    existing = _distributed_job(db_session, user, course)
    real_scalar = db_session.scalar
    preflight_calls = 0

    def simulate_raced_preflight(statement, *args, **kwargs):
        nonlocal preflight_calls
        preflight_calls += 1
        if preflight_calls == 1:
            return None
        return real_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "scalar", simulate_raced_preflight)
    raced = _distributed_job(db_session, user, course)

    assert raced.id == existing.id
    assert preflight_calls == 2


def test_explicit_active_key_collision_cannot_cross_ownership(
    db_session, job_owner_and_course
):
    first_user, first_course = job_owner_and_course
    first = create_job(
        db_session,
        course_id=first_course.id,
        user_id=first_user.id,
        job_type="preprocess",
        active_key="caller-supplied-key",
    )
    second_user = User(
        email="second-distributed-job-owner@example.com",
        hashed_password="not-used-by-this-test",
        is_verified=True,
    )
    db_session.add(second_user)
    db_session.flush()
    second_course = Course(user_id=second_user.id, filenames=["other.txt"])
    db_session.add(second_course)
    db_session.commit()

    with pytest.raises(IntegrityError):
        create_job(
            db_session,
            course_id=second_course.id,
            user_id=second_user.id,
            job_type="preprocess",
            active_key="caller-supplied-key",
        )

    assert db_session.get(ProcessingJob, first.id).user_id == first_user.id


def test_artifact_active_key_includes_stable_version(
    db_session, job_owner_and_course
):
    user, course = job_owner_and_course
    job = _distributed_job(
        db_session,
        user,
        course,
        job_type="book",
        payload_json={"course_id": course.id, "version_id": "book-v1"},
    )

    assert job.active_key == f"book:{course.id}:book-v1"
    assert job.queue_name == "generation"


def test_lease_renewal_requires_current_worker(db_session, running_job):
    old_expiry = running_job.lease_expires_at
    assert not renew_job_lease(db_session, running_job.id, "worker-b", 600)
    assert renew_job_lease(db_session, running_job.id, "worker-a", 600)
    db_session.refresh(running_job)
    assert running_job.lease_expires_at > old_expiry

    running_job.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert not renew_job_lease(db_session, running_job.id, "worker-a", 600)


def test_retry_cannot_be_claimed_before_backoff_is_due(
    db_session, job_owner_and_course
):
    user, course = job_owner_and_course
    job = _distributed_job(db_session, user, course)
    assert claim_job(db_session, job.id, "worker-a", 300)
    retry_at = datetime.utcnow() + timedelta(minutes=5)
    assert schedule_job_retry(db_session, job.id, "worker-a", retry_at)

    assert not claim_job(db_session, job.id, "worker-b", 300)
    db_session.refresh(job)
    assert job.status == "retry_scheduled"
    assert job.attempts == 1

    job.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert claim_job(db_session, job.id, "worker-b", 300)
    db_session.refresh(job)
    assert job.status == "running"
    assert job.attempts == 2
    assert job.worker_id == "worker-b"


def test_retry_releases_worker_and_refuses_exhausted_attempts(
    db_session, job_owner_and_course
):
    user, course = job_owner_and_course
    job = _distributed_job(db_session, user, course, max_attempts=2)
    assert claim_job(db_session, job.id, "worker-a", 300)
    retry_at = datetime.utcnow() + timedelta(seconds=30)

    assert not schedule_job_retry(
        db_session, job.id, "worker-b", retry_at
    )
    assert schedule_job_retry(db_session, job.id, "worker-a", retry_at)
    db_session.refresh(job)
    assert job.status == "retry_scheduled"
    assert job.worker_id is None
    assert job.lease_expires_at is None
    assert job.next_attempt_at == retry_at

    job.next_attempt_at = None
    db_session.commit()
    assert claim_job(db_session, job.id, "worker-b", 300)
    assert not schedule_job_retry(db_session, job.id, "worker-b", retry_at)


def test_worker_terminal_updates_are_owner_guarded_and_release_active_key(
    db_session, job_owner_and_course
):
    user, course = job_owner_and_course
    succeeded = _distributed_job(db_session, user, course)
    assert claim_job(db_session, succeeded.id, "worker-a", 300)
    assert not mark_job_succeeded(
        db_session, succeeded.id, worker_id="worker-b"
    )
    assert mark_job_succeeded(db_session, succeeded.id, worker_id="worker-a")
    db_session.refresh(succeeded)
    assert succeeded.status == "succeeded"
    assert succeeded.active_key is None

    fresh = _distributed_job(db_session, user, course)
    assert fresh.id != succeeded.id
    assert claim_job(db_session, fresh.id, "worker-b", 300)
    assert not mark_job_failed(
        db_session,
        fresh.id,
        worker_id="worker-a",
        error_code="TEST_FAILURE",
        message="Thử nghiệm thất bại.",
    )
    assert mark_job_failed(
        db_session,
        fresh.id,
        worker_id="worker-b",
        error_code="TEST_FAILURE",
        message="Thử nghiệm thất bại.",
    )
    db_session.refresh(fresh)
    assert fresh.status == "failed"
    assert fresh.active_key is None


def test_cancellation_is_immediate_before_claim_and_cooperative_while_running(
    db_session, job_owner_and_course
):
    user, course = job_owner_and_course
    queued = _distributed_job(db_session, user, course)
    assert cancel_job(db_session, queued.id)
    db_session.refresh(queued)
    assert queued.status == "cancelled"
    assert queued.cancel_requested is True
    assert queued.active_key is None
    assert not claim_job(db_session, queued.id, "worker-a", 300)

    retrying = _distributed_job(db_session, user, course)
    assert claim_job(db_session, retrying.id, "worker-a", 300)
    retry_at = datetime.utcnow() + timedelta(seconds=30)
    assert schedule_job_retry(
        db_session, retrying.id, "worker-a", retry_at
    )
    assert cancel_job(db_session, retrying.id)
    db_session.refresh(retrying)
    assert retrying.status == "cancelled"
    assert retrying.next_attempt_at is None

    running = _distributed_job(db_session, user, course)
    assert claim_job(db_session, running.id, "worker-a", 300)
    assert cancel_job(db_session, running.id)
    db_session.refresh(running)
    assert running.status == "running"
    assert running.cancel_requested is True
    assert not renew_job_lease(db_session, running.id, "worker-a", 600)
    retry_at = datetime.utcnow() + timedelta(seconds=30)
    assert not schedule_job_retry(
        db_session, running.id, "worker-a", retry_at
    )
    assert not mark_job_succeeded(
        db_session, running.id, worker_id="worker-a"
    )
    assert not mark_job_failed(
        db_session,
        running.id,
        worker_id="worker-a",
        error_code="TOO_LATE",
        message="Không được ghi đè yêu cầu hủy.",
    )
    assert not mark_job_cancelled(db_session, running.id, "worker-b")
    assert mark_job_cancelled(db_session, running.id, "worker-a")
    db_session.refresh(running)
    assert running.status == "cancelled"
    assert running.active_key is None


def test_two_concurrent_claim_threads_produce_one_winner(
    db_session, job_owner_and_course, tmp_path
):
    user, course = job_owner_and_course
    job = _distributed_job(db_session, user, course)
    job_id = job.id
    barrier = Barrier(2)

    if _external_engine is None:
        concurrent_engine = create_engine(
            f"sqlite:///{tmp_path / 'claims.db'}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        Base.metadata.create_all(bind=concurrent_engine)
        ConcurrentSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=concurrent_engine
        )
        with ConcurrentSessionLocal() as seed_db:
            concurrent_user = User(
                email="concurrent-job-owner@example.com",
                hashed_password="not-used-by-this-test",
            )
            seed_db.add(concurrent_user)
            seed_db.flush()
            concurrent_course = Course(
                user_id=concurrent_user.id, filenames=["source.txt"]
            )
            seed_db.add(concurrent_course)
            seed_db.commit()
            job_id = _distributed_job(
                seed_db, concurrent_user, concurrent_course
            ).id
    else:
        concurrent_engine = _external_engine
        ConcurrentSessionLocal = SessionLocal

    def claim(worker_id):
        with ConcurrentSessionLocal() as worker_db:
            barrier.wait(timeout=10)
            return claim_job(worker_db, job_id, worker_id, 300)

    with ThreadPoolExecutor(max_workers=2) as executor:
        winners = list(executor.map(claim, ["worker-a", "worker-b"]))

    assert sorted(winners) == [False, True]
    if _external_engine is None:
        concurrent_engine.dispose()
