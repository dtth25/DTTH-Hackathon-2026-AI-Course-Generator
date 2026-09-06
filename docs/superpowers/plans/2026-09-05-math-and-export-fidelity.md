# Math and Export Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve equations, symbols and multilingual text consistently in Study Guide, Slide, Quiz and Video, and prevent invalid exports from being published.

**Architecture:** Preserve canonical Markdown/LaTeX in stored artifacts and use a real, locally bundled math renderer for display. Render rich-text blocks into images for existing ReportLab/Pillow composition, retaining the exact slide images shared by the viewer/PPTX/PDF. Handle narration separately, validate completed files before atomic publication, and enforce a common Windows/Linux semantic and visual fixture suite.

**Tech Stack:** Existing React Markdown/remark-math/rehype-katex, KaTeX 0.16.47, local Chromium/Playwright, ReportLab, PyMuPDF, python-pptx, Pillow and FFmpeg.

**Spec:** [Audit findings and required outcomes](2026-09-05-generation-audit-findings.md). Source extraction requirements are implemented by [RAG/source Task 1](2026-09-05-rag-and-source-fidelity.md).

**Budget dependency:** The [balanced Book budget plan](2026-09-05-balanced-book-budget.md) limits each Book to $0.10 including generated repairs, review and retries. Rendering/font fixes run locally and should not trigger paid regeneration when stored canonical content already suffices. Model changes must pass this plan's equation-fidelity gates.

## Global Constraints

- Preserve source equations and table contents; unsupported extraction must report incomplete coverage.
- Four existing generation endpoints only; preserve auth/ownership, authenticated downloads, no public raw source IDs, three-version cap and atomic publication/lease fencing.
- Viewer, PPTX and slide PDF use the same rendered slide image. Keep expand/collapse and existing visual design tokens.
- Every executed test reports estimated and actual provider cost. Offline checks deny provider network calls.
- Book target: $0.05–$0.09 OpenRouter spend; hard user ceiling: $0.10 per logical Book generation, including generation-triggered retrieval, source-plan creation, reasoning, review, repair and retries. Spending less than $0.05 is welcome.
- Keep the selected paid OpenRouter model and one same-model content/OCR retry.
- No commits, push, or deployment without a separate user instruction. Review the diff after each task instead of committing.

## File and interface map

| Files | Responsibility |
| --- | --- |
| `src/backend/app/services/generator.py`, `text_format.py`, `pdf_utils.py` | Stop destructive display cleanup, retain canonical content |
| New `src/rendering/package.json`, lockfile, `render-rich-text.mjs`, `fonts/manifest.json`; new `src/backend/app/services/rich_text_render.py` | Local math/text image generation with pinned fonts and bounded resource use |
| `src/backend/Dockerfile`, `src/frontend/src/components/ui/markdown.tsx` | Bundle runtime/font assets and align accepted markup contracts |
| `src/backend/app/services/pdf_book.py`, `generator.py`, `video_render.py` | Compose rendered text/math blocks in each artifact |
| New `src/backend/app/services/artifact_validation.py` | Reopen/validate files before publishing ready |
| New `tests/fixtures/math/` at root, `src/backend/tests/test_math_fidelity.py`, `src/frontend/e2e/math-fidelity.spec.ts` | Shared semantic corpus, visual checks and failure fixtures |

Use a separate internal rendering package because the backend Docker build uses `src` as its build context and does not ship frontend `node_modules`. Pin exact package/browser versions in the implementation lockfile; do not depend on fonts installed incidentally on the host or fetch assets from a CDN during rendering.

### Task 1: Preserve canonical math and reject lossy normalization

**Files:** Modify `generator.py:_clean_slides_output/_clean_vid_output`, `text_format.py`, display call sites; create corpus and `test_math_fidelity.py`.

**Interfaces:** Stored `SlidesOutput` and `VidOutput` retain original math in every display field. Define `normalize_narration(text: str) -> str` for speech-only cleanup. Its result must never replace display content or persisted source math.

- [ ] Add a corpus shared by tests and render previews:

```json
[
  {"id":"fraction","text":"$\\frac{a+b}{c+d}$"},
  {"id":"nested-fraction","text":"$\\frac{1}{\\frac{2}{3}}$"},
  {"id":"root","text":"$\\sqrt{x+1}$"},
  {"id":"exponent","text":"$x^{a+b}$"},
  {"id":"matrix","text":"$\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}$"},
  {"id":"integral","text":"$\\int_0^1 x^2\\,dx=\\frac{1}{3}$"},
  {"id":"glyphs","text":"Tiếng Việt: đạo hàm. 𝛼 ∑ ℝ ∇ ∀ ₁ ᵢ 中文"},
  {"id":"literal-question","text":"Giá trị x là bao nhiêu?"}
]
```

- [ ] Write a failing test around slide/video cleaning and JSON persistence. The literal canonical fraction must round-trip unchanged:

```python
deck.slides[0].bullet_points = [r"$\frac{a+b}{c+d}$"]
cleaned = _clean_slides_output(deck)
assert cleaned.slides[0].bullet_points[0] == r"$\frac{a+b}{c+d}$"
assert SlidesOutput.model_validate_json(cleaned.model_dump_json()) == cleaned
```

- [ ] Run the failing corpus/persistence tests with fake key ($0). Replace display-path `clean_text` use with safe whitespace/control-character normalization that preserves braces, backslashes, delimiters and Unicode. Retain speech normalization only in TTS inputs. Do not attempt to reconstruct formulas already destroyed in old stored slide/video versions; report those versions as legacy and regenerate explicitly when requested.
- [ ] Add parsing tests for `$...$`, `$$...$$`, escaped dollars, currency, code spans and alternate `\(...\)`/`\[...\]` delimiters. Normalize alternate delimiters only outside code/escaped text; do not use an indiscriminate global replacement. Unsupported macros surface a controlled rendering failure with the equation preserved for correction.
- [ ] Run all text-format and frontend Markdown tests ($0). Update tests that currently bless destructive simplification; do not merely change expected strings to another lossy form.

### Task 2: Build a shared local rich-text renderer with bundled fonts

**Files:** New rendering package and Python wrapper; modify backend Dockerfile and frontend parser contract tests.

**Interfaces:** `render_rich_text(markdown: str, width_px: int, font_px: int, theme: str) -> RenderedBlock`; `RenderedBlock` contains `png_path`, `width_px`, `height_px`, `math_count`, `unsupported_codepoints` and `renderer_revision`. The internal Node process accepts bounded JSON input and returns bounded JSON metadata with local image output. It exposes no generation endpoint and no public HTML execution surface.

- [ ] Add renderer tests that use real local KaTeX and Chromium, block outbound requests, and assert grouped fractions create KaTeX fraction structure and no parse error. Test raw HTML, links to remote images, extremely long expressions, unsupported macros, missing fonts and render timeout.

```js
import katex from "katex";
import assert from "node:assert/strict";
const html = katex.renderToString(String.raw`\frac{a+b}{c+d}`, {
  throwOnError: true, trust: false, strict: "error",
  output: "htmlAndMathml", maxExpand: 1000,
});
assert.match(html, /class="mfrac"/);
assert.match(html, /<mfrac>/);
```

- [ ] Implement a locally bundled Markdown/GFM/math pipeline matching the frontend's supported syntax: parse Markdown, remark-math, convert to safe HTML, rehype-katex with strict error reporting, and serialize. Disable arbitrary raw HTML and remote image loading. Keep KaTeX `trust=false`, expansion/depth limits and input-size limits. Use the same fixture corpus against frontend and export parsing to prevent drift.
- [ ] Bundle the existing KaTeX font assets plus licensed text fonts covering Vietnamese, mathematical Unicode and CJK. Record exact font filenames, hashes, license locations and supported codepoints in `fonts/manifest.json`. CSS explicitly orders those bundled families. Use fontTools cmap checks before rendering ordinary Unicode text; an unsupported character must remain identifiable and cause a safe error/warning, never silently become `?`. Literal source question marks remain valid.
- [ ] Render each block in an isolated local browser page with scripts from document content disabled, all network blocked, `await document.fonts.ready`, fixed device scale and deterministic page dimensions. Bound render duration to 20 seconds per block, maximum dimensions to 4096×8192 pixels and input to 100,000 characters; return a safe limit error rather than exhaust a worker. Reuse one browser per worker with a bounded page pool, restart it after crash, and close pages in `finally`.
- [ ] Cache output by canonical content + parser/font revision + theme + width + font size. Keep generated paths under the job-owned temporary artifact directory, validate resolved paths before reading/writing, and discard output when the job loses its claim. User content may not select filesystem paths.
- [ ] Run renderer and parser tests on Windows and the production Linux image without paid APIs ($0). Inspect every corpus expression visually; DOM success alone cannot detect clipping or missing glyphs. Record renderer/fonts/browser versions with screenshots.

### Task 3: Integrate faithful rendering into all four artifact outputs

**Files:** Modify `pdf_book.py`, `pdf_utils.py`, `generator.py` slide/quiz renderers and `video_render.py`; extend existing PDF/video tests and new `test_math_fidelity.py`.

**Interfaces:** All static display consumers use `render_rich_text` from Task 2 for rich-text/math blocks. Existing slide images remain the canonical presentation output shared by web/PDF/PPTX. Narration consumes `normalize_narration` from Task 1; its wording is independently checked against the displayed equation.

- [ ] Create a fake-provider pack with the same fixture equation in Book sections, slide bullet, quiz stem/options/explanation and video on-screen text/diagram labels. Verify stored canonical strings are unchanged in every artifact and each display calls the rich-text renderer.

```python
formula = r"$\frac{a+b}{c+d}$"
assert book.chapters[0].sections[0].content == formula
assert slides.slides[0].bullet_points[0] == formula
assert quiz.questions[0].explanation == formula
assert video.scenes[0].on_screen_text == formula
```

- [ ] Replace text-cleaning shortcuts in Book and Quiz PDF blocks with ReportLab image flowables for math/rich blocks, preserving paragraph spacing, headings and page breaks. Split at safe block boundaries; a block too tall for a page gets a clear layout error or a supported multi-block layout, not silent clipping. Keep accessible/source text alongside raster blocks where the PDF library supports it; document text-selection limitations.
- [ ] Render slide titles/bullets/labels faithfully before assembling the slide image; ensure viewer/PPTX/PDF embed exactly that image. For Video, replace single-font Pillow text drawing for rich content with the same rendered blocks. Verify title, key points and diagram labels, not only the main paragraph.
- [ ] Add a speech-specific equation fixture: grouped numerator/denominator must be spoken with grouping rather than flattened ambiguous arithmetic. Stub TTS with silence for offline MP4 tests and record the exact narration text separately. Real TTS listening is a separate validation step with its own service-cost disclosure.
- [ ] Render a complete tiny PDF/PPTX/Quiz PDF/MP4 pack locally with no provider calls ($0). Inspect screenshots/PDF pages and actual decoded MP4 frames on Windows/Linux. Assert math is not clipped, superscripts/denominators are positioned correctly, Vietnamese/CJK glyphs are present, and the same slide image is reused in exports. These checks are required even when the previous 35 helper tests pass.

### Task 4: Fail safely on invalid files and enforce semantic/visual gates

**Files:** New `artifact_validation.py`, new `tests/test_artifact_validation.py`; modify generator export exception handlers and ready publication.

**Interfaces:** `validate_artifact(path: Path, kind: str, expected_pages: int | None = None) -> None` raises a typed safe failure on malformed output. Validation runs before `_publish_ready_version`; the previous good version remains active if any new output fails.

- [ ] Write regression tests that force ReportLab/python-pptx exceptions and prove no plaintext `.pdf`/`.pptx` is published. Use actual parsers, not just file existence:

```python
bad_pdf = tmp_path / "bad.pdf"
bad_pdf.write_text("Study guide placeholder", encoding="utf-8")
with pytest.raises(ArtifactValidationError):
    validate_artifact(bad_pdf, "pdf")
assert previously_active_version == current_active_version
```

- [ ] Delete plaintext export fallbacks. For PDF reopen via PyMuPDF and require nonzero pages; for PPTX reopen via `Presentation` and require expected image-bearing slides; for images decode and require nonzero dimensions; for MP4 use FFmpeg/ffprobe or the installed decoder to verify duration, video stream, nonempty frames and required audio stream. Reject empty slide-image lists and mismatched slide counts.
- [ ] Retain atomic temporary-directory publication and live-claim fencing. Surface a safe artifact render error with a retry path; do not return raw renderer stack traces, internal paths or source IDs. A failed new version must not destroy the old one.
- [ ] Run full relevant backend tests and frontend math visual tests. Gate: 100% canonical equation round-trip for the corpus, zero silent unsupported-glyph substitutions, zero malformed published artifacts, and human-reviewed visual parity for all four formats on Windows/Linux. Broader arbitrary documents remain subject to explicit unsupported-content errors; do not promise every possible symbol/font is supported.
- [ ] After source-fidelity and runtime cost work pass, perform one budgeted real heavy-symbol source smoke. First calculate/reserve its input/output/retry/OCR/embedding bound and report it. Compare generated claims/equations to the source, not just the screenshot. Do not infer the cost from the historical tiny TXT smoke and do not repeat the expensive run merely to obtain a cleaner report.

## Completion gate

- [ ] Backend ruff/pytest, frontend lint/tests/build, renderer tests and production image render checks pass.
- [ ] Record artifact previews, semantic/visual corpus results, exact service cost, and unsupported-format limitations. No source symbols may be silently removed to make a test pass.
- [ ] Keep authenticated downloads, slide image parity and existing version behavior verified. No commit/push/deployment during this planning request.
