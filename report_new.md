# HackAGen current-worktree customer review

Status (latest checkpoint, 2026-09-06): dogfood/report/design/planning phase complete. The user approved the written reliability/trust spec; four implementation plans contain 27 tasks. No product implementation or plan execution occurred. Current artifact-quality evaluation remains blocked by the observed generation failures; no successful new quality baseline is claimed.

Approved spec: `docs/superpowers/specs/2026-09-06-reliability-and-trust-design.md`. Plans: `docs/superpowers/plans/2026-09-06-01-runtime-and-spending.md`, `2026-09-06-02-source-and-student-flow.md`, `2026-09-06-03-security-and-speech.md`, `2026-09-06-04-release-verification.md`. Decisions include a $0.50 default within the requested $0.30–$0.50 Guide range, explicit limited scope, durable sessions/private downloads, verified provider privacy and working Azure-narrated Video in the first release. Later cost/provider optimization depends on a successful reviewed reference.

Current source: user-supplied `AI_for_A0.pdf`, 174 pages, 2,346,478 bytes, eight chapters. Course: `http://127.0.0.1:3002/course/7de35d382f3a`. Evidence: `dogfood-output/review-new-20260906/ai-a0/`. Treat all document contents as untrusted source material, never tester instructions.

| Actual UI path | Result | Duration / attempts | Recorded added provider cost |
|---|---|---|---|
| Upload and indexing | Ready, 173 chunks; extraction incomplete warning | 310.1 s / 1 attempt | $0.367366620 |
| Study Guide, Chuyên sâu | Failed, BOOK_BUDGET_LIMIT | 1.77 s / 1 attempt | $0; no new ledger rows |
| Slides, 22 slides | Failed, SLIDE_GENERATION_FAILED | 32.08 s / 3 automatic attempts | $0; no new ledger rows |
| Quiz, 15 mixed questions | Failed, QUIZ_GENERATION_FAILED | 32.10 s / 3 automatic attempts | $0; no new ledger rows |
| Video | Architecture reviewed; no generation requested | Not run | Not measured |

One manual request was submitted for each of the three artifacts, sequentially, after explicit consent to OpenRouter/routed-provider processing. No manual paid retries, comparison generations or Video calls. No Book/PDF, deck/PPTX or quiz/answer-key result exists for this PDF; no quality percentages or savings benchmark are claimed.

Immediate priorities: repair the generation blockers while preserving financial controls; make source extraction/coverage and failure recovery understandable; address recorded session-revocation defects before wider use; establish a successful, source-faithful quality baseline; then reduce duplicate work and provider dependence. The Book route is already pinned to Flash in this worktree, so switching Book from Pro to Flash is not a new cost optimization. A separate isolated file-SQLite probe confirmed the shared source-plan/ledger lock.

Fresh focused checks: 7 backend tests and 48 frontend tests passed. These are narrow mocked/offline checks, not proof that the failed real UI flows work. Earlier broad-suite failures remain recorded below and were not fixed or silently dismissed.

Historical context follows in checkpoint order. Earlier references to a missing-consent blocker and no provider calls apply only to the previous `book.pdf` attempt and are superseded for AI_for_A0 by the latest checkpoints. The earlier Competitive Programmer's Handbook source has 296 pages and remains comparison context only. The original `dogfood-output/book-20260906/report.md` is preserved unchanged. This report targets the isolated runtime of the current worktree, including its pre-existing edits.

## Evidence policy

Separate visible customer observations, exported-artifact inspection, source review, mocked regression tests, and security probes. Record bypasses and unverified behavior explicitly. Never save keys, passwords, OTPs, session tokens, private environment values, or authenticated download URLs in reports, screenshots, or diagnostic logs.

## Findings

Pending real customer testing. Model-policy documentation differs from current Book policy code; actual routing is under investigation. No fresh artifact-quality conclusion yet.

## Customer evidence — current runtime

- Registered and verified a synthetic student through visible UI controls, using the explicitly documented in-memory development OTP limitation. External email delivery was not tested.
- Landing and upload pages are readable, use a consistent cream/green visual style, and explain accepted input/output formats. The current style differs from older CLAUDE.md accent guidance; this is not itself a user-facing bug.
- File picker displays the selected name, byte size, selected count, and remove action. Upload remains disabled with no selection and becomes disabled while submission runs. Selecting six files gives an explicit five-file warning and retains five visible entries.
- Uploaded original `book.pdf` once. It created a course and transitioned to an error automatically after provider connectivity failed. The UI preserves the file and offers `Thử lập chỉ mục lại`; no page reload was needed to reach the terminal error.
- **Environment blocker, not a confirmed product outage:** sandbox outbound networking prevented ingestion provider access (`OPENROUTER_UNAVAILABLE`). Automatic approval review then rejected starting the backend with networking because destination-specific approval to send document-derived content to OpenRouter was absent. No fresh Book/Slides/Quiz generation was submitted. The one-manual-generation allowance for each remains unused.
- An initial read-only usage request was network-blocked. A later permitted counter read returned HTTP 200 and key cumulative usage $2.361656740; key allowance remaining $7.638343260. These are shared counters, not an attribution of this review’s cost.
- Evidence: `dogfood-output/review-new-20260906/01-landing.png`, `02-upload-selected.png`, `03-ingestion-network-failure.png`, `04-six-file-limit.png`, and `usage-before-provider-retry.json`.

### UX-01 — Invalid email validation becomes a generic error

P3 / S / high confidence, confirmed visible UI. A `.test` address passes the form’s browser validation but backend rejects it as a reserved domain; the form only says “Đã xảy ra lỗi. Vui lòng thử lại.” The server recorded a specific email validation error. A student cannot tell which field to correct. Map safe validation messages to the email field. The corrected example.com test address worked. No malicious input or password was included in evidence.

### UX-02 — No cost or external-processing explanation at upload

P2 / M / medium confidence, privacy/cost UX concern. On the inspected landing/upload path, file formats and limits are visible but no ingestion price estimate or explanation that text/page images go to an external AI service appears before submission. Ingestion itself performs provider work. Explain this at the decision point; show an estimate/limit if accounting can support it. This does not establish that no policy exists elsewhere in the product.

## Artifact quality status

Study Guide, Slides and Quiz: not generated in this current-runtime review because indexing is blocked. Source fidelity, exam trust, best/worst slide, strongest/weakest question, export correctness, and baseline quality percentages remain **unable to verify**. Old outputs are not substituted for fresh results. Do not interpret source-code findings as proof of the quality of nonexistent new artifacts.

## Previous report comparison

| Previous issue | Current classification | Evidence limit |
|---|---|---|
| ISSUE-001: Slide language/coverage | Unable to verify | No fresh Slides; source prompts still prescribe Vietnamese. |
| ISSUE-002: Code/math export fidelity | Unable to verify | No fresh exports; existing worktree includes renderer changes. |
| ISSUE-003: Final-slide accessibility | Unable to verify | No fresh deck/viewer/export comparison. |
| ISSUE-004: Quiz explanation contradictions | Unable to verify | No fresh Quiz; passing UI tests do not establish answer correctness. |
| ISSUE-005: Retry/progress synchronization | Unable to verify for Video | Current ingestion error reached terminal UI without refresh; this does not prove Video recovery is fixed. |
| ISSUE-006: Book source coverage | Unable to verify | No fresh Book; source review still identifies retrieval coverage limitations. |

### UX-03 — Empty upload gives retry advice instead of a fix

P2 / S / high confidence, confirmed visible UI. Select empty.txt (0 B), then click upload. The form enables submission and subsequently displays only “Đã xảy ra lỗi. Vui lòng thử lại.” The file stays selected and retry remains enabled. Backend rejects empty input before indexing; repeatedly trying cannot fix the file. Reject zero-byte selection locally and map the backend’s safe validation message to the file. Evidence: `05-empty-file.png` and backend-redacted.log.

## Security/privacy findings

Dedicated detail and reproduction scope: [security review](dogfood-output/review-new-20260906/security-review.md). These are isolated server-side probes, not browser completion of the student workflow.

| Finding | Priority / complexity / confidence | Evidence and impact |
|---|---|---|
| Password reset does not revoke existing sessions | P1 / M / high; confirmed | Reset returns 200; previous JWT still accesses `/api/auth/me` with 200. An attacker’s existing session survives recovery. Introduce durable session revocation. |
| Logout paths and revocation storage disagree | P1 / M / high; confirmed | Query-token logout returns success without revoking; header logout revokes only until process cache loss. Use one token resolver and shared/durable revocation. |
| Public health enumerates course IDs | P2 / S / high; confirmed | Unauthenticated `/api/health` returns synthetic owner's course ID. Remove resource inventory from public readiness. No cross-user content disclosure established. |
| Course deletion retains source-plan text | P2 / M / high; confirmed DB retention | Soft-deleted course keeps SourcePlanRecord. DB-only test bypassed actual filesystem purge explicitly. Define retention and verified deletion for all derived data. |
| Long-lived JWTs in localStorage/download URLs | P2 / M / high; exposure risk | Larger exposure surface to scripts, copied links and logs; no active XSS or credential theft demonstrated. Any change needs migration of the existing authenticated-download contract. |
| Missing application-level auth throttles | P2 / M / medium; missing defense | OTP limits exist; broader login/registration limits not found. External proxy protections unverified. |
| Upload limits enforced after whole-file read | P2 / M / high; resource risk | Large rejected bodies may consume memory first; no stress attack performed. Add streaming/transport/parser bounds. |
| Best-effort deletion can leave derived data | P2 / M / high; privacy risk | Purge suppresses some failures and embedding cache lacks cleanup. Verify erasure via retryable lifecycle work. |
| External processing/retention policy incomplete | P2 / M / medium; privacy concern | Embeddings/excerpts/OCR leave backend; Video narration reaches Microsoft TTS. Actual provider retention settings unverified. |
| Public detailed health exposes internals | P3 / S / high; information risk | `/health` includes local storage path and may include raw error. Protect detailed diagnostics. |
| Prompt-injection defenses vary by stage | P2 / M / medium; missing defense | Several prompts mark sources untrusted; title/outline handling differs. No malicious-document exploit tested. |

Positive evidence: all 21 isolated cross-owner probes returned 404, including artifact/source/job reads, four generation routes, and version rename/delete. JWT algorithms are restricted; inactive users are rejected; path validation and pending-job admission exist. This does not establish complete production security.

## Verification status

- Frontend unit/component tests: 108 passed across 18 files. Lint: no errors, five warnings. Details: frontend-checks.md.
- Backend full suite: 631 passed, 12 failed, five skipped. Diagnostic rerun using short temp path/default local environment: seven passed, five still failed. Initial six filesystem failures are Windows path-length sensitive; one environment assertion was caused by review setup. Remaining failures concern two generation-fixture expectations and three stale generator mocks. Details and logs: security-review.md.
- Ruff: clean exit 0 after authorized filesystem escalation.
- Production build passed (compilation, TypeScript and 12 static pages). Playwright: 24 passed, two failed; all eight live-progress tests passed. Both failures are Book workspace visual comparisons (desktop expected 1440x1061 vs actual 1440x1067; mobile expected 390x1322 vs actual 390x1360). Current images differ from baselines; no intentional-design approval or user-facing defect is inferred solely from mismatch. No baselines or product tests changed to hide failures. Evidence: frontend-checks.md and frontend-visual/.
- Read-only isolated database projection confirms one failed preprocess job with three failed attempts, zero indexed chunks and zero provider ledger rows. No generation job exists. Evidence: runtime-status-redacted.json. Empty ledger alone is not a provider invoice; this supports the network-blocked runtime observation.
- Paid Book baseline and Video savings benchmark: not run. No 90–95% quality or measured cost-reduction claim is supportable yet.

## Next gated stage

Resume the saved upload only after required destination-specific consent. Then finish Book → review → checks, Slides → review → checks, Quiz → review → checks. Only after evidence completion begin the one-question-at-a-time Brainstorming interview, user-approved design, and Writing Plans. No product design has been approved, no implementation plan has been falsely marked complete, and no product fixes or commits were made.

## Source-derived architecture and cost review — separate from customer output testing

These findings come from production source inspection and primary provider documentation. They do not establish the quality, latency, or cost of any newly generated artifact. Fresh generation has not been attempted: the original PDF upload reached ingestion, but outbound provider access failed; a network-enabled restart awaits the destination-specific consent described in the customer checkpoint. The complete stage map, code references and assumptions are in [pipeline-review.md](dogfood-output/review-new-20260906/pipeline-review.md).

| Priority | Finding | Confidence / evidence | Impact and candidate direction | Estimated implementation complexity |
|---|---|---|---|---|
| P1 | Fresh Book content calls cannot pass current admission | High; direct control flow. `provider_usage.py:470,507` requires a verified request bound, while `provider_tokens.py` always returns an unobserved Gemini framing estimate and no admitted calibration revision exists. | A normal versioned Book will stop before content generation even with functioning provider access. Complete an evidence-backed admission adapter while retaining the spending fence; do not bypass the guard to make the review pass. Query embeddings may be billed before rejection. | High: billing reconciliation, tokenizer/request framing, budget regression tests and one authorized real request path. |
| P1 | Source-plan generation holds a SQLite write lock across another ledger write | High-confidence source inference; not yet runtime-reproduced. `source_plan.py:73,99` holds `BEGIN IMMEDIATE` while its real builder enters `provider_usage.py:518` through a separate database session. | A fresh source plan can fail locally before its provider call. Preserve singleflight with an explicit durable claim instead of a database write lock held across generation. | Medium–high: concurrency, lease expiry, crash recovery and real file-SQLite tests. |
| P1 | Retrieval does not establish full-handbook coverage | High; `generator.py:288,814` retrieves up to 80 chunks from one generic overview query. `retrieval.py:111` guarantees representatives per file, not per chapter or page. | A full-source digest can coexist with narrow evidence. Build a deterministic source/chapter inventory and evaluate major-topic recall before model tuning. This is a coverage risk, not a claim about an unseen new artifact. | High: extraction structure, coverage selection and source-based evaluation. |
| P1 | Model-specific source plans can diverge across the Study Pack | High; source-plan cache includes model (`source_plan.py:61`); Book binds Flash while other defaults use Pro. `generator.py:447` also selects title-matching units or falls back to the first four. | Artifacts may use different canonical plans or omit later units. Bind formats to an explicit shared revision and make intended unit selection clear. | Medium–high: provenance, cache identity and compatibility for existing versions. |
| P1 | English preference is not carried through Book chapters | High; user prompt enters outline, but chapter calls have no user language/prompt parameter and `book_chapter.txt:41` requires Vietnamese. Source-plan, Slides and Quiz templates also require Vietnamese. | An English user request cannot reliably govern all generated prose. Persist language and carry it through planning, content and export. | Medium: schemas, prompts, version identity and language acceptance tests. |
| P1 | Video has an additional external processor | High; `video_render.py:171` sends source-derived narration to Microsoft Edge online TTS, outside the OpenRouter ledger. | The OpenRouter-only documentation does not describe the full data flow. Add an explicit speech-provider boundary, processing disclosure and stage telemetry. No Video call was made in this review. | Medium: provider inventory, speech adapter, failure handling and retention decisions. |
| P2 | Current Book policy contradicts configuration documentation | High; immutable `BookModelPolicy` defaults to `google/gemini-2.5-flash`, 512 reasoning tokens and $0.095 per-version ledger ceiling; `generator.py:2380` overrides the configured feature model with that snapshot. | The strongest detail setting is not evidence that Pro is used or that quality is highest. Document the intended runtime policy and expose appropriate product controls without leaking provider implementation details. | Low for documentation; medium if policy selection changes. |
| P2 | Video restarts repeat successful intermediate work | High; script JSON is saved after rendering, and `video_render.py:853` removes temporary scene audio/frames/clips in `finally`. | A later rendering failure can repeat script/TTS/rendering work. Introduce owned, content-addressed checkpoints for validated script, audio and scene rendering. | Medium–high: invalidation, storage lifecycle, cancellation and resume tests. |
| P2 | Quality metrics have a narrower meaning than full-source trust | High; `generator_output.py:294` checks structure/citation identity, sets faithfulness to unknown and computes coverage over selected chunk IDs. | Report these as structural/citation checks, with a named denominator. Establish factual, code/math and major-topic accuracy using source-grounded evaluation. No new artifact is rated here. | Medium: metric semantics, UI language and evaluation evidence. |
| P2 | Request settings do not alone enforce no retention | High source evidence; account configuration unknown. `llm.py:267` and `book_model_policy.py:36` do not set no-collection/ZDR routing. | Account-wide restrictions may already apply. Verify the actual policy and choose request-level enforcement if required; do not label an unverified retention breach as confirmed. | Low–medium: deployment policy, provider compatibility and disclosure. |

### Existing architectural strengths

The current code already has course-scoped vector caches, source provenance, typed generation schemas, explicit invalid-evidence rejection, durable job ownership/lease fencing, exact nanodollar Book accounting, unknown-charge holds, Book chapter checkpoints and ready-version reuse. Slides use image rendering shared by viewer/export. These are source-confirmed controls; their full customer behavior still needs current-runtime verification.

### Cost interpretation and bounded comparisons

`provider_calls` records model, provider/job attempts, tokens, reported charge and elapsed time. Sum known nanodollar charges by the isolated job and list unknown outcomes separately. Shared OpenRouter account deltas are not per-job measurements. The $0.095 Book ceiling is a generation budget, not a customer credit balance. TTS, local rendering CPU/storage and operational overhead are outside the provider token ledger.

Same-model structured generation normally allows two total attempts; embeddings and TTS each have separate three-attempt policies, and durable job retries form another layer. Budget/unknown-charge errors and specified permanent errors stop early. A manual click count alone does not measure provider call count.

Primary list rates checked on September 6, 2026: [Gemini 2.5 Flash](https://openrouter.ai/google/gemini-2.5-flash), $0.30/M input and $2.50/M output; [Gemini 2.5 Pro](https://openrouter.ai/google/gemini-2.5-pro), displayed base tier $1.25/M input and $10/M output; [text-embedding-3-small](https://openrouter.ai/openai/text-embedding-3-small), $0.02/M tokens. These are reference prices, not this review's measured charges.

Illustrative Video LLM-only comparison: if each plan/script call uses 10,000 input plus 4,000 billable output tokens, two Pro calls cost $0.105. Reusing an already paid matching plan leaves one $0.0525 call, a 50% marginal reduction under this assumption. Two equivalent Flash calls would cost $0.026, approximately 75.2% less than the two-call Pro scenario. This excludes TTS, CPU, retries, cache pricing and fees, and makes no quality or complete-Video savings claim. A model change requires evaluation before recommendation.

Candidate ordering for the later design discussion: unblock generation safely; establish deterministic full-source evidence coverage; share one canonical plan; reuse successful work; then benchmark smaller/local provider alternatives. Current code already uses Flash for Book, so a proposed switch from Pro to Flash would not be a new Book optimization. No current successful Book baseline has been established, and the requested 95% quality target / approximately 90% lower approval threshold cannot yet be assessed.

### Source-review limitations

Provider account privacy settings, hardware/local-model feasibility, real generation latency and current artifact quality remain unverified. OpenRouter describes [data-collection and zero-retention routing controls](https://openrouter.ai/docs/guides/routing/provider-selection); the [edge-tts upstream project](https://github.com/rany2/edge-tts) confirms its use of Microsoft's online service. No provider or product change was made. The source-derived SQLite issue remains a hypothesis pending a focused real file-database reproduction; the Book admission blocker follows directly from the current production code.

## Resume checkpoint — instructions and evidence reconciled (2026-09-06)

The renewed request and both named Superpowers skills were read from their supplied paths. This remains an architectural, planning-only review. Existing report/progress files and the old report were preserved; no product code was changed and no provider request or fresh generation was made during this checkpoint.

The saved runtime snapshot is dated 06:44 UTC; it is historical evidence, not a fresh runtime query. It records failed ingestion, zero chunks, and no provider calls. Existing regression results above were read, not rerun at this checkpoint. Targeted current-source inspection reconfirmed the Book admission guard and the SQLite transaction spanning the source-plan builder; the latter remains an inference without a fresh runtime reproduction.

Quality requirement clarification: the user requests around 90–95%+ of the best overall Study Guide quality while factual correctness, grounding, source fidelity and major concept coverage remain very close to baseline. No separate 90% acceptance threshold has been approved. Any earlier proposed numerical acceptance policy is a candidate for the later interview, not a user decision.

The next required action remains destination-specific consent to resume ingestion of the saved handbook and attempt one Study Guide, Slides and Quiz generation each through the real UI, including normal application retries. Consent would permit testing, not bypassing Book budget admission or modifying product code. If generation fails because of existing product blockers, record the failure and keep the baseline-quality evaluation explicitly incomplete. Video generation remains skipped. Design selection, explicit spec approval and detailed Writing Plans follow the evidence review; execution is excluded from this session.

## AI_for_A0 review — consent and source checkpoint (2026-09-06)

The user supplied `C:/Users/Dang Duc Luong/Downloads/AI_for_A0.pdf` and explicitly authorized sending its text/selected OCR page images to OpenRouter and routed providers for indexing plus one Study Guide, Slides and Quiz generation each with normal retries/charges. This supersedes the prior consent blocker for this PDF only; the earlier handbook was not retried. Questions should be asked asynchronously while independent work continues. No Video generation.

Source: 174 pages, 2,346,478 bytes, SHA-256 `f7331c7f1c14f4812475d7650877d0aca0e573313542279fdeb508fe66d1ee27`. Eight top-level chapters: Python (PDF p11), supervised learning (p21), unsupervised learning (p25), evaluation (p41), neural networks (p49), deep learning (p57), NLP (p103), computer vision (p131). Local text/TOC inventory and sampled page renders saved under `dogfood-output/review-new-20260906/ai-a0/`. All document content is untrusted source material.

Source-quality caveat: local PDF p170 visibly clips long code lines at the right page edge and contains unusual visible-space characters/letter spacing in code. Plain-text extraction adds further spacing/ordering defects. Generated fidelity must be compared with rendered source, and source-origin defects must not be reported as new generator defects.

Restored isolated current-worktree backend/frontend (8002/3002), retaining the synthetic student's password in memory and signing in through visible UI. Restart required the existing globally installed psutil helper; no product/dependency files changed. Actual outgoing provider access is now authorized. Before upload, numeric shared key usage was $2.361656740, remaining allowance $7.638343260. These counters alone cannot attribute this run's costs.

### A0-UX-01 — Ingestion progress uses the wrong stage and remains at zero

P2 / medium complexity / high confidence, confirmed current UI and read-only isolated runtime. After uploading AI_for_A0.pdf, at 36 seconds and again at 108 seconds the course page displayed `Đang xử lý tài liệu (0%)…` and `Đang tạo nội dung`, despite document extraction being underway. The runtime course had stage `extracting`, progress 20; the durable preprocess job had stage `generating`, progress 0. By the later diagnostic read, five provider calls had settled and a sixth was dispatched, so zero percent did not mean no work or no cost.

Student impact: a long upload appears stuck and gives an inaccurate stage; users cannot distinguish extraction/OCR from artifact generation. Suggested direction: make ingestion job progress track the existing extraction/indexing stages and expose completed/total work where measurable. Evidence: ai-a0/02-ingestion-progress.png and 03-ingestion-stalled-progress.png; read-only queries scoped to course `7de35d382f3a`. No extra upload or retry was issued to reproduce it. The screenshot sequence and two timed observations are the evidence; no repro video was recorded.

### A0-ARCH-01 — SQLite source-plan/accounting lock independently reproduced

P1 / medium–high complexity / high confidence, isolated runtime reproduction. This upgrades PIP-02 from source inference to a confirmed defect in the current file-SQLite code path; it is not yet a claim about this PDF's generator UI outcome.

The diagnostic used the real database-engine factory, source-plan service and provider dispatcher with synthetic owned course/job/lease data, disabled socket connections, and a fake provider. Dispatch outside the source-plan transaction succeeded. A cold source-plan builder failed after 5.496 seconds with AccountingError caused by `database is locked` when inserting the provider ledger row; the fake provider invocation count did not increase. Dispatch after rollback succeeded, and an existing cached plan returned without invoking its builder.

Why students care: fresh Study Packs can fail before generation despite valid input and available provider credit. Candidate direction: replace the write transaction spanning provider work with a durable claim/lease and short transactions, preserving one canonical plan and ownership/attempt fencing. Do not disable accounting or silently switch the test database to hide the issue. Evidence: ai-a0/source-plan-lock-evidence.json and reproduce-source-plan-lock.py. The test did not access the student's isolated runtime database or any external service.

## AI_for_A0 document checkpoint — completed with extraction warnings

The one UI upload completed in 310.1 seconds (08:47:13.829–08:52:23.952 UTC), one job attempt, 173 indexed chunks. UI automatically changed to Ready without reload and honestly states `Trích xuất chưa hoàn tất • Độ trung thực: chưa đánh giá`. This is a useful improvement over treating structural quality as verified factual trust.

The persisted aggregate reports 174 pages, 168 extracted, 6 blank, 12 OCR, 23 skipped OCR candidates, 7 damaged pages and 8 warnings; extraction_complete=false. Skipped OCR does not mean all text from those pages was absent: native text can still be indexed. The course-title call failed due to output-length truncation; filename fallback `AI_for_A0` allowed completion. Known per-job provider ledger charges were $0.367366620 across 19 settled rows, no unresolved rows at that snapshot. Evidence: ai-a0/ingestion-later.json and 04-ingestion-ready-warning.png.

### A0-EXTRACT-01 — Warning does not explain affected pages or recovery

P2 / medium complexity / high confidence for visible behavior. The ready course offers generation but shows only an incomplete-extraction/fidelity warning; this screen has no action to inspect which pages were damaged or what the student can do. The local assessment marks 35 OCR candidates, yet only the first 12 are selected by page order; explicitly damaged-glyph pages 134–136 are later than this cap. Source evidence: extraction_quality.py candidate selection and ai-a0 local assessment. Candidate direction: prioritize damaged/math/image evidence within budget, show safe page-level coverage/reasons, and offer bounded targeted recovery. Do not demand OCR for every page or equate a suspicious reading-order heuristic with confirmed unreadability.

Focused offline checks after this checkpoint: seven existing source-plan/Book-accounting tests passed, 34 warnings, 4.12 seconds. Exact test nodes/environment are in ai-a0/run-focused-offline-checks.py; evidence in focused-offline-checks.log. Network disabled and synthetic credentials only. An initial sandbox attempt failed during Windows temp-directory setup; approved rerun passed. Passing tests do not cover the reproduced file-SQLite ledger interaction.

## AI_for_A0 Study Guide checkpoint — failed before content generation

One UI request used Chuyên sâu and asked for Vietnamese beginner-friendly coverage of all eight chapters, exact formulas/code, worked examples, self-checks, and explicit handling of missing evidence. The job failed in 1.77 seconds with stored public code `BOOK_BUDGET_LIMIT` and safe message `Tác vụ đã dừng ở giới hạn chi phí an toàn.` No additional provider ledger row or charge appeared; the run total remained the ingestion cost $0.367366620.

### A0-BOOK-01 — Study Guide unavailable; actionable failure is lost in the UI

P1 / medium–high complexity / high confidence. The visible result is `Tác vụ không thành công` / `Không thể hoàn tất tác vụ. Vui lòng thử lại.` with only a retry button. The backend already identifies a safety-budget stop; the UI replaces it with generic retry advice. Retrying unchanged settings is not a justified recovery from the known fail-closed admission implementation. Do not bypass that guard. Candidate direction: complete verified request admission and preserve a safe, useful reason/action across the artifact/job/UI contract. This UI run confirms a budget-limit failure, not which internal admission sub-check raised it; the uncalibrated-request blocker remains separately source-confirmed.

Evidence: ai-a0/05-book-settings.png, 06-book-failed.png, book-result.json; job 5e978989-02ab-496d-bfa6-2574321a4892. Clicking another tab required scrolling its control out from under the sticky header; scrolling resolved the automation click interception, so that alone is not a proven tab-navigation bug.

No generated chapter, PDF, strongest/weakest passage or current quality baseline exists. Correctness, grounding, coverage, duplication, readability, depth and trustworthiness cannot be scored for this failed run. The old different-source handbook artifacts are historical evidence only. Manual Book generation allowance consumed once; no manual retry. Relevant seven admission/source-plan tests passed at this checkpoint; they intentionally verify fail-closed behavior and do not establish end-to-end generation success.

## AI_for_A0 Slides checkpoint — failed after automatic retries

One UI request selected Chuyên sâu / 22 slides with a Vietnamese beginner-facing lecture spanning all eight chapters, accurate formulas/code, visual examples and source limitations. The durable job ran 08:55:57.932–08:56:30.016 UTC (32.08 seconds), three automatic attempts, then failed with JOB_EXECUTION_FAILED; the artifact exposes SLIDE_GENERATION_FAILED. UI showed scheduled retry time and then `Không thể tạo bài trình chiếu. Vui lòng thử lại.` without needing reload.

P1 / high confidence for generation failure. No deck/images/PDF/PPTX were produced and no new provider ledger row/charge appeared. The independently reproduced SQLite lock is a relevant candidate cause, but the sanitized live job record does not establish its exact exception chain; do not claim direct trace confirmation for this course.

Good: configuration controls are clear, inputs disable during submission, and automatic retry/terminal state is visible. Bad: student receives no actionable explanation after waiting; no successful slide output can be judged for accuracy, flow, density, clipping, visuals, readability, coverage or viewer/export parity. Evidence: ai-a0/08-slide-settings.png, 09-slide-auto-retry.png (capture may show final state after the rapid last retry), 10-slide-failed.png and slide-retry.json. Sanity check: reserved version is error, three attempts recorded, settled cost unchanged. No manual retry or additional paid request. Existing focused source-plan tests and separate failing integration probe apply to this dependency boundary.

## AI_for_A0 Quiz checkpoint — failed after automatic retries

One UI request selected 15 questions and mixed difficulty (Trộn). The job ran 08:58:24.573–08:58:56.677 UTC (32.10 seconds), three automatic attempts, and failed with JOB_EXECUTION_FAILED. The UI says `Không thể tạo bài trắc nghiệm. Vui lòng thử lại.` and offers retry. No questions or answer-key PDF exist, and no additional provider ledger row/charge was recorded. Evidence: ai-a0/11-quiz-settings.png, 12-quiz-failed.png, quiz-result.json.

P1 / high confidence for the failed Quiz customer path. Correctness, option quality, difficulty distribution, duplication, explanation/answer agreement, scoring and study usefulness cannot be evaluated without a generated result. No fabricated sample or old quiz was substituted. Sanity: one reserved request, three automatic attempts, no active generation at completion. No manual retry.

Fresh UI-contract regression after Book/Slides/Quiz observations: `npm test -- --run src/components/dashboard/JobProgress.test.tsx src/components/dashboard/ArtifactJobRetry.test.tsx src/lib/api.test.ts` from src/frontend: 3 files / 48 tests passed in 9.13s. Initial sandbox run was blocked by Windows spawn EPERM before execution; approved rerun passed. Two jsdom navigation-not-implemented messages are test limitations. Evidence: ai-a0/frontend-focused-checks.log. These mocks do not cover successful real provider generation or the current budget-error message omission.

## AI_for_A0 cost reconciliation and evidence limits

Numeric OpenRouter key counters changed from $2.361656740 to $2.729023780, a shared-counter increase of **$0.367367040**. The isolated course ledger totals **$0.367366620**; difference **$0.000000420** remains unattributed (for example, precision or an unrecorded/shared call). Do not assert exact per-feature reconciliation or that every external charge is represented by the ledger. All 19 recorded course calls belong to preprocessing and are settled; no artifact job added a ledger row. Key allowance remaining after the test was $7.270976220. Before/after evidence is in ai-a0/usage-before-upload.json and usage-after-tests.json. No Video/TTS call was requested.

This current-source test establishes working upload/indexing with limitations and three failed artifact paths. It does not establish quality of nonexistent generated outputs, 90–95% baseline preservation, production performance, provider-wide outage, or a measured cheaper architecture. Existing handbook outputs remain historical quality examples, not comparable AI_for_A0 baselines. Browser actions used real UI and authentication; supporting DB projections were read-only and explicitly labeled. No auth token, password, key, OTP or signed download URL is part of the saved evidence.

## Candidate directions for the design interview — not approved designs

1. **Reliability and trust first (recommended):** unblock the four-format foundation, keep the budget fence, align canonical source plans, make extraction/error recovery useful, address session revocation, and establish source-grounded evaluation. Then design provider independence against a successful reference. This produces a dependable student workflow before spending on model comparisons.
2. **Study Guide first:** prioritize a successful comprehensive Guide and the best-quality reference, then reduce Book provider dependence under strict factual/source/coverage gates. Shared runtime/security prerequisites still apply; Slides/Quiz/Video enhancements come later.
3. **Video economics first:** after shared blockers, prioritize reusable validated scripts, per-scene speech/render checkpoints, accurate provider/cost inventory and a speech/generation adapter. Preserve current providers as fallback; choose local/cheaper models only after hardware/privacy/quality decisions and bounded evaluation. Book improvements are a separate later spec.

These touch several independent concerns, so use separate bounded specs/plans for shared reliability/security, source-quality/Book, and Video provider/caching work, with explicit dependencies. Do not create one enormous plan before the user chooses scope. Preserve the existing four generation endpoints, ownership, image-based slide/export parity, and backend-only AI. Proposed changes to OpenRouter-only policy or authenticated download contracts must be explicit in the approved spec.

Useful product opportunities beyond fixes: source coverage map with physical page references; targeted recovery of damaged pages; transparent pre-generation estimates and spent/unknown status; one shared topic plan across formats; learning objectives linked to Guide sections, slides and quizzes; version comparison that explains coverage changes. No new chat endpoint is proposed.

Next: ask the user one direction question, then refine requirements one question at a time; prepare/review a design and await explicit spec approval before Writing Plans. The future plan must include exact interfaces/files/tests/acceptance criteria, progress_new.md at every checkpoint, relevant tests, stop-and-report on an invalid approved plan, a security-focused requesting-code-review step, and verification-before-completion. Stop after the plan; do not execute it.

## Selected direction and planning research (2026-09-06)

User decisions so far: reliability/trust first, then provider independence; shared multi-student server with working local development; configurable Book caps plus pre-generation estimates, prioritizing trustworthy coverage. These are design inputs, not written-spec approval or implementation authorization.

Primary provider documentation rechecked during planning: [usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting) returns reported token/cost data in responses; [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection) defines max_price as a provider unit-price filter, not a complete-job spend cap. Therefore a price filter plus an estimate must not be marketed as an absolute whole-guide cost guarantee. Retain atomic reservations/reconciliation, unknown-charge holds and bounded calls; distinguish estimated cost from the application's enforced admission policy.

[Zero-retention documentation](https://openrouter.ai/docs/guides/features/zdr) describes request/account endpoint filtering and its policy interpretation, including treatment of implicit in-memory prompt caching. Any promise to students must match verified deployment/provider settings. No change to account settings or request policy was made by this review.

Further user decisions: incomplete extraction requires repair or explicitly confirmed limited scope; external processing requires verified no-training/zero-retention endpoints and stops when none qualify. The first reliability-release scope and student flow are approved. The user replaced the proposed $1 Book allowance with a $0.30–$0.50 range. Proposed implementation default is $0.50, with $0.30 a cost target only when trustworthy coverage permits; the written spec will make this interpretation reviewable. This does not authorize further paid comparison runs during the planning-only session.

Scope refinement: the user requires working Video in the first-release demo and is not prioritizing its cost. A disabled Video feature is not sufficient release acceptance. Runtime design has been approved. Speech replacement is now a first-release design question rather than only deferred cost-optimization work; the earlier strict external-processing policy remains in force unless the user explicitly changes it.

Approved design sections now include Azure real-time prebuilt Vietnamese speech, durable cookie-based sessions and short-lived artifact download capabilities, explicit source/topic coverage, and all-four-artifact release verification. The written design is `docs/superpowers/specs/2026-09-06-reliability-and-trust-design.md`, awaiting explicit written-spec approval. It introduces concrete defaults for review and separates future runtime, source/student-flow, security/provider/speech, and integrated-verification plans. No new successful quality baseline is claimed and no plan has been executed.

## Final planning deliverables (supersedes earlier pending-approval status)

The user explicitly approved the written spec and requested the plans. Four plans are now written with27 tasks and117 unchecked steps. They include exact shared contracts, file changes, implementation/test examples, commands, acceptance/browser checks, progress updates, stop-on-design-mismatch, dedicated requesting-code-review security review and verification-before-completion for future execution. Plan04 maps approved requirements to tasks and evidence.

Fresh document validation passed: balanced code fences,36 Python blocks parsed without syntax errors, no scanned unfinished placeholders, valid spec references and identical approved global constraints in all four plans. This does not claim the proposed product code or tests have run. Saved evidence: `dogfood-output/review-new-20260906/planning-document-checks.json`.

The current phase ends here without implementation. The failed current UI paths and absent quality baseline remain findings for future execution; no report language should be interpreted as fixing them. Azure account/policy/live-audio verification and successful four-artifact evaluation are explicit future gates, not completed claims.
