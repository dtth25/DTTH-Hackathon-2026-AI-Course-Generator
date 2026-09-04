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
from psycopg import sql
from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.engine import make_url
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


def _migration_command(source: Path, target_url: str) -> list[str]:
    return [
        sys.executable,
        str(MIGRATION_SCRIPT),
        "--source-sqlite",
        str(source),
        "--target-postgres",
        target_url,
        "--confirm",
        "MIGRATE",
    ]


def _run_migration(source: Path, target_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _migration_command(source, target_url),
        cwd=BACKEND_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )


def _reset_postgres_schema(target_engine) -> None:
    with target_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def _assert_no_sensitive_output(result: subprocess.CompletedProcess[str]) -> None:
    output = result.stdout + result.stderr
    for secret in (
        "person-0@example.com",
        "correct-horse-battery-staple",
        "sensitive-otp-hash-0",
        "payload-0",
    ):
        assert secret not in output


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for live PostgreSQL migration verification",
)
def test_sqlite_migration_is_id_preserving_rerunnable_and_source_safe(tmp_path):
    target_url = os.environ["TEST_DATABASE_URL"]
    target_engine = create_engine(target_url)
    _reset_postgres_schema(target_engine)

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
    try:
        first = subprocess.run(
            _migration_command(source, target_url),
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        second = subprocess.run(
            _migration_command(source, target_url),
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

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
        _assert_no_sensitive_output(first)
        _assert_no_sensitive_output(second)

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


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for live PostgreSQL migration verification",
)
def test_percent_encoded_postgresql_credentials_reach_alembic(tmp_path):
    admin_url = os.environ["TEST_DATABASE_URL"]
    admin_engine = create_engine(admin_url)
    role = "task6_encoded_user"
    password = "p%ss:word@reserved/path"
    source = tmp_path / "encoded-source.db"
    _seed_sqlite(source)

    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
        if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}):
            connection.exec_driver_sql(f"DROP OWNED BY {role}")
            connection.exec_driver_sql(f"DROP ROLE {role}")
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
        database_name = connection.scalar(text("SELECT current_database()"))
        quoted_database = connection.dialect.identifier_preparer.quote(database_name)
        connection.exec_driver_sql(
            f"GRANT CONNECT, CREATE ON DATABASE {quoted_database} TO {role}"
        )
        connection.exec_driver_sql(f"CREATE SCHEMA public AUTHORIZATION {role}")

    encoded_url = make_url(admin_url).set(username=role, password=password).render_as_string(hide_password=False)
    assert "%" in encoded_url
    encoded_engine = create_engine(encoded_url)
    with encoded_engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1
    encoded_engine.dispose()
    result = _run_migration(source, encoded_url)

    try:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert "users: source=2 inserted=2 target=2" in result.stdout
        _assert_no_sensitive_output(result)
        assert password not in result.stdout + result.stderr
    finally:
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
            if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}):
                connection.exec_driver_sql(f"DROP OWNED BY {role}")
                connection.exec_driver_sql(f"DROP ROLE {role}")
            connection.exec_driver_sql("CREATE SCHEMA public")
        admin_engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for live PostgreSQL migration verification",
)
def test_mismatched_user_primary_key_aborts_without_dependents_or_leakage(tmp_path):
    target_url = os.environ["TEST_DATABASE_URL"]
    target_engine = create_engine(target_url)
    _reset_postgres_schema(target_engine)
    source = tmp_path / "user-conflict.db"
    _seed_sqlite(source)
    assert _run_migration(source, target_url).returncode == 0

    with target_engine.begin() as connection:
        connection.execute(delete(ProcessingJob))
        connection.execute(delete(EmailOtpCode))
        connection.execute(delete(Course))
        connection.execute(delete(User).where(User.id == "user-1"))
        connection.execute(
            update(User)
            .where(User.id == "user-0")
            .values(email="different-owner@example.com", hashed_password="different-hash")
        )

    result = _run_migration(source, target_url)
    try:
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr == (
            "Migration aborted because an existing row differs from the source\n"
        )
        _assert_no_sensitive_output(result)
        assert "different-owner@example.com" not in result.stdout + result.stderr
        assert "different-hash" not in result.stdout + result.stderr
        with target_engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(User)) == 1
            assert connection.scalar(select(func.count()).select_from(Course)) == 0
            assert connection.scalar(select(func.count()).select_from(EmailOtpCode)) == 0
            assert connection.scalar(select(func.count()).select_from(ProcessingJob)) == 0
    finally:
        _reset_postgres_schema(target_engine)
        target_engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for live PostgreSQL migration verification",
)
def test_mismatched_course_primary_key_rolls_back_all_dependents(tmp_path):
    target_url = os.environ["TEST_DATABASE_URL"]
    target_engine = create_engine(target_url)
    _reset_postgres_schema(target_engine)
    source = tmp_path / "course-conflict.db"
    _seed_sqlite(source)
    assert _run_migration(source, target_url).returncode == 0

    with target_engine.begin() as connection:
        connection.execute(delete(ProcessingJob))
        connection.execute(delete(EmailOtpCode))
        connection.execute(delete(Course).where(Course.id == "course-1"))
        connection.execute(
            update(Course).where(Course.id == "course-0").values(user_id="user-1")
        )

    result = _run_migration(source, target_url)
    try:
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr == (
            "Migration aborted because an existing row differs from the source\n"
        )
        _assert_no_sensitive_output(result)
        with target_engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(User)) == 2
            assert connection.scalar(select(func.count()).select_from(Course)) == 1
            assert connection.scalar(select(Course.user_id).where(Course.id == "course-0")) == "user-1"
            assert connection.scalar(select(func.count()).select_from(EmailOtpCode)) == 0
            assert connection.scalar(select(func.count()).select_from(ProcessingJob)) == 0
    finally:
        _reset_postgres_schema(target_engine)
        target_engine.dispose()
