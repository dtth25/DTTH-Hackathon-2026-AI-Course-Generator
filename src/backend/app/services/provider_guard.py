"""Shared rate and circuit protection for backend OpenRouter calls.

Redis records contain only opaque permit/failure ids and numeric timestamps.  Local
inline execution uses the same semantics in memory so development does not require a
Redis process; distributed execution always fails closed when Redis is unavailable.
"""

from __future__ import annotations

import logging
import math
import random
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
# A rate-limit response can defer a durable continuation for a complete minute.
# Keep its opaque fairness record through that interval (and the bounded broker
# delay) instead of allowing redelivery timing to reorder waiting owners/jobs.
_FAIR_WAITER_MIN_TTL_SECONDS = 61

_ACQUIRE_SCRIPT = """-- hackagen-provider-acquire
local inflight = KEYS[1]
local rpm_prefix = KEYS[2]
local open_until = KEYS[3]
local permit_id = ARGV[1]
local lease_seconds = tonumber(ARGV[2])
local max_inflight = tonumber(ARGV[3])
local rpm_limit = tonumber(ARGV[4])
local redis_time = redis.call('TIME')
local seconds = tonumber(redis_time[1])
local now = seconds + tonumber(redis_time[2]) / 1000000
local rpm = rpm_prefix .. math.floor(seconds / 60)
local rpm_ttl = math.max(1, 61 - (seconds % 60))

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

# The generation gate keeps a compact, opaque waiter record per request.  It is
# deliberately separate from the generic gate above: Book work has a durable
# continuation path, so a worker which just released a permit must not repeatedly
# jump ahead of an already waiting owner/job in another process.
_FAIR_GENERATION_ACQUIRE_SCRIPT = """-- hackagen-provider-fair-generation-acquire
local inflight = KEYS[1]
local rpm_prefix = KEYS[2]
local open_until = KEYS[3]
local waiters = KEYS[4]
local sequence = KEYS[5]
local last_owner = KEYS[6]
local last_job = KEYS[7]
local waiter_prefix = KEYS[8]
local permit_id = ARGV[1]
local lease_seconds = tonumber(ARGV[2])
local max_inflight = tonumber(ARGV[3])
local rpm_limit = tonumber(ARGV[4])
local owner = ARGV[5]
local job = ARGV[6]
local request_id = ARGV[7]
local waiter_ttl = tonumber(ARGV[8])
local redis_time = redis.call('TIME')
local seconds = tonumber(redis_time[1])
local now = seconds + tonumber(redis_time[2]) / 1000000
local rpm = rpm_prefix .. math.floor(seconds / 60)
local rpm_ttl = math.max(1, 61 - (seconds % 60))

-- Individual records expire even if a continuation is cancelled.  Reap their
-- sorted-set entries before selecting the next owner/job.
for _, queued_request in ipairs(redis.call('ZRANGE', waiters, 0, -1)) do
  local record = redis.call('GET', waiter_prefix .. queued_request)
  if not record then
    redis.call('ZREM', waiters, queued_request)
  else
    local first = string.find(record, string.char(31), 1, true)
    local second = first and string.find(record, string.char(31), first + 1, true)
    local expires_at = second and tonumber(string.sub(record, second + 1)) or 0
    if expires_at <= now then
      redis.call('DEL', waiter_prefix .. queued_request)
      redis.call('ZREM', waiters, queued_request)
    end
  end
end

local record_key = waiter_prefix .. request_id
if not redis.call('GET', record_key) then
  local position = redis.call('INCR', sequence)
  redis.call('ZADD', waiters, position, request_id)
end
-- A continuation renews its existing identity without changing its queue
-- position, so consecutive RPM windows cannot age it out before admission.
redis.call('SET', record_key, owner .. string.char(31) .. job .. string.char(31) .. (now + waiter_ttl), 'EX', waiter_ttl + 1)
redis.call('EXPIRE', waiters, waiter_ttl + 1)

local circuit_deadline = tonumber(redis.call('GET', open_until) or '0')
if circuit_deadline > now then
  return {0, 'circuit', math.max(1, math.ceil(circuit_deadline - now))}
end

redis.call('ZREMRANGEBYSCORE', inflight, '-inf', now)
if redis.call('ZCARD', inflight) >= max_inflight then
  return {0, 'inflight', 1}
end

local rpm_count = tonumber(redis.call('GET', rpm) or '0')
if rpm_count >= rpm_limit then
  return {0, 'rpm', math.max(1, 60 - (math.floor(now) % 60))}
end

local queued = redis.call('ZRANGE', waiters, 0, -1)
local first_request = nil
local alternate_owner_request = nil
local alternate_job_request = nil
local previous_owner = redis.call('GET', last_owner)
local previous_job = redis.call('GET', last_job)
for _, queued_request in ipairs(queued) do
  local record = redis.call('GET', waiter_prefix .. queued_request)
  if record then
    local first = string.find(record, string.char(31), 1, true)
    local second = first and string.find(record, string.char(31), first + 1, true)
    local queued_owner = first and string.sub(record, 1, first - 1) or ''
    local queued_job = second and string.sub(record, first + 1, second - 1) or ''
    if not first_request then first_request = queued_request end
    if previous_owner and previous_owner ~= queued_owner and not alternate_owner_request then
      alternate_owner_request = queued_request
    end
    if previous_job and previous_job ~= queued_job and not alternate_job_request then
      alternate_job_request = queued_request
    end
  end
end
local head = alternate_owner_request or alternate_job_request or first_request
if head ~= request_id then
  return {0, 'fairness', 1}
end

redis.call('ZREM', waiters, request_id)
redis.call('DEL', record_key)
redis.call('SET', last_owner, owner, 'EX', waiter_ttl + 1)
redis.call('SET', last_job, job, 'EX', waiter_ttl + 1)
redis.call('ZADD', inflight, now + lease_seconds, permit_id)
redis.call('EXPIRE', inflight, lease_seconds + 1)
local count = redis.call('INCR', rpm)
if count == 1 then redis.call('EXPIRE', rpm, rpm_ttl) end
return {1, 'ok', 0}
"""

_FAIR_GENERATION_CANCEL_SCRIPT = """-- hackagen-provider-fair-generation-cancel
local removed = redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('DEL', KEYS[2] .. ARGV[1])
if redis.call('ZCARD', KEYS[1]) == 0 then redis.call('DEL', KEYS[1]) end
return removed
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
local window = tonumber(ARGV[2])
local threshold = tonumber(ARGV[3])
local open_seconds = tonumber(ARGV[4])
local redis_time = redis.call('TIME')
local now = tonumber(redis_time[1]) + tonumber(redis_time[2]) / 1000000
redis.call('ZREMRANGEBYSCORE', failures, '-inf', now - window)
redis.call('ZADD', failures, now, member)
redis.call('EXPIRE', failures, window + 1)
local count = redis.call('ZCARD', failures)
if count >= threshold then
  local proposed_deadline = now + open_seconds
  local deadline = math.max(
    tonumber(redis.call('GET', open_until) or '0'),
    proposed_deadline
  )
  local retry_after = math.max(1, math.ceil(deadline - now))
  redis.call('SET', open_until, deadline, 'EX', retry_after + 1)
  return {count, retry_after}
end
return {count, 0}
"""

_OPEN_SCRIPT = """-- hackagen-provider-open
local seconds = tonumber(ARGV[1])
local redis_time = redis.call('TIME')
local now = tonumber(redis_time[1]) + tonumber(redis_time[2]) / 1000000
local proposed_deadline = now + seconds
local deadline = math.max(
  tonumber(redis.call('GET', KEYS[1]) or '0'),
  proposed_deadline
)
local retry_after = math.max(1, math.ceil(deadline - now))
redis.call('SET', KEYS[1], deadline, 'EX', retry_after + 1)
return retry_after
"""

_RESET_SCRIPT = """-- hackagen-provider-reset
for index = 1, #KEYS - 1 do
  redis.call('DEL', KEYS[index])
end
return redis.call('INCR', KEYS[#KEYS])
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


class ProviderCapacityWait(ProviderCircuitOpen):
    """Short-lived local saturation or fairness wait before provider dispatch."""

    def __init__(
        self,
        retry_after: int,
        *,
        reason: str = "capacity",
        request_id: str | None = None,
    ) -> None:
        self.request_id = request_id
        super().__init__(
            retry_after,
            reason=reason,
            error_code="AI_CAPACITY_WAIT",
        )


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
        self._distributed = settings_obj.JOB_QUEUE_PROVIDER == "celery" or settings_obj.ENVIRONMENT == "production"
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
        self._local_preflight_generation = 0
        self._local_waiters: dict[str, dict[str, dict[str, Any]]] = {}
        self._local_owner_order: dict[str, list[str]] = {}
        self._local_owner_jobs: dict[str, dict[str, list[str]]] = {}
        self._local_job_requests: dict[str, dict[tuple[str, str], list[str]]] = {}

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

    def _capacity_wait_seconds(self, reason: str) -> int:
        if reason == "rpm":
            return 1
        lower = int(getattr(self._settings, "PROVIDER_CAPACITY_WAIT_MIN_SECONDS", 1))
        upper = int(getattr(self._settings, "PROVIDER_CAPACITY_WAIT_MAX_SECONDS", 3))
        if upper <= lower:
            return max(1, lower)
        return random.randint(lower, upper)

    def _fair_waiter_ttl_seconds(self) -> int:
        """Keep a generation waiter through the longest RPM backoff window."""
        configured = int(getattr(self._settings, "PROVIDER_CAPACITY_WAITER_TTL_SECONDS", 15))
        return max(_FAIR_WAITER_MIN_TTL_SECONDS, configured)

    def _redis_error(self, operation: str, exc: Exception) -> ProviderGuardUnavailable:
        logger.warning("Provider guard %s failed with %s", operation, type(exc).__name__)
        return ProviderGuardUnavailable()

    def acquire(
        self,
        kind: str,
        *,
        owner_key: str | None = None,
        job_key: str | None = None,
        request_id: str | None = None,
    ) -> ProviderPermit:
        kind = self._validate_kind(kind)
        permit = ProviderPermit(kind=kind, permit_id=uuid.uuid4().hex)
        if kind == "generation" and owner_key and job_key and request_id:
            return self._acquire_fair_generation(
                permit,
                owner_key=str(owner_key),
                job_key=str(job_key),
                request_id=str(request_id),
            )
        if self._redis is not None:
            try:
                result = self._redis.eval(
                    _ACQUIRE_SCRIPT,
                    3,
                    self._key(kind, "inflight"),
                    self._key(kind, "rpm:"),
                    self._key(kind, "open_until"),
                    permit.permit_id,
                    _PERMIT_TTL_SECONDS,
                    self._settings.OPENROUTER_MAX_IN_FLIGHT,
                    self._settings.OPENROUTER_RPM,
                )
            except Exception as exc:
                raise self._redis_error("acquire", exc) from exc
            if int(result[0]) != 1:
                reason = self._decode(result[1])
                if reason in {"inflight", "rpm"} and kind == "generation":
                    raise ProviderCapacityWait(
                        self._capacity_wait_seconds(reason),
                        reason=reason,
                    )
                raise ProviderCircuitOpen(int(result[2]), reason=reason)
            return permit

        now = float(self._clock())
        minute = int(now // 60)
        with self._lock:
            open_until = self._local_open_until.get(kind, 0.0)
            if open_until > now:
                raise ProviderCircuitOpen(math.ceil(open_until - now))
            leases = self._local_inflight.setdefault(kind, {})
            leases = {permit_id: expires_at for permit_id, expires_at in leases.items() if expires_at > now}
            self._local_inflight[kind] = leases
            if len(leases) >= self._settings.OPENROUTER_MAX_IN_FLIGHT:
                if kind == "generation":
                    raise ProviderCapacityWait(
                        self._capacity_wait_seconds("inflight"),
                        reason="inflight",
                    )
                raise ProviderCircuitOpen(math.ceil(min(leases.values()) - now), reason="inflight")
            rpm_key = (kind, minute)
            rpm_count = self._local_rpm.get(rpm_key, 0)
            if rpm_count >= self._settings.OPENROUTER_RPM:
                retry_after = max(1, 60 - int(now) % 60)
                if kind == "generation":
                    raise ProviderCapacityWait(retry_after, reason="rpm")
                raise ProviderCircuitOpen(retry_after, reason="rpm")
            self._local_inflight[kind][permit.permit_id] = now + _PERMIT_TTL_SECONDS
            self._local_rpm[rpm_key] = rpm_count + 1
            self._local_rpm = {key: count for key, count in self._local_rpm.items() if key[1] >= minute - 1}
        return permit

    def _register_local_waiter(
        self,
        kind: str,
        *,
        owner_key: str,
        job_key: str,
        request_id: str,
        now: float,
    ) -> None:
        waiters = self._local_waiters.setdefault(kind, {})
        expires_at = now + self._fair_waiter_ttl_seconds()
        existing = waiters.get(request_id)
        if existing is not None:
            existing["expires_at"] = expires_at
            return
        waiters[request_id] = {
            "owner": owner_key,
            "job": job_key,
            "expires_at": expires_at,
        }
        owner_order = self._local_owner_order.setdefault(kind, [])
        owner_jobs = self._local_owner_jobs.setdefault(kind, {})
        job_requests = self._local_job_requests.setdefault(kind, {})
        if owner_key not in owner_order:
            owner_order.append(owner_key)
        jobs = owner_jobs.setdefault(owner_key, [])
        if job_key not in jobs:
            jobs.append(job_key)
        job_requests.setdefault((owner_key, job_key), []).append(request_id)

    def _prune_local_waiters(self, kind: str, now: float) -> None:
        waiters = self._local_waiters.setdefault(kind, {})
        owner_order = self._local_owner_order.setdefault(kind, [])
        owner_jobs = self._local_owner_jobs.setdefault(kind, {})
        job_requests = self._local_job_requests.setdefault(kind, {})
        for request_id, item in list(waiters.items()):
            if item["expires_at"] <= now:
                waiters.pop(request_id, None)
        for owner in list(owner_order):
            jobs = owner_jobs.get(owner, [])
            live_jobs: list[str] = []
            for job in jobs:
                queue = [
                    request
                    for request in job_requests.get((owner, job), [])
                    if request in waiters
                ]
                if queue:
                    job_requests[(owner, job)] = queue
                    live_jobs.append(job)
                else:
                    job_requests.pop((owner, job), None)
            if live_jobs:
                owner_jobs[owner] = live_jobs
            else:
                owner_jobs.pop(owner, None)
                while owner in owner_order:
                    owner_order.remove(owner)

    def _local_head_waiter(self, kind: str) -> str | None:
        owner_order = self._local_owner_order.setdefault(kind, [])
        owner_jobs = self._local_owner_jobs.setdefault(kind, {})
        job_requests = self._local_job_requests.setdefault(kind, {})
        while owner_order:
            owner = owner_order[0]
            jobs = owner_jobs.get(owner, [])
            while jobs:
                job = jobs[0]
                requests = job_requests.get((owner, job), [])
                if requests:
                    return requests[0]
                jobs.pop(0)
            owner_jobs.pop(owner, None)
            owner_order.pop(0)
        return None

    def _consume_local_waiter(self, kind: str, request_id: str) -> None:
        waiters = self._local_waiters.setdefault(kind, {})
        item = waiters.pop(request_id, None)
        if item is None:
            return
        owner = item["owner"]
        job = item["job"]
        owner_order = self._local_owner_order.setdefault(kind, [])
        owner_jobs = self._local_owner_jobs.setdefault(kind, {})
        job_requests = self._local_job_requests.setdefault(kind, {})
        requests = job_requests.get((owner, job), [])
        if requests and requests[0] == request_id:
            requests.pop(0)
        elif request_id in requests:
            requests.remove(request_id)
        if requests:
            job_requests[(owner, job)] = requests
        else:
            job_requests.pop((owner, job), None)
            jobs = owner_jobs.get(owner, [])
            if job in jobs:
                jobs.remove(job)
            if jobs:
                jobs.append(job)
                owner_jobs[owner] = jobs
            else:
                owner_jobs.pop(owner, None)
        if owner in owner_order:
            owner_order.remove(owner)
            if owner in owner_jobs:
                owner_order.append(owner)

    def _acquire_fair_generation(
        self,
        permit: ProviderPermit,
        *,
        owner_key: str,
        job_key: str,
        request_id: str,
    ) -> ProviderPermit:
        if self._redis is not None:
            try:
                result = self._redis.eval(
                    _FAIR_GENERATION_ACQUIRE_SCRIPT,
                    8,
                    self._key("generation", "inflight"),
                    self._key("generation", "rpm:"),
                    self._key("generation", "open_until"),
                    self._key("generation", "waiters"),
                    self._key("generation", "waiter_sequence"),
                    self._key("generation", "last_owner"),
                    self._key("generation", "last_job"),
                    self._key("generation", "waiter:"),
                    permit.permit_id,
                    _PERMIT_TTL_SECONDS,
                    self._settings.OPENROUTER_MAX_IN_FLIGHT,
                    self._settings.OPENROUTER_RPM,
                    owner_key,
                    job_key,
                    request_id,
                    self._fair_waiter_ttl_seconds(),
                )
            except Exception as exc:
                raise self._redis_error("acquire", exc) from exc
            if int(result[0]) != 1:
                reason = self._decode(result[1])
                if reason in {"inflight", "rpm", "fairness"}:
                    retry_after = int(result[2]) if reason == "rpm" else self._capacity_wait_seconds(reason)
                    raise ProviderCapacityWait(
                        retry_after,
                        reason=reason,
                        request_id=request_id,
                    )
                raise ProviderCircuitOpen(int(result[2]), reason=reason)
            return permit

        now = float(self._clock())
        minute = int(now // 60)
        with self._lock:
            open_until = self._local_open_until.get("generation", 0.0)
            if open_until > now:
                raise ProviderCircuitOpen(math.ceil(open_until - now))
            self._register_local_waiter(
                "generation",
                owner_key=owner_key,
                job_key=job_key,
                request_id=request_id,
                now=now,
            )
            self._prune_local_waiters("generation", now)
            leases = self._local_inflight.setdefault("generation", {})
            leases = {
                permit_id: expires_at
                for permit_id, expires_at in leases.items()
                if expires_at > now
            }
            self._local_inflight["generation"] = leases
            if len(leases) >= self._settings.OPENROUTER_MAX_IN_FLIGHT:
                raise ProviderCapacityWait(
                    self._capacity_wait_seconds("inflight"),
                    reason="inflight",
                    request_id=request_id,
                )
            rpm_key = ("generation", minute)
            rpm_count = self._local_rpm.get(rpm_key, 0)
            if rpm_count >= self._settings.OPENROUTER_RPM:
                raise ProviderCapacityWait(
                    max(1, 60 - int(now) % 60),
                    reason="rpm",
                    request_id=request_id,
                )
            if self._local_head_waiter("generation") != request_id:
                raise ProviderCapacityWait(
                    self._capacity_wait_seconds("fairness"),
                    reason="fairness",
                    request_id=request_id,
                )
            self._consume_local_waiter("generation", request_id)
            self._local_inflight["generation"][permit.permit_id] = now + _PERMIT_TTL_SECONDS
            self._local_rpm[rpm_key] = rpm_count + 1
            self._local_rpm = {
                key: count for key, count in self._local_rpm.items() if key[1] >= minute - 1
            }
        return permit

    def cancel_waiter(self, request_id: str, *, kind: str = "generation") -> None:
        kind = self._validate_kind(kind)
        if self._redis is not None:
            if kind != "generation":
                return
            try:
                self._redis.eval(
                    _FAIR_GENERATION_CANCEL_SCRIPT,
                    2,
                    self._key(kind, "waiters"),
                    self._key(kind, "waiter:"),
                    request_id,
                )
            except Exception as exc:
                logger.warning("Provider guard waiter cancellation failed with %s", type(exc).__name__)
            return
        with self._lock:
            self._consume_local_waiter(kind, request_id)

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
                logger.warning("Provider guard release failed with %s", type(exc).__name__)
            return
        with self._lock:
            self._local_inflight.get(kind, {}).pop(permit.permit_id, None)

    def _open(self, kind: str, seconds: int) -> int:
        seconds = max(1, min(300, int(seconds)))
        if self._redis is not None:
            try:
                retry_after = self._redis.eval(
                    _OPEN_SCRIPT,
                    1,
                    self._key(kind, "open_until"),
                    seconds,
                )
            except Exception as exc:
                raise self._redis_error("open", exc) from exc
            return int(retry_after)
        now = float(self._clock())
        with self._lock:
            deadline = max(self._local_open_until.get(kind, 0.0), now + seconds)
            self._local_open_until[kind] = deadline
            return max(1, math.ceil(deadline - now))

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
            return self._open(kind, _PERMANENT_CIRCUIT_SECONDS)
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
            return self._open(kind, seconds)
        if code not in {ProviderErrorCode.UNAVAILABLE, ProviderErrorCode.TIMEOUT}:
            return None

        if self._redis is not None:
            try:
                result = self._redis.eval(
                    _FAILURE_SCRIPT,
                    2,
                    self._key(kind, "failures"),
                    self._key(kind, "open_until"),
                    uuid.uuid4().hex,
                    self._settings.OPENROUTER_CIRCUIT_WINDOW_SECONDS,
                    self._settings.OPENROUTER_CIRCUIT_FAILURES,
                    self._settings.OPENROUTER_CIRCUIT_OPEN_SECONDS,
                )
            except Exception as exc:
                raise self._redis_error("record failure", exc) from exc
            if int(result[0]) >= self._settings.OPENROUTER_CIRCUIT_FAILURES:
                return int(result[1])
            return None
        now = float(self._clock())
        with self._lock:
            cutoff = now - self._settings.OPENROUTER_CIRCUIT_WINDOW_SECONDS
            failures = [occurred_at for occurred_at in self._local_failures.get(kind, []) if occurred_at > cutoff]
            failures.append(now)
            self._local_failures[kind] = failures
            if len(failures) >= self._settings.OPENROUTER_CIRCUIT_FAILURES:
                deadline = max(
                    self._local_open_until.get(kind, 0.0),
                    now + self._settings.OPENROUTER_CIRCUIT_OPEN_SECONDS,
                )
                self._local_open_until[kind] = deadline
                return max(1, math.ceil(deadline - now))
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
        keys = [self._key(kind, suffix) for kind in _KINDS for suffix in ("failures", "open_until")]
        if self._redis is not None:
            try:
                self._redis.eval(
                    _RESET_SCRIPT,
                    len(keys) + 1,
                    *keys,
                    self._key("all", "preflight_generation"),
                )
            except Exception as exc:
                raise self._redis_error("preflight reset", exc) from exc
            return
        with self._lock:
            self._local_failures.clear()
            self._local_open_until.clear()
            self._local_preflight_generation += 1

    def preflight_generation(self) -> int:
        """Return the shared revision used to invalidate process-local health caches."""
        if self._redis is not None:
            try:
                value = self._redis.get(self._key("all", "preflight_generation"))
            except Exception as exc:
                raise self._redis_error("preflight generation", exc) from exc
            return int(value or 0)
        with self._lock:
            return self._local_preflight_generation


_guard: ProviderGuard | None = None
_guard_lock = threading.Lock()


def get_provider_guard() -> ProviderGuard:
    global _guard
    if _guard is None:
        with _guard_lock:
            if _guard is None:
                _guard = ProviderGuard()
    return _guard
