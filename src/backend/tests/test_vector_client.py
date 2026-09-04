"""Chroma embedded/server client selection and readiness contracts."""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import vector_client, vector_store


class _HangingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(3)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"nanosecond heartbeat": 1}')
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, _format, *_args):
        pass


class _ConstructorFailureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/heartbeat"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"nanosecond heartbeat": 1}')
            return
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "untrusted constructor detail"}')

    def log_message(self, _format, *_args):
        pass


@pytest.fixture
def hanging_http_port():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HangingHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def constructor_failure_http_port():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ConstructorFailureHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
    health_probe = Mock(return_value=True)
    monkeypatch.setattr(vector_client, "chroma_http_ready", health_probe)

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
    health_probe.assert_called_once()
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
    build_client = Mock(
        side_effect=vector_client.ChromaConnectionError(
            "Chroma HTTP service is unavailable"
        )
    )
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
    persistent_client.assert_not_called()
    assert not persist_directory.exists()


def test_hanging_http_endpoint_bounds_startup_and_readiness_without_fallback(
    monkeypatch, tmp_path, hanging_http_port
):
    configured = _chroma_settings(
        CHROMA_MODE="http",
        CHROMA_HOST="127.0.0.1",
        CHROMA_PORT=hanging_http_port,
        CHROMA_TIMEOUT_SECONDS=1.0,
        CHROMA_PERSIST_DIR=str(tmp_path / "must-not-exist"),
    )
    http_client = Mock()
    persistent_client = Mock()
    monkeypatch.setattr(vector_client.chromadb, "HttpClient", http_client)
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)

    started = time.monotonic()
    with pytest.raises(vector_client.ChromaConnectionError, match="unavailable"):
        vector_client.build_chroma_client(settings_obj=configured)
    startup_elapsed = time.monotonic() - started

    store = object.__new__(vector_store.VectorStore)
    store.client = Mock()
    store.collection = Mock()
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "http")
    monkeypatch.setattr(vector_store.settings, "CHROMA_HOST", "127.0.0.1")
    monkeypatch.setattr(vector_store.settings, "CHROMA_PORT", hanging_http_port)
    monkeypatch.setattr(vector_store.settings, "CHROMA_SSL", False)
    monkeypatch.setattr(vector_store.settings, "CHROMA_TIMEOUT_SECONDS", 1.0)

    started = time.monotonic()
    assert store.is_ready() is False
    readiness_elapsed = time.monotonic() - started

    assert startup_elapsed < 2.5
    assert readiness_elapsed < 2.5
    http_client.assert_not_called()
    persistent_client.assert_not_called()
    store.client.heartbeat.assert_not_called()
    assert not (tmp_path / "must-not-exist").exists()


def test_unavailable_http_endpoint_is_bounded_and_never_falls_back(monkeypatch, tmp_path):
    with socket.socket() as reserved_socket:
        reserved_socket.bind(("127.0.0.1", 0))
        unavailable_port = reserved_socket.getsockname()[1]

    persistent_client = Mock()
    http_client = Mock()
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)
    monkeypatch.setattr(vector_client.chromadb, "HttpClient", http_client)
    configured = _chroma_settings(
        CHROMA_MODE="http",
        CHROMA_HOST="127.0.0.1",
        CHROMA_PORT=unavailable_port,
        CHROMA_TIMEOUT_SECONDS=1.0,
        CHROMA_PERSIST_DIR=str(tmp_path / "must-not-exist"),
    )

    started = time.monotonic()
    with pytest.raises(vector_client.ChromaConnectionError, match="unavailable"):
        vector_client.build_chroma_client(settings_obj=configured)

    assert time.monotonic() - started < 2.5
    http_client.assert_not_called()
    persistent_client.assert_not_called()
    assert not (tmp_path / "must-not-exist").exists()


def test_http_constructor_failure_is_normalized_after_successful_probe(monkeypatch):
    constructor_error = ValueError("untrusted host and tenant detail")
    http_client = Mock(side_effect=constructor_error)
    persistent_client = Mock()
    monkeypatch.setattr(vector_client, "chroma_http_ready", Mock(return_value=True))
    monkeypatch.setattr(vector_client.chromadb, "HttpClient", http_client)
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)

    with pytest.raises(vector_client.ChromaConnectionError) as exc_info:
        vector_client.build_chroma_client(
            settings_obj=_chroma_settings(CHROMA_MODE="http")
        )

    assert str(exc_info.value) == "Chroma HTTP service is unavailable"
    assert exc_info.value.__cause__ is constructor_error
    persistent_client.assert_not_called()


def test_real_http_constructor_connection_failure_is_normalized_without_fallback(
    monkeypatch, tmp_path, constructor_failure_http_port
):
    persistent_client = Mock()
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)
    configured = _chroma_settings(
        CHROMA_MODE="http",
        CHROMA_HOST="127.0.0.1",
        CHROMA_PORT=constructor_failure_http_port,
        CHROMA_TIMEOUT_SECONDS=1.0,
        CHROMA_PERSIST_DIR=str(tmp_path / "must-not-exist"),
    )

    with pytest.raises(vector_client.ChromaConnectionError) as exc_info:
        vector_client.build_chroma_client(settings_obj=configured)

    assert str(exc_info.value) == "Chroma HTTP service is unavailable"
    assert exc_info.value.__cause__ is not None
    persistent_client.assert_not_called()
    assert not (tmp_path / "must-not-exist").exists()


def test_http_readiness_rechecks_heartbeat_and_returns_false(monkeypatch):
    client = Mock()
    collection = Mock(name="active-collection")
    client.get_or_create_collection.return_value = collection
    monkeypatch.setattr(vector_store, "build_chroma_client", Mock(return_value=client))
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "http")
    health_probe = Mock(return_value=False)
    monkeypatch.setattr(vector_client, "chroma_http_ready", health_probe)

    store = vector_store.VectorStore(
        collection_name="ai_course_chunks",
        persist_directory="ignored-in-http-mode",
        embedding_function=Mock(),
    )

    assert store.collection is collection
    assert store.is_ready() is False
    health_probe.assert_called_once_with(settings_obj=vector_store.settings)
    client.heartbeat.assert_not_called()


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
