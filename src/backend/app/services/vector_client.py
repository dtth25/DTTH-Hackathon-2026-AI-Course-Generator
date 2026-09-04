"""Construct and health-check the configured Chroma client."""

import logging
from typing import Any

import chromadb
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ChromaConnectionError(RuntimeError):
    """The configured Chroma service is not reachable."""


def _chroma_heartbeat_url(settings_obj: Any) -> str:
    host = str(settings_obj.CHROMA_HOST).strip().rstrip("/")
    if host.startswith(("http://", "https://")):
        base_url = host
    else:
        scheme = "https" if settings_obj.CHROMA_SSL else "http"
        url_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        base_url = f"{scheme}://{url_host}:{settings_obj.CHROMA_PORT}"
    if base_url.endswith("/api/v2"):
        return f"{base_url}/heartbeat"
    return f"{base_url}/api/v2/heartbeat"


def chroma_http_ready(*, settings_obj: Any = settings) -> bool:
    """Probe Chroma over a public HTTPX boundary with a bounded timeout."""
    try:
        with httpx.Client(
            timeout=settings_obj.CHROMA_TIMEOUT_SECONDS,
            trust_env=False,
        ) as client:
            response = client.get(_chroma_heartbeat_url(settings_obj))
            response.raise_for_status()
            payload = response.json()
            int(payload["nanosecond heartbeat"])
    except Exception as exc:
        logger.warning("Chroma HTTP readiness probe failed: %s", type(exc).__name__)
        return False
    return True


def build_chroma_client(
    *, persist_directory: str | None = None, settings_obj: Any = settings
) -> Any:
    """Build exactly one configured Chroma client without storage fallback."""
    if settings_obj.CHROMA_MODE == "embedded":
        if settings_obj.ENVIRONMENT == "production":
            raise ValueError("production requires CHROMA_MODE=http")
        return chromadb.PersistentClient(
            path=persist_directory or settings_obj.CHROMA_PERSIST_DIR
        )

    if not chroma_http_ready(settings_obj=settings_obj):
        raise ChromaConnectionError("Chroma HTTP service is unavailable")
    try:
        return chromadb.HttpClient(
            host=settings_obj.CHROMA_HOST,
            port=settings_obj.CHROMA_PORT,
            ssl=settings_obj.CHROMA_SSL,
        )
    except Exception as exc:
        raise ChromaConnectionError("Chroma HTTP service is unavailable") from exc


def chroma_client_ready(client: Any, *, settings_obj: Any = settings) -> bool:
    """Return false when the configured client cannot answer a heartbeat."""
    if settings_obj.CHROMA_MODE == "http":
        return chroma_http_ready(settings_obj=settings_obj)
    try:
        client.heartbeat()
    except Exception as exc:
        logger.warning("Chroma heartbeat failed: %s", type(exc).__name__)
        return False
    return True
