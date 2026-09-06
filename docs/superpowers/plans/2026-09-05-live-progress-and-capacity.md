# Live Progress, Cost and Capacity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show durable live progress without reload, measure and reduce long Book latency, and establish honest capacity and per-test cost evidence.

**Architecture:** Keep the existing authenticated job API and 3-second polling. Persist job and artifact progress in one fenced transaction, recover active jobs on remount, and separate heartbeat from completed work. Instrument provider calls before introducing resumable chapters and bounded concurrency; use the existing distributed deployment only after migration and capacity verification.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite/PostgreSQL, Celery/Redis, OpenRouter SDK, Next.js/React, Vitest, pytest, k6.

**Spec:** [Audit findings and required outcomes](2026-09-05-generation-audit-findings.md).

**Budget revision:** The [balanced Book budget plan](2026-09-05-balanced-book-budget.md) refines Tasks 3–6 below: $0.05–$0.09 target, $0.10 ceiling per logical Book including retries. It proposes a quality-gated Flash Book policy and replaces the prior assumption that Book must remain on Pro. Store the selected policy once per version; never switch models on retry.

## Global Constraints

- Active resources poll every 3–5 seconds until terminal state; no reload requirement.
- Four existing generation endpoints only; preserve auth/ownership, authenticated downloads, no public raw source IDs, three-version cap and atomic publication/lease fencing.
- Keep the selected paid OpenRouter model; each content/OCR call retries the same model once. Provider quota errors do not cause uncontrolled paid retries.
- Every executed test reports estimated and actual provider cost. No paid provider in 50/100-user load tests.
- Book target: $0.05–$0.09 OpenRouter spend; hard user ceiling: $0.10 per logical Book generation, including generation-triggered retrieval, source-plan creation, reasoning, review, repair and retries. Spending less than $0.05 is welcome.
- No commits, push, or deployment without a separate user instruction. Review the diff after each task instead of committing.
- Read `CLAUDE.md`, frontend `AGENTS.md` and installed Next.js documentation before implementation.

## File and interface map

| Unit | Files | Responsibility |
| --- | --- | --- |
| Durable progress | `src/backend/app/services/generator.py`, `services/job_service.py`, `services/document_processor.py`, `routers/generation.py`, `routers/jobs.py`, `schemas/generation.py`, `schemas/course.py` | Fenced progress write; safe active-job recovery envelope |
| Job observation | `src/frontend/src/hooks/usePollingArtifact.ts`, `components/dashboard/JobProgress.tsx`, Book/Slide/Quiz/Vid tabs, `lib/types.ts`, `lib/api.ts` | Recover, observe, reconnect and finish one job/version |
| Cost and latency | New `src/backend/app/services/provider_usage.py`, `models/provider_call.py`, Alembic migration; `services/llm.py`, `services/vector_store.py` | Record provider response usage, timings and bounded reservations |
| Book checkpointing | New `src/backend/app/services/book_checkpoint.py`; `services/generator.py`, `jobs/tasks.py` | Resume validated chapters without repeating successful calls |
| Admission and capacity | `services/provider_guard.py`, `services/job_service.py`, `docker-compose.production.yml`, `tests/load/mock_openrouter.py`, new `tests/load/k6/long-generation.js` | Bounded fair capacity and realistic load evidence |

All backend file paths abbreviated after the first entry above are relative to `src/backend/app`. Checkpoint and usage storage are internal; public responses contain only product stage/counts, cost aggregates where authorized, and the current user's job ID.

### Task 1: Synchronize artifact and job progress atomically

**Files:** Modify `generator.py:_set_artifact_status`; test new `src/backend/tests/test_artifact_progress_contract.py`; extend `tests/test_job_tasks.py`.

**Interfaces:** Existing `_set_artifact_status(... progress: int | None, job_id, worker_id, attempt_number, db_session_factory) -> bool` keeps its signature. A successful return means both job progress and artifact metadata committed under the same live claim.

- [ ] Add a failing regression using the isolated database setup from `docs/superpowers/diagnostics/2026-09-05-offline-audit.py`. Replace observational output with the invariant:

```python
assert written
assert job_progress == artifact_progress == 52
```

- [ ] Run `uv run --no-sync pytest tests/test_artifact_progress_contract.py -q` from backend with a fake key and provider network blocked. Expected baseline: `0 != 52`; estimated/actual provider cost $0.
- [ ] Replace the existing no-op guarded job update with a real progress/timestamp write inside the transaction that writes course metadata. Retain all job ID, course, worker, attempt, status, cancellation and lease predicates. Use monotonic progress only inside one attempt; the durable retry transition explicitly resets its progress.

```python
from sqlalchemy import case

values = {"updated_at": datetime.utcnow()}
if progress is not None:
    bounded = max(0, min(99 if status == "processing" else 100, progress))
    values["progress"] = case(
        (ProcessingJob.progress > bounded, ProcessingJob.progress),
        else_=bounded,
    )
# Apply values to the existing fenced UPDATE, then write metadata and commit once.
# Do not commit the job update before the course metadata write.
```

- [ ] Add failure/rollback cases for expired lease, stale attempt, cancellation, DB commit error, and concurrent updates to different artifacts on the same course. Serialize the course metadata read-modify-write on PostgreSQL with a row lock; keep SQLite transaction serialization. Assert stale updates change neither representation and concurrent valid updates preserve both artifact entries.
- [ ] Run the new contract tests plus `test_job_tasks.py` and `test_job_idempotency.py`. Review the diff and record test counts/cost. No provider calls.

### Task 2: Recover and observe the same job across reloads and long calls

**Files:** Modify status schemas/router envelopes, `usePollingArtifact.ts`, `JobProgress.tsx`, all four tab integrations and `lib/types.ts`; extend their existing Vitest tests.

**Interfaces:** Artifact envelopes add optional `job_id: string | null` for the selected version and only its owning course/user. Job envelopes add nullable `next_attempt_at` and a product-safe stage. Frontend job observation callbacks carry progress to the hook so secondary header buttons do not remain at 0% while the job card updates.

```ts
type JobObservation = {
  status: JobStatus;
  progress: number;
  updated_at: string;
  next_attempt_at?: string | null;
};
// JobProgress new prop:
// onUpdate?: (job: JobObservation) => void
// ArtifactStatusLike new property:
// job_id?: string | null
```

- [ ] Add hook tests for initial `{status:"processing", job_id:"j1", version_id:"v1"}`, then running updates beyond six minutes and eventual success. Use mocked APIs/fake time, not a real wait. Add a widget sequence test, not just static mocked percentages:

```ts
vi.mocked(apiGetJob)
  .mockResolvedValueOnce(job({ status: "running", progress: 15 }))
  .mockResolvedValueOnce(job({ status: "running", progress: 52 }))
  .mockResolvedValueOnce(job({ status: "succeeded", progress: 100 }));
render(<JobProgress jobId="job-1" onSucceeded={onSucceeded} />);
await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "52");
```

- [ ] Run focused Vitest tests and record failing baseline ($0). Add router ownership tests ensuring no other user's active job is returned, including when an older ready version remains selected.
- [ ] On initial artifact fetch, bind `job_id` with `startJob` when available. Stop active polling only for terminal server states or explicit navigation/unmount; elapsed UI time displays a delay message while continuing observation. Preserve legacy artifact-only polling for old records. Restore background active versions even when an older ready version is being viewed; do not replace user-selected content on every progress tick.
- [ ] Give each status request a 10-second AbortController deadline, abort on unmount/course changes, ignore responses from an old request generation, and recheck immediately on `online`/visible-tab events. Use one scheduled request at a time. Retry the read at 3–5 seconds with jitter after transient errors; handle 401/403 as session failure instead of an infinite silent retry.
- [ ] Render actual scheduled retry time from `next_attempt_at`; the current three-second polling countdown must not claim the worker retries in three seconds. Show stage/elapsed time during a long call without fabricated percent increments.
- [ ] Run hook/widget/retry suites and Playwright mocked long-job scenarios across all four tabs, including remount, version switch, late response after course change, network loss/recovery, and terminal completion. Estimated/actual provider cost $0. Acceptance: progress and finished artifact appear within five seconds of a successful status read, no manual reload.

### Task 3: Record provider cost and stage latency before paid experiments

**Files:** Create `models/provider_call.py`, `services/provider_usage.py`, migration and `tests/test_provider_usage.py`; modify LLM, OCR and embedding call boundaries; extend `tests/load/real_provider_smoke.py`.

**Interfaces:** `record_provider_call(job_id, attempt, feature, stage, response_id, elapsed_ms, usage, outcome) -> None`. Internal records store token counts, cost, provider response ID and timestamps; never store key, prompt, raw source text or raw provider errors. `reserve_test_budget(run_id, upper_bound_usd) -> bool` atomically reserves capacity before dispatch; `settle_test_budget(run_id, actual_usd) -> None` releases unused reservation.

- [ ] Test usage recording with synthetic valid and schema-invalid responses, an exception with no bill, concurrent reservations, duplicate response IDs and missing cost. Missing usage is unknown, never zero:

```python
def test_missing_usage_is_unknown():
    from app.services.provider_usage import normalize_usage
    assert normalize_usage(None) == {"cost_usd": None, "input_tokens": None, "output_tokens": None}
```

- [ ] Implement `normalize_usage(usage: dict | None) -> dict` to preserve provider-reported `cost`, `prompt_tokens` and `completion_tokens`; reject negative/nonfinite values as unknown. Record immediately after receiving the provider response, before JSON parsing can throw; include the second same-model attempt. Enforce unique response IDs, otherwise use a per-call UUID so retries cannot erase charges.

```python
import math

def normalize_usage(usage):
    usage = usage or {}
    def number(name):
        value = usage.get(name)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None
    return {
        "cost_usd": number("cost"),
        "input_tokens": number("prompt_tokens"),
        "output_tokens": number("completion_tokens"),
    }
```

- [ ] Add stage timers for queue wait, retrieve/embed, outline, each chapter, export and total duration. Persist safe product stages and heartbeat separately from progress. A heartbeat must verify/renew the current lease; it must not keep a cancelled or stolen claim alive.
- [ ] Before paid smoke, read both `/key` and `/credits`, fetch current model pricing, and reserve conservative input/output/OCR/embedding allowance including retries. Use request output caps to support the reservation. If unknown cost remains, retain the reservation pending reconciliation and do not launch additional paid work. Capture actual response-level cost rather than attributing all shared-key balance changes to the test.
- [ ] Test with fake provider usage, invalid JSON and forced timeout; run `test_provider_usage.py` and existing provider guard/parsing tests ($0). Record current pricing source/date in the smoke result. Use [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting) as the provider contract.

### Task 4: Checkpoint completed chapters and bound provider time

**Files:** New `services/book_checkpoint.py`, `tests/test_book_checkpoint.py`; modify `generator.py:generate_book`, `llm.py:_init_client`, `jobs/tasks.py` and configuration.

**Interfaces:** `checkpoint_key(source_digest, version_id, model, options_digest, prompt_revision) -> str`; `load_chapter(key, index) -> BookChapterContent | None`; `save_chapter(key, index, chapter, evidence_ids) -> None`. Store checkpoints under the owned artifact version, separate from temporary publish directories, with atomic replacement and no public route.

- [ ] Write a fake-LLM test: first attempt completes outline and chapter 1, fails chapter 2; retry reuses outline/chapter 1 and calls only unfinished chapters. Assert source/model/options/prompt changes invalidate reuse and stale worker writes cannot replace a current checkpoint.

```python
assert calls_after_first_attempt == ["outline", "chapter-1", "chapter-2"]
assert calls_after_retry == ["chapter-2", "chapter-3", "chapter-4"]
assert published_book.chapters[0] == checkpointed_chapter
```

- [ ] Implement model-validated JSON checkpoints with retrieval evidence per chapter. Check lease/attempt/cancellation before each write. Do not publish an incomplete book as ready. Cleanup checkpoints when the owning version/course is deleted; retain them for recoverable attempts.
- [ ] Configure explicit connection/read/overall attempt deadlines, starting with 10-second connect and 180-second per-call read limits as proposed tuning values. Derive retry behavior from measured stage latency; do not simply increase the six-minute UI timeout or reduce content quality. Record timeout failures and distinguish schema retry from provider-capacity rescheduling. Keep content/OCR same-model retry at one.
- [ ] Handle generation soft time limits at the task boundary so the lease is released/rescheduled with checkpoints retained. Validate hard-kill redelivery cannot publish a partial artifact or re-use an incompatible checkpoint.
- [ ] Run checkpoint and worker redelivery tests with injected failures ($0). Checkpointing is useful independently of concurrency and should land first.

### Task 5: Add bounded chapter scheduling without starving other jobs

**Files:** Modify `generator.py`, `provider_guard.py`, `core/config.py`; create `tests/test_book_scheduling.py`.

**Interfaces:** Add `BOOK_CHAPTER_CONCURRENCY` with default 2 and allowed range 1–4. A chapter worker takes immutable outline/evidence/config, owns its DB session, and returns `(chapter_index, validated_chapter)`; the coordinator persists progress and orders results.

- [ ] Use a fake LLM barrier and concurrency counter to verify overlap, stable chapter order and the configured cap. Test two user jobs simultaneously so one large guide cannot monopolize all permits.

```python
assert maximum_active_chapters <= settings.BOOK_CHAPTER_CONCURRENCY
assert [c.chapter_title for c in result.chapters] == expected_outline_order
assert both_jobs_started_before_first_job_finished
```

- [ ] Implement a bounded executor with one chapter submission per available slot, independent sessions and chapter checkpoints. Respect shared generation permits across processes. Cancel unfinished submissions on lease loss; running provider calls remain accounted for and their results cannot publish without a valid claim.
- [ ] Separate temporary in-flight saturation from provider circuit failure. Current permit TTL is one hour and is unsuitable as a normal capacity wait estimate. Defer unsent chapters briefly with jitter and fair scheduling; capacity waiting must not spend all three execution attempts or regenerate prior chapters. Expired permit recovery still uses a lease and must not create concurrent overcommit.
- [ ] Measure sequential vs bounded scheduling with identical fake delays and outputs. Require unchanged output/schema/grounding and reduced critical-path time on the fixture; do not claim a real-world speedup until capped real-provider measurement. Tests cost $0.

### Task 6: Validate real concurrency and production migration

**Files:** Extend load mock and k6 scripts; update `docs/load-test-results.md`, README and production Compose only for measured tuning.

- [ ] Extend the mock provider with deterministic outline/chapter delays, usage fields, bounded schema failures, 429s and 120–180-second calls. Keep its production-start refusal and fake-key requirement. Test the adapter itself ($0).
- [ ] Add burst runs for 50 and 100 users submitting simultaneously, plus sustained arrivals while earlier jobs remain active. Measure enqueue p95, API read p95/p99, queue wait p50/p95/max, active calls, exact backlog high-water, attempt count, drain time, memory and worker restarts. Include short Quiz jobs arriving behind Books and a worker kill after a completed chapter.
- [ ] Run on disposable PostgreSQL/Redis/Chroma/Celery volumes, with ingestion/generation/video queues and the existing provider guard. No production key and no paid service. Gate: read p95 <500ms, enqueue p95 <2s, errors <1%, no duplicate publication, bounded backlog ≤200, zero unexplained lost jobs, and exact queue metrics reported. Report measured wait times even if they are poor; these API gates do not imply acceptable generation latency.
- [ ] Use measured arrivals and service times to set worker/provider budgets. Define a maximum acceptable queue wait for the chosen product tier, and reject additional work with a safe retry-later response when that capacity is exhausted. Do not promise a completion ETA from FIFO position alone; use measured service-time bands and mark estimates.
- [ ] Prepare a migration runbook from the current inline SQLite/embedded-Chroma deployment: backup uploads/artifacts/metadata, migrate course/job ownership and vector identity, validate record counts, disable inline writer before cutover, and document rollback. Never start two writers on the same local database/Chroma volume. Deployment is a separately reviewable action, not performed by this plan.
- [ ] After all offline gates, run one explicitly budgeted small real-provider smoke with usage instrumentation, then one representative long-document test only when its reservation fits. Each Book must obey the new $0.095 internal reservation/$0.10 ceiling including retries; the historical seven-job bill of $0.30240503 is not an allowance for a new Book. Use the balanced-budget plan's staged evaluation and separately declare aggregate test spend. Report estimated and actual cost for every run; do not silently raise the ceiling.

## Completion gate

- [ ] Run backend `ruff check` and relevant/full `pytest`, frontend `npm run lint`, `npm test`, `npm run build` after code changes; all offline/fake-provider tests cost $0.
- [ ] Browser-verify real persisted job state progressing through all four tabs and a reload/reconnect on disposable staging. Record stage timings and cost ledger.
- [ ] Document achieved versus unachieved latency/capacity targets. Commit/push/deployment remain outside this planning request.
