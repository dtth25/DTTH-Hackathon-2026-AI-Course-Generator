# Balanced Book Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Target $0.05–$0.09 OpenRouter spend per Book, never intentionally authorize more than $0.10, while retaining useful depth, source coverage and mathematical correctness with lower latency.

**Architecture:** Add a durable per-Book budget before optimizing prompts or changing models. Evaluate paid Gemini 2.5 Flash as the balanced Book model, use compact evidence and adaptive chapter budgets, reuse checkpoints, and reserve costs for reasoning, review and retries before sending concurrent requests. Promote the candidate only when source-based quality and actual cost/latency gates pass.

**Tech Stack:** Existing OpenRouter Python SDK, Pydantic, SQLAlchemy/PostgreSQL, Chroma, pytest, Decimal accounting and the current Book/PDF pipeline.

**Spec:** [Audit findings, including the user's revised budget](2026-09-05-generation-audit-findings.md). This plan refines the [runtime plan](2026-09-05-live-progress-and-capacity.md) and takes precedence over its earlier unbounded Book token assumptions.

## Global Constraints

- Book target: $0.05–$0.09 OpenRouter spend; hard user ceiling: $0.10 per logical Book generation, including generation-triggered retrieval, source-plan creation, reasoning, review, repair and retries. Spending less than $0.05 is welcome.
- Preserve useful source coverage and math fidelity. Never silently publish a truncated or incomplete Book merely to meet the price.
- Keep OpenRouter paid-only. Select the model once per Book; never switch to a more expensive model during error recovery. Allow at most one same-model retry per content/OCR call, only when its cost fits the remaining reservation.
- Every executed test reports estimated and actual provider cost. No paid provider in load tests.
- Preserve four generation endpoints, auth/ownership, three versions, internal citation provenance, public metadata redaction and atomic publication.
- No runtime settings, keys, user data, commits, push or deployment change during this planning revision.

## Decision and cost envelope

The user's approximately **$0.60 per Book** is user-reported; previous auditing did not obtain a response-level bill for that particular Book. Treat it as the baseline to beat, not a newly measured charge.

Recommended candidate: **`google/gemini-2.5-flash` for Book outline, chapters and any small review call**. Do not default to Flash-Lite solely because it is cheaper, and do not introduce Pro escalation under this tier. Compare against existing Pro artifacts and the original source. The current all-Pro default remains unchanged until this plan is implemented and evaluated; the user's new balancing request permits planning a different default.

Verified 2026-09-05 standard text pricing:

| Model | Input USD / 1M tokens | Output USD / 1M tokens |
| --- | ---: | ---: |
| Gemini 2.5 Pro | 1.25 | 10.00 |
| Gemini 2.5 Flash | 0.30 | 2.50 |

Source: [OpenRouter comparison](https://openrouter.ai/compare/google/gemini-2.5-flash/google/gemini-2.5-pro). Rates can differ by provider/tier/context; refresh the eligible endpoint rates before admission. A roughly fourfold token-price reduction alone would turn $0.60 into about $0.15 at unchanged token volume, which still misses the target. Reduce duplicated input/output work as well.

**Illustrative budget, not a measured bill:**

| Allocation | Assumption | USD |
| --- | --- | ---: |
| Outline + chapter input | 40,000 total billable tokens | 0.012 |
| Outline + chapter output | 18,000 total billable tokens, including reasoning and JSON | 0.045 |
| Query embeddings | Reserved allowance, settle at actual cost | 0.001 |
| Focused verification | Reserved allowance, local checks first | 0.008 |
| Same-model repair/retry reserve | Used only when needed | 0.024 |
| Internal safety margin | Not available for discretionary generation | 0.005 |
| **Internal admitted maximum** | Sum of all allocations | **0.095** |

Normal illustrated spend is about **$0.058–$0.066**, rising toward $0.09 if repair is needed. These token counts are a feasible design envelope to test, not an assertion that the user's deep guide fits it. Whole-document ingestion/OCR already paid before this Book is separately reported; any new OCR/reindex/source-plan call triggered by the Book must count inside its limit. Report both incremental Book cost and first-use upload+Book cost so ingestion costs are not hidden. Hosting, CPU and storage are outside the OpenRouter-credit target and must not be labeled free infrastructure.

There is no unconditional guarantee of both arbitrary document depth and successful completion under $0.10. Preflight must reject a scope whose honest upper bound cannot fit; do not silently shorten the requested deep option. Failed attempts count against the same logical budget and must be included when reporting cost per successful Book.

## File and interface map

| Unit | Files | Responsibility |
| --- | --- | --- |
| Budget policy | New `src/backend/app/services/book_budget.py`, `models/book_budget.py`, Alembic migration, `tests/test_book_budget.py` | Durable monetary limit, atomic reservation and settlement |
| Provider cost | `src/backend/app/services/provider_usage.py` from runtime Task 3; `services/llm.py`, `services/vector_store.py` | Actual usage even on invalid JSON; bounded routing/pricing |
| Content planning | New `src/backend/app/services/book_content_budget.py`; `prompts/book_outline.txt`, `prompts/book_chapter.txt`, `schemas/generator_output.py`, `services/generator.py` | Adaptive evidence/chapter allocation and nontruncating generation |
| Resumability | `src/backend/app/services/book_checkpoint.py` from runtime Task 4, `services/job_service.py`, `jobs/tasks.py` | Reuse validated work; one logical budget across retries |
| Evaluation | New `src/backend/scripts/evaluate_balanced_book.py`, `tests/test_book_content_budget.py`, `tests/fixtures/book_budget/manifest.json`, `docs/book-budget-results.md` | Source-based quality/cost/latency comparison and promotion gate |

Do not create a second provider ledger: extend the runtime plan's provider-call records. Existing generation responses may expose safe delay/budget errors, not raw prices/models/provider traces in learner flows.

### Task 1: Enforce one durable budget across concurrent calls and retries

**Interfaces:** `estimate_call_usd(input_bound: int, output_bound: int, input_price: Decimal, output_price: Decimal, fixed_fees: Decimal = Decimal("0")) -> Decimal`; `reserve_call(budget_id: str, call_id: str, upper_bound_usd: Decimal) -> bool`; `settle_call(call_id: str, actual_usd: Decimal | None) -> None`. `budget_id` belongs to an owned Book version and survives job/worker retries. API resubmission with `retry_version_id` reuses this ID; only explicit creation of a new version gets a new budget.

- [ ] Add failing arithmetic and reservation tests:

```python
from decimal import Decimal as D

def test_book_price_envelope():
    assert estimate_call_usd(40_000, 18_000, D("0.30"), D("2.50")) == D("0.057")

def test_budget_includes_all_live_calls():
    assert can_reserve(D("0.06"), D("0.02"), D("0.016"), D("0.095")) is False
    assert can_reserve(D("0.06"), D("0.02"), D("0.015"), D("0.095")) is True
```

- [ ] Run `uv run --no-sync pytest tests/test_book_budget.py -q` from backend with fake key/no provider network ($0); expect missing policy behavior to fail.
- [ ] Implement Decimal arithmetic and atomic DB reservations. Use a row lock/conditional transaction; never let two chapters independently see the same unused balance. Reference policy functions:

```python
from decimal import Decimal

def estimate_call_usd(input_bound, output_bound, input_price, output_price,
                      fixed_fees=Decimal("0")):
    if input_bound < 0 or output_bound < 0:
        raise ValueError("Token bounds must be nonnegative")
    if any(not v.is_finite() or v < 0 for v in (input_price, output_price, fixed_fees)):
        raise ValueError("Prices must be finite and nonnegative")
    return (Decimal(input_bound) * input_price + Decimal(output_bound) * output_price) / Decimal(1_000_000) + fixed_fees

def can_reserve(spent, reserved, next_cost, ceiling):
    values = (spent, reserved, next_cost, ceiling)
    return all(v.is_finite() and v >= 0 for v in values) and spent + reserved + next_cost <= ceiling
```

- [ ] Include every prompt/schema/source token and fixed provider fee in the input bound. Use a verified model tokenizer or calibrated conservative upper bound, including non-ASCII Vietnamese and math. If a reliable bound or price is unavailable, do not admit the paid call. Treat reasoning as billable output; confirm the endpoint's output-limit semantics and reserve reasoning separately if it is not included in the advertised cap. Do not assume `reasoning.exclude` saves tokens.
- [ ] Reserve the remaining required chapters and repair allowance before starting optional review. Settle actual costs after response, including schema-invalid output. Missing usage and ambiguous timed-out requests keep their full reservation until reconciled; worker expiry must not release potentially spent funds. Duplicate provider response IDs settle once. Actual cost above an estimate stops further calls and records a budget incident; an application guard cannot undo a provider overcharge.
- [ ] Add concurrent-worker, missing-usage, duplicate-delivery, lease-loss, retry-budget and provider-overcharge tests. Assert the runtime reports a safe budget-limit error without publishing partial content or minting a fresh budget on automatic retry. Review results/cost ($0).

### Task 2: Select a balanced model and constrain eligible provider prices

**Interfaces:** Immutable `BookModelPolicy(model, input_price_ceiling, output_price_ceiling, reasoning_budget, revision)` saved with the Book version. Proposed candidate prices are $0.30/M input and $2.50/M output; required structured-output parameters remain enabled.

- [ ] Write a fake-client test asserting all outline/chapter/review calls and retries use the saved Book model, obey price limits and never fall back to Pro. A retry after an environment change still uses the original policy.

```python
assert {call["model"] for call in captured_calls} == {"google/gemini-2.5-flash"}
assert all(call["extra_body"]["provider"]["max_price"] ==
           {"prompt": 0.30, "completion": 2.50} for call in captured_calls)
```

- [ ] Implement candidate request policy through the existing per-feature model override, without exposing provider selection in learner UI. Keep the same-model retry invariant. Set provider price caps; choose throughput among eligible standard-price endpoints instead of selecting expensive priority tiers or the slowest discount tier blindly:

```python
extra_body = {
    "provider": {
        "require_parameters": True,
        "max_price": {"prompt": 0.30, "completion": 2.50},
        "sort": "throughput",
    },
    "reasoning": {"max_tokens": 512},
}
```

- [ ] Treat 512 reasoning tokens as the initial experimental policy, not an established quality optimum. Compare zero/512/1024 only where supported and budgeted; math-heavy chapters may allocate 1024 within the same Book ceiling. Keep enough visible-output capacity for a complete schema. Reject unsupported required parameters safely rather than silently dropping cost controls. [Reasoning accounting](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).
- [ ] Verify supported routing and output-cap behavior using fake contracts, then one capped smoke after the complete budget path exists. `max_price` is a provider token-rate filter, **not** a per-Book dollar cap; Task 1 supplies that cap. If no eligible endpoint exists, defer/fail within the same budget rather than raise its price. [Provider price/routing contract](https://openrouter.ai/docs/guides/routing/provider-selection).
- [ ] Run model/routing/parsing tests ($0). Update Book config/docs only after Task 5's quality gate; leave other features' model defaults unchanged by this Book-specific decision.

### Task 3: Allocate content and context by evidence rather than fixed verbosity

**Interfaces:** `allocate_book_budget(units, available_input_tokens, available_output_tokens, detail_level) -> list[ChapterBudget]`; `ChapterBudget` contains stable unit ID, evidence IDs, input bound, visible output allowance, reasoning allowance and expected learning objectives. It consumes the shared source plan from the RAG plan where available; first-time creation counts toward the Book budget.

- [ ] Add fake-source tests for a short document, standard multi-topic text and long mathematical document. Assert every required learning objective has evidence and chapter space, no whole-source prompt repetition, and total allocated input/output/reasoning remains within the financial envelope.

```python
assert required_objectives <= set().union(*(set(c.objectives) for c in chapters))
assert sum(c.input_bound for c in chapters) <= input_allowance
assert sum(c.visible_output_allowance + c.reasoning_allowance for c in chapters) <= output_allowance
```

- [ ] Replace the current universal 8,192 outline and 16,384 per-chapter caps with an allocation computed before generation. Start evaluation with roughly 1,500–2,000 billable outline output tokens and 16,000–20,000 total outline+chapter output tokens for standard Books; divide by objective/equation complexity, not equally or by words alone. Derive each request cap from its own complete-schema allocation, including reasoning. Rebudget remaining chapters after actual usage settles.
- [ ] Revise prompts to remove mandatory repeated introductions, 200–350-word prefaces and padded prose. Retain definitions, prerequisites, important source equations, worked examples where supported, and review questions. Adapt 4–6 chapters for representative standard sources; preserve a genuinely deeper option only where its coverage/output bound fits. Do not silently turn a selected deep guide into a summary. Remove the arbitrary four-chapter/400-word reward requirement from quality scoring in coordination with the RAG plan.

```text
Cover every assigned learning objective using its supplied evidence.
Preserve source equations exactly, including grouping, signs and units.
Explain each key idea once; avoid repeated prefaces and chapter introductions.
Use the allocated sections and output budget to produce complete valid JSON.
If evidence does not support an objective, identify that limitation; do not invent filler.
```

- [ ] Retrieve targeted source blocks per unit; deduplicate full content and include adjacent equation definitions/table headers where needed. Keep document/topic coverage before optimizing token size. Reuse indexed chunks and embedding cache; do not reindex a ready source or generate a new paid summary at every chapter. Cache reuse is an additional saving, never required for the uncached budget to fit.
- [ ] A `finish_reason=length`, missing planned unit or incomplete equation is a failed generation, not success. Repair only the incomplete chapter if its reservation fits; otherwise retain checkpoints and return a safe incomplete/budget outcome. Run allocation and schema tests with fake providers ($0).

### Task 4: Reduce latency and prevent duplicated paid work

**Files:** Runtime plan's `book_checkpoint.py`, `generator.py`, `job_service.py`, `jobs/tasks.py`; extend `test_book_checkpoint.py`, `test_book_scheduling.py`, `test_book_budget.py`.

**Interfaces:** Extend checkpoint identity with `BookModelPolicy.revision` and content allocation digest. Every resumed attempt binds the original `budget_id`; reservations are acquired before scheduling chapters.

- [ ] Add a scenario where chapter 3 fails after chapters 1–2 succeeded; assert only chapter 3 is retried, earlier usage remains charged, and no new outline is requested.

```python
assert resumed_budget_id == initial_budget_id
assert calls_on_resume == ["chapter-3", "chapter-4"]
assert total_spend == first_attempt_spend + resumed_calls_spend
```

- [ ] Implement/reuse validated checkpointing and two-chapter bounded concurrency from runtime Tasks 4–5. Reserve both calls atomically before launch; cap global provider requests separately so per-Book parallelism cannot multiply overspend across users. Parallelism reduces elapsed time, not token price.
- [ ] Serve an identical already-ready owned version from cache unless the user explicitly asks for a new variant. Key by source/options/model/prompt/render versions. Retry version reuse cannot masquerade as a new paid generation; deleted or unauthorized artifacts never become cache hits.
- [ ] Measure fake-provider critical-path latency, retrieval time, queue wait, render time and retry count separately. Proposed real standard-Book goal: 2–4 minutes after worker start, with existing 3–5 second live progress and separately reported queue wait. This is an evaluation target, not a promised production latency before measurement.
- [ ] Run worker/budget/cache tests with no network ($0); retain source quality and lease/publication invariants.

### Task 5: Demonstrate cost and quality together before promotion

**Interfaces:** Evaluation manifest stores source hashes, required facts/equations, existing baseline artifact references and expected objectives. Report `book_cost_usd`, `total_paid_run_cost_usd`, `queue_wait_ms`, `generation_ms`, `source_coverage`, `citation_correctness`, `equation_fidelity`, `human_rubric`, and `completed` for every attempt. Include failed-run cost in aggregate cost per successful Book.

- [ ] Reuse existing Pro Books as a comparison baseline; do not purchase fresh $0.60 baselines. Select three representative sources: Vietnamese standard, math/table-heavy, and longer multi-topic. Label required facts/equations from source, not from Pro output alone. Offline fixture setup costs $0.
- [ ] Implement source-based acceptance: all predeclared must-cover concepts, no critical mathematical errors, all required equations intact, valid supporting citations, and useful explanations/examples. Blind review fidelity, coverage, clarity and usefulness on a 1–5 rubric; proposed tolerance is at most 0.25 lower average than the baseline, with zero critical source/math failures. An LLM reviewer is advisory and must fit the same budget; no numeric structural score substitutes for this assessment.
- [ ] Run all deterministic budget/fidelity tests first ($0). Then evaluate one candidate Book with a $0.095 internal reservation/$0.10 user ceiling. Report the estimate immediately before dispatch and the provider cost immediately after. Expand to the remaining two only after the first passes cost and minimum quality. The proposed three-Book experiment has a separate aggregate cap of $0.30; it is a plan, not money spent or dispatched in this turn.
- [ ] Test reasoning/output adjustments using reused fixtures and changed chapters where valid; charge every paid variant explicitly against its declared evaluation budget. Stop iteration at the aggregate cap. Do not secretly buy a Pro repair, extra judge or complete rerun to make a candidate pass.
- [ ] Populate `docs/book-budget-results.md` with actual cost distributions, completion/failure counts, cost per successful Book, timing and human/source checks. Initial promotion requires all three cases below $0.10 and passing quality; three cases are a smoke gate, not statistical proof. Monitor median/p95 cost and failure rate on a larger separately budgeted sample after release.
- [ ] If Flash misses mathematical fidelity or the requested deep scope cannot fit, keep promotion blocked and record the concrete limitation. Offer a narrower explicit scope or a separately requested higher budget; do not exceed $0.10 or silently weaken the result. Run backend ruff/pytest and applicable frontend build/tests after implementation, then review the concrete diff.

## Planning validation and spend

This revision changes plans only. Decimal arithmetic and plan consistency checks are local, with estimated and actual OpenRouter cost **$0.00**. No model comparison, Book generation, OCR, embedding or deployment is performed here. All prices above are planning inputs that must be refreshed before execution; expected savings and 2–4-minute latency remain unverified targets.

Executed validation: Decimal calculations returned generation `$0.057`, normal-with-review `$0.066`, with-retry `$0.090`, and internal reservation `$0.095`; boundary checks rejected `$0.096` and allowed `$0.095`. Plan checks confirmed balanced code fences and the new ceiling referenced in every affected plan; no placeholder markers were found. All checks passed; provider cost **$0.00**. These checks validate the plan's arithmetic, not implemented budget enforcement.

Read-only balance refresh at **2026-09-05 08:00:22 UTC / 15:00:22 Asia/Saigon**: key allowance **$9.02170362**, key cumulative usage **$0.97829638**, account wallet **$520.088690501**. Values are unchanged from the prior audit. No secret was printed or saved.
