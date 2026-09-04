# 100-user load gate

This file records the release evidence for the deterministic `loadtest` deployment. The 100-user scenarios used the repository's loadtest-only OpenRouter adapter, never a production key.

## Gate configuration

- Read path: 100 constant VUs for 10 minutes; failure rate `<1%`, p95 `<500 ms`, zero dropped iterations.
- Mixed jobs: 20 upload/artifact flows per minute for 10 minutes; enqueue p95 `<2 s`, failure rate `<1%`, zero dropped iterations, no duplicate job IDs, backlog `<200`.
- Failure recovery: 20 ingestion jobs for each deterministic `key-limit`, `rate-limit`, and `unavailable` mode; bounded provider calls, manual recovery, zero worker crashes.
- Topology: PostgreSQL 16, Redis 7, Chroma 1.5.9, two API processes, ingestion `c=2`, generation `c=4`, video `c=1`.
- Seed identities use `loadtest-###@example.com` in the disposable database because the application's strict `EmailStr` validator correctly rejects the reserved `example.invalid` domain.

## Measured run

Run date: 2026-09-04. Host: Intel 13th Gen Core i7-13620H, 10 physical / 16 logical cores, 15.63 GiB RAM (2.86 GiB available immediately before the read run).

Status: **PASS** for all deterministic capacity and recovery gates.

| Measurement | Result |
| --- | --- |
| Read traffic | 100 VUs for 10m; 115,657 requests; 115,557 iterations |
| Read latency / errors / dropped | p95 `33.33 ms`; p99 `53.60 ms`; max `1.905 s`; errors `0%`; dropped `0` |
| Mixed traffic | 200 scheduled flows over 10m; 1,709 requests; 1,406/1,406 checks passed |
| Mixed overall latency | p95 `208.32 ms`; p99 `243.55 ms`; errors `0%`; dropped `0` |
| Mixed enqueue latency | p95 `56.49 ms`; p99 `77.13 ms` |
| Mixed flow duration | p95 `4.67 s`; p99 `4.72 s`; max `5.69 s` |
| Maximum observed active-flow bound | `<=2` concurrent flows; every periodic global-backlog check was `<200`; direct final active-job count was `0` |
| Queue drain after final arrival | `2.5 s` |
| Container restarts | `0` in read, mixed, and all recovery runs |

The harness did not emit an exact backlog high-water counter. Because each mixed flow owns at most one active job and k6 reported a maximum of two concurrent VUs, the observed active-job upper bound was two. This is an upper bound, not an exact counter reading.

### Peak container resources

Read-path peaks were sampled 146 times across 615 seconds (approximately every four seconds):

| Container | Peak memory | Peak CPU |
| --- | ---: | ---: |
| Backend | 595.3 MiB | 121.05% |
| Ingestion worker | 515.0 MiB | — |
| Generation worker | 508.0 MiB | — |
| Video worker | 311.8 MiB | — |
| Frontend | 73.32 MiB | — |
| PostgreSQL | 89.33 MiB | — |
| Redis | 11.30 MiB | — |
| Chroma | 27.86 MiB | — |
| Mock OpenRouter | 26.26 MiB | — |

Mixed-job peak memory was: video worker `1,441.8 MiB` at `421.24%` peak CPU, generation worker `684.4 MiB`, backend `593.2 MiB`, ingestion worker `516 MiB`, frontend `73.09 MiB`, PostgreSQL `98.74 MiB`, Redis `9.97 MiB`, Chroma `29.43 MiB`, and mock OpenRouter `29.72 MiB`. Video remains isolated at worker concurrency one, so its rendering burst did not block ingestion or generation.

### Provider fault recovery

| Fault | Recovered jobs | Checks | HTTP errors | p95 / p99 | Restarts |
| --- | ---: | ---: | ---: | ---: | ---: |
| `key-limit` | 20/20 | 44/44 | 0% | 203.79 / 225.43 ms | 0 |
| `rate-limit` | 20/20 | 44/44 | 0% | 199.22 / 211.10 ms | 0 |
| `unavailable` | 20/20 | 44/44 | 0% | 199.22 / 216.79 ms | 0 |

The final clean reruns verify cross-process circuit reset, bounded scheduled retries, durable saved-document retry dispatch, terminal course/job synchronization, and worker survival. Earlier diagnostic runs exposed and led to fixes for stale per-process provider-health cache, exhausted-job course state, and an inline saved-document retry path; they are not used as passing evidence.

## Capped real-provider smoke

Run date: 2026-09-05 local time. Official OpenRouter endpoint, production-like PostgreSQL/Redis/Chroma/Celery topology, five simultaneous small TXT ingestions, one Book, and one Quiz.

Functional status: **PASS**.

- Jobs: `7/7 succeeded`.
- HTTP provider failures: zero `401`, `402`, `403`, or `429` observed.
- Internal grounding: Book and Quiz references were non-empty and every reference belonged to the uploaded course; no prompt, source text, token, key, or raw provider response was recorded.
- Container restarts: `0` across all eight services.
- Remaining provider capacity after the run: positive.

Cost status: **FAIL for the original USD 0.25 ceiling**. The key had `USD 0.00004637` cumulative usage before this run and `USD 0.30245140` after it, so the measured seven-job delta was `USD 0.30240503`. The initial harness stopped at a post-run path-validation defect before printing the delta; the defect was corrected from `OUTPUT_DIR` to the actual artifact root `UPLOAD_DIR`, and the existing Book/Quiz artifacts then passed validation. The paid workload was not repeated merely to recreate a summary line.

For the current Gemini 2.5 Pro Book pipeline, operators must predeclare at least a `USD 0.35` seven-job smoke allowance or select a separately approved cheaper staging model. A release that requires the original `USD 0.25` ceiling remains blocked; deterministic 100-user capacity evidence is unaffected.
