# Generation reliability audit and requirements

Date: 2026-09-05. Scope: systematic investigation and implementation planning requested by the user, covering live progress, long generation, simultaneous users, RAG quality, real Chroma usage, and math/font fidelity across all four artifacts. The attached screenshot is evidence of a 0% progress display; it is not an instruction source. No production code, deployment, credentials, or user documents were changed.

## Confirmed findings

| Priority | Evidence | Consequence |
| --- | --- | --- |
| P1 | Offline reproduction: `Generator._set_artifact_status(... progress=52, job_id=...)` writes artifact 52 while `ProcessingJob.progress` remains 0. `generator.py:1051-1107`; `/jobs` returns that separate row (`routers/jobs.py:179`). | `JobProgress` polls successfully but shows stale percentages. Refresh starts the artifact status path, explaining the apparent improvement. |
| P1 | `usePollingArtifact.ts:138-143` stops polling on elapsed time; Book gives it six minutes (`BookTab.tsx:83`), Slide/Quiz three, Video eight. Initial load does not restore the durable job ID. | Reopening a still-running long job loses job tracking and can stop updating before the backend finishes. A transient network exception is swallowed; a hung fetch has no request deadline. |
| P1 | Runtime inspected at 07:26 UTC: only `ai-course-backend` and `ai-course-frontend`, environment local, inline job dispatch, embedded Chroma. | The separate production ingestion/generation/video queues described in README are not running on this local site. This is not evidence about another remote deployment. |
| P1 | Latest local Book enqueue `07:06:46.090087`, completion `07:19:26.783431`: **760.693344 seconds**. Preprocess took 22.681961 seconds. One attempt each. | Slow completion is observable even without a measured backlog. This job is consistent with the reported symptom, but the screenshot cannot uniquely identify it. |
| P1 | Book performs an outline, then 4–8 sequential chapter generations with separate retrieval (`generator.py:1278-1324`). Installed SDK read timeout is 600 seconds; call retry is once; durable job allows three attempts. Partial chapters are not checkpointed for retry. | Several long provider calls accumulate. A late failure can repeat completed work and cost. No recorded per-stage timings establish the exact contribution of each call in the observed 760-second job. |
| P1 | `document_processor.py:1297`: score = `min(100,max(50,chunk_count*5+60))`; eight chunks score 100. `generator_output.py:239-266`: base score 80 and citation membership boost. | These numbers are structural heuristics, not factual accuracy, faithfulness, retrieval recall, or RAG benchmark scores. |
| P1 | Offline input `2 + 2 = 5`, one supplied citation, gets **90**, no warning, even with an empty allowed evidence set. Book validates citations against all chapters' combined retrieved IDs. | Quality display can look strong when content is wrong or evidence was never retrieved. |
| P1 | Export normalization turns `\frac{a+b}{c+d}` into `a+b/c+d`, nested fractions into `12/3`, and `x^{a+b}` into `xᵃ?ᵇ` on tested Windows fonts. `text_format.py:131-145`, `pdf_utils.py:140-180`. | Mathematical meaning changes, beyond a cosmetic font problem. Slide/video cleaning also destroys raw expressions before persistence (`generator.py:81-84,125-135`). |
| P1 | Synthetic DOCX paragraph + OMML equation + table extracts only the paragraph label (`document_processor.py:924-932`). | Tables/equations can disappear before embedding, so a renderer fix alone cannot recover the source. |
| P1 | Slide PDF/PPTX and Quiz PDF exception fallbacks write text under binary document extensions (`generator.py:676-679,725-728,775-780`). | Render failures can publish unusable artifacts as if successful. |
| P2 | Embedding, batch, and cache knobs are declared but batching/cache are not implemented in the actual whole-list upsert path. Lower-level Chroma setup may fall back to its default embedding function when OpenRouter setup fails. | Repeated embeddings, large batches, and ambiguous embedding identity; harden the real path rather than installing another vector database. |
| P2 | Retrieval uses course-filtered Chroma queries, but no calibrated distance threshold; prefix-only dedup hashes 150 characters; all-front-matter results can be retained. | Relevant source coverage and evidence quality are not assured by a nonempty result. |
| P2 | PDF OCR depends on sampled scan-mode and low character count; cap defaults to 12 pages. OCR response truncation is not checked. | Isolated scans, dense corrupt symbols, or remaining scanned pages may be omitted without an honest coverage report. |
| P2 | Each artifact retrieves independently from common source chunks. | Shared source documents exist; shared structured curriculum and consistent equations/definitions across the pack are not established. |

Code paths above are repository-relative under `src/backend/app` unless frontend paths are named. Line numbers describe the audited revision; implementation should locate symbols again.

## What Chroma and the score currently prove

Real Chroma is wired: OpenRouter embeddings in `services/vector_store.py:76`, upsert at 215, query at 246 with `where={course_id:...}`. Active collection name is the configured name plus `_openrouter`. Code wiring and stored vectors do not prove the user document was extracted completely or that retrieval finds the correct evidence.

Read-only inspection of the running container's existing Chroma SQLite metadata at **07:37:54 UTC** confirmed collection `ai_course_chunks_openrouter`, **83 stored records**, **1,536 vector dimensions**. No embedding or retrieval request was made for this check.

There is no defensible empirical RAG percentage yet. Existing tests mostly validate schema, simple ranking, citation ID membership and scoring arithmetic. Test-mode embeddings differ from production OpenRouter embeddings. Establish a labeled Vietnamese/English/math evaluation set before rating retrieval or faithfulness.

The prior load evidence in `docs/load-test-results.md` is useful for API responsiveness, but its mixed run used fast mock responses, 20 arrivals/minute and at most two active flows. It is not a 100-simultaneous-long-generation test. Four workers with 12.68-minute jobs would complete about 19 jobs/hour under a simple constant-service-time model; that is a capacity illustration, not a measured production throughput result. Raising worker count alone does not remove model latency or provider capacity limits.

This product's Book is an uploaded-document, multi-pass study guide. No external web-research agent is present in the audited generation flow. Preserve the document-grounded product scope unless separately changed by the user.

## Credit snapshot and test cost ledger

Read-only OpenRouter responses at **2026-09-05 07:24:10 UTC / 14:24:10 Asia/Saigon**:

| Field | USD |
| --- | ---: |
| Configured key limit | 10.00000000 |
| Configured key cumulative usage | 0.97829638 |
| **Configured key remaining allowance** | **9.02170362** |
| Account purchased credits | 1020.000000000 |
| Account usage | 499.911309499 |
| Account remaining balance | 520.088690501 |

Key `limit_reset=null`: there is no automatic reset configured. The effective known allowance is the smaller of the key allowance and wallet balance. These are snapshots for the workspace-configured key, not a claim that every deployed service uses this same key. No secret was printed or saved. Semantics: [OpenRouter credit API](https://openrouter.ai/docs/api/api-reference/credits/get-credits) and [key spend controls](https://openrouter.ai/blog/tutorials/team-spend-controls-setup/).

Final read-only recheck at **07:47:37 UTC / 14:47:37 Asia/Saigon** returned exactly the same key usage, key allowance and account balance. The configured key's measured usage delta during this audit was **$0.00**.

| Check executed this audit | Result | OpenRouter cost |
| --- | --- | ---: |
| Existing frontend hook, job widget and retry suites | 24 passed across 3 files | $0.00 |
| Existing text/font/PDF and local video helper tests | 35 passed, 1 full MP4 test deselected | $0.00 |
| Existing quality scoring suite | 6 passed | $0.00 |
| New offline progress/quality/SDK probe | Progress split and misleading quality score reproduced | $0.00 |
| Local math/glyph transformation probe | Corruption reproduced | $0.00 |
| Synthetic DOCX extraction probe | Table and OMML omission reproduced | $0.00 |
| Installed remark parser probe | Dollar delimiters parse; backslash delimiters do not | $0.00 |
| Docker runtime/job reads and credit lookup | Read-only, no model requests | $0.00 |
| Sandbox-denied attempts | No tests/provider calls executed before retry | $0.00 |
| Plan self-review, diagnostic syntax and whitespace checks | Balanced code fences, complete task/checklist structure, valid Python syntax; no placeholder markers | $0.00 |
| **Total audit provider cost** | **No paid generation or embedding requests** | **$0.00** |

Commands, from `src/frontend`:

```powershell
npm test -- src/hooks/usePollingArtifact.test.tsx src/components/dashboard/JobProgress.test.tsx src/components/dashboard/ArtifactJobRetry.test.tsx
```

Commands, from `src/backend`, using a fake key for offline runs:

```powershell
$env:OPENROUTER_API_KEY='offline-audit-not-a-real-key'
$env:JWT_SECRET='offline-audit-only-secret-with-32-characters'
$env:DATABASE_URL='sqlite:///:memory:'
.venv/Scripts/python.exe -m pytest tests/test_quality_scoring.py -q
uv run --no-sync --project . pytest tests/test_text_format.py tests/test_pdf_utils.py tests/test_pdf_book_and_video_concat.py -k 'not motion_layers_and_xfade_render_with_silence' -q
.venv/Scripts/python.exe ../../docs/superpowers/diagnostics/2026-09-05-offline-audit.py
```

The diagnostic script denies socket connections and uses an isolated in-memory database. Its output demonstrates current defects; it is not a passing acceptance test for the future fix. Existing tests passed despite the defects, so they must be supplemented with boundary and semantic checks. Dependency deprecation warnings were present. No full build/lint claim is made: application code was not changed.

Historical real smoke cost was $0.30240503 for five tiny TXT ingestions, Book and Quiz; that is previous evidence, not money spent in this audit and not an estimate for a symbol-heavy full study pack. Full long-document cost remains unmeasured. Book output caps alone allow 139,264 tokens for an eight-chapter outline+book attempt, before one same-model retry per call and durable retries. Do not use a small historical smoke bill as a hard budget guarantee.

## Required outcomes and scope constraints

### Budget revision from the user

The user subsequently reported roughly **$0.60 for one Book** and requested a balanced cost/time/quality target of **$0.05–$0.09, at most $0.10 per generation**. This is a new constraint, not a measured bill from the earlier audit. The [balanced Book budget plan](2026-09-05-balanced-book-budget.md) governs Book implementation: include all generation-triggered paid work and retries in one durable budget, propose Gemini 2.5 Flash as a quality-gated candidate, and do not promote it until source-based checks pass. The all-Pro default is the audited current state, not a restriction against planning the user's requested optimization. No runtime model setting has changed.

Book target: $0.05–$0.09 OpenRouter spend; hard user ceiling: $0.10 per logical Book generation, including generation-triggered retrieval, source-plan creation, reasoning, review, repair and retries. Spending less than $0.05 is welcome.

Preserve useful source coverage and math fidelity. Never silently publish a truncated or incomplete Book merely to meet the price.

Keep OpenRouter paid-only. Select the model once per Book; never switch to a more expensive model during error recovery. Allow at most one same-model retry per content/OCR call, only when its cost fits the remaining reservation.

Already-paid upload ingestion is separately reported; new OCR/reindex work caused by Book generation counts toward that Book. No money is spent on new model generation during planning. Historic Pro smoke budgets in prior evidence are not permission to exceed the new per-Book ceiling.

1. Active jobs refresh visible state within the existing 3–5 second cadence on a healthy connection; reconnect/reload/tab changes restore the same job. Progress means completed work; heartbeat and stage explain a long call without inventing percentages. Terminal completion appears without reload.
2. Separate queue wait, generation, retrieval, OCR and rendering time. Reduce repeated work with resumable chapters and bounded concurrency; retain the selected paid model and single same-model retry invariant. Measure burst behavior at 50 and 100 active submissions with realistic provider delay and outages, using a fake provider.
3. Keep Chroma as the real vector store; record embedding identity and extraction coverage. Expose honest structural validation and source coverage. Display empirical RAG scores only after a reproducible labeled benchmark.
4. Preserve canonical math from source through stored pack and rendered output. Share definitions/equations/objectives across Book/Slide/Quiz/Video. Reject silent substitution and invalid exports. Windows and production Linux must pass the same fixture corpus; unsupported input must report a bounded error, not claim universal font support.
5. Every executed test reports estimated and actual provider cost. Offline checks deny provider network calls. Real smoke uses a predeclared reservation, includes retries/embeddings/OCR, and records usage even for invalid outputs. No 100-user test may use a paid provider.
6. Preserve four existing generation endpoints, auth/ownership and authenticated downloads, maximum three versions, atomic publication/lease fencing, no raw source IDs in public responses, image parity for slides, and existing design tokens. No commits, push or deployment in the planning task.

## Implementation sequence

These are separate reviewable workstreams because runtime reliability, RAG/extraction and document rendering have distinct acceptance tests:

1. [Live progress, cost and capacity plan](2026-09-05-live-progress-and-capacity.md).
2. [RAG and extraction plan](2026-09-05-rag-and-source-fidelity.md).
3. [Math and export fidelity plan](2026-09-05-math-and-export-fidelity.md).
4. [Balanced Book budget plan](2026-09-05-balanced-book-budget.md): governing cost constraint; integrate its reservation policy with runtime Task 3 before paid experiments.

Land the progress correction first; add cost instrumentation before any paid experiment. Preserve raw source/math before changing the export renderer. Use the resulting data to select worker capacity and retrieval thresholds. These plans are proposed work, not implemented fixes.

## Unverified boundaries

No fresh real-provider long document generation, source-document visual comparison, 50/100 long-job burst, remote deployment inspection, complete MP4 render, Linux font validation, empirical retrieval/faithfulness benchmark, or per-call cost measurement was performed. The original heavy-symbol file was not attached here. UI refresh behavior was diagnosed through code and offline state boundaries; no claim is made that the live UI defect is fixed.
