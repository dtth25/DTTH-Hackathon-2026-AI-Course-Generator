# Shared Runtime and Book Spending Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove source-plan/accounting lock contention and admit explicitly quoted Guides under an honest, durable spending policy.

**Architecture:** Persist source identities, short fenced build claims, quotes and logical provider operations. Keep provider I/O outside transactions and preserve the existing ledger, durable jobs and Book checkpoints. Plan 02 supplies source inventory/quote inputs; Plan 03 supplies privacy authorization before live use.

**Tech Stack:** Existing FastAPI, SQLAlchemy/Alembic, SQLite, PostgreSQL 16, Redis/Celery, Pydantic and Decimal.

**Spec:** `docs/superpowers/specs/2026-09-06-reliability-and-trust-design.md` (approved 2026-09-06).

## Global Constraints

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

All paths below are relative to `D:/HackaGen-appearance-worktree`. Backend commands run in `src/backend`; use `uv run --project . --extra dev python -m pytest ...` and `uv run --project . --extra dev ruff check ...`. Use an isolated test environment with fake credentials and blocked external network for ordinary tests. Do not load the user's live key into test fixtures. Windows test temporary roots must be short and inside the checkout; do not weaken application path checks to work around test paths.

Read the approved spec and the relevant existing files before each task. Record a pre-task diff fingerprint. Commit lines are suggestions only: execute a commit only if the Lead authorizes commits; otherwise leave precisely identified edits unstaged. After each task append goal, changed paths, actual commands/results, browser evidence or reason not applicable, unresolved issues and next task to `progress_new.md`.

## File and interface map

| File | Responsibility |
|---|---|
| `app/schemas/reliability.py` | Immutable source binding, quote and claim value types |
| `app/models/reliability.py` | Source revision, build claim, generation quote and logical provider operation persistence |
| `app/services/source_plan_claims.py` | Transaction-scoped claim/renew/publish/fail |
| `app/services/source_plan.py` | Network-outside-transaction orchestration |
| `app/services/generation_quotes.py` | Quote digest, persistence, consumption and replay |
| `app/services/provider_tokens.py` | Explicit estimated reservation policy |
| `app/services/provider_usage.py` | Existing accounting and new logical-operation attempt admission |
| `app/routers/generation.py` | Quote-bound atomic version/job admission |

`app/` in this table means `src/backend/app/`. Do not move unrelated generator rendering code.

## Task R1: Persist shared identities and define cross-plan types

**Goal:** Give all later tasks one exact source/quote/operation identity, including migration behavior.

**Files:** Create `src/backend/app/schemas/reliability.py`, `src/backend/app/models/reliability.py`, `src/backend/alembic/versions/a5b6c7d8e9f0_reliability_identities.py`, `src/backend/tests/test_reliability_identities.py`. Modify `src/backend/app/models/__init__.py`, `src/backend/app/models/course.py`.

**Consumes:** Existing `Base`, `Course`, `ProcessingJob`, `SourcePlanRecord` and `BookBudget`.

**Produces:** The following complete value types; ORM records use the same normalized scalar identities.

- [ ] Write the schema types and failing validation tests first:

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

ArtifactKind = Literal['book', 'slides', 'quiz', 'vid']

class SourceLocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    document_id: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    block: str | None = Field(default=None, min_length=1)

    @model_validator(mode='after')
    def one_position(self):
        if (self.page is None) == (self.block is None):
            raise ValueError('Exactly one page or block is required')
        return self

class SourceBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    owner_id: str
    course_id: str
    source_revision_id: str
    manifest_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    scope_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    included_locations: tuple[SourceLocation, ...]
    excluded_locations: tuple[SourceLocation, ...] = ()
    is_partial: bool

class WorkIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    job_id: str
    worker_id: str
    attempt: int = Field(ge=1)
    version_id: str

class PlanClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    claim_id: str
    revision: int
    generation: int
    lease_owner: str
```

```python
import pytest
from pydantic import ValidationError
from app.schemas.reliability import SourceLocation

@pytest.mark.parametrize('extra', [{}, {'page': 0}, {'page': 1, 'block': 'body[1]'}])
def test_source_location_rejects_ambiguous_position(extra):
    with pytest.raises(ValidationError):
        SourceLocation(document_id='doc-a', **extra)

def test_document_identity_distinguishes_page_one():
    assert SourceLocation(document_id='a', page=1) != SourceLocation(document_id='b', page=1)
```

- [ ] Run `uv run --project . --extra dev python -m pytest tests/test_reliability_identities.py -q`. Red state before adding types: import failure. Green state: all four cases pass.
- [ ] Add the ORM tables with **exact columns/constraints** below. Use existing declarative `Column` style, UTC-naive DB timestamps to match current tables, application-generated UUID strings, JSON only for private structured payloads. `SourceRevision.manifest_json` contains content references/assessments, never provider secrets.

| Class/table | Columns and constraints |
|---|---|
| `SourceRevision` / `source_revisions` | `id String PK`; `course_id String FK courses.id indexed NOT NULL`; `owner_id String FK users.id indexed NOT NULL`; `revision Integer NOT NULL`; `manifest_digest String(64) NOT NULL`; `manifest_json JSON NOT NULL`; `policy_revision String(100) NOT NULL`; `state String(16) NOT NULL`; `created_at DateTime NOT NULL`; unique `(course_id,revision)` |
| `SourcePlanBuild` / `source_plan_builds` | `id String PK`; `course_id String FK courses.id NOT NULL`; `owner_id String FK users.id NOT NULL`; `source_revision_id String FK source_revisions.id NOT NULL`; `scope_digest String(64) NOT NULL`; `policy_revision String(100) NOT NULL`; `revision Integer NOT NULL`; `state String(16) NOT NULL`; `generation Integer NOT NULL default 1`; `lease_owner String`; `lease_expires_at DateTime`; `job_id String FK processing_jobs.id`; `job_attempt Integer`; `result_id Integer FK source_plans.id`; `error_code String(80)`; unique `(course_id,source_revision_id,scope_digest,policy_revision)`; unique `(course_id,revision)` |
| `GenerationQuote` / `generation_quotes` | `id String PK`; `owner_id String FK users.id NOT NULL`; `course_id String FK courses.id NOT NULL`; `artifact String(16) NOT NULL`; `source_revision_id String FK source_revisions.id NOT NULL`; `scope_digest String(64) NOT NULL`; `settings_digest String(64) NOT NULL`; `policy_digest String(64) NOT NULL`; `payload_json JSON NOT NULL`; `created_at DateTime NOT NULL`; `expires_at DateTime NOT NULL`; `consumed_at DateTime`; `idempotency_key String(100)`; `job_id String FK processing_jobs.id`; `version_id String` |
| `ProviderOperation` / `provider_operations` | `id String(64) PK`; `job_id String FK processing_jobs.id NOT NULL indexed`; `version_id String NOT NULL`; `stage String(40) NOT NULL`; `unit_key String(160) NOT NULL`; `request_digest String(64) NOT NULL`; `attempts Integer NOT NULL default 0`; `state String(24) NOT NULL default pending`; `last_call_id String FK provider_calls.call_id`; `result_ref String`; unique `(job_id,stage,unit_key,request_digest)`; check `attempts >= 0 AND attempts <= 2` |
| `ProviderReconciliation` / `provider_reconciliations` | `id String PK`; `call_id String FK provider_calls.call_id NOT NULL`; `reviewer_id String nullable`; `evidence_digest String(64) NOT NULL`; `source_reference String(1024) NOT NULL`; `actual_cost BigInteger NOT NULL`; `created_at DateTime NOT NULL`; unique `(call_id,evidence_digest)`; check `actual_cost >= 0` |

Add nullable `Course.active_source_revision_id String` (opaque pointer, avoid a cyclic FK migration). Verify pointer ownership in application queries. Source plan's existing `model` column becomes provenance, not the new cache key; old unique constraints remain valid because the new policy supplies a stable builder model and prompt revision scoped to its digest.

Migration implementation uses `op.create_table` with the columns above and `op.batch_alter_table('courses')` for the pointer. Set `revision='a5b6c7d8e9f0'`, `down_revision='a4b5c6d7e8f9'`. Do not rewrite existing source plans or budgets. Downgrade removes the pointer before child tables, then reconciliations/operations/quotes/builds/revisions in dependency order. Use `sa.UniqueConstraint`/`sa.CheckConstraint`, not only application assertions.

Concrete declarative/migration pattern (repeat for each exact row, preserving names):

```python
class SourceRevision(Base):
    __tablename__ = 'source_revisions'
    __table_args__ = (UniqueConstraint('course_id', 'revision'),)
    id = Column(String, primary_key=True)
    course_id = Column(String, ForeignKey('courses.id'), nullable=False, index=True)
    owner_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    manifest_digest = Column(String(64), nullable=False)
    manifest_json = Column(JSON, nullable=False)
    policy_revision = Column(String(100), nullable=False)
    state = Column(String(16), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
```

- [ ] Add a migration round-trip test using a temporary file DB: upgrade to old head, insert a legacy course/budget, upgrade new head, inspect all new columns/uniques, assert old allowance is 95,000,000 nanodollars, downgrade only this revision, and assert the legacy rows remain. Repeat the migration check on isolated PostgreSQL in Plan 04.
- [ ] Run identity tests and `uv run --project . --extra dev ruff check app/schemas/reliability.py app/models/reliability.py`. Acceptance: no data rewrite, complete foreign-key/uniqueness coverage, immutable public value types. Browser: not applicable to schema-only checkpoint. Commit suggestion: `feat: persist source quote and provider operation identities`.

## Task R2: Claim and publish source plans without network-spanning locks

**Goal:** Claim and publish source plans without network-spanning locks.

**Files:** Create `src/backend/app/services/source_plan_claims.py`, `src/backend/tests/test_source_plan_claims.py`; modify `src/backend/app/services/source_plan.py`, `src/backend/app/services/generator.py`, `src/backend/app/jobs/tasks.py`.

**Consumes:** R1 types/tables, current `SourcePlan`, `ProviderCall`, existing job lease/capacity continuation.

**Produces:**

```python
class SourcePlanBusy(RuntimeError): pass
class SourcePlanLeaseLost(RuntimeError): pass
class SourcePlanChargeUnknown(RuntimeError): pass

def claim_source_plan(binding: SourceBinding, work: WorkIdentity, policy_revision: str,
                      *, db_session_factory, now: datetime) -> PlanClaim | SourcePlan: ...
def renew_source_plan(claim: PlanClaim, work: WorkIdentity,
                      *, db_session_factory, now: datetime) -> bool: ...
def publish_source_plan(claim: PlanClaim, binding: SourceBinding, work: WorkIdentity,
                        plan: SourcePlan, *, model: str, policy_revision: str,
                        db_session_factory, now: datetime) -> SourcePlan: ...
def fail_source_plan(claim: PlanClaim, work: WorkIdentity, code: str,
                     *, db_session_factory, now: datetime) -> None: ...
```

Signatures above are interface notation, not implementation stubs. Implement the transaction algorithms below. Every operation uses one short owned session and commits/rolls back before returning. Inject `now` for deterministic tests; production passes `datetime.utcnow()`.

- [ ] Port the saved lock diagnostic into `test_source_plan_claims.py`. Keep the real file-SQLite engine and real provider ledger dispatch; replace only provider transport with a deterministic fake. Use an active user/course/revision/job with a valid worker lease. The builder calls `dispatch_provider` and returns a minimal valid `SourcePlan`. Assert one provider invocation, one settled call, one plan and no lock exception. Before the change this must reproduce accounting/SQLite locking, not simply fail because a fake omitted a method.
- [ ] Run `uv run --project . --extra dev python -m pytest tests/test_source_plan_claims.py -q` and record the exact red failure.
- [ ] Implement a shared transaction entry helper and live-owner predicate:

```python
def begin_course_write(db, binding):
    if db.bind.dialect.name == 'sqlite':
        db.execute(text('BEGIN IMMEDIATE'))
    query = select(Course).where(Course.id == binding.course_id,
                                  Course.user_id == binding.owner_id,
                                  Course.is_deleted.is_(False))
    if db.bind.dialect.name == 'postgresql':
        query = query.with_for_update()
    course = db.scalar(query)
    revision = db.get(SourceRevision, binding.source_revision_id)
    if (course is None or revision is None or revision.state != 'ready'
        or revision.course_id != binding.course_id or revision.owner_id != binding.owner_id
        or revision.manifest_digest != binding.manifest_digest):
        raise SourcePlanLeaseLost('Source ownership is no longer valid')
    return course

def live_work(db, work, owner_id, course_id, now):
    query = select(ProcessingJob).where(
        ProcessingJob.id == work.job_id, ProcessingJob.user_id == owner_id,
        ProcessingJob.course_id == course_id, ProcessingJob.worker_id == work.worker_id,
        ProcessingJob.attempts == work.attempt, ProcessingJob.status == 'running',
        ProcessingJob.cancel_requested.is_(False), ProcessingJob.lease_expires_at > now,
    )
    if db.bind.dialect.name == 'postgresql':
        query = query.with_for_update()
    job = db.scalar(query)
    if job is None or not isinstance(job.payload_json, dict):
        return False
    if job.payload_json.get('version_id') != work.version_id:
        return False
    course = db.get(Course, course_id)
    if course is None or course.is_deleted:
        return False
    metadata = course.metadata_json or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    artifact = {'book':'book','slides':'slides','quiz':'quiz','video':'vid'}.get(job.job_type)
    versions = metadata.get('study_pack',{}).get('artifacts',{}).get(artifact,{}).get('versions',{})
    return work.version_id in versions
```

Claim algorithm under the course lock: validate `live_work`; query unique build key; return validated persisted plan if `ready`; if another unexpired builder owns it raise Busy; if expired/failed, check its prior job's provider calls for `dispatched` or `unknown` before takeover and raise ChargeUnknown if found. Otherwise increment generation, retain revision and replace owner/job/expiry. For a new record allocate `max(max(source_plans.revision), max(source_plan_builds.revision))+1` under the course lock. Store 60-second expiry. Return only copied `PlanClaim`, never a live ORM object.

Lock order for claim/publication is course, job, build. Renewal takes job then build and never later acquires a course lock. Keep locks only through the short state transaction. Deletion/cancellation code must respect this order when it needs more than one row. Claim test fixtures create a reserved version in course metadata and matching job.payload_json.version_id; otherwise they are not a valid production work identity. Add a test deleting the version while a source-plan builder is paused: publication must fail even if the course still exists.

Renew algorithm: conditional UPDATE on ID/generation/lease owner, state building, unexpired claim and `live_work`; extend by 60 seconds. Publication: repeat course/source/live-work checks, then conditional claim check, validate plan revision and source digest equal the bound source/scope digest, insert SourcePlanRecord and set result_id/state ready in the same transaction. `fail_source_plan` may change only the matching current claim; safe code only. A lost claim must not be resurrected.

Orchestration replacement:

```python
claim = claim_source_plan(binding, work, policy_revision,
                          db_session_factory=factory, now=datetime.utcnow())
if isinstance(claim, SourcePlan):
    return claim
with SourcePlanHeartbeat(claim, work, factory) as heartbeat:
    plan = create(claim.revision)  # no SQL session is retained here
    if heartbeat.lost:
        raise SourcePlanLeaseLost('Source-plan claim expired')
    return publish_source_plan(claim, binding, work, plan, model=model,
        policy_revision=policy_revision, db_session_factory=factory, now=datetime.utcnow())
```

Define `SourcePlanHeartbeat` in `source_plan_claims.py`: a context manager with a `threading.Event`, daemon thread, 15-second Event.wait interval, `renew_source_plan`, `lost: bool`; exceptions/false renewal set lost and stop; exit sets stop and joins. The lease check on publication remains authoritative even if heartbeat shutdown is delayed. Never perform a DB call in a retained caller transaction.

- [ ] Change generator `_get_source_plan` to receive `binding` and `work`, and use a fixed builder-policy revision rather than the consuming artifact model in the cache identity. Plan 02 supplies actual inventory binding. Keep legacy read-only history; do not allow the old lock-holding path for newly queued jobs. Map Busy to existing capacity continuation (1–3-second jitter); ChargeUnknown to terminal actionable accounting hold; LeaseLost to existing cancellation/lost ownership handling.
- [ ] Add tests for four concurrent builders (one build), warm-cache no calls, expiry takeover preserving revision, stale publish denied, deletion before publish denied, renewal, unknown prior charge blocking takeover and no leaked connections. Use barriers/events rather than arbitrary sleeps.

```python
def test_old_generation_cannot_publish(claim_fixture):
    first = claim_fixture.claim(worker='first')
    claim_fixture.expire(first)
    second = claim_fixture.claim(worker='second')
    assert second.revision == first.revision
    assert second.generation == first.generation + 1
    with pytest.raises(SourcePlanLeaseLost):
        claim_fixture.publish(first)
    claim_fixture.publish(second)
    assert claim_fixture.ready_plan_count() == 1
```

`claim_fixture` is defined in this test file: it owns a file-SQLite factory, inserts R1 user/course/ready revision and two running jobs, calls the production functions above, changes only stored lease timestamps in `expire`, builds one objective/unit with evidence `e1` in `publish`, and counts SourcePlanRecord rows. Methods are `claim(worker: str)`, `expire(claim)`, `publish(claim)`, `ready_plan_count()`. Its two workers must have distinct job/worker identities and valid job leases; tests must not bypass `live_work`.

- [ ] Run new tests plus `tests/test_source_plan.py` and `tests/test_provider_usage.py`. Update old concurrency assertions for Busy/continuation behavior, preserving single-build and history requirements. Browser: Plan 04 proves real first-use generation; do not call paid providers now merely to test locks. Acceptance: real cross-session ledger write inside the builder succeeds and stale ownership cannot publish. Commit suggestion: `fix: release database locks before source plan inference`.

## Task R3: Make Book reservations explicitly estimated and configurable

**Goal:** Make Book reservations explicitly estimated and configurable.

**Files:** Modify `src/backend/app/core/config.py`, `src/backend/app/models/provider_call.py`, `src/backend/app/services/book_model_policy.py`, `src/backend/app/services/provider_tokens.py`, `src/backend/app/services/provider_usage.py`, `.env.example`; create `src/backend/tests/test_estimated_book_admission.py`, `src/backend/scripts/reconcile_provider_charge.py`, `src/backend/tests/test_charge_reconciliation.py`.

**Consumes:** Existing tokenizers/price controls/reserve_call/settlement. **Produces:** `BookModelPolicy.admission_policy: str`, `estimated_request_reservation(model, request) -> RequestEstimate`, and optional `ceiling_usd: Decimal` argument to `ensure_book_budget` used only on first creation.

- [ ] Write red tests: new quote budget 500,000,000 units; existing 95,000,000 unchanged; nonfinite/negative config rejected; admission estimate includes final schema/reasoning; unsupported model/multimodal request rejected; overspend/unknown keeps existing safeguards.

```python
def test_estimate_is_margin_not_claimed_verified(monkeypatch):
    from app.services import provider_tokens as t
    monkeypatch.setattr(t, 'estimate_gemini_request', lambda *a: t.RequestEstimate(
        2024, 4512, Decimal('.30'), Decimal('2.50'), Decimal('0'),
        'old', 'old', 1024, 'unobserved-router-framing'))
    result = t.estimated_request_reservation('google/gemini-2.5-flash', {})
    assert result.input_bound == 2524
    assert result.output_bound == 4512
    assert result.calibration_state == 'estimated-not-guaranteed'
```

- [ ] Run `uv run --project . --extra dev python -m pytest tests/test_estimated_book_admission.py -q`; then implement:

```python
# provider_tokens.py: estimate_gemini_request already adds exactly 1024.
from dataclasses import replace

def estimated_request_reservation(model, request):
    measured = estimate_gemini_request(model, request)
    measured_max = measured.input_bound - measured.framing_allowance
    return replace(measured,
        input_bound=(measured_max * 3 + 1) // 2 + 1024,
        method='final-request-measurement-with-margin',
        revision='estimated-reservation-v1',
        framing_allowance=1024,
        calibration_state='estimated-not-guaranteed')
```

Add `BOOK_DEFAULT_ALLOWANCE_USD: Decimal = Field(default=Decimal('0.50'), gt=0, allow_inf_nan=False)`. Add `admission_policy='estimated-reservation-v1'` to the **new default policy**, but when deserializing saved JSON missing the field use `legacy-verified-v1`. Achieve this with a field default of legacy and `BookModelPolicy.default()` explicitly passing new. Never mutate existing stored policies during read.

In `ensure_book_budget`, return an existing record unchanged; for new record require explicit snapshotted allowance, convert with `_units`, persist it and the new policy. Missing budget on retry remains blocked_unknown; a retry cannot receive a fresh allowance.

At dispatch, select the estimator based on the persisted budget policy. Legacy uses the existing fail-closed verified path. New uses the estimated reservation for text Gemini; embedding uses verified native token counting without discarding privacy controls. Persist estimate metadata. Keep reserve -> dispatched -> network -> settlement -> parse ordering. Preserve `_settle` actual-cost/over-reservation incident behavior and unknown holds. Rename user-facing “upper bound” descriptions to “reservation estimate”; existing internal field names may remain for compatibility.

- [ ] Add concurrent-reservation and settlement tests using real DB sessions: two .30 reservations against .50 permit exactly one; .02 unknown stays reserved; actual .03 against reserved .02 records .03 and blocks subsequent work. Existing calls without usage cannot be treated as free.

Reconciliation command: `uv run --project . python scripts/reconcile_provider_charge.py --call-id CALL_ID --evidence-file PRIVATE_JSON_PATH`. The evidence is a provider billing result or administrator-saved provider statement, with call_id, provider_response_id, actual_cost_usd, checked_at and source_reference; no prompt/secret. Validate finite nonnegative cost, exact stored response/operation identity and evidence digest. Query current provider accounting metadata when a response ID supports it, without sending document text. A manual statement requires an existing active admin ID via `--reviewer-id`; check role in DB and record immutable audit. Use the ProviderReconciliation model/table already created by R1; do not edit an applied migration. Implement `reconcile_provider_charge(call_id: str, receipt: dict, reviewer_id: str | None, *, db_session_factory) -> None` in provider_usage.py; the CLI calls this function. Never overwrite an inconsistent earlier reconciliation; report conflict. Use existing settle_call/lock order and unblock only when no other unknown call/incident remains. Zero requires explicit matching provider evidence. Keep raw statements private; audit stores digest/reference only. Plan03 detaches reviewer identity at deletion.

```python
def test_reconciliation_is_idempotent_and_does_not_guess_zero(reconciliation_case):
    receipt = reconciliation_case.receipt(actual_cost_usd='0.02')
    reconciliation_case.apply(receipt)
    reconciliation_case.apply(receipt)
    assert reconciliation_case.spent_units() == 20_000_000
    assert reconciliation_case.audit_count() == 1
    with pytest.raises(ValueError):
        reconciliation_case.apply({'call_id': receipt['call_id']})
```

Define reconciliation_case with a real unknown call/.02 reservation and active administrator, evidence in tmp_path, actual application reconciliation invocation and DB reads for spent/audit counts. A second distinct-cost receipt for the settled call fails rather than double-accounting. Run `tests/test_charge_reconciliation.py` with the R3 suite.
- [ ] Run new tests, `tests/test_book_budget.py`, `tests/test_book_policy_cp8.py`, `tests/test_provider_usage.py`; update only expectations changed by explicit new policy, keeping tests for legacy denial. Acceptance: new estimated policy can dispatch a fake Gemini call, legacy is unchanged, $0.50 is not described as guaranteed billing. Browser: quote text checked R5/Plan 02. Commit suggestion: `feat: snapshot configurable estimated Book admission allowances`.

## Task R4: Persist quotes and atomically consume generation confirmation

**Goal:** Persist quotes and atomically consume generation confirmation.

**Files:** Create `src/backend/app/services/generation_quotes.py`, `src/backend/app/schemas/generation_quote.py`, `src/backend/tests/test_generation_quotes.py`; modify `src/backend/app/schemas/generation.py`, `src/backend/app/routers/generation.py`.

**Consumes:** R1 `GenerationQuote`/binding; R3 policy; existing `enqueue_generation_job`. Plan 02 provides quote inputs and UI. **Produces:**

```python
def create_quote(db: Session, *, binding: SourceBinding, artifact: ArtifactKind,
                 settings: dict, policy: dict, estimate_usd: Decimal | None,
                 allowance_usd: Decimal | None, cost_categories: dict,
                 intent: dict,
                 now: datetime) -> GenerationQuote: ...
def consume_quote(db: Session, *, quote_id: str, owner_id: str, course_id: str,
                  artifact: ArtifactKind, settings: dict, current_policy: dict,
                  active_source_revision_id: str, idempotency_key: str,
                  intent: dict,
                  partial_confirmed: bool, now: datetime) -> GenerationQuote: ...
```

- [ ] Write tests for expired quote, other owner (404), changed settings/source/policy (409), partial without confirmation (409), identical replay returning original IDs, conflicting replay (409), no estimate/over allowance (409), and version/job/budget failure rolling back quote consumption.
- [ ] Run `uv run --project . --extra dev python -m pytest tests/test_generation_quotes.py -q` and capture red; implement canonical JSON digests with existing `book_checkpoint.canonical_digest` and a ten-minute expiry. Private quote payload stores `binding.model_dump(mode='json')`, settings, policy, `estimate_usd`, `allowance_usd`, and cost categories; serialize money as Decimal strings.

```python
def quote_matches(row, *, owner_id, course_id, artifact, settings,
                  current_policy, active_source_revision_id):
    return (row.owner_id == owner_id and row.course_id == course_id
        and row.artifact == artifact
        and row.source_revision_id == active_source_revision_id
        and row.settings_digest == canonical_digest(settings)
        and row.policy_digest == canonical_digest(current_policy))
```

Consumption runs under the same course write lock as version/job admission. Check ownership before revealing quote existence. For an already consumed quote first require same owner/course/artifact/settings/policy and idempotency key; return original IDs even after expiry, without new dispatch. For unused quotes require expiry in future, current source match, estimate available, capacity allowed and partial confirmation. Mark consumed and bind idempotency key within the transaction that reserves version/budget/job. Store job/version before commit. A post-commit broker failure retains its existing scheduling recovery; a replay must not create a second job.

Store `intent={retry_version_id: str | None, new_variant: bool}` separately in payload_json and require exact match during consumption/replay. Do not include these operational flags in immutable content settings_digest/checkpoint identity: adding retry_version_id must not make otherwise identical content settings appear changed. A deliberate retry quotes the original version's unchanged content settings/policy/budget; a repair that changed the active source requires a new version/quote instead of silently rewriting the failed version's provenance.

Add required body fields to new generation requests: `quote_id: str`, `idempotency_key: str` (1–100 characters), `partial_confirmed: bool = False`, `language: Literal['vi','en']='vi'` (Video only vi). Remove the path where query-only calls bypass quote validation: respond 422/`GENERATION_QUOTE_REQUIRED` without paid work. Keep the same four route names. Retry requests quote and reference the same version; consumed-quote replay is distinct from a deliberate retry of a failed version. Validate retry version's immutable source/settings/policy and existing budget before dispatch.

Preserve cache hits but include source revision/scope/language/settings/policy in matching and return only an owned ready artifact; a cache shortcut cannot bypass source/partial confirmation. Policy changes cannot silently reuse a mismatched guide.

- [ ] Add parameterized route tests covering Book/Slides/Quiz/Video: malformed/forged quote cannot reach `enqueue_generation_job`; valid quote creates exactly one durable job with binding in `payload_json`. Use a complete fake Generator including `find_ready_book_version` so tests fail on behavior rather than missing fake methods.
- [ ] Run quote tests and `tests/test_queued_routes.py`, `tests/test_book_scheduling.py`. Acceptance: quote/version/job/budget is one transaction; no client allowance override; no paid preflight. Browser deferred until Plan 02 connects quote UI. Commit suggestion: `feat: bind generation jobs to scope and spending confirmation`.

## Task R5: Bound retries across job redelivery and expose actionable errors

**Goal:** Bound retries across job redelivery and expose actionable errors.

**Files:** Modify `src/backend/app/services/provider_usage.py`, `src/backend/app/services/llm.py`, `src/backend/app/services/public_errors.py`, `src/backend/app/jobs/tasks.py`, `src/frontend/src/lib/types.ts`, `src/frontend/src/lib/api.ts`, `src/frontend/src/components/dashboard/JobProgress.tsx`; create `src/backend/tests/test_provider_operation_retries.py`; extend frontend `JobProgress.test.tsx`, `ArtifactJobRetry.test.tsx`, `api.test.ts`.

**Consumes:** R1 ProviderOperation and R4 immutable settings; existing safe error handling. **Produces:** `begin_provider_operation(context, stage, unit_key, request_digest) -> str`, `claim_operation_attempt(operation_id, call_id) -> int`, `finish_provider_operation(operation_id, state, result_ref=None) -> None`. Context is existing ProviderCallContext; extend it with `operation_id: str | None`.

- [ ] Red test: a schema-invalid provider response uses two calls total, even when the durable job is delivered three times; timeout after dispatch holds unknown and cannot send again. A successful saved unit is read from its validated checkpoint without new inference.
- [ ] Implement operation ID as `canonical_digest([job_id, version_id, stage, unit_key, request_digest])`. Insert/find under transaction and enforce the unique key. Reserve/claim each operation attempt in the same transaction as creating its ProviderCall; conditional update `attempts < 2 AND state in ('pending','retryable')`, increments attempts and sets dispatched/last_call_id. Mark response settled before choosing retryable/schema failure. Unknown sets blocked_unknown. Success stores validated result reference only after content validation; a crash with a settled-but-unvalidated result may retry only if an attempt remains. No hidden SDK retries.

```python
allowed = db.execute(update(ProviderOperation).where(
    ProviderOperation.id == operation_id,
    ProviderOperation.attempts < 2,
    ProviderOperation.state.in_(['pending', 'retryable']),
).values(attempts=ProviderOperation.attempts + 1, state='dispatched',
         last_call_id=call_id))
if allowed.rowcount != 1:
    raise BudgetLimitError('Logical provider operation cannot dispatch')
```

Name stages `source_plan`, `outline`, `chapter`, `validation`, `repair`, `slides`, `quiz`, `video_script`, `title`, `ocr`, `embedding`; use source location/chapter ID as `unit_key`, never prompt text. A repair operation is separate from a transport retry but must fit the same quote allocation and guide budget. Plan 02 supplies stable unit keys; use the same key through worker retries.

Refactor `reserve_call` to accept optional `db: Session | None=None`: caller-supplied sessions never commit; the existing no-session wrapper owns its short transaction. This lets dispatch atomically reserve the budget, insert/flush ProviderCall, then update ProviderOperation (its last_call_id FK must reference an already inserted row). Keep global lock order budget -> call -> operation; settlement/reconciliation follow the same order. If operation admission fails, roll back its new call/reservation too. Non-Book operations use call -> operation. Add an integration assertion that a rejected exhausted operation leaves neither an orphan reservation nor an extra ProviderCall.

- [ ] Add safe public mappings and recommended actions:

| Code | Vietnamese message | Action |
|---|---|---|
| `BOOK_SCOPE_EXCEEDS_ALLOWANCE` | `Phạm vi đã chọn vượt mức chi phí cho phép.` | change_scope |
| `BOOK_BUDGET_LIMIT` | `Đã đạt mức chi phí cho phép của tài liệu này.` | change_scope |
| `ACCOUNTING_RECONCILIATION_REQUIRED` | `Cần đối soát chi phí trước khi tiếp tục.` | contact_admin |
| `GENERATION_QUOTE_STALE` | `Tài liệu hoặc thiết lập đã thay đổi. Vui lòng xác nhận lại.` | refresh_quote |
| `PARTIAL_SCOPE_CONFIRMATION_REQUIRED` | `Vui lòng xác nhận phạm vi tài liệu còn thiếu.` | confirm_scope |
| `SOURCE_PLAN_BUSY` | `Đang chuẩn bị cấu trúc tài liệu.` | wait |
| `PROVIDER_POLICY_UNAVAILABLE` | `Dịch vụ xử lý chưa đáp ứng chính sách dữ liệu.` | contact_admin |
| `SPEECH_UNAVAILABLE` | `Dịch vụ giọng đọc chưa sẵn sàng.` | contact_admin |

Unknown backend text continues to use the existing safe fallback. Permanent conditions expose no automatic retry CTA. Keep real attempt counts and next retry time. Add Book/error fields to both HTTP error normalization and job status normalization; fixing only one recreates the observed bug.

```tsx
it('shows the Book budget reason and does not suggest blind retry', async () => {
  vi.mocked(apiGetJob).mockResolvedValue(job({status: 'failed', error_code: 'BOOK_BUDGET_LIMIT'}));
  render(<JobProgress jobId="job-1" />);
  expect(await screen.findByText('Đã đạt mức chi phí cho phép của tài liệu này.')).toBeVisible();
  expect(screen.queryByRole('button', {name: /tự động thử lại/i})).not.toBeInTheDocument();
});
```

The existing test file defines `job`, `apiGetJob`, `vi`, render and screen. Exercise the retry CTA in ArtifactJobRetry tests with a permanent code as well.

- [ ] Run backend operation/ledger/job tests; frontend `npm test -- --run src/components/dashboard/JobProgress.test.tsx src/components/dashboard/ArtifactJobRetry.test.tsx src/lib/api.test.ts`. Browser with deterministic local backend: budget error readable, no reload, no permanent-error auto retry, scheduled transient retry remains visible. Acceptance: job redelivery cannot reset call attempts or guide spend. Commit suggestion: `fix: persist retry limits and expose generation recovery reasons`.

## Task R6: Runtime integration checkpoint and handoff

**Goal:** Runtime integration checkpoint and handoff.

**Files:** Extend `src/backend/tests/test_source_plan_claims.py`, `src/backend/tests/test_generation_quotes.py`; update `README.md`, `progress_new.md`.

- [ ] Add the source-plan/real-ledger cold-path test to ordinary discovery (not only a manually run diagnostic). Test a quote -> queued job -> claim -> fake provider -> settlement -> plan publication, with independent file-SQLite sessions. Test replay and unknown-charge recovery without network.
- [ ] Run `uv run --project . --extra dev python -m pytest tests/test_reliability_identities.py tests/test_source_plan_claims.py tests/test_estimated_book_admission.py tests/test_generation_quotes.py tests/test_provider_operation_retries.py tests/test_provider_usage.py tests/test_job_tasks.py -q`; run Ruff on affected backend files and frontend focused tests from R5.
- [ ] Document estimator semantics, new default, old-policy behavior, quote/retry contract and no-network claim transaction invariant. Preserve README setup paths and explicitly identify remaining Plan 02/03 integration prerequisites.
- [ ] Record checkpoint evidence. No passing helper suite is evidence of successful real artifacts. Required PostgreSQL concurrency, browser success and live billing gates occur in Plan 04.
- [ ] Acceptance: every new interface is importable; migration works; cold source planning can settle accounting; duplicate request cannot duplicate a job; policy/unknown holds survive retry. No new generation route. Commit suggestion: `test: cover runtime accounting and quote integration`.

## Plan self-review and stop rule

Additional executable regression for R4 (in test_generation_quotes.py; canonical_digest is imported from book_checkpoint):

```python
def test_quote_settings_match_is_not_just_course_match():
    from types import SimpleNamespace
    from app.services.generation_quotes import quote_matches
    settings = {'language':'vi','detail_level':'deep','user_prompt':''}
    policy = {'revision':'new-policy'}
    row = SimpleNamespace(owner_id='a', course_id='c', artifact='book',
        source_revision_id='r', settings_digest=canonical_digest(settings),
        policy_digest=canonical_digest(policy))
    args = dict(owner_id='a',course_id='c',artifact='book',settings=settings,
        current_policy=policy,active_source_revision_id='r')
    assert quote_matches(row, **args)
    assert not quote_matches(row, **{**args,'settings':{**settings,'language':'en'}})
    assert not quote_matches(row, **{**args,'owner_id':'b'})
```

R6 must include R2's actual dispatcher integration regression, with the builder returning a SourcePlan only **after** its independent ledger session settles. It is insufficient to replace the builder with a constant-return lambda. Capture the original diagnostic's negative control (holding BEGIN IMMEDIATE across that builder fails) in a separate test using a short SQLite timeout; the production path is the positive control.

Before handing this plan to workers, cross-check R1 names against Plans 02/03/04. Interface notation is accompanied by transaction algorithms; do not copy ellipsis signatures into product code. Keep all scope/budget/privacy evidence constraints from the spec. If a provider request cannot honor the saved policy, report the concrete mismatch; do not loosen policy, increase allowance or switch models automatically.
