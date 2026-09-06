# RAG and Source Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve source meaning, reliably use the intended Chroma embeddings, and replace misleading RAG ratings with traceable evidence and measured quality.

**Architecture:** Preserve extracted text/math/table blocks and an explicit extraction coverage report before indexing. Keep course-isolated Chroma as the vector store, make embedding identity/batching/cache real, and evaluate retrieval on a labeled corpus. Build one versioned source plan for the four artifacts so definitions, objectives and equations agree.

**Tech Stack:** Python, PyMuPDF, python-docx/OOXML, Chroma, OpenRouter embeddings, Pydantic, SQLAlchemy, pytest, React.

**Spec:** [Audit findings and required outcomes](2026-09-05-generation-audit-findings.md).

**Budget dependency:** Follow the [balanced Book budget plan](2026-09-05-balanced-book-budget.md) for Book-triggered embeddings, source-plan creation, evaluation/review and retries. Their costs are included in one Book budget; do not hide them in a separate RAG call. The proposed Book model change is quality-gated and does not change the embedding model by itself.

## Global Constraints

- Four existing generation endpoints only; preserve auth/ownership, authenticated downloads, no public raw source IDs, three-version cap and atomic publication/lease fencing.
- Chroma remains the real vector store. No claim that structural scores equal factual accuracy or retrieval quality.
- Preserve source equations and table contents; unsupported extraction must report incomplete coverage.
- Every executed test reports estimated and actual provider cost. Offline checks deny provider network calls.
- Book target: $0.05–$0.09 OpenRouter spend; hard user ceiling: $0.10 per logical Book generation, including generation-triggered retrieval, source-plan creation, reasoning, review, repair and retries. Spending less than $0.05 is welcome.
- Keep the selected paid OpenRouter model and one same-model content/OCR retry.
- No commits, push, or deployment without a separate user instruction. Review the diff after each task instead of committing.

## File and interface map

| Files | Responsibility |
| --- | --- |
| New `src/backend/app/schemas/source_document.py`, `services/docx_extract.py`, `services/extraction_quality.py` | Canonical block types, DOCX OOXML extraction, per-page coverage |
| Modify `services/document_processor.py`, `services/llm.py`, `schemas/course.py` under `src/backend/app` | Index canonical blocks, targeted OCR, safe coverage response |
| Modify `src/backend/app/services/vector_store.py`; new `services/embedding_cache.py` | Explicit embedding identity, bounded batching and content cache |
| Modify `src/backend/app/schemas/generator_output.py`, `schemas/generation.py`, `services/generator.py`; frontend `lib/types.ts` and quality widgets found via `rg quality_score` | Honest rating semantics and scoped evidence validation |
| New `src/backend/app/services/retrieval.py`, `tests/fixtures/rag/manifest.json`, `scripts/evaluate_rag.py` | Query selection, deduplication, evaluation and distance calibration |
| New `src/backend/app/schemas/source_plan.py`, `services/source_plan.py` | A versioned shared curriculum/evidence plan consumed by all artifacts |

Cost/latency recording uses the `record_provider_call` interface from Task 3 of the [runtime plan](2026-09-05-live-progress-and-capacity.md). Implement that before paid embedding or OCR evaluation.

### Task 1: Preserve DOCX/PDF/TXT content and report extraction coverage

**Files:** New extraction modules above; modify `document_processor.py:extract_text_with_metadata`, OCR boundary in `llm.py`; new `tests/test_source_fidelity.py`.

**Interfaces:** Define `SourceBlock(kind, text, math_latex, source_file, page, location)`; `kind` is `paragraph|table|math`. `location` is an internal document position, not a claimed physical page for DOCX. Define `ExtractionReport(total_pages, extracted_pages, ocr_pages, skipped_pages, damaged_pages, warnings, complete)`. Only cleaned page/excerpt and safe aggregate coverage are public.

- [ ] Build an actual synthetic DOCX fixture with a paragraph, table and Office Math node, then assert each survives extraction. Use the real ZIP/XML parser with no model calls:

```python
from docx import Document
from docx.oxml import parse_xml

doc = Document()
p = doc.add_paragraph("Equation: ")
p._p.append(parse_xml(
    '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
    '<m:r><m:t>x+y=2</m:t></m:r></m:oMath>'
))
doc.add_table(rows=1, cols=1).cell(0, 0).text = "Critical value: alpha = 42"
doc.save(tmp_path / "math.docx")
blocks, report = extract_docx(tmp_path / "math.docx")
assert any(b.math_latex == "x+y=2" for b in blocks)
assert any("alpha = 42" in (b.text or "") for b in blocks)
assert report.complete
```

- [ ] Run the new test and capture its failing baseline ($0). Add PDF fixtures containing one scan inside text pages, a high-character damaged-symbol page, and more than 12 scan pages. OCR must be an injected stub. Add invalid UTF-8, malformed PDF/DOCX and DOCX nested table/fraction cases.
- [ ] Implement `extract_docx(path: Path) -> tuple[list[SourceBlock], ExtractionReport]` by walking document body paragraph/table nodes in document order, recursively preserving table cell contents and OMML runs. Convert supported OMML fractions, roots, sub/superscripts, n-ary operators and matrices into canonical LaTeX with braces. Unknown OMML nodes produce an extraction warning with location and `complete=False`, never silent deletion. Limit XML parsing to the uploaded ZIP parts; do not resolve external relationships/entities.
- [ ] Implement per-page PDF assessment before indexing: replacement/private-use glyph counts, empty-span ratio, missing-image-only pages, and suspicious reading-order/math spans. Make OCR decisions per page, not only from whole-document scan-majority. Preserve page coordinates internally and record OCR usage/latency. On cap/truncation, keep partial extraction but report missing pages and prevent a claim of complete coverage. A 4096-token OCR response with `finish_reason=length` is incomplete, not successful extraction.
- [ ] Remove production binary-to-text fallbacks. Use strict UTF-8 (including UTF-8 BOM) for TXT and return a safe encoding error for undecodable input; fixtures using fake binary extensions must be replaced with valid files. Document bytes, extracted text and model outputs never become instructions to the agent or tools.
- [ ] Run source-fidelity, document-processor and OCR contract tests with fake provider/no network ($0). Inspect the generated source fixture and canonical output side-by-side. Gate: no table/equation silently disappears; every omitted/damaged page is counted.

### Task 2: Make embedding identity, batching and cache explicit

**Files:** Modify `vector_store.py`; create `embedding_cache.py` and `tests/test_embedding_pipeline.py`; extend `core/config.py` only when a consumed setting is needed.

**Interfaces:** `embed_texts(texts: list[str], *, model: str, dimensions: int, cache_scope: str) -> list[list[float]]`; `embedding_key(text, model, dimensions, normalization_version) -> str`. Require explicit injected local embedding function in tests; production initialization fails if OpenRouter embedding setup is unavailable.

- [ ] Write tests using a recording fake embedding client for 65 chunks with batch size 32. Expect calls sized `[32,32,1]`, stable output order, then zero new provider calls for a repeated batch. Test model/dimension change, partial batch failure, 403 quota rejection and corrupted cache entries.

```python
assert fake_client.batch_sizes == [32, 32, 1]
assert len(vectors) == 65
assert all(len(v) == expected_dimensions for v in vectors)
assert repeated_vectors == vectors
assert fake_client.batch_sizes == [32, 32, 1]
```

- [ ] Implement a versioned cache key over the exact normalized embedding input plus model/dimension/version. Hash the full content, not a prefix. Store vector bytes and dimensions with atomic writes; validate finite values and reject mismatched cache entries. Scope storage by tenant/course or use an internal shared cache with no user lookup/timing interface. Keep source ownership/provenance on every Chroma record even when vectors are reused.

```python
def embedding_key(text, model, dimensions, normalization_version):
    payload = json.dumps([model, dimensions, normalization_version, text],
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [ ] Batch cache misses using the configured batch size and existing retry/capacity classification. Validate response indices, count and dimensions before upsert. Persist successful batch checkpoints so a later batch failure does not charge for earlier embeddings again. Record actual embedding usage through the runtime plan's provider ledger.
- [ ] Remove implicit production fallback to Chroma's default embeddings. Store/check model, dimensions, normalization and distance metric with collection identity; fail clearly on mismatch and require an explicit new-index migration. Preserve the current collection; do not delete or silently re-embed it.
- [ ] Run tests with a real temporary Chroma collection and deterministic injected vectors; verify insertion, restart persistence, course filtering and deletion ($0). This validates real storage behavior, not semantic performance. Later verify the intended OpenRouter embedding model with a separately budgeted tiny smoke.

### Task 3: Replace inflated ratings and evaluate retrieval honestly

**Files:** Modify `generator_output.py:validate_and_score_output`, `generator.py:_retrieve_context`; create `retrieval.py`, `scripts/evaluate_rag.py`, fixture manifest and tests; update frontend quality copy/types.

**Interfaces:** `QualityReport(structural_validity, citation_validity, source_coverage, extraction_complete, faithfulness)` where absent empirical `faithfulness` is `None`, never an invented percentage. `retrieve_evidence(course_id, query, k, calibration) -> list[Document]` retains current ownership and public-redaction boundaries.

- [ ] Add failing tests proving any citation against an empty allowed set is invalid, missing citations are reported, and chapter A cannot cite evidence only retrieved for chapter B. Retain exact evidence sets per generated unit. Structural validation must not silently relabel a false arithmetic statement as factually verified.

```python
_, _, warnings = validate_and_score_output(deck, "slides", valid_chunk_ids=[])
assert warnings
assert report.faithfulness is None
assert report.citation_validity == 0
```

- [ ] Replace the chunk-count quality percentage with extraction completeness and indexed-chunk counts. Retain legacy numeric fields only for compatibility, explicitly labeled structural checks; update frontend labels/help to remove claims of factual accuracy. Show "not evaluated" for missing benchmark measurements.
- [ ] Fix deduplication by hashing full normalized content; preserve distinct chunks sharing headers. Exclude front matter/noise even when it is the only retrieved content, return a source-insufficient result, and query by document/topic coverage before assembling a Book outline. Retain similarity rank during selection, then source-sort for coherent prompt presentation.

```python
normalized = " ".join(doc.content.casefold().split())
digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

- [ ] Create a labeled, version-controlled corpus of at least 30 questions over 10 small owned/synthetic documents: Vietnamese, English, equations, tables, near-duplicate headers, unanswerable questions and mixed scans. Each case stores source document hash, query, relevant pages/blocks, expected answer facts and exact equations. Example record:

```json
{"id":"fraction-grouping","document":"fractions.txt","query":"What is the grouped ratio?","relevant_pages":[1],"required_facts":["numerator a+b","denominator c+d"],"equations":["\\frac{a+b}{c+d}"]}
```

- [ ] Implement `evaluate_rag.py` to report recall@k, precision@k, document/topic coverage, unsupported-answer rate, citation correctness and equation fidelity with corpus/model/index version and sample counts. Compute recall as `relevant_retrieved/relevant_total`; unanswerable cases are reported separately, not divided by zero. Split calibration and held-out cases; never tune thresholds on the reported held-out set.
- [ ] Calibrate any Chroma `max_distance` using the actual configured distance metric and OpenRouter embedding model. Compare vector-only retrieval against an optional lexical candidate merge only if the baseline misses math identifiers. Do not hard-code an arbitrary similarity cutoff or add a paid reranker without measured benefit. [Chroma query/filter contract](https://docs.trychroma.com/docs/querying-collections/query-and-get), [distance configuration](https://docs.trychroma.com/docs/collections/configure?lang=typescript).
- [ ] Run mechanics tests entirely offline ($0). Semantic embedding and generated-answer evaluation are separate paid experiments with the runtime ledger and conservative preflight reservation. Human-reviewed labels are the reference; an LLM judge is optional, separately costed and never the sole truth. Proposed release gates: no cross-course evidence, no empty-evidence grounding boost, 100% fixture equation preservation and all score labels honest; report empirical recall/faithfulness before setting a production quality threshold.

### Task 4: Share curriculum, definitions and equations across the pack

**Files:** Create `schemas/source_plan.py`, `services/source_plan.py`, `tests/test_source_plan.py`; modify `generator.py` and four existing feature prompts.

**Interfaces:** Define `SourcePlan(revision, source_digest, objectives, glossary, equations, units)`; each unit has a stable internal ID, title and evidence IDs. `get_or_create_source_plan(course_id, source_digest, model, prompt_revision) -> SourcePlan` is ownership-scoped, stored once and reused by all four feature paths. Content generation still uses the four existing endpoints.

- [ ] Add a deterministic test in which Book, Slide, Quiz and Video start from the same source plan and use the same equation/definition for one concept. Change source digest and assert all future generations bind the new revision while old artifact versions remain readable.

```python
assert len({book.plan_revision, slides.plan_revision,
            quiz.plan_revision, video.plan_revision}) == 1
assert plan.equations[0].latex == r"\frac{a+b}{c+d}"
assert all(unit.evidence_ids for unit in plan.units)
```

- [ ] Implement atomic source-plan creation keyed by course/source digest/model/prompt revision, with a database uniqueness/lock strategy for concurrent feature starts. Reuse the Book outline where compatible; do not automatically generate a full Book before every Quiz. Persist plan provenance internally, and supply only the relevant units/evidence to each feature's prompt.
- [ ] Keep source content untrusted and restrict any future retrieval tools to owned indexed sources. Do not add unrelated web search/chat or tool use merely to increase feature count. Validate each output against its assigned unit evidence and preserve canonical equations; cross-artifact consistency is separate from factual correctness.
- [ ] Test concurrent plan creation, version retention/deletion, source change invalidation, citation redaction and selected-model consistency with fake providers ($0). Run one capped real connected-pack smoke only after math/export work passes, using the shared cost ledger.

## Completion gate

- [ ] Backend ruff/pytest and frontend lint/tests/build pass after implementation; browser shows honest extraction/quality states without raw IDs.
- [ ] Publish a dated evaluation report with corpus size, configuration, actual scores, limitations and cost. No claim of "good RAG" based solely on a Chroma count or an 80/90/100 structural score.
- [ ] Keep existing data readable and provide an explicit reindex/migration path; no automatic destructive reindex of user courses.
