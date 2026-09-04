"""Contract tests for queue-neutral job dispatch."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import BackgroundTasks
from pydantic import ValidationError

from app.core.config import Settings
from app.jobs.dispatcher import (
    AmbiguousJobDispatchError,
    CeleryJobDispatcher,
    DefiniteJobDispatchError,
    InlineJobDispatcher,
    execute_job,
    get_job_dispatcher,
)


@pytest.fixture
def background_tasks():
    return BackgroundTasks()


@pytest.fixture
def fake_celery():
    client = Mock()
    client.send_task.return_value = SimpleNamespace(id="celery-external-id")
    return client


def _settings_values(**overrides):
    values = {
        "DATABASE_URL": "sqlite:///:memory:",
        "JWT_SECRET": "test-secret",
        "OPENROUTER_API_KEY": "test-key",
    }
    values.update(overrides)
    return values


def test_inline_dispatcher_schedules_id_only(background_tasks):
    dispatcher = InlineJobDispatcher(background_tasks)
    external_id = dispatcher.enqueue("job-1", "ingestion")

    assert external_id == "inline:job-1"
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is execute_job
    assert background_tasks.tasks[0].args == ("job-1",)
    assert background_tasks.tasks[0].kwargs == {}


def test_inline_executor_schedules_bounded_id_only_redispatch(monkeypatch):
    from app.jobs import dispatcher

    run_job = Mock(
        return_value=SimpleNamespace(queue_name="ingestion", countdown=999)
    )
    timer = Mock()
    timer_factory = Mock(return_value=timer)
    monkeypatch.setattr("app.jobs.tasks.execute_job", run_job)
    monkeypatch.setattr(dispatcher, "Timer", timer_factory, raising=False)

    dispatcher.execute_job("job-inline-retry")

    run_job.assert_called_once_with("job-inline-retry")
    timer_factory.assert_called_once_with(
        300,
        dispatcher.execute_job,
        args=("job-inline-retry",),
    )
    assert timer.daemon is True
    timer.start.assert_called_once_with()


def test_celery_dispatcher_routes_video_separately(fake_celery):
    dispatcher = CeleryJobDispatcher(fake_celery)
    external_id = dispatcher.enqueue("job-2", "video")

    fake_celery.send_task.assert_called_once_with(
        "hackagen.execute_video_job",
        args=["job-2"],
        queue="video",
        task_id="job-2",
    )
    assert external_id == "celery-external-id"


def test_dispatchers_classify_local_registration_and_transport_failures():
    background_tasks = Mock()
    background_tasks.add_task.side_effect = RuntimeError("local registration failed")
    with pytest.raises(DefiniteJobDispatchError):
        InlineJobDispatcher(background_tasks).enqueue("job-local", "ingestion")

    celery = Mock()
    celery.send_task.side_effect = ConnectionError("acceptance is unknown")
    with pytest.raises(AmbiguousJobDispatchError):
        CeleryJobDispatcher(celery).enqueue("job-remote", "generation")


@pytest.mark.parametrize(
    ("queue_name", "task_name"),
    [
        ("ingestion", "hackagen.execute_ingestion_job"),
        ("generation", "hackagen.execute_generation_job"),
        ("video", "hackagen.execute_video_job"),
    ],
)
def test_celery_dispatcher_maps_each_queue_to_an_id_only_task(
    fake_celery, queue_name, task_name
):
    dispatcher = CeleryJobDispatcher(fake_celery)

    dispatcher.enqueue("job-3", queue_name)

    fake_celery.send_task.assert_called_once_with(
        task_name,
        args=["job-3"],
        queue=queue_name,
        task_id="job-3",
    )


def test_dispatchers_reject_unknown_queue(background_tasks, fake_celery):
    with pytest.raises(ValueError, match="Unsupported job queue"):
        InlineJobDispatcher(background_tasks).enqueue("job-4", "unknown")
    with pytest.raises(ValueError, match="Unsupported job queue"):
        CeleryJobDispatcher(fake_celery).enqueue("job-4", "unknown")


def test_get_job_dispatcher_uses_inline_default(background_tasks, monkeypatch):
    monkeypatch.setattr("app.jobs.dispatcher.settings.JOB_QUEUE_PROVIDER", "inline")

    dispatcher = get_job_dispatcher(background_tasks)

    assert isinstance(dispatcher, InlineJobDispatcher)


def test_get_job_dispatcher_uses_celery_without_contacting_broker(
    fake_celery, monkeypatch
):
    celery_module = ModuleType("app.jobs.celery_app")
    celery_module.celery_app = fake_celery
    monkeypatch.setitem(sys.modules, "app.jobs.celery_app", celery_module)
    monkeypatch.setattr("app.jobs.dispatcher.settings.JOB_QUEUE_PROVIDER", "celery")

    dispatcher = get_job_dispatcher()

    assert isinstance(dispatcher, CeleryJobDispatcher)
    assert dispatcher._celery_app is fake_celery


def test_local_queue_defaults_are_bounded_and_inline():
    configured = Settings(**_settings_values())

    assert configured.ENVIRONMENT == "local"
    assert configured.JOB_QUEUE_PROVIDER == "inline"
    assert configured.REDIS_URL == "redis://localhost:6379/0"
    assert configured.MAX_PENDING_JOBS_PER_USER == 4
    assert configured.MAX_PENDING_JOBS_GLOBAL == 200
    assert configured.JOB_LEASE_SECONDS == 3600


def test_production_requires_celery_queue_provider():
    with pytest.raises(ValidationError, match="JOB_QUEUE_PROVIDER"):
        Settings(
            **_settings_values(
                ENVIRONMENT="production",
                JOB_QUEUE_PROVIDER="inline",
            )
        )
