"""Tests for the cached, redacted OpenRouter provider preflight."""

from datetime import UTC, datetime
from unittest.mock import Mock

import httpx
import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.services.database import SessionLocal
from app.services.provider_health import ProviderHealth, get_openrouter_health


class FakeResponse:
    """Small httpx response substitute that never makes a network request."""

    def __init__(self, status_code: int, payload: object):
        self.status_code = status_code
        self._payload = payload
        self.request = httpx.Request("GET", "https://openrouter.ai/api/v1/key")

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}", request=self.request, response=self
            )


class FakeHttpx:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


@pytest.fixture
def fake_httpx(monkeypatch) -> FakeHttpx:
    fake = FakeHttpx(
        [
            FakeResponse(
                200,
                {
                    "data": {
                        "label": "sk-or-v1-test-key",
                        "hash": "secret-key-hash",
                        "limit": 10,
                        "limit_remaining": 5.5,
                        "usage": 4.5,
                        "limit_reset": "monthly",
                    }
                },
            ),
            FakeResponse(200, {"data": [{"id": "google/gemini-2.5-pro"}]}),
            FakeResponse(200, {"data": [{"id": "openai/text-embedding-3-small"}]}),
        ]
    )
    monkeypatch.setattr("app.services.provider_health.httpx.get", fake.get)
    monkeypatch.setattr("app.services.provider_health._cached_health", None)
    monkeypatch.setattr("app.services.provider_health._cached_at", 0.0)
    return fake


def test_provider_health_reports_zero_remaining_without_secret(fake_httpx, monkeypatch):
    fake_httpx.responses = [
        FakeResponse(
            200,
            {
                "data": {
                    "label": "sk-or-v1-super-secret",
                    "hash": "raw-key-hash",
                    "limit": 10,
                    "limit_remaining": 0,
                    "usage": 10.05,
                    "limit_reset": None,
                }
            },
        )
    ]

    health = get_openrouter_health(force=True)

    assert health.available is False
    assert health.error_code == "OPENROUTER_KEY_LIMIT_EXCEEDED"
    assert health.limit_remaining == 0
    assert set(health.model_dump()) == {
        "available",
        "error_code",
        "checked_at",
        "limit",
        "limit_remaining",
        "limit_reset",
        "content_model_available",
        "embedding_model_available",
    }
    serialized = health.model_dump_json()
    for secret in ("sk-or", "super-secret", "raw-key-hash"):
        assert secret not in serialized
    assert fake_httpx.call_count == 1


def test_provider_health_uses_ttl_cache(fake_httpx):
    get_openrouter_health(force=True)
    get_openrouter_health()

    assert fake_httpx.call_count == 3


def test_provider_health_caches_from_preflight_completion_time(fake_httpx, monkeypatch):
    monotonic_values = iter((100.0, 190.0, 190.0))
    monkeypatch.setattr("app.services.provider_health.time.monotonic", lambda: next(monotonic_values))

    get_openrouter_health(force=True)
    get_openrouter_health()

    assert fake_httpx.call_count == 3


def test_provider_health_checks_distinct_key_and_model_response_shapes(fake_httpx):
    health = get_openrouter_health(force=True)

    assert health.available is True
    assert health.error_code is None
    assert health.content_model_available is True
    assert health.embedding_model_available is True
    assert [url for url, _ in fake_httpx.calls] == [
        "https://openrouter.ai/api/v1/key",
        "https://openrouter.ai/api/v1/models",
        "https://openrouter.ai/api/v1/embeddings/models",
    ]


def test_provider_health_fails_closed_when_model_payload_is_not_a_data_list(fake_httpx):
    fake_httpx.responses[1] = FakeResponse(200, {"data": {"id": "google/gemini-2.5-pro"}})

    health = get_openrouter_health(force=True)

    assert health.available is False
    assert health.error_code == "OPENROUTER_REQUEST_FAILED"
    assert health.content_model_available is False
    assert health.embedding_model_available is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("limit", float("nan")),
        ("limit_remaining", float("inf")),
        ("usage", float("-inf")),
    ],
    ids=("nan-limit", "positive-infinity-remaining", "negative-infinity-usage"),
)
def test_provider_health_rejects_non_finite_key_capacity_values(fake_httpx, field, value):
    fake_httpx.responses = [
        FakeResponse(
            200,
            {
                "data": {
                    "limit": 10,
                    "limit_remaining": 5.5,
                    "usage": 4.5,
                    field: value,
                }
            },
        )
    ]

    health = get_openrouter_health(force=True)

    assert health.available is False
    assert health.error_code == "OPENROUTER_REQUEST_FAILED"
    assert fake_httpx.call_count == 1


def test_provider_health_uses_task_one_classifier_for_request_failures(fake_httpx, monkeypatch):
    request = httpx.Request("GET", "https://openrouter.ai/api/v1/key")

    def raise_timeout(*args: object, **kwargs: object) -> FakeResponse:
        raise httpx.ReadTimeout("request timed out", request=request)

    monkeypatch.setattr("app.services.provider_health.httpx.get", raise_timeout)

    health = get_openrouter_health(force=True)

    assert health.available is False
    assert health.error_code == "OPENROUTER_TIMEOUT"
    assert "timed out" not in health.model_dump_json()


def _create_user_token(email: str, role: str) -> str:
    db = SessionLocal()
    try:
        user = User(
            email=email,
            hashed_password=get_password_hash("password123"),
            role=role,
            is_verified=True,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return create_access_token({"sub": user.id})
    finally:
        db.close()


def test_provider_health_endpoint_is_admin_only_and_serializes_only_safe_fields(client, monkeypatch):
    normal_token = _create_user_token("provider-user@example.com", "user")
    forbidden = client.get(
        "/api/admin/provider-health", headers={"Authorization": f"Bearer {normal_token}"}
    )
    assert forbidden.status_code == 403

    checked_at = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    safe_health = ProviderHealth(
        available=True,
        error_code=None,
        checked_at=checked_at,
        limit=10,
        limit_remaining=5.5,
        limit_reset="monthly",
        content_model_available=True,
        embedding_model_available=True,
    )
    health_lookup = Mock(return_value=safe_health)
    monkeypatch.setattr("app.routers.admin.get_openrouter_health", health_lookup)
    admin_token = _create_user_token("provider-admin@example.com", "admin")

    response = client.get(
        "/api/admin/provider-health?force=true", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    health_lookup.assert_called_once_with(force=True, reset_circuit=True)
    body = response.json()
    assert set(body) == {
        "available",
        "error_code",
        "checked_at",
        "limit",
        "limit_remaining",
        "limit_reset",
        "content_model_available",
        "embedding_model_available",
    }
    serialized = response.text
    for forbidden_field in ("key", "hash", "token", "authorization", "technical", "raw"):
        assert forbidden_field not in serialized.casefold()
