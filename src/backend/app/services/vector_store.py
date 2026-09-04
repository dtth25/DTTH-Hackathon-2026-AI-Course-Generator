"""Vector Store service wrapper around ChromaDB."""

import logging
import os
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import chromadb
from app.core.config import settings
from app.services.provider_errors import ProviderRequestError, classify_openrouter_error
from app.services.provider_guard import (
    ProviderCircuitOpen,
    ProviderGuard,
    get_provider_guard,
    retry_after_seconds,
)

logger = logging.getLogger(__name__)


class Document(BaseModel):
    """Document chunk with content and metadata."""
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OpenRouterEmbeddingFunction:
    """Chroma embedding function backed by OpenRouter."""

    def __init__(self, api_key: str, model: str, max_retries: int = 3, max_retry_delay: float = 60):
        from openai import OpenAI

        self._client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=api_key,
            max_retries=0,
        )
        self._model = model
        self._max_retries = max(1, max_retries)
        self._max_retry_delay = max(0.0, max_retry_delay)
        self._provider_guard = get_provider_guard()

    def name(self) -> str:
        return "openrouter"

    def __call__(self, input: List[str]) -> List[List[float]]:
        return self._embed(list(input))

    def embed_query(self, input: List[str]) -> List[List[float]]:
        return self._embed(list(input))

    def _embed(self, texts: List[str]) -> List[List[float]]:
        delay = 1.0
        last_failure = None
        for attempt in range(1, self._max_retries + 1):
            guard = getattr(self, "_provider_guard", None)
            if guard is None:
                guard = ProviderGuard(settings_obj=settings)
            permit = guard.acquire("embedding")
            try:
                response = self._client.embeddings.create(model=self._model, input=texts)
                embeddings = [item.embedding for item in response.data]
                if len(embeddings) != len(texts):
                    raise ValueError("Provider embedding response length did not match input")
                guard.record_success("embedding")
                return embeddings
            except ProviderCircuitOpen:
                raise
            except Exception as exc:
                failure = classify_openrouter_error(exc)
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


def _build_embedding_function() -> Optional[OpenRouterEmbeddingFunction]:
    """Build the OpenRouter embedding function, or use Chroma's test-only default."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return None
    api_key = getattr(settings, "OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    try:
        return OpenRouterEmbeddingFunction(
            api_key=api_key,
            model=settings.OPENROUTER_EMBEDDING_MODEL,
            max_retries=settings.EMBEDDING_MAX_RETRIES,
            max_retry_delay=settings.EMBEDDING_MAX_RETRY_DELAY,
        )
    except Exception as e:
        logger.warning(f"Failed to initialize OpenRouter embedding function: {e}")
        return None


class VectorStore:
    """Wrapper around ChromaDB for storing and retrieving course document chunks.

    The OpenRouter collection is primary. The original collection is retained read-only as a
    legacy source while old courses are re-embedded lazily.
    """

    def __init__(self, collection_name: str, persist_directory: str, embedding_function: Optional[Any] = None):
        self.legacy_collection_name = collection_name
        self.collection_name = f"{collection_name}_openrouter"
        self.persist_directory = persist_directory

        os.makedirs(persist_directory, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_directory)
        ef = embedding_function if embedding_function is not None else _build_embedding_function()
        if ef is not None:
            self.collection = self.client.get_or_create_collection(name=self.collection_name, embedding_function=ef)
        else:
            self.collection = self.client.get_or_create_collection(name=self.collection_name)

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
            metadatas=metadatas
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
            query_texts=[query],
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
        self, course_id: str, chunk_ids: Optional[List[str]] = None, provider: str = "openrouter"
    ) -> List[Document]:
        """Get all stored chunks for a course, optionally filtered by chunk_ids."""
        try:
            res = self._collection_for(provider).get(where={"course_id": str(course_id)})
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
