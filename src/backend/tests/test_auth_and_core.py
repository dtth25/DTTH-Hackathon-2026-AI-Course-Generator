"""Automated tests for Core Infrastructure, Authentication, and CORS."""

import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import Settings, settings
from app.core.security import create_access_token
from app.services.database import create_database_engine
from main import app


@pytest.fixture
def base_settings() -> dict[str, object]:
    """Required settings isolated from the developer's environment."""
    return {
        "_env_file": None,
        "DATABASE_URL": "sqlite:///app.db",
        "JWT_SECRET": "test-jwt-secret",
        "OPENROUTER_API_KEY": "test-openrouter-key",
    }


def test_production_rejects_sqlite(base_settings: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(
            **{
                **base_settings,
                "APP_ENV": "production",
                "DATABASE_URL": "sqlite:///app.db",
            }
        )


def test_job_capacity_must_cover_video_capacity(
    base_settings: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="MAX_ACTIVE_JOBS"):
        Settings(
            **{
                **base_settings,
                "MAX_ACTIVE_JOBS": 5,
                "MAX_ACTIVE_VIDEO_JOBS": 6,
            }
        )


def test_production_accepts_postgresql(base_settings: dict[str, object]) -> None:
    configured = Settings(
        **{
            **base_settings,
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:password@db/hackagen",
        }
    )

    assert configured.APP_ENV == "production"


def test_postgresql_engine_uses_bounded_pool_settings(
    base_settings: dict[str, object],
) -> None:
    isolated_settings = Settings(
        **{
            **base_settings,
            "DATABASE_POOL_SIZE": 7,
            "DATABASE_MAX_OVERFLOW": 9,
            "DATABASE_POOL_TIMEOUT_SECONDS": 2,
        }
    )
    database_engine = create_database_engine(
        "postgresql+psycopg://user:password@localhost/hackagen",
        isolated_settings,
    )
    try:
        assert isinstance(database_engine.pool, QueuePool)
        assert database_engine.pool.size() == 7
        assert database_engine.pool._max_overflow == 9
        assert database_engine.pool.timeout() == 2
        assert database_engine.pool._recycle == 1800
        assert database_engine.pool._pre_ping is True
    finally:
        database_engine.dispose()


def test_sqlite_memory_engine_keeps_static_pool(
    base_settings: dict[str, object],
) -> None:
    isolated_settings = Settings(**base_settings)
    database_engine = create_database_engine(
        "sqlite:///:memory:", isolated_settings
    )
    try:
        assert isinstance(database_engine.pool, StaticPool)
    finally:
        database_engine.dispose()


@pytest.mark.asyncio
async def test_blocking_auth_query_does_not_block_liveness(monkeypatch) -> None:
    """Synchronous ORM work in auth must run outside the event-loop thread."""
    release_query = threading.Event()
    query_started = threading.Event()
    monkeypatch.setattr(settings, "JWT_SECRET", "test-jwt-secret-at-least-32-bytes")

    class BlockingQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            query_started.set()
            if not release_query.wait(timeout=2):
                raise AssertionError("Blocking ORM probe was not released")
            return SimpleNamespace(
                id="probe-user",
                email="probe@example.com",
                full_name="Probe User",
                is_active=True,
                is_verified=True,
                role="user",
                created_at=None,
            )

    def blocking_query(_session, _model):
        return BlockingQuery()

    monkeypatch.setattr(Session, "query", blocking_query)
    token = create_access_token({"sub": "probe-user"})
    release_timer = threading.Timer(1, release_query.set)
    release_timer.start()

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as async_client:
            protected_request = asyncio.create_task(
                async_client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
            )
            assert await asyncio.to_thread(query_started.wait, 1)

            liveness_response = await async_client.get("/")

            assert liveness_response.status_code == 200
            assert not release_query.is_set(), (
                "Liveness only answered after the blocked ORM query was released"
            )
            release_query.set()
            assert (await protected_request).status_code == 200
    finally:
        release_query.set()
        release_timer.cancel()


def test_health_check(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_register_does_not_auto_login(client):
    """Register must NOT issue a token/cookie anymore — the account is unverified
    until /verify-email succeeds."""
    reg_data = {
        "email": "testuser@example.com",
        "password": "secretpassword123",
        "full_name": "Test User",
    }
    response = client.post("/api/auth/register", json=reg_data)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert "access_token" not in data
    assert settings.AUTH_COOKIE_NAME not in response.cookies

    # Login before verifying must be blocked
    login_res = client.post(
        "/api/auth/login",
        json={"email": "testuser@example.com", "password": "secretpassword123"},
    )
    assert login_res.status_code == 403
    assert login_res.json()["detail"]["code"] == "email_not_verified"


def test_auth_verify_email_wrong_then_right_code(client):
    reg_data = {
        "email": "verifyuser@example.com",
        "password": "secretpassword123",
        "full_name": "Verify User",
    }
    client.post("/api/auth/register", json=reg_data)

    wrong = client.post(
        "/api/auth/verify-email", json={"email": "verifyuser@example.com", "code": "999999"}
    )
    assert wrong.status_code == 400
    assert "không đúng" in wrong.json()["detail"]

    right = client.post(
        "/api/auth/verify-email", json={"email": "verifyuser@example.com", "code": "000000"}
    )
    assert right.status_code == 200, right.text
    data = right.json()
    assert "access_token" in data
    assert data["user"]["is_verified"] is True
    assert settings.AUTH_COOKIE_NAME in right.cookies

    # Now login works normally
    login_res = client.post(
        "/api/auth/login",
        json={"email": "verifyuser@example.com", "password": "secretpassword123"},
    )
    assert login_res.status_code == 200


def test_auth_forgot_and_reset_password(client):
    reg_data = {
        "email": "resetuser@example.com",
        "password": "oldpassword123",
        "full_name": "Reset User",
    }
    client.post("/api/auth/register", json=reg_data)
    client.post("/api/auth/verify-email", json={"email": "resetuser@example.com", "code": "000000"})

    forgot_res = client.post("/api/auth/forgot-password", json={"email": "resetuser@example.com"})
    assert forgot_res.status_code == 200

    reset_res = client.post(
        "/api/auth/reset-password",
        json={"email": "resetuser@example.com", "code": "000000", "new_password": "newpassword456"},
    )
    assert reset_res.status_code == 200

    old_login = client.post(
        "/api/auth/login", json={"email": "resetuser@example.com", "password": "oldpassword123"}
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login", json={"email": "resetuser@example.com", "password": "newpassword456"}
    )
    assert new_login.status_code == 200


def _register_and_verify(client, email: str, password: str = "password123") -> str:
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/verify-email", json={"email": email, "code": "000000"})
    return res.json()["access_token"]


def test_auth_login_and_cookie_flow(client):
    # Setup user
    _register_and_verify(client, "loginuser@example.com", "loginpassword123")

    # 1. Login with credentials
    login_data = {
        "email": "loginuser@example.com",
        "password": "loginpassword123",
    }
    response = client.post("/api/auth/login", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

    # Check cookie
    cookie_val = response.cookies.get(settings.AUTH_COOKIE_NAME)
    assert cookie_val is not None

    # 2. Get me using ONLY the HttpOnly cookie (no Authorization header)
    client.cookies.set(settings.AUTH_COOKIE_NAME, cookie_val)
    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "loginuser@example.com"


def test_auth_logout_blacklist(client):
    # Setup and login
    token = _register_and_verify(client, "logoutuser@example.com", "password123")

    # Verify access works
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 200
    )

    # Logout
    logout_res = client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["detail"] == "Đăng xuất thành công."

    # Verify token is now blacklisted and rejected
    me_after_logout = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_after_logout.status_code == 401
    assert "Phiên đăng nhập đã bị hủy" in me_after_logout.json()["detail"]


def test_delete_account_wrong_password(client):
    token = _register_and_verify(client, "deletewrong@example.com", "password123")
    res = client.request(
        "DELETE",
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "not-the-right-password"},
    )
    assert res.status_code == 401


def test_delete_account_purges_everything(client):
    from app.models.course import Course
    from app.models.email_otp import EmailOtpCode
    from app.models.generation_job import ArtifactType, GenerationJob, JobQueue
    from app.models.user import User
    from app.services.database import SessionLocal

    token = _register_and_verify(client, "deleteme@example.com", "password123")
    headers = {"Authorization": f"Bearer {token}"}

    course_res = client.post("/api/courses", headers=headers, json={"filenames": ["doc.pdf"]})
    assert course_res.status_code == 201

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "deleteme@example.com").first()
        assert user is not None
        user_id = user.id
        course = db.query(Course).filter(Course.user_id == user_id).one()
        db.add(
            GenerationJob(
                course_id=course.id,
                user_id=user_id,
                artifact_type=ArtifactType.BOOK.value,
                version_id="account-delete-version",
                queue_name=JobQueue.GENERATION.value,
                payload_json={},
            )
        )
        db.commit()
    finally:
        db.close()

    del_res = client.request(
        "DELETE", "/api/auth/me", headers=headers, json={"password": "password123"}
    )
    assert del_res.status_code == 200, del_res.text

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.id == user_id).first() is None
        assert db.query(Course).filter(Course.user_id == user_id).count() == 0
        assert db.query(EmailOtpCode).filter(EmailOtpCode.user_id == user_id).count() == 0
        assert db.query(GenerationJob).filter(GenerationJob.user_id == user_id).count() == 0
    finally:
        db.close()

    # The token used to delete the account must be blacklisted immediately.
    me_after = client.get("/api/auth/me", headers=headers)
    assert me_after.status_code == 401


def test_cors_headers(client):
    # Test preflight OPTIONS request
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    response = client.options("/api/auth/login", headers=headers)
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "http://localhost:3000"
    )
    assert response.headers.get("access-control-allow-credentials") == "true"
