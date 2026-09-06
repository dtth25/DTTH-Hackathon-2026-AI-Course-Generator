"""Chroma embedded/server client selection and readiness contracts."""

import asyncio
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import vector_client, vector_store


_TEST_IDENTITY = {
    "embedding_provider": "openrouter",
    "embedding_model": "deterministic-test",
    "embedding_dimensions": 3,
    "embedding_normalization_version": "v1",
    "distance_metric": "cosine",
    "hnsw:space": "cosine",
}


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


class _HeartbeatThenHangHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/heartbeat"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"nanosecond heartbeat": 1}')
            return
        time.sleep(3)
        try:
            self.send_response(503)
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, _format, *_args):
        pass


class _VectorTrafficHangHandler(BaseHTTPRequestHandler):
    collection_id = str(uuid4())

    def do_GET(self):
        if self.path.endswith("/heartbeat"):
            body = b'{"nanosecond heartbeat": 1}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length:
            self.rfile.read(content_length)
        if self.path.endswith("/collections"):
            body = (
                "{"
                f'"id":"{self.collection_id}",'
                '"name":"bounded_traffic",'
                '"configuration_json":{},'
                '"metadata":null,"dimension":null,'
                '"tenant":"default_tenant","database":"default_database"'
                "}"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.endswith("/upsert"):
            time.sleep(3)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, _format, *_args):
        pass


class _ProxyRecordingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.request_count += 1
        self.send_response(502)
        self.end_headers()

    def do_POST(self):
        self.server.request_count += 1
        self.send_response(502)
        self.end_headers()

    def log_message(self, _format, *_args):
        pass


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


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


@pytest.fixture
def heartbeat_then_hang_http_port():
    server, thread = _serve(_HeartbeatThenHangHandler)
    try:
        yield server.server_port
    finally:
        _stop_server(server, thread)


@pytest.fixture
def vector_traffic_hang_http_port():
    server, thread = _serve(_VectorTrafficHangHandler)
    try:
        yield server.server_port
    finally:
        _stop_server(server, thread)


@pytest.fixture
def recording_proxy():
    server, thread = _serve(_ProxyRecordingHandler)
    server.request_count = 0
    try:
        yield server
    finally:
        _stop_server(server, thread)


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


def test_http_mode_builds_only_bounded_http_client(monkeypatch, tmp_path):
    client = Mock()
    bounded_client = Mock(return_value=client)
    persistent_client = Mock()
    http_client = Mock(return_value=client)
    monkeypatch.setattr(vector_client, "BoundedChromaHttpClient", bounded_client)
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)
    monkeypatch.setattr(vector_client.chromadb, "HttpClient", http_client)
    configured = _chroma_settings(
        CHROMA_MODE="http",
        CHROMA_HOST="chroma.internal",
        CHROMA_PORT=8443,
        CHROMA_SSL=True,
        CHROMA_PERSIST_DIR=str(tmp_path / "must-not-exist"),
    )

    result = vector_client.build_chroma_client(
        settings_obj=configured
    )

    assert result is client
    bounded_client.assert_called_once_with(settings_obj=configured)
    client.heartbeat.assert_called_once_with()
    http_client.assert_not_called()
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
    store.client = vector_client.BoundedChromaHttpClient(settings_obj=configured)
    store.collection = Mock()
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "http")
    monkeypatch.setattr(vector_store.settings, "CHROMA_HOST", "127.0.0.1")
    monkeypatch.setattr(vector_store.settings, "CHROMA_PORT", hanging_http_port)
    monkeypatch.setattr(vector_store.settings, "CHROMA_SSL", False)
    monkeypatch.setattr(vector_store.settings, "CHROMA_TIMEOUT_SECONDS", 1.0)

    try:
        started = time.monotonic()
        assert store.is_ready() is False
        readiness_elapsed = time.monotonic() - started
    finally:
        store.client.close()

    assert startup_elapsed < 2.5
    assert readiness_elapsed < 2.5
    http_client.assert_not_called()
    persistent_client.assert_not_called()
    assert not (tmp_path / "must-not-exist").exists()


def test_http_adapter_accepts_native_openai_embedding_lists():
    values = [[0.1, 0.2], [0.3, 0.4]]
    assert vector_client._json_embeddings(values) is values


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
    bounded_client = Mock(side_effect=constructor_error)
    persistent_client = Mock()
    monkeypatch.setattr(vector_client, "BoundedChromaHttpClient", bounded_client)
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)

    with pytest.raises(vector_client.ChromaConnectionError) as exc_info:
        vector_client.build_chroma_client(
            settings_obj=_chroma_settings(CHROMA_MODE="http")
        )

    assert str(exc_info.value) == "Chroma HTTP service is unavailable"
    assert exc_info.value.__cause__ is constructor_error
    persistent_client.assert_not_called()


def test_bounded_adapter_does_not_call_failing_chroma_identity_endpoint(
    monkeypatch, tmp_path, constructor_failure_http_port
):
    persistent_client = Mock()
    http_client = Mock()
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)
    monkeypatch.setattr(vector_client.chromadb, "HttpClient", http_client)
    configured = _chroma_settings(
        CHROMA_MODE="http",
        CHROMA_HOST="127.0.0.1",
        CHROMA_PORT=constructor_failure_http_port,
        CHROMA_TIMEOUT_SECONDS=1.0,
        CHROMA_PERSIST_DIR=str(tmp_path / "must-not-exist"),
    )

    client = vector_client.build_chroma_client(settings_obj=configured)

    assert client.heartbeat() == 1
    client.close()
    http_client.assert_not_called()
    persistent_client.assert_not_called()
    assert not (tmp_path / "must-not-exist").exists()


def test_healthy_heartbeat_cannot_fall_into_hanging_constructor_network(
    heartbeat_then_hang_http_port
):
    configured = _chroma_settings(
        CHROMA_MODE="http",
        CHROMA_HOST="127.0.0.1",
        CHROMA_PORT=heartbeat_then_hang_http_port,
        CHROMA_TIMEOUT_SECONDS=1.0,
    )

    started = time.monotonic()
    client = vector_client.build_chroma_client(settings_obj=configured)

    assert time.monotonic() - started < 2.5
    assert isinstance(client, vector_client.BoundedChromaHttpClient)
    assert client.heartbeat() == 1


def test_http_initialization_and_traffic_ignore_ambient_proxy(
    monkeypatch, heartbeat_then_hang_http_port, recording_proxy
):
    proxy_url = f"http://127.0.0.1:{recording_proxy.server_port}"
    monkeypatch.setenv("HTTP_PROXY", proxy_url)
    monkeypatch.setenv("HTTPS_PROXY", proxy_url)
    monkeypatch.setenv("ALL_PROXY", proxy_url)
    monkeypatch.setenv("NO_PROXY", "")
    configured = _chroma_settings(
        CHROMA_MODE="http",
        CHROMA_HOST="127.0.0.1",
        CHROMA_PORT=heartbeat_then_hang_http_port,
        CHROMA_TIMEOUT_SECONDS=1.0,
    )

    client = vector_client.build_chroma_client(settings_obj=configured)

    assert client.heartbeat() == 1
    assert recording_proxy.request_count == 0


def test_vector_write_uses_the_same_bounded_no_proxy_transport(
    monkeypatch, vector_traffic_hang_http_port, recording_proxy
):
    proxy_url = f"http://127.0.0.1:{recording_proxy.server_port}"
    monkeypatch.setenv("HTTP_PROXY", proxy_url)
    monkeypatch.setenv("HTTPS_PROXY", proxy_url)
    monkeypatch.setenv("ALL_PROXY", proxy_url)
    monkeypatch.setenv("NO_PROXY", "")
    configured = _chroma_settings(
        CHROMA_MODE="http",
        CHROMA_HOST="127.0.0.1",
        CHROMA_PORT=vector_traffic_hang_http_port,
        CHROMA_TIMEOUT_SECONDS=1.0,
    )
    client = vector_client.build_chroma_client(settings_obj=configured)
    collection = client.get_or_create_collection(
        name="bounded_traffic", embedding_function=None
    )

    started = time.monotonic()
    with pytest.raises(vector_client.ChromaConnectionError, match="unavailable"):
        collection.upsert(ids=["one"], embeddings=[[0.1, 0.2]])

    assert time.monotonic() - started < 2.5
    assert recording_proxy.request_count == 0


def test_http_readiness_rechecks_heartbeat_and_returns_false(monkeypatch):
    client = Mock()
    client.heartbeat.side_effect = ConnectionError("server stopped")
    collection = Mock(name="active-collection", metadata=_TEST_IDENTITY)
    client.get_or_create_collection.return_value = collection
    monkeypatch.setattr(vector_store, "build_chroma_client", Mock(return_value=client))
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "http")

    store = vector_store.VectorStore(
        collection_name="ai_course_chunks",
        persist_directory="ignored-in-http-mode",
        embedding_function=Mock(),
        embedding_model="deterministic-test",
        embedding_dimensions=3,
        normalization_version="v1",
    )

    assert store.collection is collection
    assert store.is_ready() is False
    client.heartbeat.assert_called_once_with()


def test_embedded_readiness_uses_the_same_heartbeat_contract(monkeypatch, tmp_path):
    client = Mock()
    client.heartbeat.return_value = 1
    client.get_or_create_collection.return_value = Mock(metadata=_TEST_IDENTITY)
    monkeypatch.setattr(vector_store, "build_chroma_client", Mock(return_value=client))
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "embedded")

    store = vector_store.VectorStore(
        collection_name="ai_course_chunks",
        persist_directory=str(tmp_path),
        embedding_function=Mock(),
        embedding_model="deterministic-test",
        embedding_dimensions=3,
        normalization_version="v1",
    )

    assert store.is_ready() is True
    client.heartbeat.assert_called_once_with()


def test_http_identity_mismatch_is_not_reported_as_service_unavailable(monkeypatch):
    client = Mock()
    client.get_or_create_collection.return_value = Mock(metadata=None)
    monkeypatch.setattr(vector_store, "build_chroma_client", Mock(return_value=client))
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "http")

    with pytest.raises(vector_store.CollectionIdentityError, match="explicit new-index migration"):
        vector_store.VectorStore(
            collection_name="legacy_identity",
            persist_directory="ignored-in-http-mode",
            embedding_function=Mock(),
            embedding_model="deterministic-test",
            embedding_dimensions=3,
            normalization_version="v1",
        )

    client.close.assert_called_once_with()


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


def test_repeated_http_collection_init_failures_close_each_client_without_fallback(
    monkeypatch, tmp_path
):
    failures = [
        TimeoutError("collection request timed out"),
        ConnectionError("collection endpoint unavailable"),
        ValueError("invalid collection response"),
    ]
    clients = []
    for failure in failures:
        client = Mock()
        client.get_or_create_collection.side_effect = failure
        clients.append(client)

    build_client = Mock(side_effect=clients)
    persistent_client = Mock()
    monkeypatch.setattr(vector_store, "build_chroma_client", build_client)
    monkeypatch.setattr(vector_client.chromadb, "PersistentClient", persistent_client)
    monkeypatch.setattr(vector_store.settings, "CHROMA_MODE", "http")

    for failure in failures:
        with pytest.raises(vector_client.ChromaConnectionError) as exc_info:
            vector_store.VectorStore(
                collection_name="ai_course_chunks",
                persist_directory=str(tmp_path / "must-not-exist"),
                embedding_function=Mock(),
            )

        assert str(exc_info.value) == "Chroma HTTP service is unavailable"
        assert exc_info.value.__cause__ is failure

    assert build_client.call_count == 3
    for client in clients:
        client.close.assert_called_once_with()
    persistent_client.assert_not_called()
    assert not (tmp_path / "must-not-exist").exists()


def test_close_vector_store_closes_and_clears_singleton(monkeypatch):
    store = Mock()
    monkeypatch.setattr(vector_store, "_vector_store_instance", store)

    vector_store.close_vector_store()
    vector_store.close_vector_store()

    store.close.assert_called_once_with()
    assert vector_store._vector_store_instance is None


def test_application_lifespan_closes_vector_store_on_shutdown(monkeypatch):
    import main

    close_vector_store = Mock()
    monkeypatch.setattr(main, "seed_default_admin", Mock())
    monkeypatch.setattr(main, "reconcile_interrupted_inline_preprocess_jobs", Mock())
    monkeypatch.setattr(main, "reconcile_undispatched_jobs", Mock())
    monkeypatch.setattr(main, "close_vector_store", close_vector_store, raising=False)

    async def exercise_lifespan():
        async with main.lifespan(main.app):
            close_vector_store.assert_not_called()

    asyncio.run(exercise_lifespan())

    close_vector_store.assert_called_once_with()
