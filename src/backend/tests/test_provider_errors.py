from app.services.provider_errors import (
    ProviderErrorCode,
    ProviderRequestError,
    classify_openrouter_error,
)
from app.services.vector_store import OpenRouterEmbeddingFunction
import httpx


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class AlwaysFailsEmbeddings:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        raise self.error


class FakeClient:
    def __init__(self, embeddings):
        self.embeddings = embeddings


def build_embedding_function(error):
    function = OpenRouterEmbeddingFunction.__new__(OpenRouterEmbeddingFunction)
    embeddings = AlwaysFailsEmbeddings(error)
    function._client = FakeClient(embeddings)
    function._model = "openai/text-embedding-3-small"
    function._max_retries = 3
    function._max_retry_delay = 0
    return function, embeddings


def test_key_limit_403_is_manual_retry_only():
    failure = classify_openrouter_error(
        FakeStatusError(403, "Key limit exceeded (total limit)")
    )
    assert failure.code == ProviderErrorCode.KEY_LIMIT_EXCEEDED
    assert failure.can_retry is True
    assert failure.automatic_retry is False
    assert failure.recommended_action == "restore_provider_quota"
    assert "Key limit" not in failure.user_message


def test_rate_limit_429_is_automatic_retry():
    failure = classify_openrouter_error(FakeStatusError(429, "rate limited"))
    assert failure.code == ProviderErrorCode.RATE_LIMITED
    assert failure.automatic_retry is True


def test_invalid_key_and_payment_are_not_automatically_retried():
    invalid = classify_openrouter_error(FakeStatusError(401, "invalid api key"))
    payment = classify_openrouter_error(FakeStatusError(402, "payment required"))
    assert invalid.code == ProviderErrorCode.KEY_INVALID
    assert payment.code == ProviderErrorCode.CREDITS_EXHAUSTED
    assert invalid.automatic_retry is False
    assert payment.automatic_retry is False


def test_typed_httpx_timeout_is_automatically_retryable():
    request = httpx.Request("GET", "https://openrouter.ai/api/v1")
    failure = classify_openrouter_error(httpx.ReadTimeout("read timed out", request=request))
    assert failure.code == ProviderErrorCode.TIMEOUT
    assert failure.automatic_retry is True


def test_wrapped_httpx_connection_error_is_automatically_retryable():
    request = httpx.Request("GET", "https://openrouter.ai/api/v1")
    transport_error = httpx.ConnectError("connection reset", request=request)
    wrapper = RuntimeError("provider transport failed")
    wrapper.__cause__ = transport_error
    failure = classify_openrouter_error(wrapper)
    assert failure.code == ProviderErrorCode.UNAVAILABLE
    assert failure.automatic_retry is True


def test_technical_message_redacts_provider_secrets():
    exc = RuntimeError(
        "request failed Authorization: Bearer bearer-secret "
        "api_key=sk-or-v1-super-secret password=hunter2 token=jwt-secret; connection reset"
    )
    failure = classify_openrouter_error(exc)
    assert "bearer-secret" not in failure.technical_message
    assert "sk-or-v1-super-secret" not in failure.technical_message
    assert "hunter2" not in failure.technical_message
    assert "jwt-secret" not in failure.technical_message
    assert "connection reset" in failure.technical_message


def test_technical_message_redacts_json_secret_values():
    exc = RuntimeError(
        '{"api_key":"json-secret", "password": "json-password", '
        '"token" : "json-token", "Authorization": "Bearer json-bearer"}; upstream failed'
    )
    failure = classify_openrouter_error(exc)
    for secret in ("json-secret", "json-password", "json-token", "json-bearer"):
        assert secret not in failure.technical_message
    assert "api_key" in failure.technical_message
    assert "upstream failed" in failure.technical_message


def test_technical_message_redacts_python_dict_secret_values():
    exc = RuntimeError(
        "{'API_KEY': 'dict-secret', 'Password' : 'dict-password', "
        "'TOKEN':'dict-token', 'authorization': 'Bearer dict-bearer'}; request failed"
    )
    failure = classify_openrouter_error(exc)
    for secret in ("dict-secret", "dict-password", "dict-token", "dict-bearer"):
        assert secret not in failure.technical_message
    assert "API_KEY" in failure.technical_message
    assert "request failed" in failure.technical_message


def test_embedding_key_limit_stops_after_one_attempt():
    function, embeddings = build_embedding_function(
        FakeStatusError(403, "Key limit exceeded (total limit)")
    )
    try:
        function._embed(["document text"])
    except ProviderRequestError as exc:
        assert exc.failure.code == ProviderErrorCode.KEY_LIMIT_EXCEEDED
    else:
        raise AssertionError("ProviderRequestError was not raised")
    assert embeddings.calls == 1


def test_embedding_503_uses_all_three_attempts(monkeypatch):
    monkeypatch.setattr("app.services.vector_store.time.sleep", lambda _: None)
    function, embeddings = build_embedding_function(FakeStatusError(503, "unavailable"))
    try:
        function._embed(["document text"])
    except ProviderRequestError as exc:
        assert exc.failure.code == ProviderErrorCode.UNAVAILABLE
    else:
        raise AssertionError("ProviderRequestError was not raised")
    assert embeddings.calls == 3
