"""Model-level contracts for durable generation jobs."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.course import Course
from app.models.generation_job import (
    ArtifactType,
    GenerationJob,
    JobQueue,
    JobState,
)
from app.models.user import User
from app.services.database import SessionLocal
from app.services.job_service import (
    DuplicateActiveJobError,
    InvalidJobTransition,
    JobCancelled,
    JobCapacityError,
    JobNotFound,
    JobService,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fixed_clock():
    values = [datetime(2026, 9, 3, 4, 0, tzinfo=UTC)]

    def now():
        return values[0]

    now.advance = lambda **kwargs: values.__setitem__(
        0, values[0] + timedelta(**kwargs)
    )
    return now


def _limits(*, total: int = 20, video: int = 6, stale: int = 90):
    return SimpleNamespace(
        MAX_ACTIVE_JOBS=total,
        MAX_ACTIVE_VIDEO_JOBS=video,
        JOB_HEARTBEAT_STALE_SECONDS=stale,
    )


def _owned_course(db, suffix: str = "default") -> tuple[User, Course]:
    user = User(
        id=f"job-user-{suffix}",
        email=f"job-{suffix}@example.com",
        hashed_password="not-used",
        is_verified=True,
    )
    course = Course(
        id=f"job-course-{suffix}",
        user_id=user.id,
        filenames=["lesson.pdf"],
        status="ready",
        stage="completed",
    )
    db.add_all([user, course])
    db.commit()
    return user, course


def _job(user: User, course: Course, **overrides) -> GenerationJob:
    values = {
        "course_id": course.id,
        "user_id": user.id,
        "artifact_type": ArtifactType.BOOK.value,
        "version_id": "book-version-1",
        "queue_name": JobQueue.GENERATION.value,
        "payload_json": {"length": "standard"},
    }
    values.update(overrides)
    return GenerationJob(**values)


def test_generation_job_defaults_and_deterministic_task_id() -> None:
    db = SessionLocal()
    try:
        user, course = _owned_course(db)
        job = _job(user, course)
        db.add(job)
        db.commit()
        db.refresh(job)

        assert job.id
        assert job.celery_task_id == job.id
        assert job.state == JobState.QUEUED.value
        assert job.progress == 0
        assert job.stage == "queued"
        assert job.attempt == 0
        assert job.max_attempts == 3
        assert job.dispatch_attempts == 0
        assert job.error_code is None
        assert job.error_message is None
        assert job.cancel_requested_at is None
        assert job.created_at.tzinfo is not None
        assert job.created_at.utcoffset() == UTC.utcoffset(job.created_at)
        assert job.updated_at.tzinfo is not None
    finally:
        db.close()


def test_generation_job_preserves_ownership_and_replay_payload() -> None:
    db = SessionLocal()
    try:
        user, course = _owned_course(db, "ownership")
        job = _job(user, course)
        db.add(job)
        db.commit()
        db.refresh(job)

        assert job.user_id == user.id
        assert job.course_id == course.id
        assert job.version_id == "book-version-1"
        assert job.payload_json == {"length": "standard"}
    finally:
        db.close()


def test_only_one_active_job_per_course_artifact() -> None:
    db = SessionLocal()
    try:
        user, course = _owned_course(db, "active-unique")
        db.add(_job(user, course, state=JobState.QUEUED.value))
        db.commit()

        db.add(
            _job(
                user,
                course,
                id="second-active-job",
                version_id="book-version-2",
                state=JobState.RUNNING.value,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_terminal_job_does_not_block_a_new_active_job() -> None:
    db = SessionLocal()
    try:
        user, course = _owned_course(db, "terminal")
        db.add(_job(user, course, state=JobState.SUCCEEDED.value))
        db.commit()

        db.add(
            _job(
                user,
                course,
                id="new-active-job",
                version_id="book-version-2",
                state=JobState.QUEUED.value,
            )
        )
        db.commit()
    finally:
        db.close()


def test_job_enum_values_are_stable_strings() -> None:
    assert [state.value for state in JobState] == [
        "queued",
        "running",
        "retrying",
        "succeeded",
        "failed",
        "cancelled",
    ]
    assert [kind.value for kind in ArtifactType] == [
        "ingestion",
        "book",
        "slides",
        "quiz",
        "vid",
    ]
    assert [queue.value for queue in JobQueue] == [
        "ingestion",
        "generation",
        "video",
    ]


def test_total_capacity_is_enforced_transactionally(db, fixed_clock) -> None:
    service = JobService(db, _limits(total=2), fixed_clock)
    for suffix in ("capacity-1", "capacity-2"):
        user, course = _owned_course(db, suffix)
        service.enqueue(course, ArtifactType.BOOK.value, {})

    user, course = _owned_course(db, "capacity-3")
    with pytest.raises(JobCapacityError) as exc_info:
        service.enqueue(course, ArtifactType.QUIZ.value, {})
    assert exc_info.value.code == "artifact_capacity_reached"


def test_video_capacity_is_enforced_separately(db, fixed_clock) -> None:
    service = JobService(db, _limits(total=20, video=1), fixed_clock)
    user, course = _owned_course(db, "video-1")
    service.enqueue(course, ArtifactType.VID.value, {})

    user, course = _owned_course(db, "video-2")
    with pytest.raises(JobCapacityError) as exc_info:
        service.enqueue(course, ArtifactType.VID.value, {})
    assert exc_info.value.code == "video_capacity_reached"


def test_duplicate_active_generation_has_stable_error(db, fixed_clock) -> None:
    service = JobService(db, _limits(), fixed_clock)
    user, course = _owned_course(db, "duplicate")
    service.enqueue(course, ArtifactType.BOOK.value, {})

    with pytest.raises(DuplicateActiveJobError) as exc_info:
        service.enqueue(course, ArtifactType.BOOK.value, {})
    assert exc_info.value.code == "generation_in_flight"


def test_summary_is_owner_filtered_and_queue_position_is_best_effort(
    db, fixed_clock
) -> None:
    service = JobService(db, _limits(), fixed_clock)
    first_user, first_course = _owned_course(db, "queue-1")
    first = service.enqueue(first_course, ArtifactType.BOOK.value, {})
    fixed_clock.advance(seconds=1)
    second_user, second_course = _owned_course(db, "queue-2")
    second = service.enqueue(second_course, ArtifactType.QUIZ.value, {})

    assert service.get_summary(first.id, first_user.id).queue_position == 1
    assert service.get_summary(second.id, second_user.id).queue_position == 2
    with pytest.raises(JobNotFound):
        service.get_summary(first.id, second_user.id)


def test_terminal_job_cannot_return_to_running(db, fixed_clock) -> None:
    service = JobService(db, _limits(), fixed_clock)
    user, course = _owned_course(db, "terminal-transition")
    job = service.enqueue(course, ArtifactType.BOOK.value, {})
    service.start(job.id, job.celery_task_id)
    service.fail(job.id, "invalid_output", "Output failed validation")

    with pytest.raises(InvalidJobTransition):
        service.start(job.id, job.celery_task_id)


def test_heartbeat_throttles_same_stage_but_records_boundaries(db, fixed_clock) -> None:
    service = JobService(db, _limits(), fixed_clock)
    user, course = _owned_course(db, "heartbeat")
    job = service.enqueue(course, ArtifactType.BOOK.value, {})
    service.start(job.id, job.celery_task_id)

    assert service.heartbeat(job.id, stage="retrieving", progress=10) is True
    fixed_clock.advance(seconds=1)
    assert service.heartbeat(job.id, stage="retrieving", progress=11) is False
    assert job.progress == 10
    assert service.heartbeat(job.id, stage="drafting", progress=20) is True
    fixed_clock.advance(seconds=2)
    assert service.heartbeat(job.id, stage="drafting", progress=25) is True
    assert job.progress == 25


def test_cancellation_is_durable_for_queued_and_running_jobs(db, fixed_clock) -> None:
    service = JobService(db, _limits(), fixed_clock)
    queued_user, queued_course = _owned_course(db, "cancel-queued")
    queued = service.enqueue(queued_course, ArtifactType.BOOK.value, {})
    summary = service.request_cancel(queued.id, queued_user.id)
    assert summary.state == JobState.CANCELLED.value
    assert summary.can_cancel is False

    running_user, running_course = _owned_course(db, "cancel-running")
    running = service.enqueue(running_course, ArtifactType.QUIZ.value, {})
    service.start(running.id, running.celery_task_id)
    summary = service.request_cancel(running.id, running_user.id)
    assert summary.state == JobState.RUNNING.value
    assert summary.can_cancel is False
    with pytest.raises(JobCancelled):
        service.heartbeat(running.id, stage="drafting", progress=50)


def test_stale_recovery_retries_then_fails_at_attempt_limit(db, fixed_clock) -> None:
    service = JobService(db, _limits(stale=90), fixed_clock)
    user, course = _owned_course(db, "stale-retry")
    retry_job = service.enqueue(course, ArtifactType.BOOK.value, {}, max_attempts=2)
    service.start(retry_job.id, retry_job.celery_task_id)

    user, course = _owned_course(db, "stale-fail")
    failed_job = service.enqueue(course, ArtifactType.VID.value, {}, max_attempts=1)
    service.start(failed_job.id, failed_job.celery_task_id)
    fixed_clock.advance(seconds=91)

    recovered = service.recover_stale_jobs()
    assert {job.id for job in recovered} == {retry_job.id, failed_job.id}
    assert retry_job.state == JobState.RETRYING.value
    assert failed_job.state == JobState.FAILED.value
    assert failed_job.error_code == "worker_lost"


def test_pending_dispatches_include_never_sent_and_stale_rows(db, fixed_clock) -> None:
    service = JobService(db, _limits(), fixed_clock)
    user, course = _owned_course(db, "dispatch")
    job = service.enqueue(course, ArtifactType.BOOK.value, {})

    assert [item.id for item in service.find_pending_dispatches()] == [job.id]
    service.record_dispatch(job.id)
    assert service.find_pending_dispatches() == []
    fixed_clock.advance(seconds=11)
    assert [item.id for item in service.find_pending_dispatches()] == [job.id]


def test_success_is_idempotent_and_errors_are_bounded(db, fixed_clock) -> None:
    service = JobService(db, _limits(), fixed_clock)
    user, course = _owned_course(db, "success")
    job = service.enqueue(course, ArtifactType.BOOK.value, {})
    service.start(job.id, job.celery_task_id)

    first = service.succeed(job.id)
    finished_at = first.finished_at
    fixed_clock.advance(minutes=1)
    second = service.succeed(job.id)
    assert second.finished_at == finished_at
    assert second.progress == 100

    user, course = _owned_course(db, "error-bounds")
    failed = service.enqueue(course, ArtifactType.QUIZ.value, {})
    service.start(failed.id, failed.celery_task_id)
    service.fail(failed.id, "provider_error", "bad\x00" + "x" * 600)
    assert "\x00" not in failed.error_message
    assert len(failed.error_message) == 500
