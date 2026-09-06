# PDF-Only Grounded Book RAG Design

**Date:** 2026-09-01  
**Status:** Approved planning baseline  
**Scope:** Improve Book output quality while preserving strict source-only generation

## Problem

Book generation currently performs generic dense retrieval for the outline and independently retrieves a small context for each chapter. That can miss document-wide structure, overrepresent repeated sections, and produce locally plausible chapters without proving global coverage. Citation-id validation catches invalid ids but does not measure unsupported claims, omissions, or duplication.

The solution must improve information quality without adding web search, model memory, or facts not present in the uploaded PDF/document set.

## Non-Negotiable Grounding Rule

Every factual statement in the generated Book must be supported by text extracted from the current course's uploaded PDF, DOCX, or TXT files. For the requested PDF-only use case, no outside source is consulted at any pipeline stage. The LLM receives only system instructions, the user's formatting preferences, and selected source text/derived source-only structures.

If the source does not contain enough information, the Book must omit the claim or explicitly state that the uploaded material does not establish it. It must never fill the gap from model knowledge.

## Architecture

```text
Extracted page-aware chunks
  -> deterministic cleanup + heading metadata
  -> cached course Source Map
  -> chapter retrieval queries
  -> dense top-40 + lexical BM25 top-40
  -> reciprocal-rank fusion + diversity
  -> source-only evidence selector (max 16 chunks)
  -> chapter draft
  -> grounding review + one grounded revision
  -> whole-book coverage/duplication gate
  -> publish or fail safely
```

## Ingestion Metadata

Keep page boundaries during extraction. Each chunk stores:

- stable `chunk_id`
- source filename and page number
- `heading_path` inferred from nearby headings
- normalized text and SHA-256 content hash
- front-matter/noise flags
- preceding/following chunk ids

Do not merge text across source pages without retaining every contributing page. Re-embedding is versioned by `CHUNKING_VERSION`; changing the chunk contract requires the existing re-embed workflow.

## Source Map

Build and cache `indexes/source_map.json`, keyed by ordered chunk hashes, prompt version, and model id. It contains only source-derived data:

```json
{
  "documents": [{"source": "paper.pdf", "page_range": [1, 80]}],
  "sections": [{"section_id": "s1", "title": "...", "chunk_ids": ["..."]}],
  "concepts": [{"concept_id": "c1", "name": "...", "chunk_ids": ["..."]}],
  "claims": [{"claim_id": "cl1", "text": "...", "chunk_ids": ["..."]}],
  "glossary": [{"term": "...", "definition": "...", "chunk_ids": ["..."]}]
}
```

The builder batches at most 12 chunks per map call, validates that every returned id belongs to the batch, and performs one source-only reduce call. Invalid references are rejected. The source map is built once after successful ingestion and reused for Book regenerations until source hashes or the builder version change.

## Retrieval

For each planned chapter:

1. Generate 2-4 retrieval queries from its assigned source-map concepts and claim ids.
2. Retrieve the top 40 dense matches from Chroma for each query.
3. Retrieve the top 40 lexical BM25 matches from a course-local index.
4. Fuse results with reciprocal-rank fusion using `k=60`.
5. Deduplicate and apply diversity: no more than 4 neighboring chunks from one source window until all represented sections have one candidate.
6. Give at most 30 candidates to a source-only evidence selector.
7. Accept at most 16 evidence chunks, all referenced by existing ids.

The lexical index is an internal BM25 implementation persisted next to the course index; no hosted search service and no external corpus are introduced.

## Outline and Chapter Contracts

The outline is generated from the source map rather than an arbitrary top-20 retrieval. Every chapter plan declares:

- learning objective
- assigned `concept_ids` and `claim_ids`
- 2-4 retrieval queries
- expected source sections
- target word budget

The chapter draft receives only its chapter plan and evidence pack. It returns structured content plus `used_claim_ids` and `citation_ids`. Internal ids are removed from the public Book exactly as today.

## Grounding Review

After each draft, one verifier call receives the draft and the same evidence pack. It returns:

- a revised chapter containing only evidence-supported statements
- unsupported spans it removed or rewrote
- missing planned claim ids
- supported factual-claim ratio
- used source ids

This is the only revision pass, so each chapter has a maximum of two LLM calls after retrieval: draft and review/revision. All returned ids are checked against the evidence pack before acceptance.

After all chapters, a deterministic Book gate calculates:

- planned claim coverage
- represented source-section coverage
- supported factual-claim ratio aggregated from reviews
- invalid citation count
- repeated paragraph ratio using normalized shingles

Thresholds:

| Mode | Planned claim coverage | Supported ratio | Invalid ids | Repetition |
|---|---:|---:|---:|---:|
| `summary` | >= 0.70 | >= 0.95 | 0 | <= 0.10 |
| `standard` / `deep` | >= 0.85 | >= 0.95 | 0 | <= 0.10 |

If the gate fails, do not publish the Book. Store an internal `book.grounding.json` report and return `grounding_quality_below_threshold` with a user-safe explanation. Do not expose raw source ids or hidden prompts through the API.

## Cost and Latency Bounds

- Source-map work is cached by content hash.
- Evidence is capped at 16 chunks per chapter.
- Evidence selection uses one LLM call per chapter.
- Chapter drafting plus grounded review uses at most two calls per chapter.
- The existing OpenRouter-only model setting applies to every call; no hidden second provider is added.
- A failure to reach the quality gate is visible and retryable as a new version, not silently published.

## Frontend

- Book generation stays disabled until ingestion and the source map are ready.
- Status shows `Building source map`, `Planning coverage`, `Retrieving evidence`, `Writing chapter X of Y`, and `Checking grounding`.
- A successful Book may show aggregate `Source coverage` and `Grounding confidence`; raw internal ids remain hidden.
- A quality-gate failure explains that the uploaded document did not support enough of the planned Book and suggests changing depth or source documents.

## Evaluation Gate

Create a deterministic 80-page synthetic PDF fixture containing:

- exact facts distributed across early, middle, and late pages
- repeated headers/footers and a table of contents
- two near-duplicate sections
- deliberately absent facts that a general model commonly knows
- conflicting statements clearly attributed to different sections

The evaluation must verify:

1. Facts from all page regions appear when assigned to the outline.
2. Absent facts are omitted or explicitly marked unsupported.
3. Every internal id belongs to the course and evidence pack.
4. Threshold calculations match known pass/fail fixtures.
5. A prompt injection embedded in the PDF cannot enable web/model-knowledge supplementation or reveal system instructions.
6. A second generation reuses the unchanged source map.
7. The current Book PDF export and connected Study Pack behavior remain valid.

## Out of Scope

- Web search or external reference enrichment.
- Fine-tuning a model.
- Replacing Chroma in this release.
- Applying the full hierarchical pipeline to slides, quizzes, or video; they may consume the cached source map in a later change.
