"""Admission and backpressure tests for durable processing jobs."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.jobs.admission import (
    GlobalJobLimitExceeded,
    UserJobLimitExceeded,
    enforce_job_admission,
)
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.database import Base, SessionLocal
from app.services.job_service import create_job


@pytest.fixture
def db_session():
    with SessionLocal() as db:
        yield db


def _add_owner_and_course(db, *, suffix="owner"):
    user = User(
        email=f"admission-{suffix}@example.com",
        hashed_password="not-used-by-this-test",
        is_verified=True,
    )
    db.add(user)
    db.flush()
    course = Course(user_id=user.id, filenames=["source.txt"])
    db.add(course)
    db.flush()
    return user, course


def _add_jobs(db, *, user_id, course_id, statuses):
    db.add_all(
        ProcessingJob(
            user_id=user_id,
            course_id=course_id,
            job_type="preprocess",
            status=status,
        )
        for status in statuses
    )
    db.commit()


def test_four_non_terminal_user_jobs_reject_another(db_session):
    user, course = _add_owner_and_course(db_session)
    _add_jobs(
        db_session,
        user_id=user.id,
        course_id=course.id,
        statuses=["queued", "retry_scheduled", "running", "queued"],
    )

    with pytest.raises(UserJobLimitExceeded) as caught:
        enforce_job_admission(db_session, user.id)

    assert caught.value.retry_after == 30
    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "30"}
    assert caught.value.detail["code"] == "USER_JOB_LIMIT_EXCEEDED"


def test_two_hundred_non_terminal_global_jobs_reject_another(db_session):
    for index in range(50):
        user, course = _add_owner_and_course(db_session, suffix=f"global-{index}")
        for status in ("queued", "retry_scheduled", "running", "queued"):
            db_session.add(
                ProcessingJob(
                    user_id=user.id,
                    course_id=course.id,
                    job_type="preprocess",
                    status=status,
                )
            )
    new_user, _ = _add_owner_and_course(db_session, suffix="global-new")
    db_session.commit()

    with pytest.raises(GlobalJobLimitExceeded) as caught:
        enforce_job_admission(db_session, new_user.id)

    assert caught.value.retry_after == 60
    assert caught.value.status_code == 503
    assert caught.value.headers == {"Retry-After": "60"}
    assert caught.value.detail["code"] == "GLOBAL_JOB_LIMIT_EXCEEDED"


def test_terminal_jobs_do_not_count_toward_admission(db_session):
    user, course = _add_owner_and_course(db_session)
    _add_jobs(
        db_session,
        user_id=user.id,
        course_id=course.id,
        statuses=["succeeded", "failed", "cancelled", "succeeded"],
    )

    enforce_job_admission(db_session, user.id)
    created = create_job(
        db_session,
        course_id=course.id,
        user_id=user.id,
        job_type="preprocess",
    )

    assert created.status == "queued"


def test_postgresql_advisory_locks_are_global_then_user():
    statements = []

    class FakeSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement, parameters=None):
            statements.append((str(statement), parameters))

        def scalar(self, statement):
            return 0

    enforce_job_admission(FakeSession(), "user-123")

    assert statements == [
        (
            "SELECT pg_advisory_xact_lock(hashtext('hackagen:jobs:global'))",
            None,
        ),
        (
            "SELECT pg_advisory_xact_lock(hashtext('hackagen:jobs:user:' || :user_id))",
            {"user_id": "user-123"},
        ),
    ]


def test_five_concurrent_same_user_requests_accept_exactly_four(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'admission.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    concurrent_session = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    Base.metadata.create_all(bind=engine)
    with concurrent_session() as seed_db:
        user, course = _add_owner_and_course(seed_db, suffix="concurrent")
        seed_db.commit()
        user_id = user.id
        course_id = course.id

    barrier = Barrier(5)

    def submit(_request_number):
        with concurrent_session() as db:
            barrier.wait(timeout=10)
            try:
                enforce_job_admission(db, user_id)
                create_job(
                    db,
                    course_id=course_id,
                    user_id=user_id,
                    job_type="preprocess",
                )
            except UserJobLimitExceeded:
                db.rollback()
                return False
            return True

    with ThreadPoolExecutor(max_workers=5) as executor:
        accepted = list(executor.map(submit, range(5)))

    with concurrent_session() as verify_db:
        persisted = verify_db.query(ProcessingJob).count()
    engine.dispose()

    assert accepted.count(True) == 4
    assert accepted.count(False) == 1
    assert persisted == 4
