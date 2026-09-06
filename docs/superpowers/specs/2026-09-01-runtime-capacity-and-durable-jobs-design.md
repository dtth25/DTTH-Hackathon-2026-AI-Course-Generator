# Runtime Capacity and Durable Jobs Design

**Date:** 2026-09-01  
**Status:** Approved planning baseline  
**Scope:** Upload processing and the four existing generation flows (`book`, `slides`, `quiz`, `vid`)

## Problem

The current FastAPI process executes document ingestion and artifact generation with in-process `BackgroundTasks`. That makes expensive work compete with authenticated API requests, loses work when the API restarts, and provides no durable admission control. The current SQLite connection pool also stalls under concurrent authenticated polling.

Observed on the local reference machine:

- A 50-user authenticated read/poll test produced 84 timeouts out of 100 requests, about 3.3 requests/second, and a 15.05-second p95.
- A 100-user/500-request run produced 499 failures and a 10.1-second p95.
- A fresh database can report a healthy process before migrations exist, then return HTTP 500 during registration.
- Restarting the API can leave generation metadata in `processing` until a stale-state heuristic runs.

## Capacity Contract

The first production target is one deployment serving:

- 100 active authenticated users browsing and polling.
- Up to 20 accepted artifact jobs across upload ingestion and generation.
- At most 6 accepted video jobs, with 3 video jobs running concurrently on the reference deployment.
- Authenticated non-generation API p95 below 500 ms and error rate below 1% under the 100-user test.
- Generation request acceptance below 1 second; accepted jobs survive API and worker restarts.
- Queue position and current stage visible to the owner.

Worker concurrency is configuration, not a promise independent of hardware. Production may lower the video concurrency when the benchmark gate shows CPU, memory, or disk saturation. It may not raise it without rerunning the gate.

## Architecture

```text
Browser
   |
   v
FastAPI API ---- PostgreSQL (users, courses, artifacts, durable job truth)
   |                  ^
   v                  |
Redis broker ---------+---- Celery ingestion/generation workers
                            Celery video workers
                                   |
                                   +-- local artifact storage + Chroma
```

- PostgreSQL is the source of truth for jobs and application state.
- Redis is the Celery broker, not the authoritative job database.
- Celery's result backend is disabled; workers write progress and outcomes transactionally to PostgreSQL.
- SQLite remains supported for unit tests and single-user development only. Startup must reject SQLite when `APP_ENV=production`.
- The initial API keeps SQLAlchemy's synchronous session, but every dependency/route that touches it executes in FastAPI's worker threadpool; no `async def` function may make a blocking ORM call. Request handlers release sessions before broker/network work. The initial PostgreSQL pool is 20 persistent plus 20 overflow connections with a 3-second acquisition timeout, subject to the deployment connection-budget formula.
- The API and workers use the same mounted artifact and Chroma directories for the initial single-host deployment.
- Production workers run in Linux containers. Windows local worker smoke tests do not represent production timeout or process-signal behavior.

This follows FastAPI's own guidance that heavy background computation should use a separate job system, and uses Redis/Celery only behind an application-owned durable job model.

## Job Model

Add a `generation_jobs` table with these fields:

| Field | Contract |
|---|---|
| `id` | UUID string primary key |
| `course_id` | Owned course foreign key, indexed |
| `user_id` | Owner foreign key, indexed |
| `artifact_type` | `ingestion`, `book`, `slides`, `quiz`, or `vid` |
| `version_id` | Requested artifact version; nullable only for ingestion |
| `queue_name` | `ingestion`, `generation`, or `video` |
| `state` | `queued`, `running`, `retrying`, `succeeded`, `failed`, or `cancelled` |
| `payload_json` | Validated request payload needed to replay the job |
| `progress` | Integer 0-100 |
| `stage` | Stable machine-readable stage string |
| `attempt` / `max_attempts` | Attempt accounting |
| `celery_task_id` | Broker task correlation id |
| dispatch fields | `dispatched_at`, `dispatch_attempts`, `last_dispatch_error` for outbox recovery |
| `error_code` / `error_message` | Sanitized terminal error |
| timestamps | `queued_at`, `started_at`, `heartbeat_at`, `finished_at`, `created_at`, `updated_at` |

Create a partial unique index over `(course_id, artifact_type)` for active states (`queued`, `running`, `retrying`). This preserves the current one-in-flight-generation invariant across API replicas. Insertion, version allocation, and course ownership validation occur in one database transaction.

## State Transitions

```text
queued -> running -> succeeded
   |         |  \
   |         |   -> retrying -> queued
   |         |
   |         -> failed
   |
   -> cancelled

running -> cancelled only after a cooperative cancellation checkpoint
```

- A worker atomically claims only a `queued` job matching its Celery task id.
- The PostgreSQL job row is also the transactional outbox. `celery_task_id` equals `job.id` and is assigned before commit. The API attempts immediate publish after commit; a dispatcher scan republishes undispatched/stale queued rows with the same task id every 10 seconds. Duplicate deliveries are therefore expected and idempotent.
- A duplicate delivery sees the existing state and either exits (`succeeded`, `failed`, `cancelled`) or safely resumes the same idempotent version (`queued`, `running`, `retrying`).
- A heartbeat is written at stage boundaries and at most every 2 seconds during progress-heavy stages.
- A recovery sweep marks `running` jobs with a heartbeat older than 90 seconds as `retrying` if attempts remain, otherwise `failed` with `worker_lost`.
- Cancellation sets a durable `cancel_requested_at`; the worker checks it at stage boundaries before setting `cancelled`.

## Admission Control

Before inserting a job, the API counts active jobs in the same transaction:

- Reject with HTTP 429 and code `artifact_capacity_reached` when 20 total jobs are active.
- Reject a new video with HTTP 429 and code `video_capacity_reached` when 6 videos are active.
- Reject a duplicate course/artifact request with HTTP 409 and code `generation_in_flight`.
- Include `Retry-After: 30` on capacity rejections.

Accepted jobs receive a best-effort queue position derived from earlier active jobs in the same queue. Position is advisory because cancellations and retries can reorder work.

## API Contract

Keep the four generation endpoints and upload route. Do not add a fifth generation endpoint.

An accepted generation returns HTTP 202:

```json
{
  "course_id": "course-id",
  "status": "queued",
  "message": "Book generation queued",
  "estimated_time": "6-10 minutes",
  "version_id": "version-id",
  "job_id": "job-id",
  "queue_position": 2,
  "queued_at": "2026-09-01T12:00:00Z"
}
```

Existing artifact status remains backward compatible at the top level (`empty`, `processing`, `ready`, `error`). Add a nested job summary:

```json
{
  "status": "processing",
  "job": {
    "job_id": "job-id",
    "state": "running",
    "stage": "rendering_scene",
    "progress": 64,
    "queue_position": 0,
    "attempt": 1,
    "can_cancel": true
  }
}
```

Add `POST /api/course/{course_id}/artifacts/{artifact_type}/versions/{version_id}/cancel`. It is not a generation endpoint; it changes the lifecycle of an existing owned version. Return 202 for a recorded request, 409 for a terminal job, and 404 for a non-owned/missing course or version.

## Task Routing and Limits

| Queue | Work | Default worker concurrency | Soft/hard limit |
|---|---|---:|---:|
| `ingestion` | extract, chunk, embed, source-map prerequisites | 2 | 20/25 minutes |
| `generation` | book, slides, quiz | 4 | 15/18 minutes |
| `video` | script, TTS, FFmpeg | 3 | 30/35 minutes |

Celery configuration:

- `task_acks_late=True`
- `task_reject_on_worker_lost=True`
- `worker_prefetch_multiplier=1`
- `task_ignore_result=True`
- explicit task routes; no catch-all heavy task on the API process

Retries apply only to declared transient failures. Use exponential backoff with jitter. Provider/network failures get at most 2 generation attempts and 3 ingestion attempts. Validation, authorization, grounding, and malformed-document errors do not retry.

## Readiness and Startup

- `/` is liveness: it checks only that the API event loop can answer.
- `/health` is readiness and returns HTTP 503 unless database connectivity, Alembic head, Redis connectivity, required storage paths, and Chroma access are ready.
- Readiness reports worker heartbeats per required queue. A paid provider call is not made by health checks; the response reports the last provider success/failure timestamp when available.
- Docker startup applies `alembic upgrade head` before starting the API.
- Worker startup does not race schema creation; Compose waits for the migration/API readiness gate.
- Public errors use stable codes and sanitized messages. Stack traces and provider credentials stay server-side.
- The sum of `(API replicas × API pool maximum) + worker pool maxima + 10 connections of migration/operations headroom` must remain below PostgreSQL `max_connections`. Raising API or worker concurrency requires recalculating this budget and rerunning the load gate.

## Deployment

The initial Compose topology contains `postgres`, `redis`, `migrate`, `backend`, `scheduler`, `worker-default`, `worker-video`, and `frontend`. The scheduler runs the 10-second pending-job dispatch and 30-second stale-heartbeat recovery scans; both scans are safe to repeat. PostgreSQL, Redis AOF data, course artifacts, and Chroma each have explicit volumes. API and workers receive the same OpenRouter key and artifact paths; the frontend never receives provider secrets.

## Acceptance Gates

1. A clean volume starts, applies migrations, reports ready, and can register/login/upload without manual commands.
2. Killing and restarting the API while jobs run does not lose jobs or stop workers.
3. Killing a worker causes a stale job to retry or fail by the stated policy; it never remains indefinitely `processing`.
4. Killing the API between the job-row commit and Redis publish still results in dispatch by the scheduler after restart.
5. A user cannot inspect or cancel another user's job.
6. The 100-user authenticated browse/poll test holds p95 below 500 ms and errors below 1% while three videos render in the isolated worker service.
7. A 21st active artifact job and a 7th active video receive deterministic 429 responses.
8. Static analysis, backend tests, frontend tests, frontend build, migration upgrade/downgrade/upgrade, and Compose smoke tests all pass.

## Out of Scope

- Kubernetes or multi-region deployment.
- S3-compatible artifact storage; shared local storage is retained for the first deployment.
- A new public generation endpoint.
- Changing the OpenRouter-only provider invariant.
