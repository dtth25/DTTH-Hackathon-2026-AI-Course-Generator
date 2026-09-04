import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.provider_errors import ProviderRequestError, classify_openrouter_error
from app.services.provider_guard import (
    ProviderCircuitOpen,
    ProviderGuard,
    ProviderGuardUnavailable,
    ProviderPermit,
)


class FakeClock:
    def __init__(self, value: float = 1_800_000_000.0):
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeRedis:
    """Redis subset with server-side-script semantics and the test clock as TIME."""

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.lock = threading.Lock()
        self.strings: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.expiry: dict[str, float] = {}

    def _purge(self) -> None:
        now = self.clock()
        for key, expires_at in list(self.expiry.items()):
            if expires_at <= now:
                self.strings.pop(key, None)
                self.zsets.pop(key, None)
                self.expiry.pop(key, None)

    def get(self, key: str):
        self._purge()
        return self.strings.get(key)

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            deleted += int(key in self.strings or key in self.zsets)
            self.strings.pop(key, None)
            self.zsets.pop(key, None)
            self.expiry.pop(key, None)
        return deleted

    def eval(self, script: str, numkeys: int, *values):
        with self.lock:
            return self._eval(script, numkeys, *values)

    def _eval(self, script: str, numkeys: int, *values):
        del numkeys
        self._purge()
        operation = script.splitlines()[0]
        if operation == "-- hackagen-provider-acquire":
            inflight, rpm_prefix, open_until = values[:3]
            permit_id, lease_seconds, max_inflight, rpm_limit = values[3:]
            now = float(self.clock())
            rpm = f"{rpm_prefix}{int(now // 60)}"
            rpm_ttl = max(1, 61 - int(now) % 60)
            open_value = float(self.strings.get(open_until, "0"))
            if open_value > now:
                return [0, "circuit", max(1, int(open_value - now + 0.999))]
            leases = self.zsets.setdefault(inflight, {})
            for member, expires_at in list(leases.items()):
                if expires_at <= now:
                    del leases[member]
            if len(leases) >= int(max_inflight):
                oldest = min(leases.values())
                return [0, "inflight", max(1, int(oldest - now + 0.999))]
            rpm_count = int(self.strings.get(rpm, "0"))
            if rpm_count >= int(rpm_limit):
                retry_after = max(1, 60 - int(now) % 60)
                return [0, "rpm", retry_after]
            leases[str(permit_id)] = now + int(lease_seconds)
            self.expiry[inflight] = now + int(lease_seconds) + 1
            self.strings[rpm] = str(rpm_count + 1)
            self.expiry[rpm] = now + int(rpm_ttl)
            return [1, "ok", 0]
        if operation == "-- hackagen-provider-release":
            inflight, permit_id = values
            leases = self.zsets.get(inflight, {})
            removed = int(str(permit_id) in leases)
            leases.pop(str(permit_id), None)
            return removed
        if operation == "-- hackagen-provider-failure":
            failures, open_until = values[:2]
            member, window, threshold, open_seconds = values[2:]
            now = float(self.clock())
            recent = self.zsets.setdefault(failures, {})
            for item, occurred_at in list(recent.items()):
                if occurred_at <= now - int(window):
                    del recent[item]
            recent[str(member)] = now
            self.expiry[failures] = now + int(window) + 1
            count = len(recent)
            if count >= int(threshold):
                proposed = now + int(open_seconds)
                deadline = max(
                    float(self.strings.get(open_until, "0")), proposed
                )
                self.strings[open_until] = str(deadline)
                self.expiry[open_until] = deadline + 1
                return [count, max(1, int(deadline - now + 0.999))]
            return [count, 0]
        if operation == "-- hackagen-provider-open":
            open_until, seconds = values
            now = float(self.clock())
            proposed = now + int(seconds)
            deadline = max(float(self.strings.get(open_until, "0")), proposed)
            self.strings[open_until] = str(deadline)
            self.expiry[open_until] = deadline + 1
            return max(1, int(deadline - now + 0.999))
        raise AssertionError(f"unexpected Lua script: {operation}")


class BrokenRedis:
    def eval(self, *_args, **_kwargs):
        raise ConnectionError("redis is unavailable")


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def guard_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "JOB_QUEUE_PROVIDER": "celery",
        "OPENROUTER_MAX_IN_FLIGHT": 6,
        "OPENROUTER_RPM": 60,
        "OPENROUTER_CIRCUIT_FAILURES": 5,
        "OPENROUTER_CIRCUIT_WINDOW_SECONDS": 60,
        "OPENROUTER_CIRCUIT_OPEN_SECONDS": 30,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_six_concurrent_permits_succeed_and_seventh_is_delayed():
    clock = FakeClock()
    guard = ProviderGuard(
        redis_client=FakeRedis(clock), settings_obj=guard_settings(), clock=clock
    )

    permits = [guard.acquire("generation") for _ in range(6)]

    assert len({permit.permit_id for permit in permits}) == 6
    assert all(permit.kind == "generation" for permit in permits)
    with pytest.raises(ProviderCircuitOpen) as caught:
        guard.acquire("generation")
    assert caught.value.reason == "inflight"
    assert caught.value.retry_after > 0


def test_release_removes_only_the_matching_opaque_permit():
    clock = FakeClock()
    guard = ProviderGuard(
        redis_client=FakeRedis(clock), settings_obj=guard_settings(), clock=clock
    )
    permits = [guard.acquire("ocr") for _ in range(6)]

    guard.release(ProviderPermit(kind="ocr", permit_id="not-a-real-lease"))
    with pytest.raises(ProviderCircuitOpen):
        guard.acquire("ocr")

    guard.release(permits[2])
    assert guard.acquire("ocr").kind == "ocr"


def test_rpm_gate_counts_completed_calls_until_the_minute_changes():
    clock = FakeClock(value=1_800_000_010.0)
    guard = ProviderGuard(
        redis_client=FakeRedis(clock),
        settings_obj=guard_settings(OPENROUTER_MAX_IN_FLIGHT=32, OPENROUTER_RPM=2),
        clock=clock,
    )
    for _ in range(2):
        permit = guard.acquire("embedding")
        guard.release(permit)

    with pytest.raises(ProviderCircuitOpen) as caught:
        guard.acquire("embedding")
    assert caught.value.reason == "rpm"
    assert caught.value.retry_after == 50

    clock.advance(50)
    assert guard.acquire("embedding").kind == "embedding"


def test_key_limit_403_opens_the_circuit_immediately():
    clock = FakeClock()
    redis = FakeRedis(clock)
    guard = ProviderGuard(redis_client=redis, settings_obj=guard_settings(), clock=clock)
    failure = classify_openrouter_error(
        FakeStatusError(403, "Key limit exceeded (total limit)")
    )

    guard.record_failure("embedding", failure)

    with pytest.raises(ProviderCircuitOpen) as caught:
        guard.acquire("embedding")
    assert caught.value.reason == "circuit"
    assert caught.value.retry_after == 300


def test_five_5xx_failures_within_window_open_for_thirty_seconds():
    clock = FakeClock()
    guard = ProviderGuard(
        redis_client=FakeRedis(clock), settings_obj=guard_settings(), clock=clock
    )
    failure = classify_openrouter_error(FakeStatusError(503, "unavailable"))

    for _ in range(5):
        guard.record_failure("generation", failure)

    with pytest.raises(ProviderCircuitOpen) as caught:
        guard.acquire("generation")
    assert caught.value.retry_after == 30
    clock.advance(30)
    assert guard.acquire("generation").kind == "generation"


def test_429_retry_after_is_capped_at_five_minutes():
    clock = FakeClock()
    guard = ProviderGuard(
        redis_client=FakeRedis(clock), settings_obj=guard_settings(), clock=clock
    )
    failure = classify_openrouter_error(FakeStatusError(429, "rate limited"))

    guard.record_failure("ocr", failure, retry_after=999)

    with pytest.raises(ProviderCircuitOpen) as caught:
        guard.acquire("ocr")
    assert caught.value.retry_after == 300


@pytest.mark.parametrize("order", ["stronger_first", "shorter_first"])
@pytest.mark.parametrize("shorter_failure", ["rate_limit", "failure_threshold"])
def test_circuit_deadline_order_permutations_preserve_strongest_deadline(
    shorter_failure, order
):
    server_clock = FakeClock()
    guard = ProviderGuard(
        redis_client=FakeRedis(server_clock),
        settings_obj=guard_settings(),
        clock=FakeClock(server_clock() + 10_000),
    )
    quota = classify_openrouter_error(
        FakeStatusError(403, "Key limit exceeded (total limit)")
    )
    rate_limit = classify_openrouter_error(FakeStatusError(429, "rate limited"))
    unavailable = classify_openrouter_error(FakeStatusError(503, "unavailable"))
    def record_shorter_failure() -> None:
        if shorter_failure == "rate_limit":
            guard.record_failure("generation", rate_limit, retry_after=20)
        else:
            for _ in range(5):
                guard.record_failure("generation", unavailable)

    if order == "stronger_first":
        guard.record_failure("generation", quota)
        server_clock.advance(10)
        record_shorter_failure()
        expected_retry = 290
    else:
        record_shorter_failure()
        server_clock.advance(10)
        guard.record_failure("generation", quota)
        expected_retry = 300

    with pytest.raises(ProviderCircuitOpen) as caught:
        guard.acquire("generation")
    assert caught.value.retry_after == expected_retry


def test_concurrent_circuit_openers_preserve_the_strongest_deadline():
    server_clock = FakeClock()
    redis = FakeRedis(server_clock)
    guard = ProviderGuard(
        redis_client=redis, settings_obj=guard_settings(), clock=FakeClock(1.0)
    )
    quota = classify_openrouter_error(
        FakeStatusError(403, "Key limit exceeded (total limit)")
    )
    rate_limit = classify_openrouter_error(FakeStatusError(429, "rate limited"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda item: guard.record_failure(
                    "ocr", item[0], retry_after=item[1]
                ),
                ((quota, None), (rate_limit, 20)),
            )
        )

    assert max(results) == 300
    with pytest.raises(ProviderCircuitOpen) as caught:
        guard.acquire("ocr")
    assert caught.value.retry_after == 300


def test_redis_time_prevents_skewed_workers_from_reaping_live_permits_or_circuit():
    server_clock = FakeClock()
    redis = FakeRedis(server_clock)
    slow = ProviderGuard(
        redis_client=redis,
        settings_obj=guard_settings(OPENROUTER_MAX_IN_FLIGHT=1),
        clock=FakeClock(server_clock() - 3_700),
    )
    fast = ProviderGuard(
        redis_client=redis,
        settings_obj=guard_settings(OPENROUTER_MAX_IN_FLIGHT=1),
        clock=FakeClock(server_clock() + 3_700),
    )
    quota = classify_openrouter_error(
        FakeStatusError(403, "Key limit exceeded (total limit)")
    )

    permit = slow.acquire("embedding")
    with pytest.raises(ProviderCircuitOpen) as inflight:
        fast.acquire("embedding")
    assert inflight.value.reason == "inflight"
    slow.release(permit)

    slow.record_failure("embedding", quota)
    with pytest.raises(ProviderCircuitOpen) as circuit:
        fast.acquire("embedding")
    assert circuit.value.reason == "circuit"
    assert circuit.value.retry_after == 300


def test_redis_time_keeps_skewed_workers_in_one_rpm_bucket():
    server_clock = FakeClock(value=1_800_000_010.0)
    redis = FakeRedis(server_clock)
    config = guard_settings(OPENROUTER_MAX_IN_FLIGHT=32, OPENROUTER_RPM=2)
    slow = ProviderGuard(
        redis_client=redis,
        settings_obj=config,
        clock=FakeClock(server_clock() - 120),
    )
    fast = ProviderGuard(
        redis_client=redis,
        settings_obj=config,
        clock=FakeClock(server_clock() + 120),
    )
    for guard in (slow, fast):
        permit = guard.acquire("ocr")
        guard.release(permit)

    with pytest.raises(ProviderCircuitOpen) as caught:
        fast.acquire("ocr")

    assert caught.value.reason == "rpm"
    assert caught.value.retry_after == 50
    rpm_keys = [key for key in redis.strings if ":rpm:" in key]
    assert rpm_keys == ["hackagen:provider:ocr:rpm:30000000"]


def test_success_clears_transient_failure_count():
    clock = FakeClock()
    guard = ProviderGuard(
        redis_client=FakeRedis(clock), settings_obj=guard_settings(), clock=clock
    )
    failure = classify_openrouter_error(FakeStatusError(503, "unavailable"))
    for _ in range(4):
        guard.record_failure("embedding", failure)

    guard.record_success("embedding")
    guard.record_failure("embedding", failure)

    assert guard.acquire("embedding").kind == "embedding"


def test_production_redis_failure_fails_closed_with_retryable_infrastructure_error():
    clock = FakeClock()
    guard = ProviderGuard(
        redis_client=BrokenRedis(), settings_obj=guard_settings(), clock=clock
    )

    with pytest.raises(ProviderGuardUnavailable) as caught:
        guard.acquire("generation")

    assert caught.value.retry_after > 0
    assert caught.value.can_retry is True
    assert "redis" not in str(caught.value).casefold()


def test_local_inline_guard_remains_usable_without_redis():
    clock = FakeClock()
    guard = ProviderGuard(
        redis_client=None,
        settings_obj=guard_settings(ENVIRONMENT="local", JOB_QUEUE_PROVIDER="inline"),
        clock=clock,
    )

    permit = guard.acquire("generation")
    guard.release(permit)

    assert guard.acquire("generation").kind == "generation"


@pytest.mark.parametrize("environment", ["local", "test", "production"])
def test_non_official_base_url_is_rejected_outside_loadtest(environment):
    values = {
        "DATABASE_URL": "sqlite:///./test.db",
        "JWT_SECRET": "test-secret",
        "OPENROUTER_API_KEY": "test-key",
        "ENVIRONMENT": environment,
        "JOB_QUEUE_PROVIDER": "celery" if environment == "production" else "inline",
        "OPENROUTER_BASE_URL": "http://mock-provider:8001/api/v1",
    }

    with pytest.raises(ValidationError, match="only in loadtest"):
        Settings(**values)


def test_loadtest_accepts_non_official_base_url_and_exact_guard_defaults():
    configured = Settings(
        DATABASE_URL="sqlite:///./test.db",
        JWT_SECRET="test-secret",
        OPENROUTER_API_KEY="test-key",
        ENVIRONMENT="loadtest",
        OPENROUTER_BASE_URL="http://mock-provider:8001/api/v1/",
    )

    assert configured.OPENROUTER_BASE_URL == "http://mock-provider:8001/api/v1"
    assert configured.OPENROUTER_MAX_IN_FLIGHT == 6
    assert configured.OPENROUTER_RPM == 60
    assert configured.OPENROUTER_CIRCUIT_FAILURES == 5
    assert configured.OPENROUTER_CIRCUIT_WINDOW_SECONDS == 60
    assert configured.OPENROUTER_CIRCUIT_OPEN_SECONDS == 30


def test_generic_forced_preflight_does_not_clear_stale_circuits(monkeypatch):
    from datetime import UTC, datetime

    from app.services import provider_health
    from app.services.provider_health import ProviderHealth

    healthy = ProviderHealth(
        available=True,
        error_code=None,
        checked_at=datetime.now(UTC),
        limit=10,
        limit_remaining=9,
        limit_reset=None,
        content_model_available=True,
        embedding_model_available=True,
    )
    guard = Mock()
    monkeypatch.setattr(provider_health, "_check_openrouter_health", lambda: healthy)
    monkeypatch.setattr(provider_health, "get_provider_guard", lambda: guard)
    monkeypatch.setattr(provider_health, "_cached_health", None)
    monkeypatch.setattr(provider_health, "_cached_at", 0.0)

    assert provider_health.get_openrouter_health(force=True).available is True

    guard.reset_after_successful_preflight.assert_not_called()


def test_explicit_successful_preflight_reset_intent_clears_stale_circuits(
    monkeypatch,
):
    from datetime import UTC, datetime

    from app.services import provider_health
    from app.services.provider_health import ProviderHealth

    healthy = ProviderHealth(
        available=True,
        error_code=None,
        checked_at=datetime.now(UTC),
        limit=10,
        limit_remaining=9,
        limit_reset=None,
        content_model_available=True,
        embedding_model_available=True,
    )
    guard = Mock()
    monkeypatch.setattr(provider_health, "_check_openrouter_health", lambda: healthy)
    monkeypatch.setattr(provider_health, "get_provider_guard", lambda: guard)
    monkeypatch.setattr(provider_health, "_cached_health", None)
    monkeypatch.setattr(provider_health, "_cached_at", 0.0)

    result = provider_health.get_openrouter_health(
        force=True, reset_circuit=True
    )

    assert result.available is True
    guard.reset_after_successful_preflight.assert_called_once_with()


@pytest.mark.parametrize(
    ("method", "kind", "payload"),
    [
        ("content", "generation", '{"title": "Guarded"}'),
        ("ocr", "ocr", "Văn bản"),
    ],
)
def test_llm_calls_are_guarded_and_release_their_exact_permit(method, kind, payload):
    from app.services.llm import LLMService

    permit = ProviderPermit(kind=kind, permit_id="opaque-permit")
    guard = Mock()
    guard.acquire.return_value = permit
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
    )
    completions = Mock()
    completions.create.return_value = completion
    llm = LLMService()
    llm._provider_guard = guard
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    if method == "content":
        assert llm.generate_course_title("source").title == "Guarded"
    else:
        assert llm.ocr_page_image(b"png") == "Văn bản"

    guard.acquire.assert_called_once_with(kind)
    guard.record_success.assert_called_once_with(kind)
    guard.release.assert_called_once_with(permit)


def test_embedding_call_records_classified_failure_and_releases(monkeypatch):
    from app.services.vector_store import OpenRouterEmbeddingFunction

    permit = ProviderPermit(kind="embedding", permit_id="opaque-permit")
    guard = Mock()
    guard.acquire.return_value = permit
    guard.record_failure.return_value = None
    embeddings = Mock()
    embeddings.create.side_effect = FakeStatusError(403, "key limit exceeded")
    function = OpenRouterEmbeddingFunction.__new__(OpenRouterEmbeddingFunction)
    function._client = SimpleNamespace(embeddings=embeddings)
    function._model = "embedding-model"
    function._max_retries = 3
    function._max_retry_delay = 0
    function._provider_guard = guard
    monkeypatch.setattr("app.services.vector_store.time.sleep", lambda _: None)

    with pytest.raises(ProviderRequestError):
        function._embed(["text stays outside guard records"])

    guard.acquire.assert_called_once_with("embedding")
    recorded_failure = guard.record_failure.call_args.args[1]
    assert recorded_failure.code == "OPENROUTER_KEY_LIMIT_EXCEEDED"
    guard.release.assert_called_once_with(permit)


def test_distributed_embedding_retry_is_scheduled_without_worker_sleep(monkeypatch):
    from app.services.vector_store import OpenRouterEmbeddingFunction

    clock = FakeClock()
    guard = ProviderGuard(
        redis_client=FakeRedis(clock), settings_obj=guard_settings(), clock=clock
    )
    embeddings = Mock()
    embeddings.create.side_effect = FakeStatusError(503, "unavailable")
    function = OpenRouterEmbeddingFunction.__new__(OpenRouterEmbeddingFunction)
    function._client = SimpleNamespace(embeddings=embeddings)
    function._model = "embedding-model"
    function._max_retries = 3
    function._max_retry_delay = 60
    function._provider_guard = guard
    sleep = Mock()
    monkeypatch.setattr("app.services.vector_store.time.sleep", sleep)

    with pytest.raises(ProviderCircuitOpen) as caught:
        function._embed(["text remains in the SDK call only"])

    assert caught.value.reason == "transient"
    assert caught.value.error_code == "AI_UNAVAILABLE"
    assert embeddings.create.call_count == 1
    sleep.assert_not_called()
