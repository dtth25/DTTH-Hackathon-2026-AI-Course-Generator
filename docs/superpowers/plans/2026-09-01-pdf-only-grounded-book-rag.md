# PDF-Only Grounded Book RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce higher-coverage, lower-duplication Books whose factual content is demonstrably supported only by the uploaded course documents, with no web or model-knowledge supplementation.

**Architecture:** Preserve page-aware chunks, build a cached course-level source map, retrieve each chapter with dense plus lexical search and reciprocal-rank fusion, select a bounded evidence pack, draft and ground-review each chapter, then enforce a deterministic whole-book quality gate before atomic publication.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, ChromaDB, OpenRouter, SQLAlchemy, PyMuPDF, python-docx, pytest, Next.js 16, React 19

**Spec:** [PDF-Only Grounded Book RAG Design](../specs/2026-09-01-pdf-only-book-rag-design.md)

## Global Constraints

- Use only text extracted from files belonging to the current owned course. No web search, external corpus, alternate AI provider, or ungrounded model-memory fill.
- Preserve PDF/DOCX/TXT upload support. When a course contains PDFs only, every derived structure and Book claim remains PDF-only.
- Keep Chroma and the existing Book generation endpoint. This is a retrieval/generation pipeline change, not a fifth generation feature.
- Keep raw chunk, concept, claim, prompt, and verifier ids internal; public Book JSON/PDF stays clean.
- Complete the durable runtime plan through job stages before integrating the Book worker/UI tasks here.
- All automated tests mock OpenRouter. The explicit paid-provider smoke test is opt-in and must never run in normal CI.
- Do not commit unless the Lead explicitly authorizes it; commit commands are checkpoints only.
- Before Task 7, complete Tasks 1-4 of [Distinctive Product Appearance and Brand Voice](2026-09-01-distinctive-product-appearance-and-brand-voice.md). Grounding UI may state only backend-returned metrics from a passed gate and must use the shared editorial tokens, direct Vietnamese voice, and no generic AI decoration. After Task 7, regenerate the Book product screenshot and rerun the brand/visual gates when those commands exist.

## File Structure

### Create

- `src/backend/app/schemas/book_rag.py` — source-map, retrieval, evidence, review, and gate schemas.
- `src/backend/app/services/source_map.py` — content-hash cache and source-only map builder.
- `src/backend/app/services/lexical_index.py` — persisted course-local BM25 index.
- `src/backend/app/services/hybrid_retriever.py` — query expansion, RRF, deduplication, diversity, evidence selection.
- `src/backend/app/services/book_grounding.py` — id validation, chapter review, coverage/repetition gate, internal report.
- `src/backend/app/prompts/source_map_batch.txt`
- `src/backend/app/prompts/source_map_reduce.txt`
- `src/backend/app/prompts/book_evidence_select.txt`
- `src/backend/app/prompts/book_ground_review.txt`
- `src/backend/tests/test_source_map.py`
- `src/backend/tests/test_lexical_index.py`
- `src/backend/tests/test_hybrid_retriever.py`
- `src/backend/tests/test_book_grounding.py`
- `src/backend/tests/fixtures/book_rag_80_page.py` — deterministic PDF fixture builder, not a checked-in binary.
- `src/backend/tests/e2e/test_book_rag_quality.py`
- `src/frontend/src/components/dashboard/BookGroundingSummary.tsx`
- `src/frontend/src/components/dashboard/BookGroundingSummary.test.tsx`

### Modify

- `src/backend/app/services/document_processor.py` — page/heading/noise/hash metadata and post-index source map.
- `src/backend/app/services/vector_store.py` — ranked dense results with distance and bulk course read.
- `src/backend/app/schemas/generator_output.py` — richer internal outline/chapter contracts only.
- `src/backend/app/services/llm.py` — strict structured calls for map, evidence, outline, and ground review.
- `src/backend/app/prompts/book_outline.txt`, `src/backend/app/prompts/book_chapter.txt` — source-map/evidence contracts and abstention.
- `src/backend/app/services/generator.py` — orchestrate hierarchical RAG and quality gate.
- `src/backend/app/workers/tasks.py` — source-map and Book job stages.
- `src/backend/app/core/config.py` — version/budget/threshold settings.
- `src/backend/tests/test_vector_store_and_processor.py`
- `src/backend/tests/test_generation_service.py`
- `src/backend/tests/test_content_quality_fixes.py`
- `src/frontend/src/lib/types.ts`
- `src/frontend/src/components/dashboard/BookTab.tsx`
- `src/frontend/src/components/dashboard/BookOptionsPanel.tsx`
- `docs/architecture_design.md`, `docs/api_contract.md`, `README.md`

---

## Task 1: Preserve page-aware, hash-versioned ingestion metadata

**Files:**

- Modify: `src/backend/app/core/config.py`
- Modify: `src/backend/app/services/document_processor.py`
- Modify: `src/backend/app/services/vector_store.py`
- Modify: `src/backend/tests/test_vector_store_and_processor.py`

- [ ] Add failing extraction/chunk tests for page boundaries, multi-page contribution metadata, repeated header/footer flags, heading path propagation, neighbors, stable hashes, and a chunking-version change.

```python
def test_pdf_chunks_retain_page_and_neighbors(processor, three_page_pdf) -> None:
    chunks = processor.extract_and_chunk_file(three_page_pdf, course_id="c1")
    assert all(chunk.metadata["page_start"] <= chunk.metadata["page_end"] for chunk in chunks)
    assert chunks[1].metadata["previous_chunk_id"] == chunks[0].metadata["chunk_id"]
    assert chunks[0].metadata["content_hash"] == sha256_normalized(chunks[0].content)
```

- [ ] Add `CHUNKING_VERSION="2"` and validate it is nonempty. Include it in embedding/source-map cache keys.
- [ ] Refactor extraction to keep page records until after chunk construction. A chunk may span adjacent pages only when it stores `page_start`, `page_end`, and every contributing page number.
- [ ] Detect repeated page headers/footers deterministically: normalize the first/last nonempty line per page and flag a line that appears on at least 60% of pages when the document has at least 5 pages. Exclude flagged lines from embedding text but retain raw provenance.
- [ ] Infer `heading_path` with deterministic typography/text rules already available from extraction; fall back to the most recent short title-like line. Do not call the LLM for basic chunking.
- [ ] Create stable chunk ids from course id, normalized source path, page range, sequence, and `CHUNKING_VERSION`; store SHA-256 of normalized content separately.
- [ ] Add `VectorStore.get_course_documents(course_id)` returning all course documents with metadata in stable source/page/sequence order. Add an internal ranked dense result type carrying `rank` and `distance` without changing current `search()` callers.
- [ ] Run `uv run pytest tests/test_vector_store_and_processor.py -q` and the existing re-embedding script in dry-run/list mode. Document that deployed courses require `scripts/reembed_courses.py` after the version change.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/core/config.py src/backend/app/services/document_processor.py src/backend/app/services/vector_store.py src/backend/tests/test_vector_store_and_processor.py; git commit -m "feat: preserve source structure during ingestion"`.

## Task 2: Build and cache a validated source map

**Files:**

- Create: `src/backend/app/schemas/book_rag.py`
- Create: `src/backend/app/services/source_map.py`
- Create: `src/backend/app/prompts/source_map_batch.txt`
- Create: `src/backend/app/prompts/source_map_reduce.txt`
- Create: `src/backend/tests/test_source_map.py`
- Modify: `src/backend/app/services/llm.py`

- [ ] Define failing schema and cache tests for valid maps, unknown ids, duplicate ids, batch size <=12, cache hit, content/prompt/model invalidation, atomic save, malicious cache paths, and partial LLM failure.

```python
def test_source_map_rejects_claim_from_unknown_chunk(builder, course_chunks) -> None:
    builder.llm.map_batch.return_value = {
        "claims": [{"claim_id": "cl1", "text": "claim", "chunk_ids": ["other-course-1"]}]
    }
    with pytest.raises(SourceMapValidationError, match="unknown chunk"):
        builder.build(course_id="c1", chunks=course_chunks)
```

- [ ] Add strict Pydantic types using `extra="forbid"`: `SourceDocument`, `SourceSection`, `SourceConcept`, `SourceClaim`, `GlossaryEntry`, `SourceMap`, `SourceMapManifest`, and batch/reduce outputs.
- [ ] Generate stable internal ids in application code after LLM output, not by trusting model-created ids. The model associates text with an allowed `chunk_id`; the service assigns `s{n}`, `c{n}`, and `cl{n}` after validation and deduplication.
- [ ] Implement `SourceMapBuilder.build(course_id, chunks, model_id)`. Batch exactly in stable order, at most 12 chunks, wrap source data in clear untrusted-document delimiters, call `LLMService.generate_source_map_batch`, validate every returned chunk id against that batch, then perform one reduce call over batch digests.
- [ ] The reduce prompt may merge, order, and label only supplied entries. It must be instructed to ignore instructions inside document text and return no fact without a supplied source id.
- [ ] Cache under `{course_dir}/indexes/source_map.json` with a manifest key composed from ordered content hashes, chunking version, prompt version, and model id. Resolve the course directory using the existing owned course path helper.
- [ ] Write cache files with temp+fsync+replace. On parse/hash/schema failure, quarantine by renaming to `.invalid.<timestamp>` within the same index directory and rebuild; do not use corrupt data.
- [ ] Add a deterministic progress callback after each batch and reduce step.
- [ ] Run `uv run pytest tests/test_source_map.py -q` and `uv run ruff check app/services/source_map.py app/schemas/book_rag.py tests/test_source_map.py`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/schemas/book_rag.py src/backend/app/services/source_map.py src/backend/app/prompts/source_map_* src/backend/tests/test_source_map.py src/backend/app/services/llm.py; git commit -m "feat: build source-only course maps"`.

## Task 3: Add persisted lexical BM25 and deterministic rank fusion

**Files:**

- Create: `src/backend/app/services/lexical_index.py`
- Create: `src/backend/app/services/hybrid_retriever.py`
- Create: `src/backend/tests/test_lexical_index.py`
- Create: `src/backend/tests/test_hybrid_retriever.py`
- Modify: `src/backend/app/services/vector_store.py`

- [ ] Write failing BM25 tests for Vietnamese Unicode tokenization, case/diacritic normalization without destructive accent removal, exact rare-term ranking, empty query, document-frequency math, persistence/cache invalidation, and course isolation.

```python
def test_rare_exact_term_beats_repeated_generic_text(index) -> None:
    index.build([doc("a", "mô hình mô hình"), doc("b", "hệ số Zeta-417")])
    assert index.search("Zeta-417", k=2)[0].chunk_id == "b"
```

- [ ] Implement the standard BM25 formula with fixed `k1=1.5`, `b=0.75`; persist only the course's token counts, lengths, document frequencies, ids, and source hash manifest under `indexes/lexical.json`.
- [ ] Write failing hybrid tests for dense+lexical union, RRF `k=60`, duplicate removal, stable tie-breaking, source-window diversity, top-30 cap, allowed-id enforcement, and no cross-course results.
- [ ] Implement pure rank fusion so it is independently testable:

```python
def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    return sorted(scores, key=lambda cid: (-scores[cid], cid))
```

- [ ] For each chapter query, request dense top 40 and lexical top 40. Fuse every query/list, deduplicate, then select max 30 with the spec's max-four-neighbor diversity rule and section-first coverage.
- [ ] Return typed `RetrievedCandidate` records containing internal ids, text, provenance, ranks, fused score, and heading path. Never accept a candidate not in `get_course_documents(course_id)`.
- [ ] Build/cache the lexical index after vector ingestion and source-map generation; rebuilding an unchanged course must be a no-op.
- [ ] Run `uv run pytest tests/test_lexical_index.py tests/test_hybrid_retriever.py tests/test_vector_store_and_processor.py -q`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/services/lexical_index.py src/backend/app/services/hybrid_retriever.py src/backend/app/services/vector_store.py src/backend/tests; git commit -m "feat: add hybrid source retrieval"`.

## Task 4: Plan Books from the source map and select bounded evidence

**Files:**

- Modify: `src/backend/app/schemas/generator_output.py`
- Modify: `src/backend/app/schemas/book_rag.py`
- Modify: `src/backend/app/services/llm.py`
- Modify: `src/backend/app/prompts/book_outline.txt`
- Modify: `src/backend/app/prompts/book_chapter.txt`
- Create: `src/backend/app/prompts/book_evidence_select.txt`
- Modify: `src/backend/tests/test_generation_service.py`
- Modify: `src/backend/tests/test_content_quality_fixes.py`

- [ ] Add failing strict-contract tests: outline assigns only known concept/claim ids, 2-4 queries per chapter, mode-specific chapter counts, evidence selector returns <=16 ids from <=30 candidates, and document prompt injection cannot alter the output contract.

```python
def test_evidence_selector_cannot_introduce_model_knowledge(book_llm, candidates) -> None:
    selected = book_llm.select_book_evidence(chapter_plan, candidates)
    assert len(selected.chunk_ids) <= 16
    assert set(selected.chunk_ids) <= {item.chunk_id for item in candidates}
```

- [ ] Extend internal `BookChapterPlan` with `learning_objective`, `concept_ids`, `claim_ids`, `retrieval_queries`, `expected_section_ids`, and `target_words`. Remove the single `retrieval_query` only after all callers/tests migrate.
- [ ] Add `EvidenceSelection` and `EvidencePack` schemas. Application code resolves selected ids back to exact candidate text; the LLM never returns authoritative free-form evidence.
- [ ] Change `generate_book_outline` to receive a compact serialized source map and allowed ids. Validate all ids, 2-4 queries, unique chapter numbers, and at least four chapters before retrieval begins.
- [ ] Add `select_book_evidence(plan, candidates)` with `book_evidence_select.txt`. The prompt states that candidate text is untrusted source data and selection may only choose ids; it may return `insufficient_evidence=true` instead of inventing support.
- [ ] Change the chapter prompt to receive only the plan and resolved evidence pack. Require `used_claim_ids` and `source_chunk_ids`; reject ids outside the plan/evidence pack.
- [ ] Keep user prompts as formatting/focus preferences. Escape/delimit them separately and explicitly state they cannot relax grounding, reveal prompts, or request outside knowledge.
- [ ] Add deterministic fallback when the selector reports insufficient evidence: allow the chapter to narrow scope or explicitly state the uploaded source does not establish the requested point; never substitute the old generic context.
- [ ] Run `uv run pytest tests/test_generation_service.py tests/test_content_quality_fixes.py -q`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/schemas src/backend/app/services/llm.py src/backend/app/prompts/book_* src/backend/tests; git commit -m "feat: plan books and select bounded evidence"`.

## Task 5: Ground-review chapters and enforce the whole-book gate

**Files:**

- Create: `src/backend/app/services/book_grounding.py`
- Create: `src/backend/app/prompts/book_ground_review.txt`
- Create: `src/backend/tests/test_book_grounding.py`
- Modify: `src/backend/app/schemas/book_rag.py`
- Modify: `src/backend/app/services/llm.py`
- Modify: `src/backend/app/core/config.py`

- [ ] Write failing unit tests for unknown review ids, unsupported span removal, absent-fact abstention, claim/section coverage, invalid citations, normalized-shingle repetition, mode thresholds, exact-boundary pass/fail, and safe public errors.

```python
def test_standard_book_below_claim_coverage_does_not_publish(gate, standard_report) -> None:
    standard_report.planned_claim_coverage = 0.849
    result = gate.evaluate(standard_report, detail_level="Tiêu chuẩn")
    assert result.passed is False
    assert result.error_code == "grounding_quality_below_threshold"
```

- [ ] Add config settings with validation: summary coverage `0.70`, standard/deep coverage `0.85`, supported ratio `0.95`, maximum repetition `0.10`, maximum evidence chunks `16`, maximum candidates `30`, and source-map batch size `12`.
- [ ] Add strict `ChapterGroundReview`, `UnsupportedSpan`, `ChapterGroundingMetrics`, and `BookGroundingReport` models. The review call receives only draft+evidence and returns a revised structured chapter plus metrics/ids.
- [ ] Validate review ids against the evidence pack and plan. Recompute invalid-citation count and planned coverage in Python; never trust model-supplied aggregate scores.
- [ ] Implement paragraph normalization and 5-token shingles. Count a paragraph as repeated when at least 80% of its shingles occur in an earlier non-boilerplate paragraph; compute repeated/eligible paragraph ratio.
- [ ] Define factual-claim ratio as verifier-supported claims divided by verifier-identified factual claims, aggregated by counts rather than averaging chapter percentages. A chapter with zero factual claims is invalid unless explicitly marked source-insufficient.
- [ ] Write the complete internal report as `book.grounding.json` in the version staging directory. The public summary contains only percentages, pass/fail, and sanitized warnings.
- [ ] Raise `GroundingQualityError(code="grounding_quality_below_threshold")` after one review/revision if a threshold fails. Never write `book.json` or PDF for a failed gate.
- [ ] Run `uv run pytest tests/test_book_grounding.py -q` and mutation-check the boundary tests by temporarily inverting one comparison, confirming a test fails, then restore it.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/services/book_grounding.py src/backend/app/prompts/book_ground_review.txt src/backend/app/schemas/book_rag.py src/backend/app/services/llm.py src/backend/app/core/config.py src/backend/tests/test_book_grounding.py; git commit -m "feat: verify book grounding before publish"`.

## Task 6: Orchestrate the hierarchical pipeline as a durable Book job

**Files:**

- Modify: `src/backend/app/services/generator.py`
- Modify: `src/backend/app/services/document_processor.py`
- Modify: `src/backend/app/workers/tasks.py`
- Modify: `src/backend/tests/test_generation_service.py`
- Modify: `src/backend/tests/test_worker_tasks.py`

- [ ] Add failing orchestration tests for a cache miss/hit, source-map failure, lexical+dense retrieval call counts, per-chapter evidence/draft/review order, one-review maximum, progress stages, cancellation between chapters, quality failure without publish, successful atomic publish, and retry reusing the source map.

```python
def test_book_pipeline_never_uses_generic_context_fallback(service, rag_fakes) -> None:
    rag_fakes.evidence_selector.insufficient = True
    service.generate_book("course-1", version_id="v1")
    rag_fakes.vector_store.search.assert_called()
    assert not rag_fakes.generator.used_legacy_retrieve_context
```

- [ ] After document chunks embed successfully, build the lexical index and source map before marking the course `ready`. Emit `building_source_map` progress. If either fails, mark ingestion failed with a sanitized retryable/nonretryable code; do not enable generation.
- [ ] Replace only the Book path inside `GeneratorService.generate_book`:

```python
source_map = source_maps.load_or_build(course_id, reporter=reporter)
outline = book_llm.generate_book_outline(source_map, detail_level, user_prompt, doc_names)
for plan in outline.chapters:
    candidates = retriever.retrieve(course_id, plan.retrieval_queries, limit=30)
    evidence = book_llm.select_book_evidence(plan, candidates, limit=16)
    draft = book_llm.generate_book_chapter(outline.title, plan, evidence, detail_level)
    reviewed = book_llm.review_book_chapter(plan, draft, evidence)
    chapters.append(grounding.validate_review(plan, evidence, reviewed))
report = grounding.evaluate_book(outline, chapters, detail_level)
grounding.require_publishable(report)
```

- [ ] Emit stable stages: `planning_coverage`, `retrieving_evidence`, `writing_chapter`, `checking_chapter_grounding`, `checking_book_grounding`, `rendering_book_pdf`, and `publishing_version`. Include chapter current/total through the safe job summary.
- [ ] Check cancellation before every LLM call and between chapters. On retry, reuse source-map/lexical caches but create a new immutable Book version unless the runtime retry contract explicitly reuses the same failed job version.
- [ ] Save internal grounding report and cleaned `book.json`, generate PDF, then atomically publish. Preserve existing source-id stripping and connected Study Pack readiness/quality scoring.
- [ ] Remove the legacy generic outline top-20 and chapter top-10 fallback only from Book. Do not change Slides/Quiz/Vid retrieval in this plan.
- [ ] Run `uv run pytest tests/test_generation_service.py tests/test_worker_tasks.py tests/test_content_quality_fixes.py tests/test_quality_scoring.py -q`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/services/generator.py src/backend/app/services/document_processor.py src/backend/app/workers/tasks.py src/backend/tests; git commit -m "feat: orchestrate grounded book rag"`.

## Task 7: Expose safe grounding progress and summary in the Book UI

**Files:**

- Modify: `src/frontend/src/lib/types.ts`
- Modify: `src/frontend/src/components/dashboard/BookTab.tsx`
- Modify: `src/frontend/src/components/dashboard/BookOptionsPanel.tsx`
- Create: `src/frontend/src/components/dashboard/BookGroundingSummary.tsx`
- Create: `src/frontend/src/components/dashboard/BookGroundingSummary.test.tsx`

- [ ] Read `src/frontend/AGENTS.md` and its required installed Next.js 16 references.
- [ ] Add failing tests for ingestion/source-map disabled state, stage labels, chapter X/Y, successful aggregate metrics, threshold failure copy, retry as a new version, and absence of raw ids/prompts/error traces in rendered HTML.
- [ ] Extend public types with safe optional metrics only:

```ts
export type BookGroundingSummary = {
  sourceCoverage: number
  supportedClaimRatio: number
  repetitionRatio: number
  warnings: string[]
}
```

- [ ] Render stable Vietnamese labels for all Book stages. While queued/running, use the runtime plan's shared `JobProgress` component.
- [ ] Render percentages only after a ready Book. Clamp to 0-100 for display, keep backend decimals unchanged, and label them as automated grounding checks rather than certainty guarantees.
- [ ] For `grounding_quality_below_threshold`, explain that the uploaded material did not support enough of the planned Book and offer depth change/source re-upload/new-version retry. Do not suggest enabling external sources.
- [ ] Disable Book generation for every course state except `ready`; specifically test the current `error` state regression.
- [ ] Run `npm test -- --run`, `npm run lint`, and `npm run build` in `src/frontend`.
- [ ] Commit checkpoint if authorized: `git add src/frontend/src; git commit -m "feat: show book grounding quality"`.

## Task 8: Add the 80-page adversarial quality evaluation

**Files:**

- Create: `src/backend/tests/fixtures/book_rag_80_page.py`
- Create: `src/backend/tests/e2e/test_book_rag_quality.py`
- Modify: `README.md`
- Modify: `docs/architecture_design.md`
- Modify: `docs/api_contract.md`

- [ ] Build the PDF deterministically in a pytest temp directory with PyMuPDF. Put uniquely named facts on early/middle/late pages, repeated headers/footers, a table of contents, near duplicates, attributed conflicts, a PDF prompt injection, and conspicuously absent general-knowledge facts.
- [ ] Add a deterministic fake OpenRouter that returns source-map/evidence/draft/review JSON from the supplied ids. Assert the pipeline retrieves every required region, rejects unknown ids, omits absent facts, handles attributed conflicts, removes duplicates, ignores injection, and passes known metrics.
- [ ] Add explicit failing fixtures for 0.849 coverage, 0.949 supported ratio, one invalid id, and 0.101 repetition. Assert no `book.json` or PDF is published.
- [ ] Generate twice and assert the second call does not invoke source-map batch/reduce methods. Change one source page and assert the cache invalidates.
- [ ] Preserve existing Book PDF assertions and inspect that internal ids do not appear in PDF text or public JSON.
- [ ] Add an opt-in real-provider smoke marker requiring `RUN_REAL_OPENROUTER_TESTS=1`. It uploads a small known PDF, verifies only structural/id/grounding properties, redacts prompts/keys, and skips with an explicit reason on missing credentials. A 402/403 quota response must fail the smoke test as `provider_unavailable`, not masquerade as document failure.
- [ ] Document source-only guarantees, cache versioning, re-embed/rebuild commands, metric definitions, threshold behavior, provider smoke setup, and rollback to the previous Book generator behind a temporary backend-only `BOOK_RAG_PIPELINE_VERSION` setting (`legacy` allowed only during rollout; production default `hierarchical_v1`). Remove the legacy switch after one stable release.
- [ ] Run the complete test gate:

```powershell
cd src/backend
uv run ruff check app tests
uv run pytest -q
uv run pytest tests/e2e/test_book_rag_quality.py -q
cd ..\frontend
npm test -- --run
npm run lint
npm run build
```

- [ ] With a funded test key, run only the opt-in smoke once in staging and record model id, prompt versions, source fixture hash, latency, token usage, metrics, and sanitized result. Never commit the key or full provider payload.
- [ ] Commit checkpoint if authorized: `git add README.md docs src/backend/tests/e2e src/backend/tests/fixtures; git commit -m "test: add grounded book quality evaluation"`.

## Final Verification

- [ ] Run `rg -n "web search|external source|general knowledge|internet" src/backend/app/prompts src/backend/app/services` and inspect every match for a strict prohibition, not an enabled path.
- [ ] Run `rg -n "source_chunk_ids|claim_ids|concept_ids|section_ids" src/frontend` and confirm raw internal ids are not rendered.
- [ ] Trace one factual sentence from final PDF to public Book JSON, reviewed chapter, evidence pack, chunk id, source filename, and page.
- [ ] Trace one deliberately absent fact and verify it never appears in source map, outline, evidence, draft after review, public JSON, or PDF.
- [ ] Review every cache key for course id/content hash/model/prompt/chunking versions and every filesystem resolution for course-directory containment.
- [ ] Review the diff for external calls, unbounded context, unvalidated model ids, silent legacy fallback, partial artifact publication, and changes to non-Book generation paths.
