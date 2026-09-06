"""One exact-money ledger shared by provider calls and durable Book budgets.

Money is stored as signed 64-bit nanodollars (max ~$9.2 billion). Both
estimates and actual charges round UP; unknown charges retain reservations.
No source text, request body, credential, or raw provider error is persisted.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, ROUND_CEILING
import math
from queue import Empty, Queue
import time
from threading import Event, Thread
from typing import Callable
from uuid import uuid4

from sqlalchemy import case, select, update, insert, literal
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from billiard.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.provider_call import BookBudget, ProviderCall, ProviderStage, ProviderTestBudget
from app.services import database

SAFE_STAGES = frozenset({"queued", "retrieving", "outline", "chapter", "exporting", "generating", "processing", "capacity_wait"})
SCALE = Decimal(1_000_000_000)
CEILING = Decimal("0.095")


class BudgetLimitError(Exception):
    """Safe terminal failure; never eligible for an automatic paid retry."""

    error_code = "BOOK_BUDGET_LIMIT"


class AccountingError(BudgetLimitError):
    """Accounting failed, so dispatch/retry must stop."""


class ProviderAttemptTimeout(TimeoutError):
    """The wall-clock deadline elapsed after a provider call was dispatched."""


def _call_with_attempt_deadline(create, *, model, request, timeout_seconds):
    """Bound total provider-call wall time, including a responsive byte stream."""

    completed = Queue(maxsize=1)

    def invoke():
        try:
            completed.put((True, create(model=model, **request)))
        except BaseException as exc:  # propagate the provider's original exception
            completed.put((False, exc))

    worker = Thread(target=invoke, name="provider-attempt", daemon=True)
    worker.start()
    try:
        succeeded, value = completed.get(timeout=timeout_seconds)
    except Empty as exc:
        raise ProviderAttemptTimeout("Provider overall attempt deadline exceeded") from exc
    if succeeded:
        return value
    raise value


@dataclass(frozen=True)
class ProviderCallContext:
    job_id: str | None = None
    worker_id: str | None = None
    job_attempt: int | None = None
    course_id: str | None = None
    user_id: str | None = None
    version_id: str | None = None
    budget_id: str | None = None
    feature: str = "generation"
    stage: str = "generating"
    chapter: int | None = None
    heartbeat: Callable[[], bool] | None = None


_context = ContextVar("provider_call_context", default=ProviderCallContext())
_last_call = ContextVar("last_provider_call", default=None)


@contextmanager
def usage_context(context):
    token = _context.set(context)
    try:
        yield
    finally:
        _context.reset(token)


def current_provider_context() -> ProviderCallContext:
    return _context.get()


def normalize_usage(usage):
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    usage = usage if isinstance(usage, dict) else {}

    def number(name):
        value = usage.get(name)
        return (
            value
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
            else None
        )

    return {
        "cost_usd": number("cost"),
        "input_tokens": number("prompt_tokens"),
        "output_tokens": number("completion_tokens"),
    }


def estimate_call_usd(input_bound, output_bound, input_price, output_price, fixed_fees=Decimal("0")):
    if input_bound < 0 or output_bound < 0:
        raise ValueError("Token bounds must be nonnegative")
    if any(not v.is_finite() or v < 0 for v in (input_price, output_price, fixed_fees)):
        raise ValueError("Prices must be finite and nonnegative")
    return (Decimal(input_bound) * input_price + Decimal(output_bound) * output_price) / Decimal(1_000_000) + fixed_fees


def can_reserve(spent, reserved, next_cost, ceiling):
    return (
        all(v.is_finite() and v >= 0 for v in (spent, reserved, next_cost, ceiling))
        and spent + reserved + next_cost <= ceiling
    )


def _units(value):
    value = Decimal(str(value))
    if not value.is_finite() or value < 0 or value * SCALE > 2**63 - 1:
        raise ValueError("Invalid monetary amount")
    return int((value * SCALE).to_integral_value(rounding=ROUND_CEILING))


def ensure_book_budget(db, course, version_id, *, retry=False):
    from app.services.book_model_policy import BookModelPolicy

    budget = db.scalar(select(BookBudget).where(BookBudget.course_id == course.id, BookBudget.version_id == version_id))
    if budget:
        return budget.id
    budget = BookBudget(
        id=str(uuid4()),
        course_id=course.id,
        user_id=course.user_id,
        version_id=version_id,
        state="blocked_unknown" if retry else "active",
        model_policy=BookModelPolicy.default().model_dump(mode="json"),
    )
    db.add(budget)
    db.flush()
    return budget.id


def get_book_model_policy(db, course_id, version_id):
    """Load the immutable policy snapshot owned by a logical Book version."""

    from app.services.book_model_policy import BookModelPolicy

    budget = db.scalar(
        select(BookBudget).where(
            BookBudget.course_id == course_id, BookBudget.version_id == version_id
        )
    )
    if budget is None or not budget.model_policy:
        raise BudgetLimitError("Book model policy is missing")
    return BookModelPolicy.model_validate(budget.model_policy)


def get_remaining_book_budget(db, course_id, version_id):
    """Return the exact unspent, unreserved allowance for an active Book."""

    budget = db.scalar(
        select(BookBudget).where(
            BookBudget.course_id == course_id, BookBudget.version_id == version_id
        )
    )
    if budget is None:
        raise BudgetLimitError("Book budget identity is missing")
    if budget.state != "active" or budget.incident_code is not None:
        raise BudgetLimitError("Book budget is not available")
    remaining_units = budget.ceiling - budget.spent - budget.reserved
    if remaining_units < 0:
        raise AccountingError("Book budget accounting is inconsistent")
    return Decimal(remaining_units) / SCALE


def require_estimated_book_capacity(
    db,
    course_id,
    version_id,
    requests,
    *,
    retry_request=None,
    residual_usd=Decimal("0"),
):
    """Fail before dispatch when measured remaining work cannot fit the ledger.

    Gemini estimates remain explicitly uncalibrated. This is an early, conservative
    feasibility gate; CP3's verified final-request reservation remains authoritative.
    The retry allowance is the measured request that can retry at the current stage.
    """

    residual_usd = Decimal(str(residual_usd))
    if not residual_usd.is_finite() or residual_usd < 0:
        raise ValueError("Residual allowance must be finite and nonnegative")
    required = residual_usd
    for request in requests:
        required += request.upper_bound_usd
    if retry_request is not None:
        required += retry_request.upper_bound_usd
    if required > get_remaining_book_budget(db, course_id, version_id):
        raise BudgetLimitError("Estimated complete Book work exceeds remaining allowance")
    return required


def save_book_allocation_digest(db, course_id, version_id, digest):
    """Bind checkpoint identity to its source-derived allocation exactly once."""

    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("Book allocation digest must be SHA-256")
    budget = db.scalar(
        select(BookBudget).where(
            BookBudget.course_id == course_id, BookBudget.version_id == version_id
        )
    )
    if budget is None:
        raise BudgetLimitError("Book budget identity is missing")
    if budget.allocation_digest not in {None, digest}:
        raise BudgetLimitError("Book allocation changed after admission")
    budget.allocation_digest = digest


def _live_predicate(context):
    return (
        select(ProcessingJob.id)
        .where(
            ProcessingJob.id == context.job_id,
            ProcessingJob.worker_id == context.worker_id,
            ProcessingJob.attempts == context.job_attempt,
            ProcessingJob.course_id == BookBudget.course_id,
            ProcessingJob.user_id == BookBudget.user_id,
            ProcessingJob.status == "running",
            ProcessingJob.cancel_requested.is_(False),
            ProcessingJob.lease_expires_at > datetime.utcnow(),
        )
        .exists()
    )


def reserve_call(budget_id, call_id, upper_bound_usd):
    amount = _units(upper_bound_usd)
    context = _context.get()
    with database.SessionLocal.begin() as db:
        db.execute(update(BookBudget).where(BookBudget.id == budget_id).values(id=budget_id))
        existing = db.get(ProviderCall, call_id)
        if existing:
            return existing.budget_id == budget_id and existing.reserved == amount and existing.state == "reserved"
        conditions = [
            BookBudget.id == budget_id,
            BookBudget.state == "active",
            BookBudget.incident_code.is_(None),
            BookBudget.spent + BookBudget.reserved + amount <= BookBudget.ceiling,
            select(Course.id)
            .where(
                Course.id == BookBudget.course_id, Course.user_id == BookBudget.user_id, Course.is_deleted.is_(False)
            )
            .exists(),
        ]
        if context.job_id:
            conditions.append(_live_predicate(context))
            conditions.append(
                ~select(ProviderCall.call_id)
                .where(
                    ProviderCall.budget_id == budget_id,
                    ProviderCall.state.in_(["dispatched", "unknown"]),
                    ProviderCall.job_id == context.job_id,
                    ProviderCall.job_attempt != context.job_attempt,
                )
                .exists()
            )
        result = db.execute(update(BookBudget).where(*conditions).values(reserved=BookBudget.reserved + amount))
        if result.rowcount != 1:
            return False
        budget = db.get(BookBudget, budget_id)
        db.add(
            ProviderCall(
                call_id=call_id,
                budget_id=budget_id,
                reserved=amount,
                course_id=budget.course_id,
                user_id=budget.user_id,
                job_id=context.job_id,
                job_attempt=context.job_attempt,
                feature=context.feature,
                stage=context.stage,
            )
        )
    return True


def _lock_call(db, call_id):
    """Use budget -> call lock order for dispatch and every settlement.

    The scalar lookup does not trust an ORM snapshot. Updating the shared budget
    serializes distinct-call state decisions on PostgreSQL and SQLite. Locks are
    released before any provider request; dispatch authorization is the atomic
    reserved -> dispatched transition, not the later network send.
    """
    budget_id = db.scalar(select(ProviderCall.budget_id).where(ProviderCall.call_id == call_id))
    if budget_id:
        db.execute(update(BookBudget).where(BookBudget.id == budget_id).values(id=budget_id))
    db.execute(update(ProviderCall).where(ProviderCall.call_id == call_id).values(call_id=call_id))
    return db.get(ProviderCall, call_id, populate_existing=True)


def _settle(db, call, actual_usd):
    call = _lock_call(db, call.call_id)
    if call is None:
        raise AccountingError("Unknown provider call")
    if call.state in {"settled", "not_sent"}:
        return
    budget_id = call.budget_id
    if actual_usd is None:
        db.execute(
            update(ProviderCall)
            .where(ProviderCall.call_id == call.call_id, ProviderCall.state.not_in(["settled", "not_sent"]))
            .values(state="unknown")
        )
        if budget_id:
            # Never flush a stale ORM state over a concurrently committed incident.
            db.execute(
                update(BookBudget)
                .where(BookBudget.id == budget_id, BookBudget.state == "active", BookBudget.incident_code.is_(None))
                .values(state="blocked_unknown")
            )
        return
    amount = _units(actual_usd)
    updated = db.execute(
        update(ProviderCall)
        .where(ProviderCall.call_id == call.call_id, ProviderCall.state.not_in(["settled", "not_sent"]))
        .values(state="settled", cost=amount, original_cost=str(actual_usd), completed_at=datetime.utcnow())
    )
    if updated.rowcount != 1:
        return
    if budget_id:
        values = {
            "reserved": case(
                (BookBudget.reserved < call.reserved, 0),
                else_=BookBudget.reserved - call.reserved,
            ),
            "spent": BookBudget.spent + amount,
        }
        if amount > call.reserved:
            values.update(state="incident", incident_code="PROVIDER_OVERCHARGE")
        db.execute(update(BookBudget).where(BookBudget.id == budget_id).values(**values))
        if amount <= call.reserved:
            unresolved = (
                select(ProviderCall.call_id)
                .where(ProviderCall.budget_id == budget_id, ProviderCall.state == "unknown")
                .exists()
            )
            db.execute(
                update(BookBudget)
                .where(
                    BookBudget.id == budget_id,
                    BookBudget.state == "blocked_unknown",
                    BookBudget.incident_code.is_(None),
                    BookBudget.spent <= BookBudget.ceiling,
                    ~unresolved,
                )
                .values(state="active")
            )


def settle_call(call_id, actual_usd):
    with database.SessionLocal.begin() as db:
        call = _lock_call(db, call_id)
        if call is None:
            raise AccountingError("Unknown provider call")
        _settle(db, call, actual_usd)


def record_provider_call(job_id, attempt, feature, stage, response_id, elapsed_ms, usage, outcome, *, call_id=None):
    normalized = normalize_usage(usage)
    context = _context.get()
    call_id = call_id or str(uuid4())
    try:
        with database.SessionLocal.begin() as db:
            call = _lock_call(db, call_id)
            if response_id:
                duplicate = db.scalar(select(ProviderCall).where(ProviderCall.response_id == response_id))
                if duplicate and duplicate.call_id != call_id:
                    if call:
                        _settle(db, call, None)
                    return
            if call is None:
                # Public recorder supports standalone calls, but cannot recreate deleted jobs.
                if job_id and db.get(ProcessingJob, job_id) is None:
                    raise AccountingError("Provider ownership no longer exists")
                call = ProviderCall(
                    call_id=call_id,
                    job_id=job_id,
                    job_attempt=context.job_attempt,
                    feature=feature,
                    stage=stage if stage in SAFE_STAGES else "generating",
                    reserved=0,
                )
                db.add(call)
                db.flush()
            if call.state == "settled":
                return
            call.response_id = response_id
            call.provider_attempt = attempt
            call.elapsed_ms = max(0, int(elapsed_ms))
            call.outcome = (
                outcome
                if outcome in {"received", "valid", "schema_invalid", "timeout", "no_bill", "error"}
                else "error"
            )
            for key in ("input_tokens", "output_tokens"):
                value = normalized[key]
                setattr(call, key, int(value) if value is not None and value == int(value) and value < 2**63 else None)
            db.flush()
            cost = normalized["cost_usd"]
            _settle(db, call, Decimal(str(cost)) if cost is not None else None)
    except Exception as exc:
        raise AccountingError("Unable to persist provider accounting") from exc


def reserve_test_budget(run_id, upper_bound_usd):
    amount = _units(upper_bound_usd)
    try:
        with database.SessionLocal.begin() as db:
            # One durable envelope per run; repeat calls never mint more capacity.
            db.add(ProviderTestBudget(run_id=run_id, ceiling=amount, reserved=amount))
        return True
    except IntegrityError:
        return False


def settle_test_budget(run_id, actual_usd):
    with database.SessionLocal.begin() as db:
        db.execute(update(ProviderTestBudget).where(ProviderTestBudget.run_id == run_id).values(run_id=run_id))
        budget = db.get(ProviderTestBudget, run_id)
        if budget is None:
            raise AccountingError("Unknown test budget")
        if budget.state in {"settled", "incident"}:
            return
        if actual_usd is None:
            budget.state = "blocked_unknown"
            return
        budget.spent = _units(actual_usd)
        budget.reserved = 0
        budget.state = "incident" if budget.spent > budget.ceiling else "settled"


def verified_request_bound(model, request, feature):
    """Use verified offline embedding tokens; deny unresolved Gemini conversion.

    The embedding endpoint price is constrained in the actual provider request.
    Gemini's exact local measurement is available for allocation, but the
    OpenRouter response-schema framing conversion has no verified maximum yet.
    """
    from app.services.provider_tokens import count_embedding_input, estimate_gemini_request

    if feature == "embedding" and model == "openai/text-embedding-3-small":
        tokens = count_embedding_input(model, request.get("input"))
        request["extra_body"] = {
            "provider": {
                "only": ["OpenAI"],
                "allow_fallbacks": False,
                "require_parameters": True,
                "max_price": {"prompt": 0.02, "completion": 0},
            }
        }
        return estimate_call_usd(tokens, 0, Decimal("0.02"), Decimal("0"))
    if feature == "ocr":
        raise BudgetLimitError("OCR image billing bound is unverified")
    estimate = estimate_gemini_request(model, request)
    if estimate.calibration_state == "unobserved-router-framing":
        raise BudgetLimitError("Gemini framing estimate requires observed prompt-token reconciliation")
    # No boolean/config override admits an uncalibrated method. A future
    # calibrated revision must supply its own evidence-backed adapter here.
    raise BudgetLimitError("Unsupported request-bound calibration revision")


def dispatch_provider(create, *, model, request, feature, attempt):
    try:
        return _dispatch_provider(create, model=model, request=request, feature=feature, attempt=attempt)
    except SQLAlchemyError as exc:
        raise AccountingError("Provider accounting unavailable") from exc


def _dispatch_provider(create, *, model, request, feature, attempt):
    """Reserve -> claim dispatch -> HTTP -> account, all before content parsing."""
    context = _context.get()
    call_id = str(uuid4())
    _last_call.set(None)
    if context.budget_id:
        upper = verified_request_bound(model, request, feature)
        if not reserve_call(context.budget_id, call_id, upper):
            raise BudgetLimitError("Book budget admission denied")
    else:
        if context.feature == "book":
            raise BudgetLimitError("Book budget identity is missing")
        with database.SessionLocal.begin() as db:
            if context.job_id:
                values = {
                    "call_id": call_id,
                    "job_id": context.job_id,
                    "job_attempt": context.job_attempt,
                    "course_id": context.course_id,
                    "user_id": context.user_id,
                    "feature": context.feature,
                    "stage": context.stage,
                    "reserved": 0,
                    "state": "reserved",
                    "provider_attempt": attempt,
                    "created_at": datetime.utcnow(),
                }
                source = (
                    select(*(literal(value) for value in values.values()))
                    .select_from(ProcessingJob)
                    .join(Course, Course.id == ProcessingJob.course_id)
                    .where(
                        ProcessingJob.id == context.job_id,
                        ProcessingJob.worker_id == context.worker_id,
                        ProcessingJob.attempts == context.job_attempt,
                        ProcessingJob.status == "running",
                        ProcessingJob.cancel_requested.is_(False),
                        ProcessingJob.lease_expires_at > datetime.utcnow(),
                        Course.is_deleted.is_(False),
                        Course.user_id == ProcessingJob.user_id,
                    )
                )
                if db.execute(insert(ProviderCall).from_select(list(values), source)).rowcount != 1:
                    raise BudgetLimitError("Provider ownership no longer live")
            else:
                db.add(ProviderCall(call_id=call_id, feature=feature, stage=context.stage, reserved=0))
    with database.SessionLocal.begin() as db:
        call = _lock_call(db, call_id)
        conditions = [ProviderCall.call_id == call_id, ProviderCall.state == "reserved"]
        if context.budget_id:
            budget_conditions = [
                BookBudget.id == context.budget_id,
                BookBudget.id == ProviderCall.budget_id,
                BookBudget.state == "active",
                BookBudget.incident_code.is_(None),
                BookBudget.course_id == ProviderCall.course_id,
                BookBudget.user_id == ProviderCall.user_id,
                Course.id == BookBudget.course_id,
                Course.user_id == BookBudget.user_id,
                Course.is_deleted.is_(False),
            ]
            if context.version_id is not None:
                budget_conditions.append(BookBudget.version_id == context.version_id)
            if context.course_id is not None:
                budget_conditions.append(BookBudget.course_id == context.course_id)
            if context.user_id is not None:
                budget_conditions.append(BookBudget.user_id == context.user_id)
            conditions.append(
                select(BookBudget.id).join(Course, Course.id == BookBudget.course_id).where(*budget_conditions).exists()
            )
        if context.job_id:
            conditions.append(
                select(ProcessingJob.id)
                .join(Course, Course.id == ProcessingJob.course_id)
                .where(
                    ProcessingJob.id == context.job_id,
                    ProcessingJob.worker_id == context.worker_id,
                    ProcessingJob.attempts == context.job_attempt,
                    ProcessingJob.status == "running",
                    ProcessingJob.cancel_requested.is_(False),
                    ProcessingJob.lease_expires_at > datetime.utcnow(),
                    ProcessingJob.course_id == ProviderCall.course_id,
                    ProcessingJob.user_id == ProviderCall.user_id,
                    Course.is_deleted.is_(False),
                    Course.user_id == ProcessingJob.user_id,
                )
                .exists()
            )
        changed = db.execute(
            update(ProviderCall)
            .where(*conditions)
            .values(
                state="dispatched",
                model=model,
                provider_attempt=attempt,
                bound_metadata=(
                    {
                        "method": "cl100k_base",
                        "revision": "tiktoken-0.12.0",
                        "framing_allowance": 0,
                        "calibration_state": "text-only-exact",
                        "input_price_per_million": "0.02",
                        "fixed_fees": "0",
                        "pricing_source": "https://openrouter.ai/openai/text-embedding-3-small",
                        "pricing_checked_at": "2026-09-05",
                        "reserved_nanodollars": _units(upper),
                    }
                    if context.budget_id and feature == "embedding"
                    else None
                ),
            )
        )
        dispatched = changed.rowcount == 1
        if not dispatched and call is not None:
            # Only our still-reserved row proves no dispatch occurred. Unknown or
            # dispatched rows keep their entire hold, including after lease loss.
            released = db.execute(
                update(ProviderCall)
                .where(ProviderCall.call_id == call_id, ProviderCall.state == "reserved")
                .values(state="not_sent", cost=0, original_cost="0", outcome="no_bill", completed_at=datetime.utcnow())
            )
            if released.rowcount == 1 and call.budget_id:
                db.execute(
                    update(BookBudget)
                    .where(BookBudget.id == call.budget_id)
                    .values(reserved=BookBudget.reserved - call.reserved)
                )
    if not dispatched:
        raise BudgetLimitError("Provider dispatch authorization no longer valid")
    _last_call.set(call_id)
    started = time.monotonic()
    stopped, claim_lost = Event(), Event()

    def renew():
        while not stopped.wait(15):
            try:
                if not context.heartbeat():
                    claim_lost.set()
                    return
            except Exception:
                claim_lost.set()
                return

    heartbeat = Thread(target=renew, name="provider-fenced-lease", daemon=True) if context.heartbeat else None
    if heartbeat:
        heartbeat.start()
    try:
        response = _call_with_attempt_deadline(
            create,
            model=model,
            request=request,
            timeout_seconds=settings.OPENROUTER_ATTEMPT_TIMEOUT_SECONDS,
        )
    except SoftTimeLimitExceeded:
        record_provider_call(
            context.job_id,
            attempt,
            feature,
            context.stage,
            None,
            (time.monotonic() - started) * 1000,
            None,
            "timeout",
            call_id=call_id,
        )
        raise
    except Exception:
        record_provider_call(
            context.job_id,
            attempt,
            feature,
            context.stage,
            None,
            (time.monotonic() - started) * 1000,
            None,
            "timeout",
            call_id=call_id,
        )
        if context.budget_id:
            raise BudgetLimitError("Provider charge is unknown") from None
        raise
    finally:
        stopped.set()
        if heartbeat:
            heartbeat.join(timeout=1)
    record_provider_call(
        context.job_id,
        attempt,
        feature,
        context.stage,
        getattr(response, "id", None),
        (time.monotonic() - started) * 1000,
        getattr(response, "usage", None),
        "received",
        call_id=call_id,
    )
    if claim_lost.is_set():
        raise BudgetLimitError("Execution claim lost while provider request was in flight")
    if context.budget_id:
        with database.SessionLocal() as db:
            budget = db.get(BookBudget, context.budget_id)
            if budget is None or budget.state != "active":
                raise BudgetLimitError("Provider accounting blocks further work")
    return response


@contextmanager
def stage_timer(stage, chapter=None):
    context = _context.get()
    if stage not in SAFE_STAGES | {"total"}:
        raise ValueError("Unsafe product stage")
    started = time.monotonic()
    event_id = str(uuid4())
    if context.heartbeat and not context.heartbeat():
        raise BudgetLimitError("Execution claim no longer live")
    if context.job_id:
        with database.SessionLocal.begin() as db:
            db.add(
                ProviderStage(
                    id=event_id, job_id=context.job_id, attempt=context.job_attempt, stage=stage, chapter=chapter
                )
            )
            if stage != "total":
                db.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == context.job_id,
                        ProcessingJob.worker_id == context.worker_id,
                        ProcessingJob.attempts == context.job_attempt,
                        ProcessingJob.status == "running",
                        ProcessingJob.cancel_requested.is_(False),
                        ProcessingJob.lease_expires_at > datetime.utcnow(),
                    )
                    .values(product_stage=stage)
                )
    with usage_context(replace(context, stage=stage if stage != "total" else context.stage, chapter=chapter)):
        try:
            yield
        finally:
            if context.job_id:
                with database.SessionLocal.begin() as db:
                    db.execute(
                        update(ProviderStage)
                        .where(ProviderStage.id == event_id)
                        .values(elapsed_ms=int((time.monotonic() - started) * 1000))
                    )


def anonymize_account(db, user_id, course_ids):
    """Retain accounting tombstones but detach all ownership before SQLite deletes."""
    job_ids = select(ProcessingJob.id).where(ProcessingJob.user_id == user_id)
    db.query(ProviderStage).filter(ProviderStage.job_id.in_(job_ids)).delete(synchronize_session=False)
    db.query(ProviderCall).filter(
        (ProviderCall.user_id == user_id) | ProviderCall.course_id.in_(course_ids) | ProviderCall.job_id.in_(job_ids)
    ).update({"user_id": None, "course_id": None, "job_id": None}, synchronize_session=False)
    db.query(BookBudget).filter((BookBudget.user_id == user_id) | BookBudget.course_id.in_(course_ids)).update(
        {"user_id": None, "course_id": None, "version_id": None, "state": "closed"}, synchronize_session=False
    )


def mark_response_outcome(outcome):
    """Annotate validation without changing already recorded monetary usage."""
    call_id = _last_call.get()
    if call_id is None:
        return
    if outcome not in {"valid", "schema_invalid"}:
        raise ValueError("Unsafe provider outcome")
    try:
        with database.SessionLocal.begin() as db:
            db.execute(update(ProviderCall).where(ProviderCall.call_id == call_id).values(outcome=outcome))
    except SQLAlchemyError as exc:
        raise AccountingError("Unable to record provider validation") from exc


def reserve_required_allowance(budget_id, call_id, remaining_chapters_usd, repair_usd):
    """Hold the complete required-work envelope before a future optional review.

    No optional review exists in the current pipeline. The allocation checkpoint
    must carve actual calls from this hold rather than reserve them twice.
    """
    return reserve_call(budget_id, call_id, remaining_chapters_usd + repair_usd)


def book_usage(function):
    """Bind Book identity even for direct service execution, before retrieval."""

    @wraps(function)
    def run(self, course_id, *args, **kwargs):
        current = _context.get()
        if current.feature == "book":
            return function(self, course_id, *args, **kwargs)
        factory = kwargs.get("db_session_factory") or database.SessionLocal
        with factory() as db:
            course = db.get(Course, course_id)
            version_id = kwargs.get("version_id")
            budget = (
                db.scalar(
                    select(BookBudget).where(BookBudget.course_id == course_id, BookBudget.version_id == version_id)
                )
                if version_id
                else None
            )
            context = replace(
                current,
                feature="book",
                course_id=course_id,
                user_id=course.user_id if course else None,
                version_id=version_id,
                budget_id=budget.id if budget else None,
            )
        with usage_context(context):
            return function(self, course_id, *args, **kwargs)

    return run


def assert_accounting_ready(job_id, job_attempt):
    """A crashed prior attempt cannot turn an ambiguous dispatch into a free retry."""
    with database.SessionLocal() as db:
        prior = db.scalar(
            select(ProviderCall.call_id).where(
                ProviderCall.job_id == job_id,
                ProviderCall.job_attempt < job_attempt,
                ProviderCall.state.in_(["dispatched", "unknown"]),
            )
        )
        if prior:
            raise AccountingError("Earlier provider charges require reconciliation")
