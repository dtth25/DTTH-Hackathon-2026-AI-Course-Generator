"""Cached, secret-free OpenRouter availability preflight for administrators."""

from datetime import UTC, datetime
import threading
import time
from typing import Any, Optional

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.services.provider_errors import ProviderErrorCode, classify_openrouter_error


OPENROUTER_API_BASE_URL = "https://openrouter.ai/api/v1"


class ProviderHealth(BaseModel):
    """The deliberately small, safe provider status returned to administrators."""

    available: bool
    error_code: Optional[str]
    checked_at: datetime
    limit: Optional[float]
    limit_remaining: Optional[float]
    limit_reset: Optional[str]
    content_model_available: bool
    embedding_model_available: bool


_cached_health: Optional[ProviderHealth] = None
_cached_at = 0.0
_cache_lock = threading.Lock()


def _safe_number(value: object) -> Optional[float]:
    """Return JSON numeric values only, excluding bool which is not a quota."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _model_ids(payload: object) -> set[str]:
    """Validate the documented list response shape instead of guessing at variants."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("OpenRouter model response did not contain a data list")

    result: set[str] = set()
    for item in payload["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("OpenRouter model response contained an invalid model")
        result.add(item["id"])
    return result


def _unavailable_health(
    error_code: str,
    *,
    limit: Optional[float] = None,
    limit_remaining: Optional[float] = None,
    limit_reset: Optional[str] = None,
) -> ProviderHealth:
    return ProviderHealth(
        available=False,
        error_code=error_code,
        checked_at=datetime.now(UTC),
        limit=limit,
        limit_remaining=limit_remaining,
        limit_reset=limit_reset,
        content_model_available=False,
        embedding_model_available=False,
    )


def _request(path: str) -> object:
    """Fetch and decode one preflight endpoint without retaining its raw payload."""
    response = httpx.get(
        f"{OPENROUTER_API_BASE_URL}{path}",
        headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
        timeout=settings.OPENROUTER_PREFLIGHT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _check_openrouter_health() -> ProviderHealth:
    try:
        key_payload = _request("/key")
        if not isinstance(key_payload, dict) or not isinstance(key_payload.get("data"), dict):
            raise ValueError("OpenRouter key response did not contain a data object")

        key_data: dict[str, Any] = key_payload["data"]
        limit = _safe_number(key_data.get("limit"))
        limit_remaining = _safe_number(key_data.get("limit_remaining"))
        limit_reset_value = key_data.get("limit_reset")
        limit_reset = limit_reset_value if isinstance(limit_reset_value, str) else None

        if key_data.get("limit_remaining") is not None and limit_remaining is None:
            raise ValueError("OpenRouter key response contained an invalid limit_remaining")
        if limit_remaining is not None and limit_remaining <= 0:
            return _unavailable_health(
                ProviderErrorCode.KEY_LIMIT_EXCEEDED,
                limit=limit,
                limit_remaining=limit_remaining,
                limit_reset=limit_reset,
            )

        content_models = _model_ids(_request("/models"))
        embedding_models = _model_ids(_request("/embeddings/models"))
        content_model_available = settings.OPENROUTER_MODEL in content_models
        embedding_model_available = settings.OPENROUTER_EMBEDDING_MODEL in embedding_models
        if not content_model_available or not embedding_model_available:
            return ProviderHealth(
                available=False,
                error_code=ProviderErrorCode.REQUEST_FAILED,
                checked_at=datetime.now(UTC),
                limit=limit,
                limit_remaining=limit_remaining,
                limit_reset=limit_reset,
                content_model_available=content_model_available,
                embedding_model_available=embedding_model_available,
            )

        return ProviderHealth(
            available=True,
            error_code=None,
            checked_at=datetime.now(UTC),
            limit=limit,
            limit_remaining=limit_remaining,
            limit_reset=limit_reset,
            content_model_available=True,
            embedding_model_available=True,
        )
    except Exception as exc:
        # The classifier maps HTTP and transport failures to stable, secret-free codes.
        # No exception text or provider response is retained in the cache or API result.
        return _unavailable_health(str(classify_openrouter_error(exc).code))


def get_openrouter_health(force: bool = False) -> ProviderHealth:
    """Return cached preflight state until the configured monotonic TTL expires."""
    global _cached_at, _cached_health

    with _cache_lock:
        now = time.monotonic()
        if (
            not force
            and _cached_health is not None
            and now - _cached_at < settings.OPENROUTER_PREFLIGHT_TTL_SECONDS
        ):
            return _cached_health

        _cached_health = _check_openrouter_health()
        _cached_at = now
        return _cached_health
