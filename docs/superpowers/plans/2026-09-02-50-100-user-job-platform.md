# 50–100 User Job Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep HackaGen responsive and crash-safe for 50–100 simultaneously active users by accepting heavy AI work quickly, applying bounded backpressure, and executing ingestion, generation, and video jobs in isolated durable workers.

**Architecture:** Keep FastAPI responsible for auth, validation, ownership, and enqueueing; Redis is the Celery broker and shared provider guard, PostgreSQL stores application/job state, and Chroma runs as a dedicated HTTP service. Three queues isolate ingestion, ordinary Study Pack generation, and CPU-heavy video rendering so web requests stay responsive and long videos cannot starve PDF indexing or Book/Slide/Quiz work.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Psycopg 3, Celery 5.5+, Redis 7, Chroma HTTP server, Docker Compose, Next.js 16, React 19, pytest, Vitest, Playwright, Grafana k6.

**Spec:** `docs/PRD.md` sections 3–5, `docs/api_contract.md` sections 1–4, and `docs/architecture_design.md` sections 2–6; requires completion of `docs/superpowers/plans/2026-09-02-openrouter-recovery-and-document-retry.md`.

## Global Constraints

- Capacity target means 50–100 active web users, not 100 simultaneous video renders; excess heavy work must queue with an honest position/status instead of spawning unbounded threads.
- Initial production topology is one Linux Docker host with shared upload/output/cache volumes; multi-host object storage is explicitly a later deployment phase.
- Local/dev defaults remain SQLite, embedded Chroma, and inline jobs so contributors can run without Redis/PostgreSQL.
- Production requires PostgreSQL, Redis/Celery, and Chroma HTTP mode; startup must fail if production is configured with SQLite, embedded Chroma, or inline jobs.
- Keep exactly four generation endpoints and preserve all current auth, ownership, grounding, artifact-version, polling, and authenticated-download invariants.
- Celery messages contain IDs and JSON options only; never serialize ORM objects, API keys, document text, JWTs, or uploaded bytes into Redis.
- Every worker task is idempotent because late acknowledgement can redeliver a job after worker loss.
- Long tasks use `worker_prefetch_multiplier=1`; Celery documents this setting for fair distribution of long-running tasks.
- Default worker concurrency on an 8-vCPU/16-GB host: ingestion `2`, generation `4`, video `1`; all values are environment-configurable.
- Default admission limits: at most `4` queued/running jobs per user and `200` globally; return `429` with `Retry-After: 30` when the user limit is reached and `503` with `Retry-After: 60` when the global limit is reached.
- API SLO under the load-test adapter: non-upload API p95 under `500 ms`, enqueue response p95 under `2 s`, HTTP failure rate below `1%`, no dropped k6 iterations, no duplicate completed jobs, and no API process crash.
- Provider tests at 100 users use a deterministic load-test adapter; the paid OpenRouter smoke test is capped at 5 simultaneous users to control cost and respect external rate limits.
- Never enable the deterministic AI adapter when `ENVIRONMENT=production`.

## File Map

- Create `src/backend/app/jobs/celery_app.py`: Celery configuration and queue routing.
- Create `src/backend/app/jobs/tasks.py`: ID-only ingestion and artifact task entrypoints.
- Create `src/backend/app/jobs/dispatcher.py`: inline/Celery dispatcher boundary.
- Create `src/backend/app/jobs/admission.py`: per-user/global queue admission.
- Create `src/backend/app/services/provider_guard.py`: Redis rate gate and circuit breaker.
- Create `src/backend/app/services/vector_client.py`: embedded/HTTP Chroma client factory.
- Create `src/backend/app/routers/jobs.py`: ownership-protected job status/cancel endpoints and admin queue summary.
- Create `src/backend/alembic/versions/c9d0e1f2a3b4_add_distributed_job_fields.py`: payload, active-key, queue, lease, attempt, and cancellation fields.
- Create `src/backend/scripts/migrate_sqlite_to_postgres.py`: id-preserving application-state migration.
- Create `src/backend/tests/test_job_dispatcher.py`: inline/Celery dispatch contract.
- Create `src/backend/tests/test_job_idempotency.py`: claim, lease, redelivery, and duplicate suppression.
- Create `src/backend/tests/test_job_admission.py`: user/global backpressure.
- Create `src/backend/tests/test_provider_guard.py`: rate-limit/circuit behavior.
- Create `src/backend/tests/test_vector_client.py`: embedded and HTTP Chroma modes.
- Create `docker-compose.production.yml`: PostgreSQL, Redis, Chroma, API, frontend, and three worker services.
- Create `docker-compose.loadtest.yml`: production topology plus deterministic OpenRouter adapter.
- Create `tests/load/mock_openrouter.py`: deterministic embeddings/chat responses and fault injection.
- Create `tests/load/k6/read-path.js`: 100-user login/list/status/poll test.
- Create `tests/load/k6/mixed-jobs.js`: upload and four-artifact enqueue load.
- Create `tests/load/k6/provider-outage.js`: 403/429/5xx circuit-breaker recovery test.
- Create `tests/load/fixtures/load-document.txt`: deterministic non-sensitive document fixture.
- Create `src/backend/scripts/seed_load_users.py`: guarded creation of verified load-test accounts.
- Create `src/backend/tests/test_production_compose.py`: production Compose topology/config validation.
- Create `docs/load-test-results.md`: repeatable capacity evidence template and measured results.
- Modify `src/backend/pyproject.toml` and `src/backend/uv.lock`: Celery/Redis/Psycopg dependencies.
- Modify `src/backend/app/core/config.py`: environment, queue, PostgreSQL, Chroma HTTP, admission, worker, and provider-guard settings.
- Modify `src/backend/app/models/processing_job.py`: distributed execution fields.
- Modify `src/backend/app/services/job_service.py`: atomic claim, lease renewal, completion, retry, and cancellation.
- Modify `src/backend/app/services/database.py`: configurable PostgreSQL pool sizes and worker-safe engine lifecycle.
- Modify `src/backend/app/services/vector_store.py`: use client factory and provider guard.
- Modify `src/backend/app/services/llm.py`: use provider guard around OpenRouter calls.
- Modify `src/backend/app/services/provider_health.py`: use the validated OpenRouter base URL in load tests.
- Modify `src/backend/app/services/document_processor.py`: lease/progress heartbeats and ID-only execution.
- Modify `src/backend/app/services/generator.py`: lease/progress heartbeats and idempotent version completion.
- Modify `src/backend/app/routers/upload.py`: enqueue preprocessing instead of running it in the API process.
- Modify `src/backend/app/routers/generation.py`: enqueue all four artifact tasks without changing route names.
- Modify `src/backend/main.py`: production config validation, job router, and expanded local dependency health.
- Modify `src/frontend/src/lib/types.ts`, `src/frontend/src/lib/api.ts`, course workspace components, and tests: durable queued/running/retry status.
- Modify `.env.example`, `README.md`, `docs/architecture_design.md`, and `docs/api_contract.md`: topology, sizing, rollout, rollback, and operations.

---

### Task 1: Distributed Job Schema and Atomic Leasing

**Files:**
- Create: `src/backend/alembic/versions/c9d0e1f2a3b4_add_distributed_job_fields.py`
- Modify: `src/backend/app/models/processing_job.py`
- Modify: `src/backend/app/services/job_service.py`
- Modify: `src/backend/pyproject.toml`
- Modify: `src/backend/uv.lock`
- Create: `src/backend/tests/test_job_idempotency.py`

**Interfaces:**
- Consumes: `ProcessingJob` and lifecycle functions from Plan A.
- Produces: `claim_job(job_id, worker_id, lease_seconds) -> bool`, `renew_job_lease(job_id, worker_id, lease_seconds)`, `schedule_job_retry()`, `cancel_job()`, and unique nullable `active_key` enforcement.

- [ ] **Step 1: Write failing claim/redelivery tests**

```python
def test_only_one_worker_claims_a_queued_job(db_session, queued_job):
    assert claim_job(db_session, queued_job.id, "worker-a", 300) is True
    assert claim_job(db_session, queued_job.id, "worker-b", 300) is False


def test_expired_lease_allows_redelivery(db_session, running_job):
    running_job.worker_id = "dead-worker"
    running_job.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert claim_job(db_session, running_job.id, "worker-b", 300) is True
    db_session.refresh(running_job)
    assert running_job.attempts == 2


def test_succeeded_job_ignores_redelivery(db_session, succeeded_job):
    assert claim_job(db_session, succeeded_job.id, "worker-b", 300) is False
```

Define the `db_session`, `queued_job`, `running_job`, and `succeeded_job` fixtures in the same test file using `SessionLocal` and `create_job()` so the file runs independently.

- [ ] **Step 2: Run the tests and verify missing distributed fields/functions**

Run: `uv run --project . pytest tests/test_job_idempotency.py -q`

Expected: FAIL because lease and claim fields do not exist.

- [ ] **Step 3: Extend the job model and migration**

Add:

```python
payload_json = Column(JSON, nullable=False, default=dict)
active_key = Column(String(180), nullable=True, unique=True, index=True)
queue_name = Column(String(32), nullable=False)
attempts = Column(Integer, nullable=False, default=0)
max_attempts = Column(Integer, nullable=False, default=3)
worker_id = Column(String(120), nullable=True)
lease_expires_at = Column(DateTime, nullable=True, index=True)
next_attempt_at = Column(DateTime, nullable=True, index=True)
cancel_requested = Column(Boolean, nullable=False, default=False)
```

Use revision `c9d0e1f2a3b4` and `down_revision = "b8c9d0e1f2a3"`. Backfill `queue_name = "ingestion"` and `{}` payload before making those two columns non-null. Backfill `active_key = "legacy:" + id` only for `queued`, `retry_scheduled`, or `running` rows; leave it `NULL` for terminal rows. A new job uses `preprocess:{course_id}` or `{artifact}:{course_id}:{version_id}`. If the unique insert races, roll back and return the existing active job instead of creating a duplicate.

- [ ] **Step 4: Implement atomic claim semantics**

Use a single SQL `UPDATE processing_jobs SET ... WHERE id=:id AND (...)` and require `rowcount == 1`. Claim only `queued`, `retry_scheduled`, or `running` with an expired lease; never claim `succeeded`, `failed`, or `cancelled`. Increment `attempts`, set `worker_id`, `lease_expires_at`, and status `running` in the same transaction.

```python
claimable = or_(
    ProcessingJob.status.in_(["queued", "retry_scheduled"]),
    and_(
        ProcessingJob.status == "running",
        ProcessingJob.lease_expires_at < now,
    ),
)
```

- [ ] **Step 5: Add lease renewal, retry, completion, and cancellation**

Every update must include `worker_id` and current non-terminal status in its `WHERE` clause. `schedule_job_retry()` clears the lease and worker, stores `next_attempt_at`, and refuses when `attempts >= max_attempts`. Success, final failure, and cancellation must set `active_key=NULL`, which allows a later explicit retry to create a fresh job. `cancel_job()` sets `cancel_requested`; workers check it between pipeline stages and finish as `cancelled`.

- [ ] **Step 6: Run migration and idempotency tests on SQLite and PostgreSQL**

Install the PostgreSQL driver, then run the same test module once with the default SQLite test fixture and once with `TEST_DATABASE_URL=postgresql+psycopg://hackagen:hackagen@127.0.0.1:5432/hackagen_test`:

```powershell
uv add "psycopg[binary]>=3.2,<4"
uv run --project . pytest tests/test_job_idempotency.py -q
docker run --rm -d --name hackagen-job-test-postgres -e POSTGRES_USER=hackagen -e POSTGRES_PASSWORD=hackagen -e POSTGRES_DB=hackagen_test -p 55431:5432 postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://hackagen:hackagen@127.0.0.1:55431/hackagen_test'
uv run --project . pytest tests/test_job_idempotency.py -q
Remove-Item Env:TEST_DATABASE_URL
docker stop hackagen-job-test-postgres
```

Expected: both runs pass and two concurrent claim threads produce exactly one winner.

- [ ] **Step 7: Commit distributed job state**

```powershell
git add src/backend/app/models/processing_job.py src/backend/app/services/job_service.py src/backend/alembic/versions/c9d0e1f2a3b4_add_distributed_job_fields.py src/backend/pyproject.toml src/backend/uv.lock src/backend/tests/test_job_idempotency.py
git commit -m "feat: add idempotent distributed job leasing"
```

---

### Task 2: Queue-Neutral Dispatcher and Backpressure

**Files:**
- Create: `src/backend/app/jobs/__init__.py`
- Create: `src/backend/app/jobs/dispatcher.py`
- Create: `src/backend/app/jobs/admission.py`
- Create: `src/backend/tests/test_job_dispatcher.py`
- Create: `src/backend/tests/test_job_admission.py`
- Modify: `src/backend/app/core/config.py`

**Interfaces:**
- Produces: `JobDispatcher.enqueue(job_id: str, queue_name: str) -> str`, `InlineJobDispatcher`, `CeleryJobDispatcher`, `get_job_dispatcher(background_tasks=None)`, and `enforce_job_admission(db, user_id)`.

- [ ] **Step 1: Write failing dispatcher contract tests**

```python
def test_inline_dispatcher_schedules_id_only(background_tasks):
    dispatcher = InlineJobDispatcher(background_tasks)
    external_id = dispatcher.enqueue("job-1", "ingestion")
    assert external_id == "inline:job-1"
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].args == ("job-1",)


def test_celery_dispatcher_routes_video_separately(fake_celery):
    dispatcher = CeleryJobDispatcher(fake_celery)
    dispatcher.enqueue("job-2", "video")
    fake_celery.send_task.assert_called_once_with(
        "hackagen.execute_video_job",
        args=["job-2"],
        queue="video",
        task_id="job-2",
    )
```

- [ ] **Step 2: Write failing admission tests**

Create four non-terminal jobs for one user and assert `UserJobLimitExceeded(retry_after=30)`. Create 200 non-terminal jobs across users and assert `GlobalJobLimitExceeded(retry_after=60)`. Terminal jobs must not count.

- [ ] **Step 3: Run tests and verify dispatcher/admission imports fail**

Run: `uv run --project . pytest tests/test_job_dispatcher.py tests/test_job_admission.py -q`

Expected: FAIL during import.

- [ ] **Step 4: Add validated queue settings**

```python
ENVIRONMENT: str = Field(default="local", pattern="^(local|test|loadtest|production)$")
JOB_QUEUE_PROVIDER: str = Field(default="inline", pattern="^(inline|celery)$")
REDIS_URL: str = Field(default="redis://localhost:6379/0")
MAX_PENDING_JOBS_PER_USER: int = Field(default=4, ge=1, le=20)
MAX_PENDING_JOBS_GLOBAL: int = Field(default=200, ge=10, le=2000)
JOB_LEASE_SECONDS: int = Field(default=3600, ge=60, le=7200)
```

Add a model validator that rejects `ENVIRONMENT=production` with `JOB_QUEUE_PROVIDER != "celery"`.

- [ ] **Step 5: Implement inline and Celery dispatchers**

The inline dispatcher must schedule one shared `execute_job(job_id)` function through FastAPI `BackgroundTasks`. The Celery dispatcher maps `ingestion`, `generation`, and `video` to `hackagen.execute_ingestion_job`, `hackagen.execute_generation_job`, and `hackagen.execute_video_job`, calls `send_task()` with task id equal to job id, and stores the returned external id. Neither implementation may serialize payloads beyond the job id.

- [ ] **Step 6: Implement SQL admission checks and HTTP mapping**

Count `queued`, `retry_scheduled`, and `running` jobs. Map user overflow to HTTP `429` with `Retry-After: 30`; map global overflow to `503` with `Retry-After: 60`. Perform admission and job insertion in the same DB transaction. In PostgreSQL, acquire `pg_advisory_xact_lock(hashtext('hackagen:jobs:global'))` and then `pg_advisory_xact_lock(hashtext('hackagen:jobs:user:' || :user_id))` before counting and inserting; all API processes must acquire them in that order. Inline SQLite mode wraps count-plus-insert in one process-wide `threading.Lock`. Add concurrent admission tests proving five same-user requests accept exactly four and a 201st global request is rejected.

- [ ] **Step 7: Run dispatcher/admission tests**

Run: `uv run --project . pytest tests/test_job_dispatcher.py tests/test_job_admission.py -q`

Expected: PASS in inline mode without Redis and in fake-Celery mode without a live broker.

- [ ] **Step 8: Commit queue boundary and admission control**

```powershell
git add src/backend/app/jobs src/backend/app/core/config.py src/backend/tests/test_job_dispatcher.py src/backend/tests/test_job_admission.py
git commit -m "feat: add bounded job dispatch and admission control"
```

---

### Task 3: Celery Workers and Queue Routing

**Files:**
- Create: `src/backend/app/jobs/celery_app.py`
- Create: `src/backend/app/jobs/tasks.py`
- Modify: `src/backend/pyproject.toml`
- Modify: `src/backend/uv.lock`
- Modify: `src/backend/app/services/document_processor.py`
- Modify: `src/backend/app/services/generator.py`
- Create: `src/backend/tests/test_job_tasks.py`

**Interfaces:**
- Consumes: job leasing from Task 1 and dispatcher job ids from Task 2.
- Produces: three Celery task entrypoints with queue-specific time limits and ID-only handlers for `preprocess`, `book`, `slides`, `quiz`, and `video`.

- [ ] **Step 1: Add dependencies with bounded major versions**

Run:

```powershell
Set-Location src/backend
uv add "celery[redis]>=5.5,<6"
```

Expected: `pyproject.toml` and `uv.lock` add Celery and its Redis transport dependencies while retaining Psycopg 3 from Task 1.

- [ ] **Step 2: Write failing task routing/idempotency tests**

Assert `preprocess -> ingestion`, `book/slides/quiz -> generation`, and `video -> video`. Execute the same succeeded job twice and assert the generator/processor mock runs zero times on redelivery. Execute a queued job twice concurrently and assert the mock runs exactly once.

- [ ] **Step 3: Configure Celery for long jobs**

```python
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_routes={
        "hackagen.execute_ingestion_job": {"queue": "ingestion"},
        "hackagen.execute_generation_job": {"queue": "generation"},
        "hackagen.execute_video_job": {"queue": "video"},
    },
)
```

Use task decorators to enforce soft/hard limits: preprocess `900/1200` seconds, ordinary generation `1200/1500`, and video `2700/3000`.

- [ ] **Step 4: Implement the ID-only task entrypoint**

```python
def _run(self, job_id: str) -> None:
    execute_job(job_id, worker_id=self.request.hostname or "celery-worker")


@celery_app.task(bind=True, name="hackagen.execute_ingestion_job", soft_time_limit=900, time_limit=1200)
def execute_ingestion_job(self, job_id: str) -> None:
    _run(self, job_id)


@celery_app.task(bind=True, name="hackagen.execute_generation_job", soft_time_limit=1200, time_limit=1500)
def execute_generation_job(self, job_id: str) -> None:
    _run(self, job_id)


@celery_app.task(bind=True, name="hackagen.execute_video_job", soft_time_limit=2700, time_limit=3000)
def execute_video_job(self, job_id: str) -> None:
    _run(self, job_id)
```

`execute_job()` opens its own `SessionLocal`, atomically claims the job, loads `payload_json`, invokes the exact processor/generator method, renews its lease at each existing progress update, and writes terminal status. Unknown job types fail with `JOB_TYPE_UNSUPPORTED`; they are never retried.

- [ ] **Step 5: Make processor and generator entrypoints idempotent**

Preprocess uses stable chunk ids and Chroma `upsert`; before work, delete any partial chunks for the same course only when the previous job is non-terminal. Artifact jobs key on `course_id + artifact + version_id`; if that version is already `ready`, return success without regenerating or rewriting files. Use the existing version reservation as the single artifact identity.

- [ ] **Step 6: Run task and generation regression tests**

Run:

```powershell
uv run --project . pytest tests/test_job_tasks.py tests/test_generation_service.py tests/test_vector_store_and_processor.py -q
```

Expected: PASS; redelivery does not duplicate chunks, versions, or output files.

- [ ] **Step 7: Commit Celery workers**

```powershell
git add src/backend/pyproject.toml src/backend/uv.lock src/backend/app/jobs/celery_app.py src/backend/app/jobs/tasks.py src/backend/app/services/document_processor.py src/backend/app/services/generator.py src/backend/tests/test_job_tasks.py
git commit -m "feat: execute study pack jobs in durable Celery workers"
```

---

### Task 4: Enqueue Upload and All Four Generation Paths

**Files:**
- Modify: `src/backend/app/routers/upload.py:23-127`
- Modify: `src/backend/app/routers/generation.py:152-242`
- Create: `src/backend/app/routers/jobs.py`
- Modify: `src/backend/main.py`
- Modify: `src/backend/app/schemas/generation.py`
- Create: `src/backend/tests/test_queued_routes.py`

**Interfaces:**
- Consumes: dispatcher/admission and durable jobs.
- Produces: immediate `201/202` responses with `job_id`; `GET /api/jobs/{job_id}`; `DELETE /api/jobs/{job_id}` for cooperative cancellation.

- [ ] **Step 1: Write failing route tests**

For upload assert `201`; for each of the four existing public generation endpoints assert `200`. In all five cases, assert response time is independent of a blocked fake processor/generator, `job_id` is present, and exactly one job is queued with the correct type/payload. Add tests proving another user receives `404` for job read/cancel and a cancelled video job does not produce an MP4.

- [ ] **Step 2: Run tests and verify routes still execute `BackgroundTasks` directly**

Run: `uv run --project . pytest tests/test_queued_routes.py -q`

Expected: FAIL because routes do not return job ids and call generator methods directly.

- [ ] **Step 3: Replace direct background calls with job creation and dispatch**

Upload payload is `{ "course_id": course_id }`; workers rediscover saved paths. Artifact payloads contain only validated existing options plus `course_id`, `artifact`, and `version_id`. Call `enforce_job_admission()` before reserving a new artifact version so rejected requests do not leave phantom `processing` versions.

- [ ] **Step 4: Add job read/cancel and admin summary endpoints**

`GET /api/jobs/{job_id}` returns the Plan A `JobResponse`. `DELETE /api/jobs/{job_id}` sets `cancel_requested` and returns `202`; terminal jobs return `409`. `GET /api/admin/jobs/summary` returns counts by queue/status and oldest queued age, never payload/document text.

- [ ] **Step 5: Keep the four generation routes and response compatibility**

Add optional `job_id` to `GenerateResponse`; do not add new generator routes. Existing artifact polling continues to use version status, while job polling supplies queue position/message.

- [ ] **Step 6: Run upload, generation, auth, and queued-route tests**

Run:

```powershell
uv run --project . pytest tests/test_queued_routes.py tests/test_course_and_upload.py tests/test_generation_service.py tests/test_auth_and_core.py -q
```

Expected: PASS in inline mode; ownership and artifact-version limits remain unchanged.

- [ ] **Step 7: Commit queued API routes**

```powershell
git add src/backend/app/routers/upload.py src/backend/app/routers/generation.py src/backend/app/routers/jobs.py src/backend/app/schemas/generation.py src/backend/main.py src/backend/tests/test_queued_routes.py
git commit -m "feat: enqueue all heavy study pack operations"
```

---

### Task 5: Shared OpenRouter Rate Gate and Circuit Breaker

**Files:**
- Create: `src/backend/app/services/provider_guard.py`
- Create: `src/backend/tests/test_provider_guard.py`
- Modify: `src/backend/app/services/vector_store.py`
- Modify: `src/backend/app/services/llm.py`
- Modify: `src/backend/app/services/provider_health.py`
- Modify: `src/backend/app/core/config.py`

**Interfaces:**
- Produces: `ProviderGuard.acquire(kind) -> ProviderPermit`, `ProviderGuard.release(permit)`, `record_success(kind)`, `record_failure(kind, failure)`, `reset_after_successful_preflight()`, and `ProviderCircuitOpen(retry_after)` backed by Redis in Celery mode.

- [ ] **Step 1: Write failing guard tests with a fake Redis clock**

Cover: six concurrent permits succeed and the seventh is delayed; key-limit `403` opens the circuit immediately; five `5xx` errors within 60 seconds open for 30 seconds; a `429` uses `Retry-After` capped at 300 seconds; a success clears transient failure count; no Redis connection in production fails closed with a retryable infrastructure error.

- [ ] **Step 2: Run tests and verify the provider guard is missing**

Run: `uv run --project . pytest tests/test_provider_guard.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Add exact provider guard settings**

```python
OPENROUTER_MAX_IN_FLIGHT: int = Field(default=6, ge=1, le=32)
OPENROUTER_RPM: int = Field(default=60, ge=1, le=1000)
OPENROUTER_CIRCUIT_FAILURES: int = Field(default=5, ge=2, le=20)
OPENROUTER_CIRCUIT_WINDOW_SECONDS: int = Field(default=60, ge=10, le=300)
OPENROUTER_CIRCUIT_OPEN_SECONDS: int = Field(default=30, ge=5, le=300)
OPENROUTER_BASE_URL: str = Field(default="https://openrouter.ai/api/v1")
```

Extend the environment validator so a non-official `OPENROUTER_BASE_URL` is accepted only for `ENVIRONMENT=loadtest`; production, local, and test reject it. Replace hard-coded OpenRouter URLs in `llm.py`, `vector_store.py`, and `provider_health.py` with this setting.

- [ ] **Step 4: Implement atomic Redis guard keys**

Use namespaced keys `hackagen:provider:{kind}:inflight`, `:rpm:{minute}`, `:failures`, and `:open_until`. Acquire/release in-flight permits with a Lua script and TTL so worker death cannot leak a permit forever. Check `open_until` before rate counters. Do not store prompts, model output, document text, user ids, or keys in Redis guard records.

- [ ] **Step 5: Wrap embeddings, content generation, and OCR**

Call `permit = guard.acquire(kind)` immediately before each OpenRouter SDK call; always call `guard.release(permit)` in `finally`; pass Task 1 classified failures to `record_failure()`; call `record_success()` only on a valid provider response. `ProviderPermit` contains only `kind` and an opaque random permit id so release cannot decrement another request's lease. When the admin-only forced provider preflight returns a usable key and both configured models exist, call `reset_after_successful_preflight()` to clear a stale permanent-quota circuit. When open/rate-limited, worker jobs transition to `retry_scheduled` with a Celery countdown rather than sleeping inside a worker process.

- [ ] **Step 6: Run provider and generation tests**

Run:

```powershell
uv run --project . pytest tests/test_provider_guard.py tests/test_provider_errors.py tests/test_generation_service.py tests/test_vector_store_and_processor.py -q
```

Expected: PASS; permanent quota failure creates no retry storm and 429/5xx recovery is bounded.

- [ ] **Step 7: Commit provider protection**

```powershell
git add src/backend/app/services/provider_guard.py src/backend/app/services/vector_store.py src/backend/app/services/llm.py src/backend/app/services/provider_health.py src/backend/app/core/config.py src/backend/tests/test_provider_guard.py
git commit -m "feat: protect OpenRouter with distributed rate and circuit guards"
```

---

### Task 6: PostgreSQL Production Persistence

**Files:**
- Modify: `src/backend/app/services/database.py`
- Modify: `src/backend/app/core/config.py`
- Create: `src/backend/scripts/migrate_sqlite_to_postgres.py`
- Create: `src/backend/tests/test_postgres_database.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: PostgreSQL pool settings and an id-preserving, rerunnable SQLite-to-PostgreSQL migration command.

- [ ] **Step 1: Write failing production-validation and pool tests**

Assert production rejects a SQLite URL. With PostgreSQL config, assert pool size `10`, max overflow `20`, pool timeout `30`, recycle `1800`, and `pool_pre_ping=True`. Assert a worker child process disposes inherited connections before opening its first session.

- [ ] **Step 2: Add pool settings and worker engine hook**

```python
DB_POOL_SIZE: int = Field(default=10, ge=2, le=50)
DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
DB_POOL_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=120)
DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=300, le=7200)
```

Pass all four to `create_engine()` for non-SQLite URLs. Register Celery `worker_process_init` to call `engine.dispose(close=False)` so forked workers do not reuse parent connections.

- [ ] **Step 3: Implement the guarded migration script**

Require `--source-sqlite`, `--target-postgres`, and `--confirm MIGRATE`. Run `alembic upgrade head` against the target first, then copy users, courses, email OTP rows, and processing jobs in FK order using preserved primary keys. Use PostgreSQL `ON CONFLICT DO NOTHING`; print only table counts, never password hashes, emails, OTP codes, or job payloads.

- [ ] **Step 4: Test clean schema, migration replay, and rollback backup**

Create a disposable PostgreSQL database, seed SQLite with two users/courses/jobs, run the script twice, and assert target counts remain `2` rather than duplicate to `4`. Verify ownership queries and login against PostgreSQL. Restore the pre-migration SQLite file after the test.

Run:

```powershell
docker run --rm -d --name hackagen-plan-postgres -e POSTGRES_USER=hackagen -e POSTGRES_PASSWORD=hackagen -e POSTGRES_DB=hackagen_test -p 55432:5432 postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://hackagen:hackagen@127.0.0.1:55432/hackagen_test'
uv run --project . pytest tests/test_postgres_database.py -q
Remove-Item Env:TEST_DATABASE_URL
docker stop hackagen-plan-postgres
```

Expected: both migration runs exit `0`; row counts remain stable, ownership/login tests pass, and the original SQLite file hash matches its pre-test backup after restoration.

- [ ] **Step 5: Commit PostgreSQL support**

```powershell
git add src/backend/app/services/database.py src/backend/app/core/config.py src/backend/scripts/migrate_sqlite_to_postgres.py src/backend/tests/test_postgres_database.py .env.example
git commit -m "feat: add production PostgreSQL persistence"
```

---

### Task 7: Chroma Client/Server Mode

**Files:**
- Create: `src/backend/app/services/vector_client.py`
- Create: `src/backend/tests/test_vector_client.py`
- Modify: `src/backend/app/services/vector_store.py`
- Modify: `src/backend/app/core/config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `build_chroma_client()` returning `PersistentClient` for local and `HttpClient` for production with unchanged `VectorStore` behavior.

- [ ] **Step 1: Write failing mode-selection tests**

Assert `CHROMA_MODE=embedded` calls `chromadb.PersistentClient(path=...)`; `CHROMA_MODE=http` calls `chromadb.HttpClient(host, port, ssl)`; production rejects embedded mode; client heartbeat failure makes readiness false.

- [ ] **Step 2: Add exact Chroma settings**

```python
CHROMA_MODE: str = Field(default="embedded", pattern="^(embedded|http)$")
CHROMA_HOST: str = Field(default="localhost")
CHROMA_PORT: int = Field(default=8000, ge=1, le=65535)
CHROMA_SSL: bool = Field(default=False)
CHROMA_TIMEOUT_SECONDS: float = Field(default=10.0, ge=1.0, le=60.0)
```

- [ ] **Step 3: Implement the client factory and health behavior**

Use the factory in `VectorStore.__init__`; keep collection names, embedding function, metadata filters, upsert, retrieval, and deletion unchanged. For HTTP mode, call `heartbeat()` during startup/readiness and return false on connection failure without falling back to embedded storage.

- [ ] **Step 4: Test embedded and live HTTP modes**

Run unit tests with mocked constructors, then launch a disposable `chromadb/chroma:1.5.9` container and run the existing vector-store/processor integration tests against `CHROMA_MODE=http`.

Run:

```powershell
uv run --project . pytest tests/test_vector_client.py -q
docker run --rm -d --name hackagen-plan-chroma -p 58000:8000 chromadb/chroma:1.5.9
$env:CHROMA_MODE='http'
$env:CHROMA_HOST='127.0.0.1'
$env:CHROMA_PORT='58000'
uv run --project . pytest tests/test_vector_client.py tests/test_vector_store_and_processor.py -q
Remove-Item Env:CHROMA_MODE,Env:CHROMA_HOST,Env:CHROMA_PORT
docker stop hackagen-plan-chroma
```

Expected: both modes pass the same upsert/retrieval/delete contract; an unavailable HTTP server makes readiness fail and never creates a local embedded collection.

- [ ] **Step 5: Commit Chroma server mode**

```powershell
git add src/backend/app/services/vector_client.py src/backend/app/services/vector_store.py src/backend/app/core/config.py src/backend/tests/test_vector_client.py .env.example
git commit -m "feat: support dedicated Chroma server mode"
```

---

### Task 8: Production and Load-Test Docker Topologies

**Files:**
- Create: `docker-compose.production.yml`
- Create: `docker-compose.loadtest.yml`
- Create: `src/backend/tests/test_production_compose.py`
- Modify: `src/backend/Dockerfile`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces one API, PostgreSQL, Redis, Chroma, frontend, and isolated ingestion/generation/video workers on one private Docker network.

- [ ] **Step 1: Add a Compose config validation test**

Create `src/backend/tests/test_production_compose.py`; have it run `docker compose -f docker-compose.yml -f docker-compose.production.yml config` and assert these eight services exist: `postgres`, `redis`, `chroma`, `backend`, `frontend`, `worker-ingestion`, `worker-generation`, and `worker-video`. Assert only frontend publishes a host port, each worker subscribes to exactly one named queue, and production env selects PostgreSQL/Celery/HTTP Chroma.

- [ ] **Step 2: Define durable infrastructure services**

Pin `postgres:16-alpine`, `redis:7-alpine`, and `chromadb/chroma:1.5.9`. Enable Redis AOF with `redis-server --appendonly yes`; add named volumes for PostgreSQL, Redis, and Chroma. Add healthchecks using `pg_isready`, `redis-cli ping`, and Chroma heartbeat.

- [ ] **Step 3: Define API and worker services from one backend image**

API command:

```yaml
command: ["sh", "-c", "uv run --project . alembic upgrade head && uv run --project . uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2"]
```

Each worker service uses the same backend image and its own `command`:

```yaml
worker-ingestion:
  command: ["uv", "run", "--project", ".", "celery", "-A", "app.jobs.celery_app:celery_app", "worker", "-Q", "ingestion", "-c", "2", "--loglevel=INFO"]
worker-generation:
  command: ["uv", "run", "--project", ".", "celery", "-A", "app.jobs.celery_app:celery_app", "worker", "-Q", "generation", "-c", "4", "--loglevel=INFO"]
worker-video:
  command: ["uv", "run", "--project", ".", "celery", "-A", "app.jobs.celery_app:celery_app", "worker", "-Q", "video", "-c", "1", "--loglevel=INFO"]
```

All four backend services mount the same upload/output/cache volumes; only Chroma mounts vector persistence.

- [ ] **Step 4: Add dependency-aware startup and production validation**

API and workers wait for healthy PostgreSQL, Redis, and Chroma. Frontend waits for healthy API. Production startup rejects empty `POSTGRES_PASSWORD`, default JWT secret, `EMAIL_DEV_FALLBACK=true`, non-official OpenRouter base URL, inline jobs, SQLite, or embedded Chroma.

- [ ] **Step 5: Start production topology and run smoke checks**

Run:

```powershell
docker compose -f docker-compose.yml -f docker-compose.production.yml config
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build --wait --wait-timeout 300
docker compose -f docker-compose.yml -f docker-compose.production.yml ps
```

Expected: all services healthy; port 3000 is the only published application port.

- [ ] **Step 6: Commit deployment topology**

```powershell
git add docker-compose.production.yml docker-compose.loadtest.yml src/backend/Dockerfile .env.example README.md
git commit -m "feat: add production worker topology for 100 active users"
```

---

### Task 9: Queued Job UX

**Files:**
- Modify: `src/frontend/src/lib/types.ts`
- Modify: `src/frontend/src/lib/api.ts`
- Modify: `src/frontend/src/hooks/usePollingArtifact.ts`
- Modify: `src/frontend/src/app/course/[id]/page.tsx`
- Modify: `src/frontend/src/components/dashboard/BookTab.tsx`
- Modify: `src/frontend/src/components/dashboard/SlideTab.tsx`
- Modify: `src/frontend/src/components/dashboard/QuizTab.tsx`
- Modify: `src/frontend/src/components/dashboard/VidTab.tsx`
- Create: `src/frontend/src/components/dashboard/JobProgress.tsx`
- Create: `src/frontend/src/components/dashboard/JobProgress.test.tsx`
- Modify: `src/frontend/e2e/visual-brand.spec.ts`

**Interfaces:**
- Consumes: `job_id` and `GET /api/jobs/{job_id}`.
- Produces: honest queued/running/retrying/cancelled UI without changing artifact tabs or generation endpoints.

- [ ] **Step 1: Write failing job-progress tests**

Test these exact states: queued shows `Đang chờ` plus queue name; running shows backend progress; retry-scheduled shows retry countdown; cancelled stops polling; failed shows safe error and retry action; succeeded switches back to artifact polling. Assert no raw payload, worker id, provider response, or technical error is rendered.

- [ ] **Step 2: Add job types and clients**

```typescript
export interface JobStatusResponse {
  id: string;
  course_id: string;
  job_type: "preprocess" | "book" | "slides" | "quiz" | "video";
  status: "queued" | "running" | "retry_scheduled" | "succeeded" | "failed" | "cancelled";
  progress: number;
  message: string;
  error_code?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}
```

Implement `apiGetJob(jobId)` and `apiCancelJob(jobId)` with encoded ids and existing authenticated `apiFetch`.

- [ ] **Step 3: Implement `JobProgress` and polling transitions**

Poll queued/running/retry-scheduled jobs every 3 seconds, stop on terminal state, and abort fetches on unmount. Keep polling hidden tabs only while a job is non-terminal. Cancel is available for queued/running video; cancellation is cooperative and copy must not claim immediate process termination.

- [ ] **Step 4: Wire all five heavy paths**

Upload/course status uses preprocess job id. Book, Slide, Quiz, and Vid save returned job id beside their reserved version id and show `JobProgress`. On success, resume existing artifact polling so download URLs and version switching remain unchanged.

- [ ] **Step 5: Run unit and browser queue journeys**

Run:

```powershell
npm test -- --run src/components/dashboard/JobProgress.test.tsx
npx playwright test --project=chromium --grep "queued|retry|cancel"
```

Expected: PASS at desktop/mobile, with no endless poll after terminal state.

- [ ] **Step 6: Commit queued job UX**

```powershell
git add src/frontend/src/lib/types.ts src/frontend/src/lib/api.ts src/frontend/src/hooks/usePollingArtifact.ts 'src/frontend/src/app/course/[id]/page.tsx' src/frontend/src/components/dashboard src/frontend/e2e/visual-brand.spec.ts
git commit -m "feat: show durable queue progress for study pack jobs"
```

---

### Task 10: Deterministic 100-User Load and Failure Tests

**Files:**
- Create: `tests/load/mock_openrouter.py`
- Create: `tests/load/fixtures/load-document.txt`
- Create: `tests/load/k6/read-path.js`
- Create: `tests/load/k6/mixed-jobs.js`
- Create: `tests/load/k6/provider-outage.js`
- Create: `src/backend/scripts/seed_load_users.py`
- Create: `docs/load-test-results.md`
- Modify: `docker-compose.loadtest.yml`
- Modify: `README.md`

**Interfaces:**
- Produces reproducible capacity evidence without spending real OpenRouter credit and a separately capped live-provider smoke procedure.

- [ ] **Step 1: Build a production-forbidden deterministic provider adapter**

Expose OpenRouter-compatible `/api/v1/key`, `/api/v1/models`, `/api/v1/embeddings/models`, `/api/v1/embeddings`, and `/api/v1/chat/completions`. Add `PUT /__control/fault` accepting `{ "mode": "healthy|key-limit|rate-limit|unavailable" }`; require `Authorization: Bearer ${LOAD_TEST_CONTROL_TOKEN}` and refuse to start the adapter unless `ENVIRONMENT=loadtest`. The backend must also reject `OPENROUTER_BASE_URL != https://openrouter.ai/api/v1` outside `ENVIRONMENT=loadtest`.

- [ ] **Step 2: Add a guarded user seeder**

`seed_load_users.py --count 100 --confirm LOADTEST` must refuse unless `ENVIRONMENT=loadtest`, create verified users `loadtest-001@example.invalid` through `loadtest-100@example.invalid`, hash one password from `LOAD_TEST_PASSWORD`, and print counts only.

- [ ] **Step 3: Implement the 100-user read-path test**

Use k6 `constant-vus` with 100 VUs for 10 minutes. Each VU logs in once, then alternates course list, course status, study-pack reads, and job status. Set thresholds:

```javascript
export const options = {
  scenarios: {
    active_users: { executor: "constant-vus", vus: 100, duration: "10m" },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
    dropped_iterations: ["count==0"],
  },
};
```

- [ ] **Step 4: Implement mixed queue pressure**

Use `constant-arrival-rate`: 20 upload/enqueue flows per minute for 10 minutes with 100 preallocated/max VUs. Each flow uploads `load-document.txt`, waits for ready, enqueues one rotating artifact type, and polls job status. Add tagged threshold `http_req_duration{endpoint:enqueue}: p(95)<2000`; require failure rate below 1%, no duplicate job ids, and global backlog below 200.

- [ ] **Step 5: Implement provider outage/recovery test**

Start with 20 queued ingestion jobs, call the authenticated `PUT /__control/fault` route with `key-limit`, and assert the first permanent failure opens the circuit and no job makes three identical provider calls. Set the mode back to `healthy`, call the application admin endpoint `GET /api/admin/provider-health?force=true` to clear the stale quota circuit, manually retry paused jobs, and require all 20 to succeed. Repeat with `rate-limit` and `unavailable`; assert bounded scheduled retries and zero worker crash. The control token exists only in the load-test Compose overlay and must never be logged or exposed by the application API.

- [ ] **Step 6: Run load gates and capture machine sizing**

Run:

```powershell
docker compose -f docker-compose.yml -f docker-compose.production.yml -f docker-compose.loadtest.yml up -d --build --wait --wait-timeout 300
docker compose exec backend uv run python scripts/seed_load_users.py --count 100 --confirm LOADTEST
docker run --rm --network hackagen-network -v "${PWD}/tests/load:/scripts" grafana/k6 run /scripts/k6/read-path.js
docker run --rm --network hackagen-network -v "${PWD}/tests/load:/scripts" grafana/k6 run /scripts/k6/mixed-jobs.js
docker run --rm --network hackagen-network -v "${PWD}/tests/load:/scripts" grafana/k6 run /scripts/k6/provider-outage.js
docker stats --no-stream
```

Record host CPU/RAM, container peak memory, queue drain time, p95/p99 latency, error rate, and dropped iterations in `docs/load-test-results.md`. A run fails if any threshold fails or a container restarts.

Expected: all k6 thresholds pass, no container restart is reported, global backlog stays below `200`, and the evidence file contains the measured host/container values rather than estimates.

- [ ] **Step 7: Run a capped real-OpenRouter smoke**

On staging only, restore the official base URL and a key with positive `limit_remaining`. Run five simultaneous small TXT/PDF ingestions plus two Book/Quiz generations. Require zero `401/402/403/429`, verify all outputs cite only uploaded content internally, and record actual provider cost from OpenRouter activity. Do not run the 100-user scenario against the paid provider.

Expected: all seven capped jobs reach `succeeded`, grounding checks pass, and the recorded cost/request count stays within the operator's predeclared smoke-test budget.

- [ ] **Step 8: Commit load harness and evidence template**

```powershell
git add tests/load src/backend/scripts/seed_load_users.py docker-compose.loadtest.yml README.md docs/load-test-results.md
git commit -m "test: gate capacity and provider recovery at 100 users"
```

---

### Task 11: Final Operations, Security, and Rollback Gate

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture_design.md`
- Modify: `docs/api_contract.md`
- Modify: `.env.example`

**Interfaces:**
- Documents the shipped topology and exact operator actions.

- [ ] **Step 1: Document queue sizing and alerts**

Document default concurrency, admission limits, queue names, time limits, and these alert conditions: any container restart; oldest ingestion/generation job over 5 minutes; oldest video job over 15 minutes; provider circuit open over 2 minutes; global backlog over 150; job failure rate over 5% in 10 minutes; PostgreSQL/Redis/Chroma unhealthy.

- [ ] **Step 2: Document backup and rollback**

Before rollout: back up SQLite, `data/uploads`, `data/outputs`, and Chroma data. Rollback stops API/workers, restores the previous image and SQLite `.env`, restores the Chroma snapshot if writes occurred, and starts the prior two-service Compose topology. Never run old SQLite and new PostgreSQL writers simultaneously.

- [ ] **Step 3: Run security tests**

Verify ordinary users cannot read/cancel another user's jobs, admin summaries contain no payloads or document text, Redis is not host-published, PostgreSQL and Chroma are not host-published, Celery accepts JSON only, production rejects the mock provider, and logs redact JWTs/API keys/passwords/OTP codes.

- [ ] **Step 4: Run complete release gates**

```powershell
Set-Location src/backend
uv run --project . ruff check .
uv run --project . pytest tests
Set-Location ../frontend
npm run audit:brand
npm test -- --run
npm run lint
npm run build
npm run test:visual
Set-Location ../..
docker compose -f docker-compose.yml -f docker-compose.production.yml config
git diff --check
```

Expected: every command exits `0`, no test leaks secrets, and the capacity test evidence meets every Global Constraint SLO.

- [ ] **Step 5: Commit final operations documentation**

```powershell
git add README.md docs/architecture_design.md docs/api_contract.md .env.example
git commit -m "docs: add 100-user operations and rollback runbook"
```

## Plan B Completion Criteria

- 100 active users can browse/poll while heavy jobs are queued without API crashes or unbounded memory/thread growth.
- Upload and all four generation routes return quickly with durable job ids.
- Worker death/redelivery creates no duplicate chunks, artifact versions, or output files.
- Video work cannot block ingestion or Book/Slide/Quiz workers.
- Provider quota/rate/outage events create bounded retries and visible recoverable states, not request storms.
- PostgreSQL, Redis, and Chroma are private-network services with passing health checks and backups.
- k6 read, mixed-job, and provider-outage scenarios pass stated thresholds, followed by a capped real-provider smoke.

## Reference Rationale

- Celery long-task fairness uses `worker_prefetch_multiplier=1`: https://docs.celeryq.dev/en/stable/userguide/configuration.html
- Late acknowledgement requires idempotent tasks: https://docs.celeryq.dev/en/stable/userguide/tasks.html
- SQLAlchemy uses `QueuePool` for concurrent non-SQLite engines: https://docs.sqlalchemy.org/en/20/core/engines.html
- Chroma supports Docker server plus `HttpClient`: https://docs.trychroma.com/guides/deploy/docker
- k6 arrival-rate executors and thresholds provide repeatable load plus pass/fail SLOs: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/ and https://grafana.com/docs/k6/latest/using-k6/thresholds/
