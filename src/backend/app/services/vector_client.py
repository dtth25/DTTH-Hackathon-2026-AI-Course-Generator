"""Construct bounded embedded or HTTP Chroma clients."""

import logging
from typing import Any
from urllib.parse import quote

import chromadb
import httpx
from chromadb.api.models.Collection import Collection
from chromadb.api.types import (
    DefaultEmbeddingFunction,
    convert_np_embeddings_to_list,
    deserialize_metadata,
    serialize_metadata,
)
from chromadb.config import DEFAULT_DATABASE, DEFAULT_TENANT
from chromadb.types import Collection as CollectionModel

from app.core.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_FUNCTION = DefaultEmbeddingFunction()


class ChromaConnectionError(RuntimeError):
    """The configured Chroma service is not reachable."""


def _chroma_api_url(settings_obj: Any) -> str:
    host = str(settings_obj.CHROMA_HOST).strip().rstrip("/")
    if host.startswith(("http://", "https://")):
        base_url = host
    else:
        scheme = "https" if settings_obj.CHROMA_SSL else "http"
        url_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        base_url = f"{scheme}://{url_host}:{settings_obj.CHROMA_PORT}"
    return base_url if base_url.endswith("/api/v2") else f"{base_url}/api/v2"


class BoundedChromaHttpClient:
    """Chroma v2 client using one bounded, no-ambient-proxy transport.

    Chroma 1.5.9's public synchronous HttpClient hard-codes ``timeout=None`` and
    offers no transport injection. This adapter retains Chroma's public Collection
    model (including its validation and embedding behavior) while owning the HTTP
    boundary used by every operation required by VectorStore.
    """

    def __init__(self, *, settings_obj: Any = settings) -> None:
        self.tenant = DEFAULT_TENANT
        self.database = DEFAULT_DATABASE
        self._api_url = _chroma_api_url(settings_obj)
        self._http = httpx.Client(
            timeout=settings_obj.CHROMA_TIMEOUT_SECONDS,
            trust_env=False,
            headers={"Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._http.close()

    def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> Any:
        try:
            response = self._http.request(
                method,
                f"{self._api_url}{path}",
                json=json,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except Exception as exc:
            logger.warning("Chroma HTTP request failed: %s", type(exc).__name__)
            raise ChromaConnectionError("Chroma HTTP service is unavailable") from exc

    def heartbeat(self) -> int:
        payload = self._request("GET", "/heartbeat")
        try:
            return int(payload["nanosecond heartbeat"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ChromaConnectionError("Chroma HTTP service is unavailable") from exc

    def get_or_create_collection(
        self,
        name: str,
        *,
        embedding_function: Any = _DEFAULT_EMBEDDING_FUNCTION,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> Collection:
        payload = self._request(
            "POST",
            f"/tenants/{quote(self.tenant, safe='')}/databases/"
            f"{quote(self.database, safe='')}/collections",
            json={
                "name": name,
                "metadata": metadata,
                "configuration": None,
                "schema": None,
                "get_or_create": True,
            },
        )
        return Collection(
            client=self,
            model=CollectionModel.from_json(payload),
            embedding_function=embedding_function,
        )

    def get_collection(
        self,
        name: str,
        *,
        embedding_function: Any = _DEFAULT_EMBEDDING_FUNCTION,
        **_: Any,
    ) -> Collection:
        payload = self._request(
            "GET",
            f"/tenants/{quote(self.tenant, safe='')}/databases/"
            f"{quote(self.database, safe='')}/collections/{quote(name, safe='')}",
        )
        return Collection(
            client=self,
            model=CollectionModel.from_json(payload),
            embedding_function=embedding_function,
        )

    def _upsert(
        self,
        *,
        collection_id: Any,
        ids: list[str],
        embeddings: Any,
        metadatas: list[dict[str, Any]] | None = None,
        documents: list[str] | None = None,
        uris: list[str] | None = None,
        tenant: str = DEFAULT_TENANT,
        database: str = DEFAULT_DATABASE,
    ) -> bool:
        serialized_metadatas = (
            [serialize_metadata(item) if item is not None else None for item in metadatas]
            if metadatas is not None
            else None
        )
        self._request(
            "POST",
            self._collection_operation_path(
                tenant, database, collection_id, "upsert"
            ),
            json={
                "ids": ids,
                "embeddings": convert_np_embeddings_to_list(embeddings),
                "metadatas": serialized_metadatas,
                "documents": documents,
                "uris": uris,
            },
        )
        return True

    def _query(
        self,
        *,
        collection_id: Any,
        query_embeddings: Any,
        ids: list[str] | None = None,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
        include: list[str] | None = None,
        tenant: str = DEFAULT_TENANT,
        database: str = DEFAULT_DATABASE,
    ) -> dict[str, Any]:
        included = include or ["metadatas", "documents", "distances"]
        payload = self._request(
            "POST",
            self._collection_operation_path(
                tenant, database, collection_id, "query"
            ),
            json={
                "ids": ids,
                "query_embeddings": convert_np_embeddings_to_list(query_embeddings),
                "n_results": n_results,
                "where": where,
                "where_document": where_document,
                "include": included,
            },
        )
        metadata_batches = payload.get("metadatas")
        if metadata_batches is not None:
            metadata_batches = [
                [
                    deserialize_metadata(item) if item is not None else None
                    for item in batch
                ]
                if batch is not None
                else None
                for batch in metadata_batches
            ]
        return {
            "ids": payload["ids"],
            "distances": payload.get("distances"),
            "embeddings": payload.get("embeddings"),
            "metadatas": metadata_batches,
            "documents": payload.get("documents"),
            "uris": payload.get("uris"),
            "data": None,
            "included": included,
        }

    def _get(
        self,
        *,
        collection_id: Any,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        where_document: dict[str, Any] | None = None,
        include: list[str] | None = None,
        tenant: str = DEFAULT_TENANT,
        database: str = DEFAULT_DATABASE,
    ) -> dict[str, Any]:
        included = include or ["metadatas", "documents"]
        payload = self._request(
            "POST",
            self._collection_operation_path(tenant, database, collection_id, "get"),
            json={
                "ids": ids,
                "where": where,
                "limit": limit,
                "offset": offset,
                "where_document": where_document,
                "include": included,
            },
        )
        metadatas = payload.get("metadatas")
        if metadatas is not None:
            metadatas = [
                deserialize_metadata(item) if item is not None else None
                for item in metadatas
            ]
        return {
            "ids": payload["ids"],
            "embeddings": payload.get("embeddings"),
            "metadatas": metadatas,
            "documents": payload.get("documents"),
            "data": None,
            "uris": payload.get("uris"),
            "included": included,
        }

    def _delete(
        self,
        *,
        collection_id: Any,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
        limit: int | None = None,
        tenant: str = DEFAULT_TENANT,
        database: str = DEFAULT_DATABASE,
    ) -> dict[str, int]:
        payload = self._request(
            "POST",
            self._collection_operation_path(
                tenant, database, collection_id, "delete"
            ),
            json={
                "ids": ids,
                "where": where,
                "where_document": where_document,
                **({"limit": limit} if limit is not None else {}),
            },
        )
        return {"deleted": int(payload.get("deleted", 0)) if payload else 0}

    @staticmethod
    def _collection_operation_path(
        tenant: str, database: str, collection_id: Any, operation: str
    ) -> str:
        return (
            f"/tenants/{quote(tenant, safe='')}/databases/"
            f"{quote(database, safe='')}/collections/"
            f"{quote(str(collection_id), safe='')}/{operation}"
        )


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

    client = None
    try:
        client = BoundedChromaHttpClient(settings_obj=settings_obj)
        client.heartbeat()
    except ChromaConnectionError:
        if client is not None:
            client.close()
        raise
    except Exception as exc:
        if client is not None:
            client.close()
        raise ChromaConnectionError("Chroma HTTP service is unavailable") from exc
    return client


def chroma_client_ready(client: Any, *, settings_obj: Any = settings) -> bool:
    """Return false when the configured client cannot answer a heartbeat."""
    try:
        client.heartbeat()
    except Exception as exc:
        logger.warning("Chroma heartbeat failed: %s", type(exc).__name__)
        return False
    return True
