# Architecture Design

## 1. System overview

HackaGen is a document-to-Study-Pack application. A user uploads PDF, DOCX, or TXT files, then generates exactly four grounded artifacts: Book, Slide, Quiz, and Video.

Production uses one public entry point and seven private services:

```text
Browser
  -> Next.js frontend (only host-published port)
       -> same-origin /api proxy
            -> FastAPI API (2 Uvicorn workers)
                 -> PostgreSQL 16 (users, courses, durable jobs)
                 -> Redis 7 (Celery broker/result backend + provider guard)
                 -> Chroma 1.5.9 HTTP (grounded chunks)
                 -> shared uploads / outputs / embedding-cache volumes

Redis/Celery
  -> ingestion worker   queue=ingestion   concurrency=2
  -> generation worker  queue=generation  concurrency=4
  -> video worker       queue=video       concurrency=1
```

PostgreSQL, Redis, Chroma, FastAPI, and all workers are private to the Compose network. Local development remains a separate, single-process profile using SQLite, embedded Chroma, and inline `BackgroundTasks`.

## 2. Upload and indexing flow

1. The frontend sends `POST /api/upload` with multipart field `files` or compatibility field `files[]`.
2. FastAPI authenticates the caller, validates at most five `.pdf`, `.docx`, or `.txt` files, rejects empty files and files over 50 MiB, and saves them under `uploads/{course_id}/`.
3. In one database transaction, admission control reserves capacity and creates a durable `ProcessingJob` with only IDs and validated options in `payload_json`.
4. The API publishes the job ID to the `ingestion` queue and immediately returns `course_id` plus `job_id`.
5. A worker atomically claims the row with a lease, extracts and cleans text, chunks it, obtains guarded OpenRouter embeddings, and writes course-scoped vectors to Chroma.
6. Progress is fenced by job ID, worker ID, attempt, and live lease. A stale/redelivered worker cannot overwrite a newer attempt.
7. The worker commits terminal job and course state together. Provider quota or transient failures become safe retryable states instead of disappearing background exceptions.

Saved-document retry uses the same persisted job and Celery dispatcher; production never falls back to process-local inline execution.

## 3. Grounded generation flow

```text
owned ready course_id
  -> reserve artifact version + durable job in one transaction
  -> enqueue job ID on generation or video queue
  -> retrieve course-filtered chunks from Chroma
  -> remove extraction/debug noise
  -> call the configured paid OpenRouter model through the shared permit/circuit guard
  -> validate schema and source_chunk_ids
  -> write to attempt-specific staging
  -> lease-fenced atomic publication of the artifact version
  -> frontend polls job and artifact endpoints
```

Book, Slide, and Quiz use the `generation` queue. Video uses its own concurrency-one queue because ffmpeg rendering has a much larger CPU/RAM burst. Internal `source_chunk_ids` remain persisted for quality and source lookup, but public artifact payloads recursively remove raw chunk IDs, technical errors, prompts, and debug metadata.

## 4. Load-bearing modules

| Module | Responsibility |
| --- | --- |
| `main.py` and `app/routers/*` | FastAPI lifecycle, auth, ownership, enqueue/read/cancel contracts |
| `app/models/processing_job.py` | Durable job state, queue, attempts, lease, active-operation uniqueness |
| `app/jobs/admission.py` | Atomic per-user/global admission limits |
| `app/jobs/dispatcher.py` | Queue-neutral ID-only inline/Celery dispatch |
| `app/jobs/celery_app.py` and `app/jobs/tasks.py` | JSON-only queue routing, late ack, retry, lease renewal, cancellation |
| `app/services/document_processor.py` | PDF/DOCX/TXT extraction, cleanup, chunking, indexing |
| `app/services/vector_client.py` and `vector_store.py` | Embedded local Chroma or fail-closed private HTTP Chroma |
| `app/services/provider_guard.py` and `provider_health.py` | Shared permits, RPM bound, circuit breaker, redacted preflight |
| `app/services/generator.py` | Book, Slide, Quiz, Video generation and version publication |
| `app/services/job_resource_state.py` | Consistent terminal state for jobs, courses, and artifacts |

## 5. Storage and consistency

| Profile | Database | Vector storage | File storage |
| --- | --- | --- | --- |
| Local/dev | `data/app.db` SQLite | `data/chroma/` embedded | `data/uploads`, `data/outputs`, local cache |
| Production | `production-postgres` volume | `production-chroma` volume owned by Chroma HTTP | shared `production-uploads`, `production-outputs`, `production-cache` volumes |

Redis AOF is stored in `production-redis`, but PostgreSQL job rows are the durable source of job truth. Artifact publication uses attempt-specific temporary directories and a lease-fenced rename so redelivery cannot publish duplicate/stale output. Chroma cleanup is attempt-scoped.

## 6. Queue sizing and execution limits

| Queue | Worker concurrency | Soft / hard task limit | Alert age |
| --- | ---: | ---: | ---: |
| `ingestion` | 2 | 15 / 20 minutes | oldest queued job >5 minutes |
| `generation` | 4 | 20 / 25 minutes | oldest queued job >5 minutes |
| `video` | 1 | 45 / 50 minutes | oldest queued job >15 minutes |

Admission defaults are four active jobs per user and 200 globally. Workers use late acknowledgement, reject-on-worker-loss, `worker_prefetch_multiplier=1`, a 3,600-second renewable job lease, and JSON-only task/result serialization. OpenRouter defaults to six calls in flight and 60 requests per minute across processes through Redis.

Scale only one isolated queue at a time after rerunning `tests/load`; do not increase video concurrency on a 16 GiB host without new peak-memory evidence. The measured 100-user profile and container peaks are in `docs/load-test-results.md`.

## 7. Operations and alerts

Alert on:

- any container restart;
- oldest queued ingestion or generation job over five minutes;
- oldest queued video job over 15 minutes;
- provider circuit open for more than two minutes;
- global active backlog over 150 (before the hard admission limit of 200);
- terminal job failure rate over 5% in any 10-minute window;
- PostgreSQL, Redis, or Chroma becoming unhealthy.

`GET /api/admin/jobs/summary` provides aggregate counts and oldest queued age without job payloads or document text. `GET /api/admin/provider-health` provides a redacted provider check. Container health/restart state remains the deployment platform's responsibility.

Backup, rollout, and rollback commands are maintained in `README.md`. Old SQLite/embedded-Chroma writers and new PostgreSQL/Chroma-HTTP writers must never run simultaneously against the same logical dataset.

## 8. Architecture decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Public outputs | Exactly Book, Slide, Quiz, Video | Keeps one connected Study Pack surface |
| AI boundary | Frontend -> FastAPI -> OpenRouter | No provider credential reaches the browser |
| Retrieval | Chroma only | One course-filtered grounded index, no silent fallback |
| Job durability | PostgreSQL rows + Redis/Celery wake-ups | Durable state survives API/worker restarts |
| Queue isolation | ingestion / generation / video | Video bursts cannot block document readiness |
| Public metadata | Sanitized source views only | Preserves grounding without exposing raw internals |
| Auth | Bearer JWT or HttpOnly `agy_session` cookie | Ownership enforcement for documents, jobs, and artifacts |
