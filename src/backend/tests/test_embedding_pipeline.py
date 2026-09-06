from __future__ import annotations

import hashlib
from pathlib import Path
import struct
from types import SimpleNamespace
from unittest.mock import Mock

import chromadb
import pytest

from app.services.embedding_cache import EmbeddingCache, embedding_key
from app.services.provider_errors import ProviderErrorCode, ProviderRequestError
from app.services.vector_store import (
    CollectionIdentityError,
    Document,
    OpenRouterEmbeddingFunction,
    VectorStore,
    _build_embedding_function as production_embedding_builder,
)


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class RecordingEmbeddings:
    def __init__(self, *, dimensions: int, fail_call: int | None = None, failure: Exception | None = None):
        self.dimensions = dimensions
        self.fail_call = fail_call
        self.failure = failure or RuntimeError("deterministic failure")
        self.batch_sizes: list[int] = []
        self.requests: list[tuple[str, int]] = []

    def create(self, *, model: str, input: list[str], dimensions: int):
        self.batch_sizes.append(len(input))
        self.requests.append((model, dimensions))
        if self.fail_call == len(self.batch_sizes):
            raise self.failure
        data = []
        for index, text in reversed(list(enumerate(input))):
            seed = hashlib.sha256(f"{model}\0{text}".encode()).digest()
            vector = [float(seed[offset]) / 255 for offset in range(dimensions)]
            data.append(SimpleNamespace(index=index, embedding=vector))
        return SimpleNamespace(id=f"fake-{len(self.batch_sizes)}", usage={"cost": 0}, data=data)


def embedding_service(tmp_path: Path, client: RecordingEmbeddings, *, version: str = "v1"):
    service = OpenRouterEmbeddingFunction.__new__(OpenRouterEmbeddingFunction)
    service._client = SimpleNamespace(embeddings=client)
    service._model = "openai/text-embedding-3-small"
    service._dimensions = client.dimensions
    service._normalization_version = version
    service._batch_size = 32
    service._batch_delay = 0
    service._max_retries = 3
    service._max_retry_delay = 0
    service._cache = EmbeddingCache(tmp_path / "cache")
    service._provider_guard = SimpleNamespace(
        acquire=lambda _: None,
        release=lambda _: None,
        record_success=lambda _: None,
        record_failure=lambda *a, **k: 0,
        distributed=False,
    )
    return service


def test_embedding_key_uses_full_content_and_all_identity_fields():
    prefix = "same" * 1000
    assert embedding_key(prefix + "A", "model", 3, "v1") != embedding_key(prefix + "B", "model", 3, "v1")
    base = embedding_key("text", "model", 3, "v1")
    assert base != embedding_key("text", "other", 3, "v1")
    assert base != embedding_key("text", "model", 4, "v1")
    assert base != embedding_key("text", "model", 3, "v2")


def test_batches_cache_and_preserves_provider_index_order(tmp_path):
    client = RecordingEmbeddings(dimensions=4)
    service = embedding_service(tmp_path, client)
    texts = [f"chunk-{index}" for index in range(65)]

    vectors = service.embed_texts(texts, model=service._model, dimensions=4, cache_scope="course-a")
    assert client.batch_sizes == [32, 32, 1]
    assert client.requests[:3] == [(service._model, 4)] * 3
    assert vectors == [
        [float(hashlib.sha256(f"{service._model}\0{text}".encode()).digest()[offset]) / 255 for offset in range(4)]
        for text in texts
    ]
    assert service.embed_texts(texts, model=service._model, dimensions=4, cache_scope="course-a") == vectors
    assert client.batch_sizes == [32, 32, 1]

    service.embed_texts(texts[:1], model="other-model", dimensions=4, cache_scope="course-a")
    service.embed_texts(texts[:1], model=service._model, dimensions=4, cache_scope="course-b")
    service.embed_texts(texts[:1], model=service._model, dimensions=5, cache_scope="course-a")
    embedding_service(tmp_path, client, version="v2").embed_texts(
        texts[:1], model=service._model, dimensions=4, cache_scope="course-a"
    )
    assert client.batch_sizes[-4:] == [1, 1, 1, 1]


def test_duplicate_inputs_keep_positions_without_duplicate_provider_work(tmp_path):
    client = RecordingEmbeddings(dimensions=3)
    service = embedding_service(tmp_path, client)
    vectors = service.embed_texts(["one", "one", "two"], model=service._model, dimensions=3, cache_scope="course")
    assert client.batch_sizes == [2]
    assert vectors[0] == vectors[1]
    assert vectors[0] != vectors[2]


def test_partial_failure_checkpoints_completed_batches(tmp_path):
    client = RecordingEmbeddings(dimensions=3, fail_call=3)
    service = embedding_service(tmp_path, client)
    texts = [f"chunk-{index}" for index in range(65)]
    with pytest.raises(ProviderRequestError):
        service.embed_texts(texts, model=service._model, dimensions=3, cache_scope="course")
    assert client.batch_sizes == [32, 32, 1]

    client.fail_call = None
    vectors = service.embed_texts(texts, model=service._model, dimensions=3, cache_scope="course")
    assert len(vectors) == 65
    assert client.batch_sizes == [32, 32, 1, 1]


def test_403_key_limit_is_classified_and_not_retried(tmp_path):
    client = RecordingEmbeddings(
        dimensions=3,
        fail_call=1,
        failure=FakeStatusError(403, "Key limit exceeded (total limit)"),
    )
    service = embedding_service(tmp_path, client)
    with pytest.raises(ProviderRequestError) as caught:
        service.embed_texts(["text"], model=service._model, dimensions=3, cache_scope="course")
    assert caught.value.failure.code == ProviderErrorCode.KEY_LIMIT_EXCEEDED
    assert client.batch_sizes == [1]


def test_corrupted_cache_entry_is_a_miss_and_replaced(tmp_path):
    client = RecordingEmbeddings(dimensions=3)
    service = embedding_service(tmp_path, client)
    key = embedding_key("text", service._model, 3, service._normalization_version)
    path = service._cache.path_for("course", key)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"broken")

    expected = service.embed_texts(["text"], model=service._model, dimensions=3, cache_scope="course")
    assert client.batch_sizes == [1]
    assert service.embed_texts(["text"], model=service._model, dimensions=3, cache_scope="course") == expected
    assert client.batch_sizes == [1]


@pytest.mark.parametrize(
    "payload",
    [
        b"wrong-header",
        b"HGEMB01\0" + struct.pack("!I2d", 2, 0.1, 0.2),
        b"HGEMB01\0" + struct.pack("!I2d", 3, 0.1, 0.2),
        b"HGEMB01\0" + struct.pack("!I3d", 3, float("nan"), 0.1, 0.2),
        b"HGEMB01\0" + struct.pack("!I3d", 3, float("inf"), 0.1, 0.2),
    ],
    ids=["header", "stored-dimension", "byte-length", "nan", "infinity"],
)
def test_malformed_cache_payloads_are_misses(tmp_path, payload):
    cache = EmbeddingCache(tmp_path)
    path = cache.path_for("course", "key")
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    assert cache.get("course", "key", 3) is None


@pytest.mark.parametrize(
    "data",
    [
        [SimpleNamespace(index=0, embedding=[0.1, 0.2, 0.3])],
        [SimpleNamespace(index=0, embedding=[0.1, 0.2]), SimpleNamespace(index=0, embedding=[0.1, 0.2])],
        [SimpleNamespace(index=0, embedding=[0.1]), SimpleNamespace(index=1, embedding=[0.1, 0.2])],
        [SimpleNamespace(index=0, embedding=[float("nan"), 0.2]), SimpleNamespace(index=1, embedding=[0.1, 0.2])],
        [SimpleNamespace(index=0, embedding=[0.1, 0.2]), SimpleNamespace(index=2, embedding=[0.1, 0.2])],
    ],
    ids=["wrong-count", "duplicate-index", "wrong-dimension", "non-finite", "incomplete-coverage"],
)
def test_invalid_provider_response_is_rejected_before_cache_or_success(tmp_path, data):
    create = Mock(return_value=SimpleNamespace(id="invalid", usage={"cost": 0}, data=data))
    service = embedding_service(tmp_path, RecordingEmbeddings(dimensions=2))
    service._client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    guard = Mock()
    guard.acquire.return_value = None
    guard.record_failure.return_value = 0
    guard.distributed = False
    service._provider_guard = guard

    with pytest.raises(ProviderRequestError):
        service.embed_texts(["a", "b"], model=service._model, dimensions=2, cache_scope="course")
    guard.record_success.assert_not_called()
    assert list((tmp_path / "cache").rglob("*.bin")) == []


class DeterministicEmbeddingService:
    def embed_texts(self, texts, *, model, dimensions, cache_scope):
        vectors = []
        for text in texts:
            folded = text.casefold()
            vectors.append([
                1.0 if "python" in folded else 0.0,
                1.0 if "history" in folded else 0.0,
                0.25,
            ][:dimensions])
        return vectors


def test_real_chroma_persistence_filter_delete_and_identity(tmp_path):
    path = tmp_path / "chroma"
    kwargs = dict(
        collection_name="explicit_vectors",
        persist_directory=str(path),
        embedding_service=DeterministicEmbeddingService(),
        embedding_model="deterministic-test",
        embedding_dimensions=3,
        normalization_version="v1",
        distance_metric="cosine",
    )
    store = VectorStore(**kwargs)
    store.add_documents([Document(content="Python language", metadata={"chunk_id": "a1", "source_file": "a.txt"})], "A")
    store.add_documents([Document(content="History lesson", metadata={"chunk_id": "b1", "source_file": "b.txt"})], "B")
    assert store.collection.metadata["embedding_dimensions"] == 3
    assert store.collection._embedding_function is None
    assert len(store.collection.get(include=["embeddings"])["embeddings"][0]) == 3
    store.close()

    reopened = VectorStore(**kwargs)
    assert reopened.get_course_stats("A")["chunk_count"] == 1
    assert reopened.get_course_stats("B")["chunk_count"] == 1
    assert [doc.metadata["course_id"] for doc in reopened.search("Python", "A")] == ["A"]
    reopened.delete_course("A")
    assert reopened.get_course_stats("A")["chunk_count"] == 0
    assert reopened.get_course_stats("B")["chunk_count"] == 1
    reopened.close()


@pytest.mark.parametrize(
    "changed",
    [
        {"embedding_model": "model-b"},
        {"embedding_dimensions": 4},
        {"normalization_version": "v2"},
        {"distance_metric": "l2"},
    ],
)
def test_collection_identity_mismatch_preserves_original_collection(tmp_path, changed):
    path = tmp_path / "chroma"
    base = dict(
        collection_name="identity_guard",
        persist_directory=str(path),
        embedding_service=DeterministicEmbeddingService(),
        embedding_model="model-a",
        embedding_dimensions=3,
        normalization_version="v1",
        distance_metric="cosine",
    )
    store = VectorStore(**base)
    store.add_documents([Document(content="Python", metadata={"chunk_id": "a"})], "A")
    store.close()

    with pytest.raises(CollectionIdentityError, match="explicit new-index migration"):
        VectorStore(**{**base, **changed})

    original = VectorStore(**base)
    assert original.get_course_stats("A")["chunk_count"] == 1
    original.close()


def _empty_identity_store_kwargs(path: Path, collection_name: str) -> dict:
    return {
        "collection_name": collection_name,
        "persist_directory": str(path),
        "embedding_service": DeterministicEmbeddingService(),
        "embedding_model": "model-a",
        "embedding_dimensions": 3,
        "normalization_version": "v1",
        "distance_metric": "cosine",
    }


def test_empty_identity_mismatch_raises_migration_error_without_relabeling(tmp_path):
    path = tmp_path / "empty-mismatch"
    base = _empty_identity_store_kwargs(path, "empty_identity")
    store = VectorStore(**base)
    original_metadata = dict(store.collection.metadata)
    store.close()

    with pytest.raises(CollectionIdentityError, match="explicit new-index migration"):
        VectorStore(**{**base, "embedding_model": "model-b"})

    original = VectorStore(**base)
    assert original.collection.count() == 0
    assert original.collection.metadata == original_metadata
    original.close()


def test_empty_legacy_collection_without_identity_requires_migration_and_is_unchanged(tmp_path):
    path = tmp_path / "legacy-empty"
    raw = chromadb.PersistentClient(path=str(path))
    legacy = raw.get_or_create_collection(name="legacy_identity_openrouter", embedding_function=None)
    assert legacy.count() == 0
    original_metadata = legacy.metadata

    with pytest.raises(CollectionIdentityError, match="explicit new-index migration"):
        VectorStore(**_empty_identity_store_kwargs(path, "legacy_identity"))

    preserved = raw.get_collection(name="legacy_identity_openrouter", embedding_function=None)
    assert preserved.count() == 0
    assert preserved.metadata == original_metadata


def test_collection_emptied_after_use_cannot_be_implicitly_relabeled(tmp_path):
    path = tmp_path / "emptied-after-use"
    base = _empty_identity_store_kwargs(path, "used_identity")
    store = VectorStore(**base)
    store.add_documents([Document(content="Python", metadata={"chunk_id": "a"})], "A")
    store.delete_course("A")
    assert store.collection.count() == 0
    original_metadata = dict(store.collection.metadata)
    store.close()

    with pytest.raises(CollectionIdentityError, match="explicit new-index migration"):
        VectorStore(**{**base, "normalization_version": "v2"})

    original = VectorStore(**base)
    assert original.collection.count() == 0
    assert original.collection.metadata == original_metadata
    original.close()


def test_default_embedding_builder_fails_closed_without_key(monkeypatch):
    from app.services.vector_store import settings

    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        production_embedding_builder()


def test_artifact_generator_construction_is_lazy_about_vector_store(monkeypatch):
    from app.routers import generation

    generation._generator_instance = None
    monkeypatch.setattr(generation, "get_vector_store", Mock(side_effect=AssertionError("eager vector init")))
    generator = generation.get_generator()
    assert generator._vector_store is None
