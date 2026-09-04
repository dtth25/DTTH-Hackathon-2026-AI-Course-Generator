"""Chroma embedded/server client selection and readiness contracts."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import vector_client, vector_store


def _settings_values(**overrides):
    values = {
        "DATABASE_URL": "sqlite:///:memory:",
        "JWT_SECRET": "test-secret",
        "OPENROUTER_API_KEY": "test-key",
    }
    values.update(overrides)
    return values


def _chroma_settings(**overrides):
    values = {
        "CHROMA_MODE": "embedded",
        "CHROMA_PERSIST_DIR": "data/chroma",
        "CHROMA_HOST": "localhost",
        "CHROMA_PORT": 8000,
        "CHROMA_SSL": False,
        "CHROMA_TIMEOUT_SECONDS": 10.0,
        "ENVIRONMENT": "local",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_chroma_settings_have_local_defaults_and_bounds(monkeypatch):
    for field in (
        "CHROMA_MODE",
        "CHROMA_HOST",
        "CHROMA_PORT",
        "CHROMA_SSL",
        "CHROMA_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(field, raising=False)
    configured = Settings(**_settings_values())

    assert configured.CHROMA_MODE == "embedded"
    assert configured.CHROMA_HOST == "localhost"
    assert configured.CHROMA_PORT == 8000
    assert configured.CHROMA_SSL is False
    assert configured.CHROMA_TIMEOUT_SECONDS == 10.0

    for field, value in (
        ("CHROMA_MODE", "remote"),
        ("CHROMA_PORT", 0),
        ("CHROMA_PORT", 65536),
        ("CHROMA_TIMEOUT_SECONDS", 0.5),
        ("CHROMA_TIMEOUT_SECONDS", 61),
    ):
        with pytest.raises(ValidationError, match=field):
            Settings(**_settings_values(**{field: value}))


def test_embedded_mode_builds_persistent_client_at_configured_path(monkeypatch, tmp_path):
    client = Mock()
    persistent_client = Mock(return_value=client)
    http_client = Mock()
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)
    monkeypatch.setattr(vector_client.chromadb, "HttpClient", http_client)

    result = vector_client.build_chroma_client(
        settings_obj=_chroma_settings(CHROMA_PERSIST_DIR=str(tmp_path))
    )

    assert result is client
    persistent_client.assert_called_once_with(path=str(tmp_path))
    http_client.assert_not_called()


def test_http_mode_builds_only_http_client(monkeypatch, tmp_path):
    client = Mock()
    persistent_client = Mock()
    http_client = Mock(return_value=client)
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)
    monkeypatch.setattr(vector_client.chromadb, "HttpClient", http_client)

    result = vector_client.build_chroma_client(
        settings_obj=_chroma_settings(
            CHROMA_MODE="http",
            CHROMA_HOST="chroma.internal",
            CHROMA_PORT=8443,
            CHROMA_SSL=True,
            CHROMA_PERSIST_DIR=str(tmp_path / "must-not-exist"),
        )
    )

    assert result is client
    http_client.assert_called_once_with(host="chroma.internal", port=8443, ssl=True)
    persistent_client.assert_not_called()
    assert not (tmp_path / "must-not-exist").exists()


def test_production_rejects_embedded_before_creating_local_storage(monkeypatch, tmp_path):
    persistent_client = Mock()
    http_client = Mock()
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)
    monkeypatch.setattr(vector_client.chromadb, "HttpClient", http_client)
    persist_directory = tmp_path / "must-not-exist"

    with pytest.raises(ValueError, match="production.*CHROMA_MODE=http"):
        vector_client.build_chroma_client(
            settings_obj=_chroma_settings(
                ENVIRONMENT="production",
                CHROMA_PERSIST_DIR=str(persist_directory),
            )
        )

    persistent_client.assert_not_called()
    http_client.assert_not_called()
    assert not persist_directory.exists()


def test_http_heartbeat_failure_aborts_before_collection_and_never_falls_back(
    monkeypatch, tmp_path
):
    client = Mock()
    client.heartbeat.side_effect = ConnectionError("server unavailable")
    build_client = Mock(return_value=client)
    persistent_client = Mock()
    monkeypatch.setattr(vector_store, "build_chroma_client", build_client)
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "http")
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)
    persist_directory = tmp_path / "must-not-exist"

    with pytest.raises(vector_client.ChromaConnectionError, match="unavailable"):
        vector_store.VectorStore(
            collection_name="ai_course_chunks",
            persist_directory=str(persist_directory),
            embedding_function=Mock(),
        )

    build_client.assert_called_once_with(persist_directory=str(persist_directory))
    client.heartbeat.assert_called_once_with()
    client.get_or_create_collection.assert_not_called()
    persistent_client.assert_not_called()
    assert not persist_directory.exists()


def test_http_readiness_rechecks_heartbeat_and_returns_false(monkeypatch):
    client = Mock()
    client.heartbeat.side_effect = [1, ConnectionError("server stopped")]
    collection = Mock(name="active-collection")
    client.get_or_create_collection.return_value = collection
    monkeypatch.setattr(vector_store, "build_chroma_client", Mock(return_value=client))
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "http")

    store = vector_store.VectorStore(
        collection_name="ai_course_chunks",
        persist_directory="ignored-in-http-mode",
        embedding_function=Mock(),
    )

    assert store.collection is collection
    assert store.is_ready() is False
    assert client.heartbeat.call_count == 2


def test_embedded_readiness_uses_the_same_heartbeat_contract(monkeypatch, tmp_path):
    client = Mock()
    client.heartbeat.return_value = 1
    client.get_or_create_collection.return_value = Mock()
    monkeypatch.setattr(vector_store, "build_chroma_client", Mock(return_value=client))
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "embedded")

    store = vector_store.VectorStore(
        collection_name="ai_course_chunks",
        persist_directory=str(tmp_path),
        embedding_function=Mock(),
    )

    assert store.is_ready() is True
    client.heartbeat.assert_called_once_with()


def test_health_endpoint_reports_http_heartbeat_failure(client, monkeypatch):
    unavailable_store = Mock()
    unavailable_store.is_ready.return_value = False
    monkeypatch.setattr("main.get_vector_store", Mock(return_value=unavailable_store))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["vector_db_ready"] is False
    assert response.json()["details"]["vector_db"] is False
    unavailable_store.is_ready.assert_called_once_with()
