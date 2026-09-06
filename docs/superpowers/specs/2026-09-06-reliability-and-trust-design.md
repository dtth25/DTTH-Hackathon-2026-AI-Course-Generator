# HackaGen first reliability release — design

Date: 2026-09-06. Status: user approved the written spec on 2026-09-06 and requested detailed plans. This session is ONLY PLAN; this document does not authorize implementation or additional paid tests.

## 1. Outcome and evidence

Deliver a shared multi-student server, with working Windows/local development, on which a student can upload documents and obtain a trustworthy, connected Book, Slides, Quiz and narrated Video. Establish a successful reviewed reference before optimizing Book or Video cost/provider dependence.

Read `CLAUDE.md`, `README.md`, `report_new.md` and `progress_new.md`. The report distinguishes current observations from earlier runs. Current `AI_for_A0.pdf` has 174 physical pages and eight major chapters. Upload/indexing succeeded with extraction gaps. Book failed with `BOOK_BUDGET_LIMIT`; Slides and Quiz exhausted automatic retries. A separate network-disabled integration probe reproduced the source-plan transaction blocking provider-accounting writes on file SQLite. There are no new generated artifacts that can honestly serve as the current quality baseline. The older handbook report remains historical and must not be overwritten.

Source PDF SHA-256: `f7331c7f1c14f4812475d7650877d0aca0e573313542279fdeb508fe66d1ee27`. Local source path: `C:/Users/Dang Duc Luong/Downloads/AI_for_A0.pdf`. Do not commit the PDF or private extracted content. The saved evaluation rubric is `dogfood-output/review-new-20260906/ai-a0/evaluation-rubric.md`.

## 2. Decisions and release boundaries

The user approved reliability/trust before provider independence; shared-server plus local operation; estimates/configurable Book allowances; explicit repair or confirmed partial scope; verified no-training/zero-retention external processing; the student flow, runtime design, security migration, source-quality checks and four-artifact release gates.

The user supplied a **$0.30–$0.50 per-Guide range**. This spec selects **$0.50** as the default allowance and treats $0.30 as an optimization target only when coverage permits. This upper-endpoint selection is a concrete interpretation presented for approval here. Automatic retries, outline, first-use shared-plan construction, chapter generation and validation calls attributable to the guide share its allowance. Upload extraction, OCR, indexing and explicitly requested source repair are separate costs and must be displayed as such. A reused shared plan costs the consuming guide zero new provider calls; its original charge remains with its creator.

Working Video is required in the first release. The user is not prioritizing Video cost for the demo and approved **Azure real-time speech with prebuilt Vietnamese voices**, subject to verifying the privacy policy before use. There is no automatic fallback to the unofficial Edge service. A missing eligible speech service prevents Video spending and blocks release completion; a disabled Video feature is not a passing demo.

This design is organized into separately reviewable implementation plans:

1. Shared runtime and Book spending admission.
2. Source revisions, coverage and student recovery.
3. Sessions, private access, provider policy and Azure narration.
4. Integrated release verification and baseline capture.

All four are required for release. The first three produce independently testable changes; the fourth assembles the evidence. Source/runtime interfaces are specified below so executors cannot independently redesign their boundaries. Authentication/provider deployment gates must be complete before student documents are used in live validation.

Deferred: local/cheaper Book inference, model-routing optimization, local speech selection, cross-version Video scene caching, broader UI redesign, new chats, new artifact types, and a claim that a cheaper model preserves 90–95%+ quality. Later work receives its own spec and plan after the reference exists. First-release Video persists its script for recovery; it does not add a general cross-version media cache.

## 3. Global constraints

- Planning phase: do not modify product code, execute the implementation plan, commit or push.
- Future execution: preserve pre-existing work; never reset or bulk-stage the dirty worktree.
- Four generation endpoints remain `/api/generate-book`, `/api/generate-slide`, `/api/generate-quiz`, `/api/generate-vid`.
- No independent chat or fifth generation endpoint. Quote, source-health, repair and download-ticket endpoints are support operations.
- Backend-only AI. OpenRouter remains the content/OCR/embedding gateway. Azure real-time Speech is the explicit approved speech exception.
- Next.js 16.2.9 / React 19 / Tailwind 4, FastAPI, SQLAlchemy/Alembic, existing Chroma interfaces. Read installed Next.js documentation before changing its integration.
- SQLite/local inline execution and PostgreSQL 16 / Redis / Celery / private Chroma HTTP must both work.
- Poll processing resources every 3–5 seconds; stop at terminal states. Do not require a reload.
- Preserve three-version limits, readable completed versions, rename/delete controls and Expand/Collapse.
- Slides use the same rendered images in browser, PDF and PPTX.
- Public responses expose clean file labels, page/block locations and excerpts; never raw storage paths, chunk IDs, provider responses, prompts, secrets or debug traces.
- Reuse layout, elevation, motion and stage tokens from `CLAUDE.md`; the intentionally dark slide stage remains dark.
- Source documents, OCR, model output and generated code are untrusted data. Never execute embedded instructions or source/generated code during ordinary generation.
- Future task checkpoints update `progress_new.md`, run the task's relevant checks, and record actual outcomes. If the approved design is wrong, stop and report the mismatch instead of silently redesigning.

## 4. Student flow

1. Validate selected documents and show processing stages: validation, extraction, OCR when needed, indexing, ready/needs attention. Indeterminate stages show activity and stage text, not a fabricated percentage. OCR shows completed/selected pages when known.
2. Show source health by document and physical page (DOCX/TXT use stable block locations). Distinguish intentional blanks, readable pages, damaged text, skipped OCR and processing errors. Skipped OCR does not automatically mean no native text exists.
3. Offer repair for specific affected locations or exclusion of those locations from the requested scope. Show the changed topic coverage before confirmation. No unresolved page is silently treated as a fully trustworthy source.
4. Show Book scope, language, detail, estimated generation spend, remaining allowance and separately measured preprocessing/repair spend. Default UI language remains Vietnamese. Generation language is an explicit persisted `vi` or `en` field for Book/Slides/Quiz; narration remains Vietnamese in this release and rejects unsupported languages before spending.
5. A partial guide requires an unchecked-by-default confirmation naming its excluded locations/topics. The server binds confirmation to source revision, scope, generation settings, quote and policy. A source/settings change requires a fresh quote and confirmation.
6. Existing generation buttons submit the quote ID with the existing settings. Duplicate submissions reuse the same logical version/job; they cannot create duplicate spending records.
7. Progress reflects durable stage and retry state. Budget exhaustion offers revised scope or administrator-adjusted allowance, provider policy failure offers administrator setup, damaged source offers repair. Do not suggest an automatic retry for a permanent condition.
8. Completed outputs expose their scope and source revision. A partial label appears in the reader and exports. Older artifacts remain associated with their original source revision; repair does not rewrite their citations or content.

## 5. Source storage and scope contracts

Add immutable private `SourceRevision` records and per-location `SourcePageRecord` records. A revision stores owner/course, monotonically allocated revision number, original-file hashes, extraction-policy revision, manifest digest, state (`building`, `ready`, `failed`) and creation time. A page record stores an opaque document ID, clean display name, physical page or block location, extraction method, assessment reasons, private content reference and content digest. It does not expose a filesystem path.

`SourceLocation` has `document_id: str`, `page: int | None`, `block: str | None`; exactly one of page/block is present. Physical page numbers are one-based and validated against that document. Identity always includes document ID because different uploads each have page 1.

`SourceScope` has `source_revision_id: str`, `included_locations: list[SourceLocation]`, `excluded_locations: list[SourceLocation]`, `scope_digest: str`, `is_partial: bool`. The server calculates the digest from sorted normalized locations and the manifest digest; it never accepts a client-supplied digest as evidence of consent. Empty, unknown, duplicated or contradictory scope locations are rejected. Partial status is server-derived.

Each active course points at one ready revision. Initial extraction builds privately, writes revision-specific vectors/content, then atomically publishes the pointer after index verification. Repair creates a new candidate from unchanged old page records plus the selected repaired locations. Failure leaves the old active revision intact. In-flight artifacts retain their original scope binding; new quotes use the new active revision.

Generation jobs/artifact metadata persist `source_revision_id`, `scope_digest`, `source_plan_revision` and generation settings. Legacy artifacts remain readable with `legacy_unversioned` provenance and no invented coverage score. New generation from legacy courses requires a manifest rebuild from saved originals; if originals are absent, show re-upload recovery. Existing output content is not rewritten by migration.

Public support APIs:

- `GET /api/documents/{course_id}/source-health`: active revision, safe location assessments, repair availability, and separately recorded processing spend/unknown status.
- `POST /api/documents/{course_id}/repair`: `source_revision_id`, selected locations, `idempotency_key`; enqueues the existing preprocess job type with repair mode and returns 202 `{job_id, course_id}`. It rejects a stale base revision or conflicting active repair with 409. Local deterministic repair occurs first; external OCR obeys provider policy, accounting and explicit processing confirmation.
- `POST /api/courses/{course_id}/generation-quotes`: artifact, normalized settings and selected scope; returns a persisted, expiring preflight result. It never invokes paid inference. It can inspect provider capability metadata without document text.

The first two endpoints enforce course ownership and return 404 for another student's course. The quote endpoint follows the same rule. No raw manifest/content is sent to the browser.

## 6. Extraction and connected topic plan

Build a complete deterministic location inventory before selecting OCR work. Rank unreadable/damaged nonblank pages before weak-but-readable pages; use source order only as a tie-breaker. Keep the existing bounded OCR batch size of 12 per processing attempt, expose the remaining queue, and let the student request another selected batch. A detector-marked blank is labeled `blank_detected`; it is not silently declared intentional. A student may explicitly confirm blank exclusion in the scope UI.

Preserve paragraph/table/math blocks and add code blocks with language, exact text and source location. Keep whitespace/indentation. Never label reconstructed code as a verbatim source quotation. Incomplete source code is quoted as incomplete or replaced with a clearly labeled explanatory example grounded in the readable source. Runtime generation never executes it.

Derive topic boundaries from valid PDF outline/headings or DOCX headings. When headings are absent, use ordered bounded location groups and label them as page/block groups; do not pretend inferred groups are author chapter titles. Every included substantive location belongs to a group. No fixed global top-k overview retrieval may define full-document coverage.

Persist one canonical source plan per `(course, source revision, scope digest, plan policy revision)`, independent of the consuming artifact's model. The plan builder uses the pinned `google/gemini-2.5-flash` policy for evidenced objective/glossary/equation enrichment; deterministic inventory fixes the unit boundaries. Builder/model identity is stored as provenance but is not selected independently by each artifact. Changing the builder policy creates a new plan-policy revision.

Book, Slides, Quiz and Video consume that plan. Retrieve evidence per unit/objective and source location; retain the existing relevance filtering and noise removal. If the complete selected scope cannot fit the configured requests/allowance, fail with an actionable scope/capacity result instead of silently taking only the first units. Shared plan construction is charged to the job that actually claims/builds it; consumers reuse the result. A failed charged build remains in its creator's ledger.

The full Guide requires every selected major unit and required objective to have a substantive explanation and evidence mapping. Slides/Quiz/Video select units according to format limits and expose their selected coverage. For the eight-unit fixture, a 22-slide deck and 15-question broad quiz must represent all eight units. A short Video may select fewer and must state its scope.

## 7. Work claims and transactions

Retain durable job admission, worker leases, version reservation and accounting. Replace `get_or_create_source_plan`'s network-spanning course lock with a persisted `SourcePlanBuild` claim:

- Unique key: course/source revision/scope digest/plan-policy revision.
- Fields: state, allocated plan revision, lease owner, generation counter, lease expiry, result record ID and safe failure code.
- Acquire a claim in a short transaction: SQLite `BEGIN IMMEDIATE`, PostgreSQL row lock. Validate owner/course not deleted and bound source exists. Allocate the revision at claim creation; a takeover keeps that revision and increments the generation counter.
- Commit before retrieval/provider work. Renew every 15 seconds with a 60-second lease, without holding a connection across a network wait.
- Other callers receive `SOURCE_PLAN_BUSY` and use the existing durable capacity-wait continuation. A capacity wait does not consume a provider-failure retry.
- Publish only if claim owner, generation counter, unexpired lease, live job/version and source scope still match. Stale workers discard local content and cannot publish. Their dispatched calls must still reconcile real charges.
- An expired claim with a dispatched call of unknown charge cannot trigger blind duplicate inference. Hold/reconcile the call first. Local leases cannot guarantee provider-side exactly-once billing.
- Release/failure is conditional on the same fencing values. No long transaction spans provider calls, OCR, rendering or bcrypt.

Deletion cancels jobs and invalidates claims before asynchronous purge. A worker finishing after deletion cannot recreate the course's index or publish an artifact. File writes use version/revision-specific temporary directories and atomic rename after publication checks.

## 8. Spending admission and provider request policy

Money remains integer nanodollars in the ledger, with Decimal parsing at boundaries. Configuration `BOOK_DEFAULT_ALLOWANCE_USD=0.50` applies to newly quoted versions; existing budgets keep their snapshots. Administrator configuration can raise/lower the default without changing historical versions. Finite positive values are required. An ordinary student cannot grant themselves a higher allowance through the request body.

The $0.50 allowance is an **application admission limit for measured/estimated commitments, not a guaranteed provider invoice ceiling**. Current OpenRouter framing is not a proven token bound; this release must not relabel it as one. Replace the unconditional unobserved-framing dead end with an explicitly named `estimated-reservation-v1` policy, subject to the checks below. Preserve the old policy for already-started legacy versions; offer a newly quoted version when its old policy cannot run.

For text-only Gemini calls, count the final serialized request including schema with the existing pinned offline tokenizer; compute input reservation tokens as `ceil(max(native_typed_count, final_json_count) * 1.5) + 1024`. Reserve the explicit maximum output plus explicit reasoning allowance at the snapshotted price ceilings. This margin is a stated engineering estimate, not mathematical proof. Store estimator revision, counts and margin with the call. Multimodal OCR remains a separate preprocessing estimate and must not be passed through a text-only estimator.

The quote contains `quote_id`, owner/course, artifact, source/scope/settings digests, policy revisions, `estimate_usd` (Decimal string or null), `allowance_usd` (Book only), cost categories, capacity decision, partial flag and `expires_at` (10 minutes). A quote requiring an unavailable estimate is not generation-ready. Re-evaluate request capacity immediately before each dispatch.

Book preflight budgets for source-plan creation when uncached, outline, all chapters, validation and one bounded same-model repair reserve. Chapter minima continue to depend on detail level and evidenced objectives. Never make a request fit by deleting required objectives. If the whole proposed allocation exceeds the allowance, return `BOOK_SCOPE_EXCEEDS_ALLOWANCE` without paid calls and offer reduced scope or an administrator change. A later price/policy/source change invalidates the quote.

Generation atomically consumes a quote, reserves a version, snapshots its allowance/policy and creates its job. Quote reuse with the same idempotency key returns the original result; reuse with different settings is 409. Automatic and explicit retry of the same version retain its budget and successful chapter checkpoints. A distinct new variant requires a new quote and visible spending confirmation.

Before a provider call: check privacy/capabilities, current job ownership and remaining commitment capacity; atomically reserve; mark dispatched; release DB connection; send. Account the response before parsing. Unknown billing retains its reservation and blocks further guide dispatch. If actual charge exceeds its reservation, record all actual spend, flag an incident and stop further calls; never truncate the recorded bill to the allowance. Resolve billing through a durable administrator reconciliation command that records evidence and cannot mark unknown spend as zero without provider evidence.

Defaults preserve current content choices: Book `google/gemini-2.5-flash`, 512 reasoning tokens per ordinary Book call with the existing 1024 maximum; Slides/Quiz/Video script and OCR `google/gemini-2.5-pro`; embeddings `openai/text-embedding-3-small`. Shared-plan enrichment uses Flash. These are initial policies, not an assertion that Flash is the best reference. No free endpoints or automatic model switching. Same-model retry remains bounded; provider retries and job redelivery must not multiply an already exhausted call-level retry allowance.

OpenRouter unit-price filters are separate from the job allowance. Pin request capabilities and prices to the quote/policy; fail closed when no endpoint can satisfy them. Provider availability/rates must be rechecked at execution; a retired model requires reporting a spec mismatch, not silently substituting another model.

## 9. Privacy, Azure speech and Video recovery

One backend policy gateway covers title generation, source planning, OCR, embeddings, all artifact calls and speech. OpenRouter requests set `data_collection=deny`, `zdr=true`, `require_parameters=true`, plus the eligible endpoint allowlist and price/capability controls. Do not overwrite these controls when adding budget controls. No fallback can relax privacy or change the selected model.

Deployment verification records endpoint/service identity, relevant primary policy URLs, review date, no-training/no-content-retention decision, account logging settings and reviewer. Provider metadata is checked before calls (30-second cache); policy evidence expires after 30 days and requires operator renewal. An admin's boolean alone is not evidence. Missing, stale or conflicting evidence stops document processing with a safe setup error. Allowing in-memory request processing does not mean consent to persistent prompt caching; any provider cache interpretation must be disclosed consistently with its verified policy.

Speech adapter: `AzureRealtimeSpeech`, prebuilt `vi-VN-HoaiMyNeural` for female and `vi-VN-NamMinhNeural` for male. Use the Azure Speech SDK for real-time synthesis, word-boundary timing and `Audio24Khz48KBitRateMonoMp3`; no Long Audio/batch API, custom voice training, avatars or data-logging opt-in. Escape narration as text/SSML and never accept provider endpoints, arbitrary SSML or voice IDs from source material. Configure credentials and region server-side; allowlisted Azure regional endpoints only. Persist only private course/version audio and timing files.

Validate speech credentials/configuration, voice support, policy evidence and local ffmpeg/render prerequisites before generating a paid Video script. Do not assert a configured credential is valid without a service preflight. A release verification call uses authorized test narration and must produce audible speech; the existing pytest/loadtest silence substitute is not live evidence.

Persist the validated script before synthesis. Within the same Video version, store scene audio completion and timing atomically, keyed by script digest, voice, rate and speech-policy revision. Retry resumes completed scenes; changed text/voice invalidates the affected cache. Keep the existing local renderer and image/MP4 output contract. At most one automatic speech retry for a transient failure; authentication, policy and invalid-input failures do not retry. Track attempted characters and estimated speech cost separately from reconciled provider billing, with unknown cost explicitly represented.

Working Video is a release requirement, but neither the current three-feature testing consent nor this plan authorizes uploading text to Azure today. Future execution obtains/provisions the Azure resource and destination-specific live-test authorization before making the concrete paid validation call. No credentials belong in documentation, reports or browser storage.

## 10. Authentication and download migration

Add durable `AuthSession` records with opaque session ID, user ID, creation/expiry/revocation timestamps and user authentication epoch. JWTs carry `sub`, `sid`, `auth_epoch`, `iat`, `exp`, explicit issuer/audience and session purpose. Preserve the seven-day maximum session lifetime initially. Validate the active user, session and epoch on every protected request across all workers. Expired session cleanup is an operational job, not part of correctness.

Logout revokes the current session durably before clearing the cookie. Password reset increments the user's epoch in the same transaction as the password change, invalidating all sessions. Login performs bcrypt without holding a DB connection and then re-reads the user's password/epoch/active state before issuing a session, closing the reset/login race. Account disable/delete immediately invalidates access.

Browser code stops reading/writing bearer credentials in localStorage and uses the existing HttpOnly cookie with `credentials: include`. Remove old `agy_auth_token` values on startup. Bootstrap authentication from `/api/auth/me`, with loading/authenticated/unauthenticated states rather than treating localStorage as proof. Legacy JWTs without the required session claims require one sign-in after rollout. Retain Authorization bearer support for explicit API clients using the same durable session validation.

Shared deployment requires HTTPS and secure cookies. Local loopback development supports the existing separate frontend/backend ports. Cookie-authenticated unsafe requests require an allowed Origin and `X-AGY-Request: 1`; login/registration/reset also require that header and reject a supplied unapproved Origin. Configure exact CORS origins, credentials and permitted headers. Header-only clients without cookies may use bearer authentication; they do not bypass authentication or resource ownership.

Explicitly replace `CLAUDE.md`'s full-JWT download-query rule. `POST /api/courses/{course_id}/download-tickets` accepts an owned artifact, version and asset selector and returns a server-generated same-API URL containing a 120-second signed capability. Bind it to session ID, owner/course, exact artifact/version/asset, purpose and expiry. The download route revalidates the live session, current ownership, course/version existence, selector and safe storage root. A ticket is not valid for any other API, file, version or image index. If an authenticated cookie accompanies it, require the same user. Never concatenate an arbitrary client path.

Tickets are reusable within their brief expiry to support Range requests and slide loading; they are not general public share links. The Video reader obtains a fresh ticket on expiry without losing playback position. Keep actual MP4 Range behavior. Existing browser helpers change together with backend ticket support; full session tokens in query strings cease to authenticate all routes. Existing completed artifacts remain downloadable after signing in.

Set private/no-store responses for authenticated metadata/tickets/downloads, no-referrer on artifact views, and sanitize API/proxy access logs so credentials/query capabilities are never logged. Browser token removal alone is not an XSS defense: keep Markdown/HTML sanitization, block script/unsafe URL schemes, and escape generated text in renderers.

## 11. Upload, abuse and deletion controls

Preserve five files and 50 MiB per file. Read uploads in bounded chunks into task-specific spooled files; enforce byte limits while reading, validate all files before promoting any, and clean temporary files on every rejection. Total HTTP body limit is 256 MiB at proxy and application ingress. Validate type/signature: PDF header/parser, valid DOCX ZIP with required members, and supported nonbinary text. Reject encrypted/password-protected PDFs with actionable copy.

Parser limits: PDF at most 1,000 pages and 25 million raster pixels per rendered page; DOCX at most 10,000 ZIP entries, 200 MiB expanded bytes and 100:1 expansion ratio. Run untrusted extraction in a bounded subprocess (60 seconds native parse per file, 512 MiB on the Linux shared server), with provider OCR outside the parser sandbox and separately bounded. Local Windows uses a terminating subprocess deadline and the same structural/byte limits; do not claim an unimplemented OS memory cap. Reject unsafe external document relationships and never fetch embedded remote URLs.

Distributed auth limits use Redis in shared deployment and the same single-process semantics locally. Defaults: login 10 attempts per IP per 10 minutes and 5 per normalized-account hash per 10 minutes; registration/reset/verification email 5 per IP and 3 per account hash per hour, in addition to existing OTP limits. Return generic public errors and Retry-After; do not expose account existence through new diagnostics. Trust forwarded IP headers only from explicitly configured proxies. On shared limiter outage fail closed with 503; generation retains its existing durable owner/global admission and provider capacity limits.

Public health endpoints return only coarse status; detailed dependency diagnostics require administrator authentication and exclude course IDs, paths and raw exception text. Provider logs contain opaque job/call IDs, stage, timings and sanitized codes, not document excerpts or secrets.

Deletion immediately tombstones the course, invalidates sessions if deleting an account, cancels active work and enqueues a durable purge record in the same transaction. Purge removes originals, all source revisions, vectors, source plans/builds, embedding caches, partial output/checkpoints, speech files and finished artifacts. Cache ownership must be course/revision scoped; do not retain a hidden global content cache. Idempotent retries handle unavailable files/vector services, and stale workers cannot republish.

Purge target: complete within 24 hours; show pending/failed cleanup to administrators and retry with bounded backoff. Retain only content-free accounting/security records for 30 days after deletion, with document/user identifiers removed or irreversibly detached when account deletion completes. Backup retention is at most 30 days; a restored backup must replay deletion tombstones before serving traffic. These are proposed operational defaults included for written-spec approval, not a claim about the current deployment.

## 12. Output checks and release evidence

Automated validation checks schema, evidence membership, selected-unit/objective coverage, nonempty substantive fields, balanced/parseable math, complete code fences, unique question IDs/options, exactly one correct choice, coherent answer-key mapping and successful rendering. Similarity/keyword presence is not factual entailment. Factual faithfulness remains `not_evaluated` unless a separately documented factual review ran; never convert structural scores into a factual percentage.

Generation language reaches every chapter/format prompt and output metadata. Equation/code handling is shared between browser and exports. Reject truncated required content and repair only the failed unit within remaining allowance. Invalid quiz questions cannot be marked ready just because a schema parser accepted them. Document-origin errors and illustrative reconstructions remain labeled.

Release evidence is a manifest binding commit/worktree fingerprint, source hash, settings, source/scope/plan revisions, saved model/provider policy, artifact checksums, job IDs, measured/estimated/unknown costs, test commands and reviewer findings. No secret or private source text is committed. Changes after an evidence run invalidate affected checks.

Required automated cases:

- Real source-plan builder path with real ledger writes and fake network on file SQLite; concurrent PostgreSQL claims; stale worker publish denial; crash/lease recovery and deletion race.
- Atomic duplicate quote/enqueue, stale scope/quote rejection, $0.50 new-budget snapshot, legacy budget preservation, parallel reservations, retry reuse, unknown-charge hold and actual over-reservation incident.
- Multi-document same-page-number scope, damaged pages beyond first 12, selected repair, failed repair preserving old revision, complete topic inventory and no false complete-coverage label.
- Cross-worker/restart logout and reset, login/reset race, cross-user API/ticket probes, expired/tampered/cross-version capabilities, CSRF and allowed local cookie flows.
- Streaming oversize/signature/ZIP/parser-limit rejection, limiter outage, redacted health/logs, provider-policy failure before document transfer, prompt-injection and XSS fixtures, delete/purge/restart/recovery.
- Azure adapter timing and error mapping with injected fakes, no accidental Edge fallback, script/scene recovery, and a separate authorized audible live Video test.

Required visible student checks: upload and source warnings; targeted repair or confirmed partial scope; Book quote/confirmation and complete guide; all chapter/PDF inspection; every slide and image/PDF/PPTX count/layout; every quiz stem/options/answer/explanation plus correct/incorrect interactions and key PDF; Video beginning/middle/end audio, synchronization, readable frames, seeking and download; tab switches, old-version access, retry UI and no reload requirement.

For AI_for_A0, check all eight major chapters against the saved rubric, including precision/recall/F1, ReLU, attention scaling, clustering and CLIP. Compare formulas/code with the rendered PDF where extraction is damaged. A passing full guide has substantive coverage of all eight selected major units and no known material factual/grounding error. A partial guide can pass only its explicitly approved narrower scope and cannot be used as a full-source reference.

Reference selection: review every successful candidate from the same source, scope and detail profile; record factual accuracy, grounding, fidelity, coverage, clarity, depth, usefulness, repetition and readability separately. Select the strongest reviewed candidate among those actually tested and label the candidate set. Do not claim global best-model quality. If later cost work needs Pro/Flash comparison, obtain a separate bounded evaluation authorization; no such extra call is part of this planning session.

Later optimization target remains the user's 90–95%+ overall range, with factual correctness, grounding, fidelity and major coverage very close to baseline. It is not a first-release numerical pass score. No fabricated percentage may replace a missing successful reference.

Run applicable targeted tests at each future checkpoint, then required frontend lint/build/tests, backend Ruff/pytest, browser verification and shared-runtime integration. Existing historical failures must be diagnosed and resolved or explicitly reported as release blockers; do not hide them by changing test discovery. Mocks and silence audio are not a substitute for live artifact evidence.

Final future gate uses `superpowers:requesting-code-review` with a security-focused brief covering auth, IDOR/cross-user access, DB/storage ownership, signed links, secrets/logs, external leakage, prompt injection, XSS, CSRF/SSRF, uploads, rate/expensive-generation abuse and deletion/retention. Follow with `superpowers:verification-before-completion`. A failed required gate means the release is incomplete.

## 13. Primary references and verification limits

- [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting): response usage/cost supports reconciliation; shared account counters alone do not attribute a job.
- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection): privacy, capability and unit-price controls are request routing requirements, not a guaranteed whole-job invoice ceiling.
- [OpenRouter ZDR](https://openrouter.ai/docs/guides/features/zdr) and [embedding API](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings): verify current endpoint eligibility and embedding routing controls during implementation.
- [Azure speech privacy](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/speech-service/text-to-speech/data-privacy-security?view=foundry-classic): real-time prebuilt synthesis retention differs from batch/custom services. This page is evidence for retention; do not generalize unrelated custom-training language into proof of every no-training obligation.
- [Azure speech language support](https://learn.microsoft.com/en-us/azure/ai-services/Speech-Service/language-support) and [speech synthesis](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis): supported Vietnamese voices and word-boundary integration.

Documentation was researched on 2026-09-06; account-specific policy, credentials, endpoint capability and live speech remain future verification gates. This spec does not claim they have already passed.

## 14. Approval and plan handoff

The user reviews this written spec before Writing Plans. Approval includes the concrete defaults introduced here: $0.50 estimated-commitment admission allowance, 120-second download capabilities, session migration requiring sign-in, bounded upload/parser limits, and deletion/backup retention targets. Changes requested during review are incorporated before plans are written.

After explicit approval, create four detailed plans matching section 2. Each task must name exact files, interfaces/types, implementation and test code, commands with expected results, browser checks, acceptance criteria and a commit suggestion. Preserve the user's no-commit rule unless explicitly authorized at execution. End after delivering the report/progress/spec/plan paths. Do not execute the plans in this session.

Written plan set (planning artifacts only):

- `docs/superpowers/plans/2026-09-06-01-runtime-and-spending.md` — R1–R6.
- `docs/superpowers/plans/2026-09-06-02-source-and-student-flow.md` — S1–S7.
- `docs/superpowers/plans/2026-09-06-03-security-and-speech.md` — P1–P8.
- `docs/superpowers/plans/2026-09-06-04-release-verification.md` — V1–V6.
