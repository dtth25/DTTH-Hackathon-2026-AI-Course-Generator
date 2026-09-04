"""Shared rate and circuit protection for backend OpenRouter calls.

Redis records contain only opaque permit/failure ids and numeric timestamps.  Local
inline execution uses the same semantics in memory so development does not require a
Redis process; distributed execution always fails closed when Redis is unavailable.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.provider_errors import ProviderErrorCode, ProviderFailure


logger = logging.getLogger(__name__)

_KINDS = frozenset({"embedding", "generation", "ocr"})
_PERMIT_TTL_SECONDS = 3600
_PERMANENT_CIRCUIT_SECONDS = 300
_INFRASTRUCTURE_RETRY_SECONDS = 5

_ACQUIRE_SCRIPT = """-- hackagen-provider-acquire
local inflight = KEYS[1]
local rpm = KEYS[2]
local open_until = KEYS[3]
local permit_id = ARGV[1]
local now = tonumber(ARGV[2])
local lease_seconds = tonumber(ARGV[3])
local max_inflight = tonumber(ARGV[4])
local rpm_limit = tonumber(ARGV[5])
local rpm_ttl = tonumber(ARGV[6])

local circuit_deadline = tonumber(redis.call('GET', open_until) or '0')
if circuit_deadline > now then
  return {0, 'circuit', math.max(1, math.ceil(circuit_deadline - now))}
end

redis.call('ZREMRANGEBYSCORE', inflight, '-inf', now)
if redis.call('ZCARD', inflight) >= max_inflight then
  local oldest = redis.call('ZRANGE', inflight, 0, 0, 'WITHSCORES')
  local retry_after = 1
  if oldest[2] then
    retry_after = math.max(1, math.ceil(tonumber(oldest[2]) - now))
  end
  return {0, 'inflight', retry_after}
end

local rpm_count = tonumber(redis.call('GET', rpm) or '0')
if rpm_count >= rpm_limit then
  return {0, 'rpm', math.max(1, 60 - (math.floor(now) % 60))}
end

redis.call('ZADD', inflight, now + lease_seconds, permit_id)
redis.call('EXPIRE', inflight, lease_seconds + 1)
local count = redis.call('INCR', rpm)
if count == 1 then
  redis.call('EXPIRE', rpm, rpm_ttl)
end
return {1, 'ok', 0}
"""

_RELEASE_SCRIPT = """-- hackagen-provider-release
local removed = redis.call('ZREM', KEYS[1], ARGV[1])
if redis.call('ZCARD', KEYS[1]) == 0 then
  redis.call('DEL', KEYS[1])
end
return removed
"""

_FAILURE_SCRIPT = """-- hackagen-provider-failure
local failures = KEYS[1]
local open_until = KEYS[2]
local member = ARGV[1]
local now = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local threshold = tonumber(ARGV[4])
local open_seconds = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', failures, '-inf', now - window)
redis.call('ZADD', failures, now, member)
redis.call('EXPIRE', failures, window + 1)
local count = redis.call('ZCARD', failures)
if count >= threshold then
  redis.call('SET', open_until, now + open_seconds, 'EX', open_seconds + 1)
end
return count
"""

_OPEN_SCRIPT = """-- hackagen-provider-open
local now = tonumber(ARGV[1])
local seconds = tonumber(ARGV[2])
redis.call('SET', KEYS[1], now + seconds, 'EX', seconds + 1)
return 1
"""


@dataclass(frozen=True, slots=True)
class ProviderPermit:
    """One opaque provider-call lease; no request or user data is retained."""

    kind: str
    permit_id: str


class ProviderCircuitOpen(RuntimeError):
    """Retryable provider-capacity signal consumed by durable workers."""

    def __init__(
        self,
        retry_after: int,
        reason: str = "circuit",
        error_code: str = "AI_RATE_LIMITED",
    ) -> None:
        self.retry_after = max(1, min(300, int(retry_after)))
        self.reason = reason
        self.can_retry = True
        self.error_code = error_code
        super().__init__("AI capacity is temporarily unavailable.")


class ProviderGuardUnavailable(ProviderCircuitOpen):
    """The distributed guard cannot safely authorize a provider request."""

    def __init__(self, retry_after: int = _INFRASTRUCTURE_RETRY_SECONDS) -> None:
        super().__init__(retry_after, reason="infrastructure")
        self.error_code = "AI_UNAVAILABLE"


def retry_after_seconds(exc: Exception) -> int | None:
    """Read a numeric Retry-After without retaining response or header content."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    value = headers.get("Retry-After") if headers is not None else None
    if value is None and headers is not None:
        value = headers.get("retry-after")
    if value is None:
        value = getattr(exc, "retry_after", None)
    try:
        parsed = math.ceil(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return max(1, min(300, parsed))


class ProviderGuard:
    """Atomic per-kind provider rate gate and circuit breaker."""

    def __init__(
        self,
        redis_client: Any | None = None,
        *,
        settings_obj: Any = settings,
        clock=time.time,
    ) -> None:
        self._settings = settings_obj
        self._clock = clock
        self._distributed = (
            settings_obj.JOB_QUEUE_PROVIDER == "celery"
            or settings_obj.ENVIRONMENT == "production"
        )
        self._redis = redis_client
        if self._distributed and self._redis is None:
            from redis import Redis

            self._redis = Redis.from_url(
                settings_obj.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        self._lock = threading.Lock()
        self._local_inflight: dict[str, dict[str, float]] = {}
        self._local_rpm: dict[tuple[str, int], int] = {}
        self._local_failures: dict[str, list[float]] = {}
        self._local_open_until: dict[str, float] = {}

    @staticmethod
    def _validate_kind(kind: str) -> str:
        if kind not in _KINDS:
            raise ValueError("Unsupported provider guard kind.")
        return kind

    @property
    def distributed(self) -> bool:
        return self._distributed

    @staticmethod
    def _key(kind: str, suffix: str) -> str:
        return f"hackagen:provider:{kind}:{suffix}"

    @staticmethod
    def _decode(value: Any) -> str:
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    def _redis_error(self, operation: str, exc: Exception) -> ProviderGuardUnavailable:
        logger.warning("Provider guard %s failed with %s", operation, type(exc).__name__)
        return ProviderGuardUnavailable()

    def acquire(self, kind: str) -> ProviderPermit:
        kind = self._validate_kind(kind)
        now = float(self._clock())
        permit = ProviderPermit(kind=kind, permit_id=uuid.uuid4().hex)
        minute = int(now // 60)
        if self._redis is not None:
            try:
                result = self._redis.eval(
                    _ACQUIRE_SCRIPT,
                    3,
                    self._key(kind, "inflight"),
                    self._key(kind, f"rpm:{minute}"),
                    self._key(kind, "open_until"),
                    permit.permit_id,
                    now,
                    _PERMIT_TTL_SECONDS,
                    self._settings.OPENROUTER_MAX_IN_FLIGHT,
                    self._settings.OPENROUTER_RPM,
                    max(1, 61 - int(now) % 60),
                )
            except Exception as exc:
                raise self._redis_error("acquire", exc) from exc
            if int(result[0]) != 1:
                raise ProviderCircuitOpen(
                    int(result[2]), reason=self._decode(result[1])
                )
            return permit

        with self._lock:
            open_until = self._local_open_until.get(kind, 0.0)
            if open_until > now:
                raise ProviderCircuitOpen(math.ceil(open_until - now))
            leases = self._local_inflight.setdefault(kind, {})
            leases = {
                permit_id: expires_at
                for permit_id, expires_at in leases.items()
                if expires_at > now
            }
            self._local_inflight[kind] = leases
            if len(leases) >= self._settings.OPENROUTER_MAX_IN_FLIGHT:
                raise ProviderCircuitOpen(
                    math.ceil(min(leases.values()) - now), reason="inflight"
                )
            rpm_key = (kind, minute)
            rpm_count = self._local_rpm.get(rpm_key, 0)
            if rpm_count >= self._settings.OPENROUTER_RPM:
                raise ProviderCircuitOpen(
                    max(1, 60 - int(now) % 60), reason="rpm"
                )
            self._local_inflight[kind][permit.permit_id] = (
                now + _PERMIT_TTL_SECONDS
            )
            self._local_rpm[rpm_key] = rpm_count + 1
            self._local_rpm = {
                key: count
                for key, count in self._local_rpm.items()
                if key[1] >= minute - 1
            }
        return permit

    def release(self, permit: ProviderPermit) -> None:
        kind = self._validate_kind(permit.kind)
        if self._redis is not None:
            try:
                self._redis.eval(
                    _RELEASE_SCRIPT,
                    1,
                    self._key(kind, "inflight"),
                    permit.permit_id,
                )
            except Exception as exc:
                # The lease TTL is the recovery path. Do not hide an SDK failure with a
                # secondary release failure from the finally block.
                logger.warning(
                    "Provider guard release failed with %s", type(exc).__name__
                )
            return
        with self._lock:
            self._local_inflight.get(kind, {}).pop(permit.permit_id, None)

    def _open(self, kind: str, seconds: int) -> None:
        seconds = max(1, min(300, int(seconds)))
        now = float(self._clock())
        if self._redis is not None:
            try:
                self._redis.eval(
                    _OPEN_SCRIPT,
                    1,
                    self._key(kind, "open_until"),
                    now,
                    seconds,
                )
            except Exception as exc:
                raise self._redis_error("open", exc) from exc
            return
        with self._lock:
            self._local_open_until[kind] = now + seconds

    def record_failure(
        self,
        kind: str,
        failure: ProviderFailure,
        *,
        retry_after: int | None = None,
    ) -> int | None:
        kind = self._validate_kind(kind)
        code = ProviderErrorCode(failure.code)
        if code in {
            ProviderErrorCode.KEY_INVALID,
            ProviderErrorCode.KEY_LIMIT_EXCEEDED,
            ProviderErrorCode.CREDITS_EXHAUSTED,
            ProviderErrorCode.ACCESS_DENIED,
        }:
            self._open(kind, _PERMANENT_CIRCUIT_SECONDS)
            return _PERMANENT_CIRCUIT_SECONDS
        if code == ProviderErrorCode.RATE_LIMITED:
            requested = retry_after
            if requested is None:
                requested = getattr(failure, "retry_after", None)
            seconds = max(
                1,
                min(
                    300,
                    int(requested or self._settings.OPENROUTER_CIRCUIT_OPEN_SECONDS),
                ),
            )
            self._open(kind, seconds)
            return seconds
        if code not in {ProviderErrorCode.UNAVAILABLE, ProviderErrorCode.TIMEOUT}:
            return None

        now = float(self._clock())
        if self._redis is not None:
            try:
                count = self._redis.eval(
                    _FAILURE_SCRIPT,
                    2,
                    self._key(kind, "failures"),
                    self._key(kind, "open_until"),
                    uuid.uuid4().hex,
                    now,
                    self._settings.OPENROUTER_CIRCUIT_WINDOW_SECONDS,
                    self._settings.OPENROUTER_CIRCUIT_FAILURES,
                    self._settings.OPENROUTER_CIRCUIT_OPEN_SECONDS,
                )
            except Exception as exc:
                raise self._redis_error("record failure", exc) from exc
            if int(count) >= self._settings.OPENROUTER_CIRCUIT_FAILURES:
                return self._settings.OPENROUTER_CIRCUIT_OPEN_SECONDS
            return None
        with self._lock:
            cutoff = now - self._settings.OPENROUTER_CIRCUIT_WINDOW_SECONDS
            failures = [
                occurred_at
                for occurred_at in self._local_failures.get(kind, [])
                if occurred_at > cutoff
            ]
            failures.append(now)
            self._local_failures[kind] = failures
            if len(failures) >= self._settings.OPENROUTER_CIRCUIT_FAILURES:
                self._local_open_until[kind] = (
                    now + self._settings.OPENROUTER_CIRCUIT_OPEN_SECONDS
                )
                return self._settings.OPENROUTER_CIRCUIT_OPEN_SECONDS
        return None

    def record_success(self, kind: str) -> None:
        kind = self._validate_kind(kind)
        if self._redis is not None:
            try:
                self._redis.delete(self._key(kind, "failures"))
            except Exception as exc:
                raise self._redis_error("record success", exc) from exc
            return
        with self._lock:
            self._local_failures.pop(kind, None)

    def reset_after_successful_preflight(self) -> None:
        keys = [
            self._key(kind, suffix)
            for kind in _KINDS
            for suffix in ("failures", "open_until")
        ]
        if self._redis is not None:
            try:
                self._redis.delete(*keys)
            except Exception as exc:
                raise self._redis_error("preflight reset", exc) from exc
            return
        with self._lock:
            self._local_failures.clear()
            self._local_open_until.clear()


_guard: ProviderGuard | None = None
_guard_lock = threading.Lock()


def get_provider_guard() -> ProviderGuard:
    global _guard
    if _guard is None:
        with _guard_lock:
            if _guard is None:
                _guard = ProviderGuard()
    return _guard
