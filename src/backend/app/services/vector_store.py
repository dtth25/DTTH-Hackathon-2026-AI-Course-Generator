"""Vector Store service wrapper around ChromaDB."""

import logging
import math
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.services.embedding_cache import EmbeddingCache, embedding_key
from app.services.provider_usage import (
    BudgetLimitError,
    dispatch_provider,
    mark_response_outcome,
)
from app.core.config import settings
from app.services.provider_errors import ProviderRequestError, classify_openrouter_error
from app.services.provider_guard import (
    ProviderCircuitOpen,
    ProviderGuard,
    get_provider_guard,
    retry_after_seconds,
)
from app.services.vector_client import (
    ChromaConnectionError,
    build_chroma_client,
    chroma_client_ready,
)

logger = logging.getLogger(__name__)


def _close_chroma_client(client: Any) -> None:
    """Close an owned Chroma client without masking the active failure."""
    close = getattr(client, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception as exc:
        logger.warning("Failed to close Chroma client: %s", type(exc).__name__)


class Document(BaseModel):
    """Document chunk with content and metadata."""
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CollectionIdentityError(RuntimeError):
    """The existing vector collection cannot prove its embedding identity."""


class OpenRouterEmbeddingFunction:
    """Explicit cached OpenRouter embedding service used outside Chroma."""

    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int = 1536,
        normalization_version: str = "exact-v1",
        cache_directory: str | None = None,
        batch_size: int = 32,
        batch_delay: float = 0,
        max_retries: int = 2,
        max_retry_delay: float = 60,
    ):
        from openai import OpenAI

        self._client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=api_key,
            max_retries=0,
        )
        self._model = model
        self._dimensions = dimensions
        self._normalization_version = normalization_version
        self._cache = EmbeddingCache(cache_directory or settings.EMBEDDING_CACHE_DIR)
        self._batch_size = max(1, int(batch_size))
        self._batch_delay = max(0.0, batch_delay)
        self._max_retries = max(1, int(max_retries))
        self._max_retry_delay = max(0.0, max_retry_delay)
        self._provider_guard = get_provider_guard()

    def name(self) -> str:
        return "openrouter"

    def __call__(self, input: List[str]) -> List[List[float]]:
        return self.embed_texts(
            list(input),
            model=self._model,
            dimensions=self._dimensions,
            cache_scope="chroma-callback-forbidden",
        )

    def embed_query(self, input: List[str]) -> List[List[float]]:
        return self.__call__(input)

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def normalization_version(self) -> str:
        return self._normalization_version

    @staticmethod
    def _response_item(item: Any, name: str) -> Any:
        return item.get(name) if isinstance(item, dict) else getattr(item, name, None)

    def _validate_response(self, response: Any, count: int, dimensions: int) -> list[list[float]]:
        data = getattr(response, "data", None)
        if not isinstance(data, (list, tuple)) or len(data) != count:
            raise ValueError("Provider embedding response count did not match input")
        by_index: dict[int, list[float]] = {}
        for item in data:
            index = self._response_item(item, "index")
            vector = self._response_item(item, "embedding")
            if isinstance(index, bool) or not isinstance(index, int) or index in by_index:
                raise ValueError("Provider embedding response contained invalid or duplicate indices")
            if not isinstance(vector, (list, tuple)) or len(vector) != dimensions:
                raise ValueError("Provider embedding response dimension did not match request")
            clean: list[float] = []
            for value in vector:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Provider embedding response contained a non-finite numeric value")
                clean.append(float(value))
            by_index[index] = clean
        if set(by_index) != set(range(count)):
            raise ValueError("Provider embedding response indices did not exactly cover the request")
        return [by_index[index] for index in range(count)]

    def _embed(self, texts: List[str], *, model: str | None = None, dimensions: int | None = None) -> List[List[float]]:
        requested_model = model or self._model
        requested_dimensions = dimensions or getattr(self, "_dimensions", settings.EMBEDDING_DIMENSIONS)
        delay = 1.0
        last_failure = None
        for attempt in range(1, self._max_retries + 1):
            guard = getattr(self, "_provider_guard", None)
            if guard is None:
                guard = ProviderGuard(settings_obj=settings)
            permit = guard.acquire("embedding")
            try:
                response = dispatch_provider(
                    self._client.embeddings.create,
                    model=requested_model,
                    request={"input": texts, "dimensions": requested_dimensions},
                    feature="embedding",
                    attempt=attempt,
                )
                try:
                    embeddings = self._validate_response(response, len(texts), requested_dimensions)
                except Exception:
                    mark_response_outcome("schema_invalid")
                    raise
                mark_response_outcome("valid")
                guard.record_success("embedding")
                return embeddings
            except (ProviderCircuitOpen, BudgetLimitError):
                raise
            except Exception as exc:
                failure = exc.failure if isinstance(exc, ProviderRequestError) else classify_openrouter_error(exc)
                last_failure = failure
                opened_for = guard.record_failure(
                    "embedding",
                    failure,
                    retry_after=retry_after_seconds(exc),
                )
                logger.warning(
                    "OpenRouter embedding attempt %s/%s failed with %s",
                    attempt,
                    self._max_retries,
                    failure.code,
                )
                if not failure.automatic_retry or attempt == self._max_retries:
                    raise ProviderRequestError(failure) from exc
                if opened_for:
                    raise ProviderCircuitOpen(
                        opened_for,
                        error_code="AI_UNAVAILABLE",
                    ) from exc
                if guard.distributed:
                    raise ProviderCircuitOpen(
                        max(1, min(300, int(delay))),
                        reason="transient",
                        error_code="AI_UNAVAILABLE",
                    ) from exc
                time.sleep(min(delay, self._max_retry_delay))
                delay *= 2
            finally:
                guard.release(permit)
        raise ProviderRequestError(last_failure)

    def embed_texts(
        self,
        texts: list[str],
        *,
        model: str,
        dimensions: int,
        cache_scope: str,
    ) -> list[list[float]]:
        """Resolve cache hits and checkpoint fully validated provider batches."""
        if not texts:
            return []
        if not model.strip() or dimensions <= 0 or not cache_scope:
            raise ValueError("Embedding model, dimensions, and cache scope are required")
        normalization_version = self._normalization_version
        keys = [embedding_key(text, model, dimensions, normalization_version) for text in texts]
        results: list[list[float] | None] = [None] * len(texts)
        missing: dict[str, tuple[str, list[int]]] = {}
        for position, (text, key) in enumerate(zip(texts, keys)):
            cached = self._cache.get(cache_scope, key, dimensions)
            if cached is not None:
                results[position] = cached
                continue
            if key in missing:
                missing[key][1].append(position)
            else:
                missing[key] = (text, [position])

        misses = list(missing.items())
        for offset in range(0, len(misses), self._batch_size):
            batch = misses[offset : offset + self._batch_size]
            vectors = self._embed(
                [entry[1][0] for entry in batch],
                model=model,
                dimensions=dimensions,
            )
            for (key, (_, positions)), vector in zip(batch, vectors):
                self._cache.put(cache_scope, key, vector, dimensions)
                for position in positions:
                    results[position] = vector
            if self._batch_delay and offset + self._batch_size < len(misses):
                time.sleep(self._batch_delay)
        if any(vector is None for vector in results):
            raise RuntimeError("Embedding pipeline did not resolve every input")
        return [vector for vector in results if vector is not None]


def _build_embedding_function() -> OpenRouterEmbeddingFunction:
    """Build the configured OpenRouter service or fail before Chroma can embed."""
    api_key = getattr(settings, "OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required for explicit embeddings")
    if not settings.OPENROUTER_EMBEDDING_MODEL:
        raise ValueError("OPENROUTER_EMBEDDING_MODEL is required for explicit embeddings")
    return OpenRouterEmbeddingFunction(
        api_key=api_key,
        model=settings.OPENROUTER_EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
        normalization_version=settings.EMBEDDING_NORMALIZATION_VERSION,
        cache_directory=settings.EMBEDDING_CACHE_DIR,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        batch_delay=settings.EMBEDDING_BATCH_DELAY,
        max_retries=settings.EMBEDDING_MAX_RETRIES,
        max_retry_delay=settings.EMBEDDING_MAX_RETRY_DELAY,
    )


class VectorStore:
    """Wrapper around ChromaDB for storing and retrieving course document chunks.

    The OpenRouter collection is primary. The original collection is retained read-only as a
    legacy source while old courses are re-embedded lazily.
    """

    def __init__(
        self,
        collection_name: str,
        persist_directory: str,
        embedding_function: Optional[Any] = None,
        *,
        embedding_service: Optional[Any] = None,
        embedding_model: str | None = None,
        embedding_dimensions: int | None = None,
        normalization_version: str | None = None,
        distance_metric: str = "cosine",
    ):
        self.legacy_collection_name = collection_name
        self.collection_name = f"{collection_name}_openrouter"
        self.persist_directory = persist_directory

        service = embedding_service or embedding_function or _build_embedding_function()
        self._embedding_service = service
        service_model = getattr(service, "model", None)
        service_dimensions = getattr(service, "dimensions", None)
        service_version = getattr(service, "normalization_version", None)
        self.embedding_model = embedding_model if embedding_model is not None else (
            service_model if isinstance(service_model, str) else settings.OPENROUTER_EMBEDDING_MODEL
        )
        self.embedding_dimensions = embedding_dimensions if embedding_dimensions is not None else (
            service_dimensions
            if isinstance(service_dimensions, int) and not isinstance(service_dimensions, bool)
            else settings.EMBEDDING_DIMENSIONS
        )
        self.normalization_version = normalization_version if normalization_version is not None else (
            service_version if isinstance(service_version, str) else settings.EMBEDDING_NORMALIZATION_VERSION
        )
        if (
            not self.embedding_model.strip()
            or self.embedding_dimensions <= 0
            or not self.normalization_version.strip()
        ):
            raise ValueError("Complete explicit embedding identity is required")
        if distance_metric not in {"cosine", "l2", "ip"}:
            raise ValueError("Unsupported Chroma distance metric")
        self.distance_metric = distance_metric
        self.collection_identity = {
            "embedding_provider": "openrouter",
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "embedding_normalization_version": self.normalization_version,
            "distance_metric": self.distance_metric,
            "hnsw:space": self.distance_metric,
        }

        self.client = build_chroma_client(persist_directory=persist_directory)
        try:
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=None,
                metadata=self.collection_identity,
            )
            self._verify_collection_identity()
        except Exception as exc:
            _close_chroma_client(self.client)
            if settings.CHROMA_MODE == "http" and not isinstance(exc, CollectionIdentityError):
                if isinstance(exc, ChromaConnectionError):
                    raise
                raise ChromaConnectionError(
                    "Chroma HTTP service is unavailable"
                ) from exc
            raise

    def _verify_collection_identity(self) -> None:
        metadata = getattr(self.collection, "metadata", None) or {}
        mismatches = {
            key: (metadata.get(key), expected)
            for key, expected in self.collection_identity.items()
            if metadata.get(key) != expected
        }
        if not mismatches:
            return
        raise CollectionIdentityError(
            f"Collection {self.collection_name!r} has missing or mismatched embedding identity; "
            "preserve it and perform an explicit new-index migration"
        )

    def close(self) -> None:
        """Release resources owned by this store's Chroma client."""
        _close_chroma_client(self.client)

    def is_ready(self) -> bool:
        """Check that the configured Chroma backend is responding now."""
        return self.collection is not None and chroma_client_ready(
            self.client, settings_obj=settings
        )

    def _collection_for(self, provider: str) -> Any:
        """Return the sole active embedding collection."""
        if provider != "openrouter":
            raise ValueError(f"Unsupported active embedding provider: {provider}")
        return self.collection

    def add_documents(self, documents: List[Document], course_id: str, provider: str = "openrouter") -> None:
        """Add document chunks to ChromaDB collection with course_id metadata."""
        if not documents:
            return

        ids = []
        contents = []
        metadatas = []

        for idx, doc in enumerate(documents):
            # Ensure each document has a unique ID and course_id in metadata
            chunk_id = doc.metadata.get("chunk_id", f"{course_id}_chunk_{idx}")
            ids.append(str(chunk_id))
            contents.append(doc.content)

            meta = dict(doc.metadata)
            meta["course_id"] = str(course_id)
            # Convert any complex types or None in metadata to string/int/float/bool for ChromaDB compatibility
            clean_meta = {}
            for k, v in meta.items():
                if v is None:
                    clean_meta[k] = ""
                elif isinstance(v, (str, int, float, bool)):
                    clean_meta[k] = v
                else:
                    clean_meta[k] = str(v)
            metadatas.append(clean_meta)

        # Use upsert to prevent duplicate ID errors on re-processing
        self._collection_for(provider).upsert(
            ids=ids,
            documents=contents,
            metadatas=metadatas,
            embeddings=self._embedding_service.embed_texts(
                contents,
                model=self.embedding_model,
                dimensions=self.embedding_dimensions,
                cache_scope=str(course_id),
            ),
        )
        logger.info(
            f"Added {len(documents)} chunks for course {course_id} to collection "
            f"{self.collection_name}"
        )

    def search(
        self, query: str, course_id: str, k: int = 10, max_distance: Optional[float] = None, provider: str = "openrouter"
    ) -> List[Document]:
        """Search for top-k relevant chunks for a specific course. When max_distance is set,
        chunks beyond that Chroma distance (lower = more similar) are dropped even if it means
        returning fewer than k results, instead of padding with irrelevant tail matches."""
        if not query or not query.strip():
            return []

        collection = self._collection_for(provider)

        # Check if course has any documents first
        stats = self.get_course_stats(course_id, provider=provider)
        if stats.get("chunk_count", 0) == 0:
            return []

        # Ensure k is not larger than total chunks for this course
        n_results = min(k, stats["chunk_count"])
        if n_results <= 0:
            return []

        results = collection.query(
            query_embeddings=self._embedding_service.embed_texts(
                [query],
                model=self.embedding_model,
                dimensions=self.embedding_dimensions,
                cache_scope=str(course_id),
            ),
            n_results=n_results,
            where={"course_id": str(course_id)}
        )

        documents = []
        if results and "documents" in results and results["documents"]:
            docs_list = results["documents"][0]
            metas_list = (
                results["metadatas"][0]
                if "metadatas" in results and results["metadatas"]
                else [{}] * len(docs_list)
            )
            distances_list = (
                results["distances"][0]
                if "distances" in results and results["distances"]
                else [None] * len(docs_list)
            )
            for content, meta, distance in zip(docs_list, metas_list, distances_list):
                if max_distance is not None and distance is not None and distance > max_distance:
                    continue
                documents.append(Document(content=content, metadata=meta or {}))

        return documents

    def delete_course(self, course_id: str) -> None:
        """Delete active and legacy chunks for a removed course."""
        try:
            self.collection.delete(where={"course_id": str(course_id)})
            logger.info(f"Deleted vector chunks for course {course_id}")
        except Exception as e:
            logger.warning(f"Error deleting chunks for course {course_id}: {e}")
        try:
            legacy = self.client.get_collection(name=self.legacy_collection_name, embedding_function=None)
            legacy.delete(where={"course_id": str(course_id)})
        except Exception:
            pass  # OpenRouter collection never used for this course, or not configured — fine.

    def delete_job_attempt(
        self, *, course_id: str, job_id: str, attempt_number: int
    ) -> None:
        """Delete only chunks still attributed to one abandoned ingestion attempt.

        A newer stable-ID upsert replaces this metadata, so cleanup cannot erase chunks
        already published by the reclaimed attempt.
        """
        self.collection.delete(
            where={
                "$and": [
                    {"course_id": str(course_id)},
                    {"processing_job_id": str(job_id)},
                    {"processing_attempt": int(attempt_number)},
                ]
            }
        )

    def get_course_stats(self, course_id: str, provider: str = "openrouter") -> dict:
        """Get statistics about stored chunks for a course."""
        try:
            collection = self._collection_for(provider)
            res = collection.get(where={"course_id": str(course_id)})
            count = len(res["ids"]) if res and "ids" in res else 0
            return {
                "course_id": str(course_id),
                "chunk_count": count,
                "collection_name": collection.name,
            }
        except Exception as e:
            logger.warning(f"Error getting stats for course {course_id}: {e}")
            return {
                "course_id": str(course_id),
                "chunk_count": 0,
                "collection_name": self.collection_name,
            }

    def get_course_chunks(
        self,
        course_id: str,
        chunk_ids: Optional[List[str]] = None,
        provider: str = "openrouter",
        *,
        source_file: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Document]:
        """Get all stored chunks for a course, optionally filtered by chunk_ids."""
        try:
            where: Dict[str, Any] = {"course_id": str(course_id)}
            if source_file is not None:
                where = {
                    "$and": [
                        {"course_id": str(course_id)},
                        {"source_file": str(source_file)},
                    ]
                }
            get_kwargs: Dict[str, Any] = {"where": where}
            if limit is not None:
                get_kwargs["limit"] = max(0, int(limit))
            if offset is not None:
                get_kwargs["offset"] = max(0, int(offset))
            res = self._collection_for(provider).get(**get_kwargs)
            documents = []
            if res and "ids" in res and res["ids"]:
                ids_list = res["ids"]
                docs_list = res.get("documents", [""] * len(ids_list))
                metas_list = res.get("metadatas", [{}] * len(ids_list))

                target_ids = set(chunk_ids) if chunk_ids else None
                for cid, content, meta in zip(ids_list, docs_list, metas_list):
                    meta_dict = meta or {}
                    meta_dict["chunk_id"] = cid
                    if target_ids is None or cid in target_ids:
                        documents.append(Document(content=content or "", metadata=meta_dict))
            return documents
        except Exception as e:
            logger.warning(f"Error getting chunks for course {course_id}: {e}")
            return []

    def get_legacy_course_chunks(self, course_id: str) -> List[Document]:
        """Read raw chunks from the pre-OpenRouter collection without embedding queries."""
        try:
            legacy = self.client.get_collection(name=self.legacy_collection_name, embedding_function=None)
            res = legacy.get(where={"course_id": str(course_id)})
            return [
                Document(content=content or "", metadata={**(metadata or {}), "chunk_id": chunk_id})
                for chunk_id, content, metadata in zip(
                    res.get("ids", []), res.get("documents", []), res.get("metadatas", [])
                )
            ]
        except Exception as exc:
            logger.warning("Unable to read legacy chunks for course %s: %s", course_id, exc)
            return []


# Singleton instance
_vector_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get singleton VectorStore instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        from app.core.config import settings
        _vector_store_instance = VectorStore(
            collection_name=settings.CHROMA_COLLECTION_NAME,
            persist_directory=settings.CHROMA_PERSIST_DIR,
        )
    return _vector_store_instance


def close_vector_store() -> None:
    """Close and clear the process-wide VectorStore singleton."""
    global _vector_store_instance
    store = _vector_store_instance
    _vector_store_instance = None
    if store is not None:
        store.close()
