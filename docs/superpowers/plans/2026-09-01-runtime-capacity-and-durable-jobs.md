# Runtime Capacity and Durable Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep authenticated API traffic responsive for 100 active users while making upload and artifact jobs durable, observable, cancellable, and recoverable.

**Architecture:** Separate the FastAPI request process from Celery workers. PostgreSQL owns application/job state, Redis transports tasks, and workers update a durable `generation_jobs` record instead of relying on Celery results or in-memory `BackgroundTasks`.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 17, Celery 5.6, Redis 7, Pydantic 2, Next.js 16, React 19, Vitest, pytest, Locust

**Spec:** [Runtime Capacity and Durable Jobs Design](../specs/2026-09-01-runtime-capacity-and-durable-jobs-design.md)

## Global Constraints

- Preserve exactly the four public generation endpoints: Book, Slides, Quiz, Vid.
- Preserve OpenRouter-only AI access and backend-only provider credentials.
- Enforce course ownership in every job read, enqueue, and cancel path.
- SQLite is only for tests/single-user development; PostgreSQL is mandatory in production.
- Workers and API use shared course/Chroma storage for this release.
- Do not commit during execution unless the Lead explicitly authorizes commits. Each task includes the intended commit checkpoint for that case.
- Before frontend implementation, read `src/frontend/AGENTS.md` and the relevant installed Next.js 16 docs as required by that file.
- Before Task 7, complete Tasks 1-4 of [Distinctive Product Appearance and Brand Voice](2026-09-01-distinctive-product-appearance-and-brand-voice.md). `JobProgress` must use its paper/ink tokens, direct Vietnamese stage copy, Lucide icons, and claim rules; do not introduce glow, gradients, emoji, or promotional performance language. After Task 7, regenerate product screenshots and rerun `npm run audit:brand` plus `npm run test:visual` when those commands exist.

## File Structure

### Create

- `src/backend/app/models/generation_job.py` — durable job table and state enum.
- `src/backend/app/schemas/job.py` — public owner-safe job summaries.
- `src/backend/app/services/job_service.py` — admission, state transitions, progress, cancellation, recovery.
- `src/backend/app/workers/celery_app.py` — broker configuration and routes.
- `src/backend/app/workers/tasks.py` — thin idempotent task entry points.
- `src/backend/app/workers/__init__.py`
- `src/backend/alembic/versions/b8c9d0e1f2a3_add_generation_jobs.py` — schema migration after current head `a7b8c9d0e1f2`.
- `src/backend/tests/test_job_service.py`
- `src/backend/tests/test_worker_tasks.py`
- `src/backend/tests/test_readiness.py`
- `src/backend/tests/load/locustfile.py` — repeatable 100-user and mixed-render profiles.
- `src/backend/tests/load/README.md` — exact benchmark setup and acceptance commands.
- `src/frontend/src/components/course/JobProgress.tsx` — queue/stage/cancel UI shared by artifact tabs.
- `src/frontend/src/components/course/JobProgress.test.tsx`

### Modify

- `src/backend/app/models/__init__.py` — register `GenerationJob` for Alembic metadata.
- `src/backend/app/core/config.py` — broker, environment, limits, timeouts, worker-heartbeat settings.
- `src/backend/app/services/database.py` — production pool policy and startup guard.
- `src/backend/app/core/deps.py` — keep synchronous ORM calls off the event loop and close sessions promptly.
- `src/backend/app/schemas/generation.py` — accepted-job fields and nested job status.
- `src/backend/app/routers/upload.py` — enqueue ingestion instead of `BackgroundTasks`.
- `src/backend/app/routers/generation.py` — enqueue four artifacts, return 202, expose cancel/status.
- `src/backend/app/services/document_processor.py` — worker-safe entry point with job progress.
- `src/backend/app/services/generator.py` — worker-safe entry point with job progress.
- `src/backend/main.py` — liveness/readiness semantics and recovery scheduling.
- `src/backend/pyproject.toml`, `src/backend/requirements.txt`, `src/backend/uv.lock` — queue/database/load dependencies.
- `docker-compose.yml`, `src/backend/Dockerfile`, `.env.example` — PostgreSQL, Redis, API, two worker services, migration gate.
- `src/frontend/src/lib/types.ts`, `src/frontend/src/lib/api.ts` — job contract and cancellation call.
- `src/frontend/src/hooks/usePollingArtifact.ts` — terminal-state polling rather than browser-owned generation timeout.
- Four artifact panels/tabs under `src/frontend/src/components/course/` — display `JobProgress`.
- `README.md`, `docs/architecture_design.md`, `docs/api_contract.md` — operations and contract.

---

## Task 1: Add configuration and fail closed for production SQLite

**Files:**

- Modify: `src/backend/app/core/config.py`
- Modify: `src/backend/app/services/database.py`
- Modify: `src/backend/app/core/deps.py`
- Modify: `src/backend/pyproject.toml`
- Modify: `src/backend/requirements.txt`
- Test: `src/backend/tests/test_auth_and_core.py`

- [ ] Add failing configuration tests using isolated `Settings(...)` construction:

```python
def test_production_rejects_sqlite(base_settings: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(**{**base_settings, "APP_ENV": "production", "DATABASE_URL": "sqlite:///app.db"})


def test_job_capacity_must_cover_video_capacity(base_settings: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="MAX_ACTIVE_JOBS"):
        Settings(**{**base_settings, "MAX_ACTIVE_JOBS": 5, "MAX_ACTIVE_VIDEO_JOBS": 6})
```

- [ ] Run the focused tests and confirm they fail for missing settings:

```powershell
cd src/backend
uv run pytest tests/test_auth_and_core.py -k "production_rejects_sqlite or job_capacity" -q
```

- [ ] Add typed settings with the spec defaults:

```python
APP_ENV: Literal["development", "test", "production"] = "development"
REDIS_URL: str = "redis://localhost:6379/0"
MAX_ACTIVE_JOBS: int = 20
MAX_ACTIVE_VIDEO_JOBS: int = 6
DEFAULT_WORKER_CONCURRENCY: int = 4
VIDEO_WORKER_CONCURRENCY: int = 3
JOB_HEARTBEAT_STALE_SECONDS: int = 90
DATABASE_POOL_SIZE: int = 20
DATABASE_MAX_OVERFLOW: int = 20
DATABASE_POOL_TIMEOUT_SECONDS: int = 3
```

- [ ] Extend the model validator to reject non-PostgreSQL production URLs and invalid capacity relationships; do not weaken the current required-secret or paid-model validation.
- [ ] Change `get_current_user` and any other dependency that calls synchronous SQLAlchemy from `async def` to `def`, so FastAPI runs it in the threadpool. Add a regression test that monkeypatches the ORM query with a blocking probe and asserts the event loop can still answer a concurrent liveness request.
- [ ] Configure PostgreSQL with `pool_pre_ping=True`, a 20/20 pool, 3-second acquisition timeout, and bounded recycling. Add a documented startup calculation proving API pools + worker pools + 10 operational connections stay below PostgreSQL `max_connections`; do not apply PostgreSQL pool settings to SQLite tests.
- [ ] Add `celery[redis]>=5.6.3,<6.0.0`, `psycopg[binary]>=3.2,<4.0`, and `locust>=2.37,<3.0` (dev extra) in `pyproject.toml`, regenerate `uv.lock`, and keep `requirements.txt` aligned with the project's documented install path.
- [ ] Run `uv run pytest tests/test_auth_and_core.py -q` and `uv run ruff check app tests`.
- [ ] Commit checkpoint if authorized: `git commit -am "build: add durable worker configuration"` (include regenerated dependency files).

## Task 2: Add the durable job model and migration

**Files:**

- Create: `src/backend/app/models/generation_job.py`
- Modify: `src/backend/app/models/__init__.py`
- Create: `src/backend/alembic/versions/b8c9d0e1f2a3_add_generation_jobs.py`
- Test: `src/backend/tests/test_job_service.py`

- [ ] Write failing model tests for defaults, ownership fields, and the active-job uniqueness invariant:

```python
def test_only_one_active_job_per_course_artifact(db, course, user) -> None:
    db.add(make_job(course, user, artifact_type="book", state="queued"))
    db.commit()
    db.add(make_job(course, user, artifact_type="book", state="running"))
    with pytest.raises(IntegrityError):
        db.commit()
```

- [ ] Define string enums and the SQLAlchemy model. Store enum values as portable strings, timestamps as timezone-aware UTC, and JSON payloads through SQLAlchemy `JSON`:

```python
class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(16), index=True)
    state: Mapped[str] = mapped_column(String(16), index=True, default=JobState.QUEUED.value)
```

- [ ] Add all fields from the spec, including `dispatched_at`, `dispatch_attempts`, and bounded `last_dispatch_error`, plus relationships only where they do not create accidental eager loading. Assign `celery_task_id=id` before insert so every publish uses one deterministic id.
- [ ] Generate an Alembic revision after importing the model into metadata. Edit the revision to add a partial unique index for `queued`, `running`, and `retrying`; use dialect-correct `postgresql_where` and `sqlite_where` expressions.
- [ ] Verify the migration on an empty database and as upgrade/downgrade/upgrade:

```powershell
cd src/backend
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run pytest tests/test_job_service.py -q
```

- [ ] Inspect the generated migration: it must not drop, rename, or rewrite existing user/course data.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/models src/backend/alembic src/backend/tests/test_job_service.py; git commit -m "feat: add durable generation job model"`.

## Task 3: Implement transactional admission and lifecycle rules

**Files:**

- Create: `src/backend/app/services/job_service.py`
- Create: `src/backend/app/schemas/job.py`
- Modify: `src/backend/app/schemas/generation.py`
- Test: `src/backend/tests/test_job_service.py`

- [ ] Add failing service tests for total capacity, video capacity, duplicate active generation, ownership, legal transitions, throttled progress, cancellation, stale recovery, undispatched-row recovery, and idempotent success. Freeze time in heartbeat tests.

```python
def test_seventh_active_video_is_rejected(job_service, owned_course) -> None:
    for _ in range(6):
        job_service.enqueue(owned_course, "vid", payload={})
    with pytest.raises(JobCapacityError) as exc:
        job_service.enqueue(another_owned_course(), "vid", payload={})
    assert exc.value.code == "video_capacity_reached"


def test_terminal_job_cannot_return_to_running(job_service, failed_job) -> None:
    with pytest.raises(InvalidJobTransition):
        job_service.start(failed_job.id, celery_task_id="task-2")
```

- [ ] Implement exceptions with stable codes and safe public messages: `JobCapacityError`, `DuplicateActiveJobError`, `InvalidJobTransition`, `JobCancelled`, and `JobNotFound`.
- [ ] Implement `enqueue()` in one transaction. On PostgreSQL, take a transaction-scoped advisory lock keyed to deployment admission plus a row lock for the course; on SQLite tests, serialize through the test transaction. Count active total/video jobs, allocate or reuse the requested version, insert, flush, then return the job.
- [ ] Make legal transitions explicit rather than accepting arbitrary state strings:

```python
ALLOWED_TRANSITIONS = {
    JobState.QUEUED: {JobState.RUNNING, JobState.CANCELLED},
    JobState.RUNNING: {JobState.RETRYING, JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED},
    JobState.RETRYING: {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
}
```

- [ ] Implement owner-filtered `get_summary`, `request_cancel`, `start`, `heartbeat`, `succeed`, `fail`, `record_dispatch`, `find_pending_dispatches`, and `recover_stale_jobs`. Store only sanitized error text (maximum 500 characters); log exceptions separately.
- [ ] Compute advisory queue position from earlier nonterminal jobs in the same queue. Document that it is best effort.
- [ ] Add Pydantic `JobSummary` and extend `GenerateResponse` with `job_id`, `queue_position`, and `queued_at`, preserving the current fields.
- [ ] Run `uv run pytest tests/test_job_service.py -q` then `uv run pytest tests/test_generation_service.py -q`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/services/job_service.py src/backend/app/schemas src/backend/tests/test_job_service.py; git commit -m "feat: implement durable job lifecycle"`.

## Task 4: Configure Celery and idempotent worker entry points

**Files:**

- Create: `src/backend/app/workers/__init__.py`
- Create: `src/backend/app/workers/celery_app.py`
- Create: `src/backend/app/workers/tasks.py`
- Modify: `src/backend/app/services/document_processor.py`
- Modify: `src/backend/app/services/generator.py`
- Test: `src/backend/tests/test_worker_tasks.py`

- [ ] Write eager-mode worker tests with generator/processor fakes. Cover success, transient retry, nonretryable validation failure, duplicate delivery after success, cancellation, worker loss recovery, and dispatch of a committed job whose immediate publish never occurred.

```python
def test_completed_redelivery_does_not_generate_twice(task_harness, fake_generator) -> None:
    job = task_harness.ready_job("book")
    run_generation.apply(args=[job.id]).get()
    run_generation.apply(args=[job.id]).get()
    fake_generator.generate_book.assert_called_once()
```

- [ ] Configure Celery without a result backend and with explicit routes:

```python
celery_app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=None,
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.process_ingestion": {"queue": "ingestion"},
        "app.workers.tasks.run_generation": {"queue": "generation"},
        "app.workers.tasks.run_video": {"queue": "video"},
    },
)
```

- [ ] Make each task a thin database boundary: load job, idempotently claim it, construct the existing service, pass a progress/cancellation callback, and record one terminal outcome. Do not pass ORM objects, file bytes, or secrets through Redis.
- [ ] Route `vid` exclusively to `run_video`; route `book`, `slides`, and `quiz` through `run_generation`; route upload extraction/embedding through `process_ingestion`.
- [ ] Add `dispatch_pending_jobs` and `recover_stale_jobs` maintenance tasks. Every 10 seconds, scan a bounded page of queued rows not dispatched recently and publish with `task_id=job.id`; every 30 seconds, apply the 90-second heartbeat policy. Use a database advisory lock so only one scheduler instance performs each scan.
- [ ] Declare retryable exceptions (provider timeout, temporary network failure, worker-lost recovery) and use Celery exponential backoff with jitter. Do not autoretry JSON/schema validation, authorization, missing file, or grounding errors.
- [ ] Refactor `DocumentProcessor.process_course` and artifact generator methods to accept a `JobReporter` protocol:

```python
class JobReporter(Protocol):
    def progress(self, stage: str, percent: int) -> None: ...
    def raise_if_cancelled(self) -> None: ...
```

- [ ] Use the reporter only at stable stage boundaries; preserve direct calls in existing unit tests through a no-op reporter default.
- [ ] Run `uv run pytest tests/test_worker_tasks.py tests/test_generation_service.py tests/test_vector_store_and_processor.py -q`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/workers src/backend/app/services src/backend/tests/test_worker_tasks.py; git commit -m "feat: run generation in durable workers"`.

## Task 5: Replace `BackgroundTasks` with enqueue APIs and cancellation

**Files:**

- Modify: `src/backend/app/routers/upload.py`
- Modify: `src/backend/app/routers/generation.py`
- Modify: `src/backend/app/schemas/generation.py`
- Test: `src/backend/tests/test_course_and_upload.py`
- Test: `src/backend/tests/test_generation_service.py`

- [ ] Change API tests first. Assert HTTP 202, returned job metadata, exact Celery dispatch after commit, 409 duplicate, 429 capacity with `Retry-After`, owner-only nested summaries, and cancellation responses.

```python
response = client.post(f"/api/course/{course.id}/generate/book", json={"detail_level": "Tiêu chuẩn"})
assert response.status_code == 202
assert response.json()["status"] == "queued"
assert response.json()["job_id"]
dispatch.assert_called_once_with(response.json()["job_id"])
```

- [ ] Remove `BackgroundTasks` parameters and imports from upload/generation routers.
- [ ] Enqueue inside the request transaction, commit, then dispatch with deterministic `task_id=job.id`. If the immediate Redis publish fails, record a bounded dispatch error and still return the durable job as queued; the scheduler republishes it. Readiness turns 503 while Redis is unavailable, preventing normal new traffic, but a committed row is never discarded or falsely marked terminal.
- [ ] Keep all four existing request schemas and routes. Map capacity exceptions to 429, duplicate active work to 409, malformed request to 422, and non-owned ids to 404.
- [ ] Add the generic artifact-version cancellation route specified in the design and check ownership before revealing whether the job exists.
- [ ] Include the most recent active/terminal `JobSummary` in artifact status/version responses without exposing `payload_json`, Celery ids, stack traces, or other users' queue data.
- [ ] Run `uv run pytest tests/test_course_and_upload.py tests/test_generation_service.py -q` and verify `rg "BackgroundTasks" src/backend/app/routers` returns no matches.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/routers src/backend/app/schemas src/backend/tests; git commit -m "feat: expose durable generation jobs"`.

## Task 6: Make startup and readiness truthful

**Files:**

- Modify: `src/backend/main.py`
- Modify: `src/backend/app/services/database.py`
- Create: `src/backend/tests/test_readiness.py`
- Modify: `src/backend/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] Write readiness tests that independently fail database connectivity, migration-head validation, Redis ping, Chroma access, required directory writes, and queue heartbeat. Assert `/` still answers liveness and `/health` returns 503 with component details.

```python
def test_missing_schema_is_not_ready(client, readiness_checks) -> None:
    readiness_checks.alembic_head.return_value = ComponentHealth(False, "schema_outdated")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["components"]["database"]["code"] == "schema_outdated"
```

- [ ] Replace the current Chroma/directory-only health function with bounded checks. Do not call OpenRouter from health; return its last known success/failure timestamp when recorded.
- [ ] Run migrations in a one-shot Compose `migrate` service, not concurrently in every API replica. Make backend and workers depend on its successful completion plus PostgreSQL/Redis health.
- [ ] Expand Compose with PostgreSQL 17, Redis 7 with append-only persistence, a Celery `scheduler`, `worker-default` (`-Q ingestion,generation,maintenance -c 4`) and `worker-video` (`-Q video -c 3`). Mount uploads, outputs, cache, and Chroma identically into API and workers.
- [ ] Add graceful worker stop time sufficient for child cleanup. Keep hard time limits as safety boundaries, not normal cancellation.
- [ ] Add production-safe `.env.example` values and comments for `DATABASE_URL`, `REDIS_URL`, capacity, concurrency, and timeouts; keep secrets blank.
- [ ] Verify from clean named volumes:

```powershell
docker compose config
docker compose up --build -d
docker compose ps
docker compose exec backend python -m alembic current
```

- [ ] Register/login/upload through the frontend proxy on the clean deployment, then inspect `docker compose logs --tail=200 backend scheduler worker-default worker-video` for tracebacks or secret leakage.
- [ ] Commit checkpoint if authorized: `git add docker-compose.yml .env.example src/backend/Dockerfile src/backend/main.py src/backend/tests/test_readiness.py; git commit -m "ops: add postgres redis workers and readiness"`.

## Task 7: Show durable job progress in the frontend

**Files:**

- Modify: `src/frontend/src/lib/types.ts`
- Modify: `src/frontend/src/lib/api.ts`
- Modify: `src/frontend/src/hooks/usePollingArtifact.ts`
- Modify: `src/frontend/src/hooks/usePollingArtifact.test.tsx`
- Create: `src/frontend/src/components/course/JobProgress.tsx`
- Create: `src/frontend/src/components/course/JobProgress.test.tsx`
- Modify: Book/Slide/Quiz/Vid artifact tab components under `src/frontend/src/components/course/`

- [ ] Read `src/frontend/AGENTS.md` and its required Next.js 16 references before changing frontend code.
- [ ] Add failing hook/component tests for queued position, running stage/progress, retry attempt, terminal failure, cancel success, cancel conflict, unmount, request timeout recovery, and no overall generation timeout.

```tsx
it("keeps polling beyond the old generation timeout", async () => {
  vi.useFakeTimers()
  mockStatus.mockResolvedValue({ status: "processing", job: { state: "running", progress: 50 } })
  renderHook(() => usePollingArtifact(optionsWithoutOverallTimeout))
  await vi.advanceTimersByTimeAsync(9 * 60_000)
  expect(mockStatus).toHaveBeenCalled()
  expect(onError).not.toHaveBeenCalled()
})
```

- [ ] Add exact unions for internal job state and owner-safe `JobSummary`; preserve the existing artifact top-level status union.
- [ ] Remove required `timeoutMs` as an overall job deadline. Give each HTTP call a 30-second abort timeout, use 3-second active and 10-second queued polling, and stop only on backend terminal state/unmount.
- [ ] Implement `JobProgress` with accessible live status, stable labels, bounded progress values, advisory queue text, and cancel confirmation. Do not display raw backend error strings.
- [ ] Integrate the shared component in all four tabs and disable generation unless course status is `ready`; explicitly render ingestion error state.
- [ ] Run:

```powershell
cd src/frontend
npm test -- --run
npm run lint
npm run build
```

- [ ] Commit checkpoint if authorized: `git add src/frontend/src; git commit -m "feat: show durable artifact job progress"`.

## Task 8: Add the reproducible load gate and operating runbook

**Files:**

- Create: `src/backend/tests/load/locustfile.py`
- Create: `src/backend/tests/load/README.md`
- Modify: `README.md`
- Modify: `docs/architecture_design.md`
- Modify: `docs/api_contract.md`

- [ ] Implement two authenticated Locust shapes with seeded test users/courses:

```python
class BrowseAndPoll(HttpUser):
    wait_time = between(1, 3)

    @task(4)
    def list_courses(self):
        self.client.get("/api/courses")

    @task(6)
    def poll_artifact(self):
        self.client.get(f"/api/course/{self.course_id}/artifacts/vid")
```

- [ ] Profile A ramps to 100 users and holds 5 minutes. Profile B starts three offline video fixtures, then runs the same API traffic. Produce CSV output and fail the wrapper when p95 is >=500 ms or failure rate is >=1%.
- [ ] Add an admission scenario that submits 21 total and 7 video jobs, verifying exactly the expected 202/429 split and codes.
- [ ] Document host CPU, memory, disk, Docker limits, fixture hash, worker concurrency, git revision, and baseline/results in the load README so performance claims are comparable.
- [ ] Document clean setup, migration, workers, readiness interpretation, queue recovery, cancellation, capacity tuning, backup paths, and rollback. Link the official [FastAPI background-task caveat](https://fastapi.tiangolo.com/tutorial/background-tasks/), [Celery task guidance](https://docs.celeryq.dev/en/stable/userguide/tasks.html), [Celery worker controls](https://docs.celeryq.dev/en/stable/userguide/workers.html), and [Redis persistence options](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).
- [ ] Run the complete gate:

```powershell
cd src/backend
uv run ruff check app tests
uv run pytest -q
uv run locust -f tests/load/locustfile.py --headless --users 100 --spawn-rate 10 --run-time 5m --csv load-results
cd ..\frontend
npm test -- --run
npm run lint
npm run build
```

- [ ] Run `docker compose down` without `-v`, restart, and verify ready state and retained jobs/artifacts. Do not delete user volumes as part of a normal test.
- [ ] Commit checkpoint if authorized: `git add README.md docs src/backend/tests/load; git commit -m "test: add runtime capacity acceptance gate"`.

## Final Verification

- [ ] Run `rg -n "BackgroundTasks|sqlite:///" src/backend/app docker-compose.yml .env.example` and confirm only intentional dev/test documentation references remain.
- [ ] Run `rg -n "OPENROUTER_API_KEY|JWT_SECRET" src/frontend` and confirm no provider/auth secrets were introduced.
- [ ] Exercise a worker kill, an API kill immediately after database commit/before publish, API restart, cancellation, capacity rejection, and clean-volume startup manually once.
- [ ] Record the final Locust p50/p95/p99, error rate, throughput, CPU, memory, and disk utilization in `src/backend/tests/load/README.md`.
- [ ] Review the diff for accidental endpoint additions, unowned job queries, raw provider errors, migration data loss, and changes outside this plan.
