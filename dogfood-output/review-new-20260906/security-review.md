# Security and privacy review — 2026-09-06

Review of the current worktree, without product edits, production data access, provider calls, or paid generation. Evidence combines code inspection with isolated FastAPI TestClient requests against a fresh in-memory SQLite database and two synthetic users. This is separate from the main agent's customer browser evidence. Paths below are relative to the repository root.

## Confirmed observations and findings

| ID | Severity / classification | Evidence and actual result | Impact and improvement direction |
|---|---|---|---|
| SEC-01 | High; confirmed session revocation defect | `src/backend/app/routers/auth.py:182` resets only `hashed_password` at line 203. `src/backend/app/core/deps.py:47` checks blacklist and user activity but no password-change/session epoch. In-memory HTTP proof: successful `/api/auth/reset-password` returned **200**, then the pre-reset bearer token still returned **200** from `/api/auth/me`. | An already compromised session survives password recovery until token expiry (configured default seven days at `core/config.py:66`). Introduce server-side session revocation/versioning and invalidate existing sessions on password reset. |
| SEC-02 | Medium; confirmed logout defect and architecture limitation | `routers/auth.py:52` reads bearer/cookie but omits query tokens accepted by `core/deps.py:35`. Query-token logout returned **200** and the same bearer token subsequently returned **200**. Header-token logout returned **200**, then token returned **401**. Clearing only the isolated process cache made that same token return **200** again. `services/cache.py:9` and line 42 show process-local storage. | Supported authentication mechanisms disagree about logout; revocation cannot survive worker changes or restarts. Use the same token resolver and shared/durable revocation. The cache-clear check simulates process-state loss; this review did not restart a deployment or prove load-balancer routing behavior. |
| SEC-03 | Low; confirmed unauthenticated metadata disclosure | `src/backend/main.py:142` has no auth dependency and queries every Course ID at line 147. A fresh unauthenticated TestClient received **200** from `/api/health`, including the synthetic owner's private course ID. `src/frontend/next.config.ts:29` proxies `/api/*`. | Reveals global course identifiers and activity, including potentially deleted courses; ownership controls still prevent reading their contents. Return coarse health/readiness only; put inventory behind admin authentication. |
| SEC-04 | Medium; confirmed retention behavior / privacy concern | `routers/courses.py:126`–153 soft-deletes the course and purges filesystem/vectors but never removes `SourcePlanRecord`; `models/source_plan.py:27` stores derived source text as `plan_json`. In-memory proof: DELETE `/api/courses/review-course` returned **200**, course was soft-deleted, and **one source-plan row remained**. For this DB-only proof the filesystem/vector purge was replaced with a no-op; no real files were deleted. | Customer deletion retains document-derived text in the database. Decide and disclose retention, then implement complete deletion or explicit retention policy. Account deletion does explicitly delete owner source-plan rows at `routers/auth.py:321`. |

## Risks and missing defenses; no exploitation claimed

| ID | Severity / classification | Exact code evidence | Impact and improvement direction |
|---|---|---|---|
| SEC-05 | Medium; privacy / credential exposure risk | `src/frontend/src/lib/auth.ts:12`–16 stores the JWT in localStorage; `src/frontend/src/lib/api.ts:560`–562 adds it to download query strings; `core/config.py:66` sets seven-day default expiry. | Script access and URLs increase token exposure to XSS, copied links, access logs and browser history. No XSS or production log leak was demonstrated. Prefer authenticated cookie downloads or short-lived resource-scoped tickets, with a planned migration of the documented query-token contract. |
| SEC-06 | Medium; missing abuse defense | `routers/auth.py:209` login does bcrypt verification with no request/identity limiter; registration at line 65 sends mail. `main.py:42`–48 installs CORS, with no application request limiter found in routers/main. `services/otp_service.py:113` limits attempts per OTP and `:47` implements resend cooldown. | OTP protections are useful but do not bound repeated password guesses, registration/email volume, or expensive bcrypt requests. Add identity/IP throttles and deployment-edge body/request limits. External proxy controls were not verified; do not characterize this as a demonstrated production brute-force attack. |
| SEC-07 | Medium; resource-exhaustion risk | `routers/upload.py:93` reads each whole file before checking `len(content)`; file-count cap is five at line 24, size cap 50 MiB at line 59, admission occurs only at line 109. Validation is extension-based (`:84`). | A rejected oversized body can consume memory before the 50 MiB check; multiple permitted files are held together. No stress attack or malformed decompression bomb was submitted. Enforce transport/streaming limits and parser limits, and validate file signatures. Keep existing all-files-before-persistence behavior. |
| SEC-08 | Medium; incomplete erasure / best-effort cleanup | `services/document_processor.py:825`–835 uses `rmtree(ignore_errors=True)` and vector deletion; `services/vector_store.py:465`–476 catches deletion failures without propagating them. `services/embedding_cache.py:39`–41 stores course-scoped vectors under a hash; `vector_store.py:405` passes course ID as scope. No cache purge is called by course/account deletion. | Successful deletion can leave files/vectors after IO errors; embedding cache persists beyond deletion. Cached vectors are not plaintext source files, but remain derived data. Use retryable deletion jobs with verified completion and include cache scope cleanup. This review did not induce real storage failures. |
| SEC-09 | Medium; provider privacy policy gap | `services/llm.py:261` sends the formatted prompt, including source excerpts, as a user message; `:435` sends OCR image content. `services/vector_store.py:150` sends text to embedding provider. `services/book_model_policy.py:41` controls parameters/prices/routing but sets no data-collection or zero-retention policy; general LLM request at `llm.py:272` does not either. `services/video_render.py:180` sends narration through `edge_tts.Communicate`. | Source excerpts, OCR images and embeddings leave the backend; optional Video also involves external TTS beyond OpenRouter. Actual vendor/account retention settings were not inspected. Define disclosure, retention requirements and provider routing policy, then verify account and endpoint capabilities before making privacy guarantees. Keyword inspection of frontend source found no matching privacy/third-party explanation; a complete legal/privacy UI audit remains unverified. |
| SEC-10 | Low; information disclosure risk | Unauthenticated `/health`, `main.py:116`, returns raw exception text; lines 135–138 expose Chroma storage path/collection and error. | Internal diagnostics can reveal infrastructure details when the backend endpoint is reachable. No real failure/secret response was provoked. Return coarse public health and protect detailed diagnostics. |
| SEC-11 | Medium; prompt-injection defense inconsistency | `prompts/source_plan.txt:1`, `book_chapter.txt:28`, `slides.txt:14`, `quiz.txt:17`, `vid.txt:22` explicitly mark source instructions as untrusted. `prompts/course_title.txt:5` and `book_outline.txt:15` interpolate source without the same explicit rule. `services/llm.py:261` places both instructions and source in one user message. | Important defense exists, but not consistently across stages. No malicious document/provider trial was performed, so no injection vulnerability is confirmed. Standardize trust boundaries and add offline adversarial prompt/payload tests plus bounded live evaluation only if separately authorized. |

## Confirmed ownership strengths

The real dependency/router code was exercised with two synthetic active verified users and separate JWTs. One owned course and one owned queued job were inserted only into the in-memory database. Cross-owner requests all returned **404**, with the same missing-resource messages used for nonexistent resources:

- Twelve course reads: status, study-pack, book, slide, quiz, vid, book.pdf, slide.pdf, slide.pptx, quiz-key.pdf, vid.mp4, slide-images/1 under `/api/course/{id}`.
- Both source aliases: `/api/documents/{id}/sources` and `/documents/{id}/sources`.
- Job polling `/api/jobs/{id}`.
- All four generation requests, rejected before any generator/provider work: `/api/generate-book`, `-slide`, `-quiz`, `-vid`.
- Artifact-version PATCH and DELETE for the other user's course.

This is **21 cross-owner request checks**. It verifies denial before artifact retrieval; it does not prove successful reads of populated artifacts, every plural route alias, admin privileges, or races under production infrastructure. Core ownership guard: `routers/generation.py:160`–177; jobs: `routers/jobs.py:132`–140. Source chunks are filtered by course after ownership checks (`generation.py:832`–839). Public source results expose page/excerpt; chunk IDs require both `developer=true` and admin at line 857.

Other positive code evidence:

- JWT decoding explicitly restricts HS256, password hashing uses bcrypt, inactive accounts are rejected (`core/security.py:47`, `core/deps.py:63`). Cookie is HttpOnly/SameSite=Lax (`core/security.py:58`); Secure is deployment-configurable, default false for local HTTP. Production cookie configuration was not verified.
- Version paths reject directory components (`services/versioning.py:71`, `:140`); saved-upload retry ignores out-of-root symlinks (`services/document_processor.py:837`).
- Pending-job admission is bounded and transactionally serialized (`jobs/admission.py:102`); user/global defaults are 4/200 (`core/config.py:162`). These are concurrency limits, not per-user lifetime/daily spending limits.
- Account deletion retains anonymized accounting tombstones rather than raw ownership (`services/provider_usage.py:755`), and structured public errors avoid most provider details. The separate health endpoints are exceptions.

## Checks, failures and reproducibility

No source files were changed. No provider request was issued by this review. The TestClient process did not enter app lifespan, so did not seed an admin, reconcile production jobs, or start services. Tests used `DATABASE_URL=sqlite:///:memory:`, a synthetic JWT key, dummy OpenRouter key, `ENVIRONMENT=test`, and synthetic users; real environment secrets were never read or printed. The isolated script set `PYTEST_CURRENT_TEST` for the existing offline LLM behavior. The generation denial checks terminated in the ownership guard.

Existing regression selection attempted from `src/backend`:

```text
uv run --offline pytest tests/test_auth_and_core.py tests/test_course_and_upload.py tests/test_artifact_status_jobs.py tests/test_job_idempotency.py tests/test_job_admission.py tests/test_provider_health.py -q
```

- First attempt failed before collection: uv cache ACL access denied.
- Direct `.venv/Scripts/python.exe -m pytest` first used invalid `ENVIRONMENT=development`; corrected to the supported `test` value. This was a review-harness configuration error, not a product test failure.
- Corrected invocation collected **57 tests**, but all errored during pytest temporary-directory setup due to Windows `WinError 5` in the user Temp directory.
- A retry with a unique workspace `--basetemp=.../security-pytest-<uuid>` also failed with directory ACL errors, including pytest teardown. No assertion-level test result can be claimed from these runs.
- The in-memory TestClient proof commands subsequently exited **0** and produced the results above without pytest filesystem fixtures. First password-reset proof used a reserved `.test` email rejected by email validation (**422**); rerun with `example.com` produced successful reset **200** and pre-reset token **200**. Only the corrected run supports SEC-01.

To reproduce the core findings independently: create fresh in-memory SQLAlchemy tables; override `get_db` and `main.SessionLocal` with that same session factory; insert owner/other users plus an owned course/job; use TestClient without lifespan. Mint isolated JWTs, issue the routes listed above, create a password-reset OTP directly through `otp_service.create_otp`, submit reset, and check the old token. For logout query-path verification, clear client cookies before logout. For the course-retention check, replace only `get_document_processor().purge_course_storage` with a no-op and inspect `SourcePlanRecord` after real DELETE route execution. Never run this harness against a deployment database.

Remaining security verification: production proxy/log configuration, actual multi-worker revocation, successful populated artifact downloads, concurrent delete/generation races, provider account retention, real malicious-document evaluation, and dependency vulnerability inventory. No claim of complete penetration testing or regulatory compliance is made.

## Completed backend baseline after Windows ACL escalation

The authorized full backend suite was subsequently run outside the sandbox with direct `.venv/Scripts/python.exe`, resolving the earlier pytest ACL block. No source modifications were made. All provider credentials remained synthetic; SMTP was pointed at localhost. Test logs were sanitized for JWT/query-token patterns.

| Check | Exact command from `src/backend` | Result |
|---|---|---|
| Full backend regression | `.venv/Scripts/python.exe -m pytest tests -q --basetemp=D:/HackaGen-appearance-worktree/dogfood-output/review-new-20260906/security-pytest-full-e02a572d69fd4fa8a8c50508688f838d` with `ENVIRONMENT=test` | **631 passed, 12 failed, 5 skipped**, 3501 warnings, 105.91 seconds; exit 1. |
| Failure-only diagnostic rerun | `.venv/Scripts/python.exe -m pytest tests --lf -q --basetemp=D:/HackaGen-appearance-worktree/.st-d68bfd0b` with `ENVIRONMENT=local` | **7 passed, 5 failed**, 281 warnings, 4.34 seconds; exit 1. |
| Backend lint | `.venv/Scripts/python.exe -m ruff check .` | **Exit 0, no output** on escalated run. An earlier sandbox invocation had ACL scan warnings and is not the clean result. |

Effective settings were independently checked without printing secrets: `JOB_QUEUE_PROVIDER=inline`, `PROCESSING_EXECUTION_MODE=inline`, `INLINE_PROCESSING_RECOVERY_ENABLED=False`, pending job limits 4 per user / 200 global. The command also set `JOB_DISPATCHER=inline`, but that is not a Settings field; the independently verified `JOB_QUEUE_PROVIDER` value is the actual queue configuration. Database was `sqlite:///:memory:`; outputs were redirected to `test_security_outputs_tmp`; pytest's existing fixtures isolate uploads/vector storage.

Seven initial failures did not recur with the short temp path/default local environment: two Book checkpoint tests, four embedding-cache tests, and one default-environment assertion. Six filesystem/checkpoint failures are **Windows path-length sensitive**: the long-path run failed cache rename/open/cleanup and checkpoint resumption, while all six passed with the short root. These remain portability evidence, not six proven platform-independent product regressions. The environment assertion explicitly expects `local` and was caused by the initial test harness's `ENVIRONMENT=test` override.

Five failures remained in the diagnostic rerun:

1. `tests/test_generation_service.py::test_generation_api_endpoints_complete`: expected generation response 200 but received 429 `USER_JOB_LIMIT_EXCEEDED`. Fixture uploads arbitrary dummy bytes labeled PDF; extraction fails, no usable source exists, and failed generation attempts remain relevant to admission behavior. This is not a test of `book.pdf` quality.
2. `tests/test_generation_service.py::test_book_api_error_status_envelope`: expected generic Book failure text, received the specific no-indexed-source error. Fixture again is not a valid PDF.
3. `tests/test_queued_routes.py::test_generation_route_enqueues_one_validated_job_without_running_generator[/api/generate-book-options0-book-book-generation-worker_options0]`.
4. `tests/test_queued_routes.py::test_job_read_and_cancel_are_owner_scoped_and_safe`.
5. `tests/test_queued_routes.py::test_admission_rejection_does_not_reserve_artifact_or_create_job`.

The final three fail on `AttributeError: find_ready_book_version` in the generator mock, indicating test doubles have not kept up with the Book ready-cache lookup. Do not infer that cross-user reads succeeded: the independent 21-route ownership proof above passed. The baseline is **not clean**, and no tests were modified to mask failures. Full-suite logs also include an unhandled test-thread warning, so warning review should accompany fixture/test maintenance.

Saved evidence: `dogfood-output/review-new-20260906/backend-pytest-security-baseline.log`, `backend-pytest-shortpath-rerun.log`, and `backend-ruff-security-baseline.log`. These checks are offline regression evidence, not real customer UI verification.
