"""Construct and health-check the configured Chroma client."""

import logging
from typing import Any

import chromadb

from app.core.config import settings

logger = logging.getLogger(__name__)


class ChromaConnectionError(RuntimeError):
    """The configured Chroma service is not reachable."""


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

    return chromadb.HttpClient(
        host=settings_obj.CHROMA_HOST,
        port=settings_obj.CHROMA_PORT,
        ssl=settings_obj.CHROMA_SSL,
    )


def chroma_client_ready(client: Any) -> bool:
    """Return false when the configured client cannot answer a heartbeat."""
    try:
        client.heartbeat()
    except Exception as exc:
        logger.warning("Chroma heartbeat failed: %s", type(exc).__name__)
        return False
    return True
