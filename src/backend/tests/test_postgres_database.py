"""Production database configuration and SQLite migration contracts."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import Response
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.security import get_password_hash
from app.models import Course, EmailOtpCode, ProcessingJob, User
from app.schemas.user import UserLogin
from app.services import database


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_SCRIPT = BACKEND_DIR / "scripts" / "migrate_sqlite_to_postgres.py"


def _settings_values(**overrides):
    values = {
        "DATABASE_URL": "sqlite:///:memory:",
        "JWT_SECRET": "test-secret",
        "OPENROUTER_API_KEY": "test-key",
    }
    values.update(overrides)
    return values


def test_production_rejects_sqlite_database_url():
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(
            **_settings_values(
                ENVIRONMENT="production",
                JOB_QUEUE_PROVIDER="celery",
            )
        )

    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(
            **_settings_values(
                DATABASE_URL="postgresql-not-a-real-dialect://db/app",
                ENVIRONMENT="production",
                JOB_QUEUE_PROVIDER="celery",
            )
        )


def test_postgresql_engine_uses_bounded_pool_settings():
    configured = Settings(
        **_settings_values(DATABASE_URL="postgresql+psycopg://user:pass@db/app")
    )

    engine = database.create_database_engine(configured)
    try:
        assert engine.pool.size() == 10
        assert engine.pool._max_overflow == 20
        assert engine.pool.timeout() == 30
        assert engine.pool._recycle == 1800
        assert engine.pool._pre_ping is True
    finally:
        engine.dispose()


def test_worker_child_disposes_inherited_connections_before_first_session(monkeypatch):
    from app.jobs import celery_app

    events: list[str] = []
    inherited_engine = Mock()
    inherited_engine.dispose.side_effect = lambda **_: events.append("dispose")
    first_session = Mock(side_effect=lambda: events.append("session"))
    monkeypatch.setattr(database, "engine", inherited_engine)
    monkeypatch.setattr(database, "SessionLocal", first_session)

    celery_app._dispose_inherited_connections()
    database.SessionLocal()

    inherited_engine.dispose.assert_called_once_with(close=False)
    assert events == ["dispose", "session"]


def test_migration_guard_rejects_wrong_confirmation_before_schema_change(tmp_path, monkeypatch):
    from scripts import migrate_sqlite_to_postgres as migration

    source = tmp_path / "source.db"
    source.touch()
    upgrade = Mock()
    monkeypatch.setattr(migration, "upgrade_target_schema", upgrade)

    result = migration.main(
        [
            "--source-sqlite",
            str(source),
            "--target-postgres",
            "postgresql+psycopg://user:pass@db/app",
            "--confirm",
            "NO",
        ]
    )

    assert result == 2
    upgrade.assert_not_called()


def test_migration_guard_rejects_non_postgresql_target(tmp_path, monkeypatch):
    from scripts import migrate_sqlite_to_postgres as migration

    source = tmp_path / "source.db"
    source.touch()
    upgrade = Mock()
    monkeypatch.setattr(migration, "upgrade_target_schema", upgrade)

    result = migration.main(
        [
            "--source-sqlite",
            str(source),
            "--target-postgres",
            "sqlite:///target.db",
            "--confirm",
            "MIGRATE",
        ]
    )

    assert result == 2
    upgrade.assert_not_called()


def _seed_sqlite(source: Path) -> None:
    engine = create_engine(f"sqlite:///{source.as_posix()}")
    database.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    password_hash = get_password_hash("correct-horse-battery-staple")
    now = datetime.utcnow()
    with session_factory.begin() as db:
        for index in range(2):
            user_id = f"user-{index}"
            course_id = f"course-{index}"
            db.add(
                User(
                    id=user_id,
                    email=f"person-{index}@example.com",
                    hashed_password=password_hash,
                    full_name=f"Person {index}",
                    is_verified=True,
                )
            )
            db.add(Course(id=course_id, user_id=user_id, filenames=[f"doc-{index}.txt"]))
            db.add(
                EmailOtpCode(
                    id=f"otp-{index}",
                    user_id=user_id,
                    purpose="reset_password",
                    code_hash=f"sensitive-otp-hash-{index}",
                    expires_at=now + timedelta(minutes=10),
                )
            )
            db.add(
                ProcessingJob(
                    id=f"job-{index}",
                    course_id=course_id,
                    user_id=user_id,
                    job_type="preprocess",
                    payload_json={"secret": f"payload-{index}"},
                    active_key=f"preprocess:{course_id}",
                )
            )
    engine.dispose()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for live PostgreSQL migration verification",
)
def test_sqlite_migration_is_id_preserving_rerunnable_and_source_safe(tmp_path):
    target_url = os.environ["TEST_DATABASE_URL"]
    target_engine = create_engine(target_url)
    with target_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    source = tmp_path / "source.db"
    backup = tmp_path / "source.backup.db"
    _seed_sqlite(source)
    shutil.copy2(source, backup)
    original_hash = _file_hash(backup)

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": target_url,
            "JWT_SECRET": "postgres-test-secret",
            "OPENROUTER_API_KEY": "postgres-test-key",
            "ENVIRONMENT": "test",
            "JOB_QUEUE_PROVIDER": "inline",
        }
    )
    command = [
        sys.executable,
        str(MIGRATION_SCRIPT),
        "--source-sqlite",
        str(source),
        "--target-postgres",
        target_url,
        "--confirm",
        "MIGRATE",
    ]

    try:
        first = subprocess.run(command, cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=False)
        second = subprocess.run(command, cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=False)

        assert first.returncode == 0, first.stderr
        assert second.returncode == 0, second.stderr
        assert first.stderr == ""
        assert second.stderr == ""
        assert first.stdout.splitlines() == [
            "users: source=2 inserted=2 target=2",
            "courses: source=2 inserted=2 target=2",
            "email_otp_codes: source=2 inserted=2 target=2",
            "processing_jobs: source=2 inserted=2 target=2",
        ]
        assert second.stdout.splitlines() == [
            "users: source=2 inserted=0 target=2",
            "courses: source=2 inserted=0 target=2",
            "email_otp_codes: source=2 inserted=0 target=2",
            "processing_jobs: source=2 inserted=0 target=2",
        ]
        assert _file_hash(source) == original_hash
        combined_output = first.stdout + first.stderr + second.stdout + second.stderr
        for secret in (
            "person-0@example.com",
            "correct-horse-battery-staple",
            "sensitive-otp-hash-0",
            "payload-0",
        ):
            assert secret not in combined_output

        target_session = sessionmaker(bind=target_engine)
        with target_session() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 2
            assert db.scalar(select(func.count()).select_from(Course)) == 2
            assert db.scalar(select(func.count()).select_from(EmailOtpCode)) == 2
            assert db.scalar(select(func.count()).select_from(ProcessingJob)) == 2
            assert set(db.scalars(select(User.id))) == {"user-0", "user-1"}
            assert set(db.scalars(select(Course.id))) == {"course-0", "course-1"}
            assert set(db.scalars(select(EmailOtpCode.id))) == {"otp-0", "otp-1"}
            assert set(db.scalars(select(ProcessingJob.id))) == {"job-0", "job-1"}
            assert db.scalar(select(Course.user_id).where(Course.id == "course-1")) == "user-1"
            assert db.scalar(select(ProcessingJob.course_id).where(ProcessingJob.id == "job-1")) == "course-1"

            from app.routers.auth import login

            result = login(
                UserLogin(email="person-1@example.com", password="correct-horse-battery-staple"),
                Response(),
                db,
            )
            assert result["user"].id == "user-1"
    finally:
        shutil.copy2(backup, source)
        assert _file_hash(source) == original_hash
        with target_engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        target_engine.dispose()
