# Plan A final fix report

## Result

Closed the three final recovery-boundary findings without changing Plan A documents
or the pre-existing `src/backend/Dockerfile` working-tree edit.

- OCR now classifies provider requests through `ProviderRequestError`: permanent
  authentication/payment/quota/access failures make one call, while transient OCR
  failures make at most two same-model calls. Typed failures cross PDF extraction and
  reach the existing durable course/job provider-failure path instead of becoming
  `DOCUMENT_TEXT_EXTRACTION_FAILED` / `upload_clearer_pdf`. Valid empty OCR responses
  still represent genuine no-text pages.
- A centralized recursive public-payload sanitizer removes grounding IDs, raw source/
  citation fields, debug fields, and technical metadata from both the aggregate Study
  Pack and all four individual artifact routes. It returns a new response copy; stored
  artifact JSON and course metadata remain unchanged for internal grounding.
- `apiFetch` now owns fetch, body-read, and successful-JSON parsing failures. Body
  `TypeError` becomes the fixed `ApiNetworkError`; `AbortError` remains unmodified;
  malformed, truncated, empty, null, or primitive successful JSON becomes the typed
  provider-neutral `ApiResponseError` (`INVALID_RESPONSE`). Structured non-2xx parsing
  and bodyless `204` behavior remain intact. The XHR upload path uses the same successful
  response parser and handles response reads, status `0`, abort, and timeout safely.

## RED evidence

Backend OCR/document tests before implementation:

```text
uv run --project . pytest tests/test_llm_real_parsing_contract.py tests/test_document_retry.py -q
7 failed, 63 passed, 1 skipped
```

The failures showed permanent OCR quota errors making two calls, OCR returning empty
instead of raising a typed provider failure, fully scanned files becoming extraction
failures, and mixed files continuing toward ordinary processing failure/ready behavior.

Study Pack sanitizer test before implementation:

```text
uv run --project . pytest tests/test_generation_service.py -q
collection error: cannot import name 'sanitize_public_payload'
```

Frontend response-boundary tests before implementation:

```text
npm test -- --run src/lib/api.test.ts 'src/app/course/[id]/page.test.tsx' src/hooks/usePollingArtifact.test.tsx
7 failed, 34 passed
```

The failures exposed raw response-body `TypeError`, raw successful JSON parse failures,
accepted primitive artifact payloads, XHR's generic malformed-success error, and the
missing XHR abort boundary.

## GREEN evidence

Backend focused OCR/provider/generation/Study Pack regression suite:

```text
uv run --project . pytest tests/test_provider_errors.py tests/test_provider_health.py tests/test_llm_real_parsing_contract.py tests/test_document_retry.py tests/test_vector_store_and_processor.py tests/test_generation_service.py -q
117 passed, 1 skipped, 390 warnings in 40.72s
```

Backend full suite and Ruff:

```text
uv run --project . ruff check .
All checks passed

uv run --project . pytest tests -q
201 passed, 1 skipped, 576 warnings in 58.88s
```

Frontend focused response/component coverage:

```text
npm test -- --run src/lib/api.test.ts 'src/app/course/[id]/page.test.tsx' src/hooks/usePollingArtifact.test.tsx
3 files passed, 43 tests passed
```

Frontend complete unit/component, static, and browser gates:

```text
npm test -- --run
15 files passed, 71 tests passed

npx tsc --noEmit --incremental false
exit 0

npm run lint
exit 0; 3 pre-existing @next/next/no-img-element warnings in SlideTab.tsx

npx playwright test --project=chromium --grep "document retry"
2 passed
```

## Coverage added

- Raw OCR quota `403` and transient `503` call counts in `LLMService`.
- Preflight-success followed by OCR provider failure for fully scanned and mixed PDFs,
  including internal persistence and provider-neutral public course status.
- Recursive sanitizer behavior and non-mutation of stored data.
- Aggregate plus individual Book/Slide/Quiz/Vid API responses containing nested legacy
  grounding/debug/technical fields in every artifact.
- Fetch response-body TypeError, truncated JSON, primitive artifact JSON, body abort,
  non-2xx body failure, `204`, and XHR malformed/read/abort/timeout behavior.
- Course-load, retry, and artifact-hook rendering assertions that parser/body diagnostics
  never reach visible state.

## Remaining concerns

- The one skipped backend test is the already-recorded Windows symlink-permission test.
- Pytest warnings are the existing Starlette/httpx and `datetime.utcnow()` deprecations.
- No paid live OpenRouter call was made; the ledger's zero-capacity live-smoke deferral
  remains unchanged.
- The two Plan B durability/lease items remain parked exactly as ruled in `progress.md`.
