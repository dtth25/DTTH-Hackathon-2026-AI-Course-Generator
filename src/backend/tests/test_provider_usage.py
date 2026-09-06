from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier, Event
import time
from uuid import uuid4
from sqlalchemy.schema import CreateSchema, DropSchema
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from app.models.course import Course
from app.models.user import User
from app.models.processing_job import ProcessingJob
from app.models.provider_call import BookBudget, ProviderCall, ProviderTestBudget
from app.services import database
from app.services.provider_usage import (
    AccountingError,
    BudgetLimitError,
    ProviderCallContext,
    dispatch_provider,
    ensure_book_budget,
    normalize_usage,
    record_provider_call,
    reserve_call,
    settle_call,
    reserve_test_budget,
    settle_test_budget,
    usage_context,
)


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    postgres_url = os.environ.get("CP3_FIX_TEST_DATABASE_URL")
    schema = None
    if postgres_url:
        assert "127.0.0.1:55433/cp3" in postgres_url, "Only disposable CP3 PostgreSQL is allowed"
        schema = "cp3_" + uuid4().hex
        engine = create_engine(postgres_url, execution_options={"schema_translate_map": {None: schema}})
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
    else:
        engine = create_engine(
            f'sqlite:///{tmp_path / "ledger.db"}', connect_args={"check_same_thread": False, "timeout": 15}
        )
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    with factory.begin() as db:
        db.add(User(id="user", email="ledger@example.com", hashed_password="fake"))
        db.flush()
        db.add(Course(id="course", user_id="user", name="test", filenames=[]))
        db.flush()
        budget_id = ensure_book_budget(db, db.get(Course, "course"), "version")
        db.add(
            ProcessingJob(
                id="job",
                course_id="course",
                user_id="user",
                job_type="book",
                status="running",
                worker_id="worker",
                attempts=1,
                lease_expires_at=datetime.utcnow() + timedelta(minutes=5),
            )
        )
    try:
        yield factory, budget_id
    finally:
        if schema:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def test_missing_usage_is_unknown():
    assert normalize_usage(None) == {"cost_usd": None, "input_tokens": None, "output_tokens": None}


@pytest.mark.parametrize("bad", [-1, float("inf"), float("nan"), True, "0.1"])
def test_invalid_usage_is_unknown(bad):
    assert all(
        value is None
        for value in normalize_usage({"cost": bad, "prompt_tokens": bad, "completion_tokens": bad}).values()
    )


def test_concurrent_independent_worker_reservations(ledger):
    factory, budget = ledger
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(lambda n: reserve_call(budget, str(n), D("0.02")), range(8)))
    assert sum(accepted) == 4
    with factory() as db:
        assert db.get(BookBudget, budget).reserved == 80_000_000


def test_duplicate_call_and_delivery(ledger):
    factory, budget = ledger
    assert reserve_call(budget, "call", D("0.05"))
    assert reserve_call(budget, "call", D("0.05"))
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda _: settle_call("call", D("0.03")), range(5)))
    with factory() as db:
        row = db.get(BookBudget, budget)
        assert (row.spent, row.reserved) == (30_000_000, 0)


def test_unknown_holds_full_reservation(ledger):
    factory, budget = ledger
    assert reserve_call(budget, "call", D("0.06"))
    settle_call("call", None)
    assert not reserve_call(budget, "retry", D("0.01"))
    with factory() as db:
        assert db.get(BookBudget, budget).reserved == 60_000_000
    settle_call("call", D("0.02"))
    settle_call("call", None)
    with factory() as db:
        assert db.get(ProviderCall, "call").cost == 20_000_000
    assert reserve_call(budget, "after-reconciliation", D(".01"))


def test_duplicate_response_does_not_release_other_reservation(ledger):
    factory, budget = ledger
    for call in ("one", "two"):
        assert reserve_call(budget, call, D("0.04"))
        record_provider_call(None, 1, "book", "chapter", "response", 10, {"cost": 0.02}, "received", call_id=call)
    with factory() as db:
        row = db.get(BookBudget, budget)
        assert (row.spent, row.reserved, row.state) == (20_000_000, 40_000_000, "blocked_unknown")


def test_overcharge_records_incident_and_blocks(ledger):
    factory, budget = ledger
    assert reserve_call(budget, "one", D(".03"))
    settle_call("one", D(".12"))
    assert not reserve_call(budget, "two", D(".001"))
    with factory() as db:
        row = db.get(BookBudget, budget)
        assert (row.spent, row.reserved, row.state) == (120_000_000, 0, "incident")


def test_lease_loss_denies_admission_but_allows_settlement(ledger):
    factory, budget = ledger
    context = ProviderCallContext(job_id="job", worker_id="worker", job_attempt=1)
    with usage_context(context):
        assert reserve_call(budget, "one", D(".03"))
        with factory.begin() as db:
            db.execute(update(ProcessingJob).values(worker_id="new-worker"))
        assert not reserve_call(budget, "two", D(".03"))
    settle_call("one", D(".02"))
    with factory() as db:
        assert db.get(BookBudget, budget).spent == 20_000_000


def test_retry_keeps_budget_and_legacy_retry_unknown(ledger):
    factory, budget = ledger
    with factory.begin() as db:
        course = db.get(Course, "course")
        assert ensure_book_budget(db, course, "version", retry=True) == budget
        legacy = ensure_book_budget(db, course, "legacy", retry=True)
        assert db.get(BookBudget, legacy).state == "blocked_unknown"
        assert ensure_book_budget(db, course, "new") != budget


def test_fail_closed_unverified_request_never_dispatches(ledger):
    _, budget = ledger
    with usage_context(ProviderCallContext(feature="book", budget_id=budget)):
        with pytest.raises(BudgetLimitError):
            dispatch_provider(
                lambda **_: pytest.fail("paid dispatch"),
                model="google/gemini-2.5-pro",
                request={"messages": [{"content": "Tiếng Việt ∑ √ ảnh"}]},
                feature="generation",
                attempt=1,
            )


def test_response_accounted_before_json_error_and_same_model_retry(ledger):
    factory, _ = ledger
    from app.services.llm import LLMService
    from app.schemas.generator_output import CourseTitleOutput

    service = LLMService()
    replies = iter(
        [
            SimpleNamespace(
                id="bad-json",
                usage=SimpleNamespace(model_dump=lambda: {"cost": 0.001, "prompt_tokens": 20}),
                choices=[SimpleNamespace(message=SimpleNamespace(content="invalid"))],
            ),
            SimpleNamespace(
                id="valid-json",
                usage={"cost": 0.002},
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"title":"test"}'))],
            ),
        ]
    )
    models = []

    def create(**kwargs):
        models.append(kwargs["model"])
        return next(replies)

    service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert service._call_openrouter_strict("private source", CourseTitleOutput, lambda: None, 100).title == "test"
    with factory() as db:
        rows = db.scalars(select(ProviderCall).order_by(ProviderCall.provider_attempt)).all()
        assert [row.cost for row in rows] == [1_000_000, 2_000_000]
        assert [row.provider_attempt for row in rows] == [1, 2]
        assert [row.outcome for row in rows] == ["schema_invalid", "valid"]
    assert models == [service.model, service.model]


def test_timeout_keeps_charge_and_stops_retry(ledger, monkeypatch):
    factory, budget = ledger
    monkeypatch.setattr("app.services.provider_usage.verified_request_bound", lambda *a: D(".03"))
    sent = []

    def timeout(**kwargs):
        sent.append(1)
        raise TimeoutError("private provider error")

    with usage_context(ProviderCallContext(feature="book", budget_id=budget)):
        with pytest.raises(BudgetLimitError):
            dispatch_provider(timeout, model="fake", request={}, feature="generation", attempt=1)
        with pytest.raises(BudgetLimitError):
            dispatch_provider(timeout, model="fake", request={}, feature="generation", attempt=2)
    assert len(sent) == 1
    with factory() as db:
        assert db.get(BookBudget, budget).reserved == 30_000_000


def test_overall_attempt_deadline_bounds_responsive_transport_and_holds_charge(ledger, monkeypatch):
    factory, budget = ledger
    monkeypatch.setattr("app.services.provider_usage.verified_request_bound", lambda *a: D(".03"))
    monkeypatch.setattr("app.services.provider_usage.settings.OPENROUTER_ATTEMPT_TIMEOUT_SECONDS", 0.02)
    transport_finished = Event()

    def responsive_but_too_long(**_kwargs):
        # Simulates bytes arriving within the read timeout while the total call
        # keeps running beyond the independent wall-clock attempt deadline.
        time.sleep(0.06)
        transport_finished.set()
        return SimpleNamespace(id="late", usage={"cost": 0.01}, choices=[])

    with usage_context(ProviderCallContext(feature="book", budget_id=budget)):
        with pytest.raises(BudgetLimitError, match="charge is unknown"):
            dispatch_provider(
                responsive_but_too_long,
                model="fake",
                request={},
                feature="generation",
                attempt=1,
            )
    assert not transport_finished.is_set()
    assert transport_finished.wait(1)
    with factory() as db:
        call = db.scalar(select(ProviderCall).order_by(ProviderCall.created_at.desc()))
        assert call.outcome == "timeout"
        assert call.cost is None
        assert db.get(BookBudget, budget).reserved == 30_000_000


def test_soft_time_limit_propagates_without_provider_retry(ledger):
    from billiard.exceptions import SoftTimeLimitExceeded
    from app.schemas.generator_output import CourseTitleOutput
    from app.services.llm import LLMService

    service = LLMService()
    attempts = []

    def interrupted(**_kwargs):
        attempts.append(1)
        raise SoftTimeLimitExceeded()

    service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=interrupted)))
    with pytest.raises(SoftTimeLimitExceeded):
        service._call_openrouter_strict("private", CourseTitleOutput, lambda: None, 100)
    assert attempts == [1]


def test_accounting_failure_never_provider_retry(ledger, monkeypatch):
    from app.services.llm import LLMService
    from app.schemas.generator_output import CourseTitleOutput

    service = LLMService()
    sent = []

    def create(**kwargs):
        sent.append(1)
        return SimpleNamespace(id="id", usage={"cost": 0.01})

    def fail(*args, **kwargs):
        raise AccountingError("fail")

    service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr("app.services.provider_usage.record_provider_call", fail)
    with pytest.raises(AccountingError):
        service._call_openrouter_strict("private", CourseTitleOutput, lambda: None, 100)
    assert len(sent) == 1


def test_test_budget_one_envelope_and_unknown(ledger):
    factory, _ = ledger
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _: reserve_test_budget("run", D(".2")), range(4))) == 1
    settle_test_budget("run", None)
    with factory() as db:
        assert db.get(ProviderTestBudget, "run").reserved == 200_000_000
    settle_test_budget("run", D(".04"))
    settle_test_budget("run", D(".03"))
    with factory() as db:
        assert db.get(ProviderTestBudget, "run").spent == 40_000_000


def test_dispatched_previous_attempt_holds_budget(ledger):
    factory, budget = ledger
    with usage_context(ProviderCallContext(job_id="job", worker_id="worker", job_attempt=1)):
        assert reserve_call(budget, "crashed", D(".03"))
    with factory.begin() as db:
        db.execute(update(ProviderCall).values(state="dispatched"))
        db.execute(update(ProcessingJob).values(attempts=2))
    with usage_context(ProviderCallContext(job_id="job", worker_id="worker", job_attempt=2)):
        assert not reserve_call(budget, "retry", D(".01"))
    with factory() as db:
        assert db.get(BookBudget, budget).reserved == 30_000_000


def test_account_cleanup_retains_anonymous_late_settlement(ledger):
    from app.services.provider_usage import anonymize_account

    factory, budget = ledger
    assert reserve_call(budget, "late", D(".03"))
    with factory.begin() as db:
        anonymize_account(db, "user", ["course"])
        db.query(ProcessingJob).delete()
        db.query(Course).delete()
        db.query(User).delete()
    record_provider_call("job", 1, "book", "chapter", "late-response", 10, {"cost": 0.02}, "received", call_id="late")
    with factory() as db:
        call = db.get(ProviderCall, "late")
        budget_row = db.get(BookBudget, budget)
        assert (call.user_id, call.course_id, call.job_id) == (None, None, None)
        assert (budget_row.user_id, budget_row.course_id, budget_row.version_id) == (None, None, None)
        assert budget_row.spent == 20_000_000
        assert budget_row.state == "closed"


def test_safe_stage_projection_and_fenced_heartbeat(ledger):
    from app.jobs.tasks import _progress_callback
    from app.models.provider_call import ProviderStage
    from app.routers.jobs import job_response
    from app.services.provider_usage import stage_timer

    factory, _ = ledger
    context = ProviderCallContext(
        job_id="job", worker_id="worker", job_attempt=1, heartbeat=_progress_callback("job", "worker", 1)
    )
    with usage_context(context), stage_timer("chapter", 2):
        with factory() as db:
            assert job_response(db, db.get(ProcessingJob, "job"))["stage"] == "chapter"
    with factory.begin() as db:
        event = db.scalar(select(ProviderStage))
        assert event.chapter == 2 and event.elapsed_ms is not None
        job = db.get(ProcessingJob, "job")
        job.product_stage = "google/private/chunk-id"
        assert job_response(db, job)["stage"] == "generating"
        job.cancel_requested = True
    with usage_context(context), pytest.raises(BudgetLimitError):
        with stage_timer("exporting"):
            pytest.fail("cancelled heartbeat")


def test_no_bill_exception_recorded_as_explicit_zero(ledger):
    factory, budget = ledger
    assert reserve_call(budget, "not-sent", D(".03"))
    record_provider_call(None, 1, "book", "outline", None, 0, {"cost": 0}, "no_bill", call_id="not-sent")
    with factory() as db:
        row = db.get(BookBudget, budget)
        assert (row.spent, row.reserved, row.state) == (0, 0, "active")


def test_runtime_budget_error_is_terminal_and_does_not_mint_budget(ledger, monkeypatch):
    from app.jobs import tasks

    factory, budget = ledger
    with factory.begin() as db:
        job = db.get(ProcessingJob, "job")
        job.status = "queued"
        job.attempts = 0
        job.payload_json = {"version_id": "version", "budget_id": budget}

    def fail(*args, **kwargs):
        raise BudgetLimitError("internal details never public")

    monkeypatch.setattr(tasks, "_execute_artifact", fail)
    assert tasks.execute_job("job", "worker") is None
    with factory() as db:
        job = db.get(ProcessingJob, "job")
        assert (job.status, job.error_code, job.attempts) == ("failed", "BOOK_BUDGET_LIMIT", 1)
        assert db.query(BookBudget).count() == 1
        assert job.payload_json["budget_id"] == budget


def test_sqlite_migration_roundtrip(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from app.core.config import settings

    url = f'sqlite:///{tmp_path / "migration.db"}'
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    inspector = inspect(engine)
    assert {"book_budgets", "provider_calls", "provider_test_budgets", "provider_stages"} <= set(
        inspector.get_table_names()
    )
    assert "product_stage" in {column["name"] for column in inspector.get_columns("processing_jobs")}
    engine.dispose()
    command.downgrade(config, "c9d0e1f2a3b4")
    command.upgrade(config, "head")


def test_offline_tokenizers_include_vietnamese_math_schema_and_explicit_caps(monkeypatch):
    from app.services.provider_tokens import estimate_gemini_request, count_embedding_input, ARTIFACTS, artifact_dir

    if any(not (artifact_dir() / name).exists() for name in ARTIFACTS):
        pytest.skip("Run python -m app.services.provider_tokens once during setup")
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("request-time download"))
    request = {
        "messages": [
            {"role": "system", "content": "Bạn là giáo viên."},
            {"role": "user", "content": "Tính ∑ x² + √π tiếng Việt"},
        ],
        "max_tokens": 100,
        "response_format": {
            "json_schema": {"schema": {"type": "object", "properties": {"answer": {"type": "string"}}}}
        },
        "extra_body": {"reasoning": {"max_tokens": 128}},
    }
    estimate = estimate_gemini_request("google/gemini-2.5-flash", request)
    assert estimate.input_bound > 1024
    assert estimate.output_bound == 228
    assert estimate.framing_allowance == 1024
    assert estimate.calibration_state == "unobserved-router-framing"
    assert estimate.upper_bound_usd > 0
    assert request["extra_body"]["provider"]["max_price"] == {"prompt": 0.3, "completion": 2.5}
    assert count_embedding_input("openai/text-embedding-3-small", ["Tiếng Việt ∑ √π"]) > 0
    with pytest.raises(BudgetLimitError):
        estimate_gemini_request(
            "google/gemini-2.5-flash", {"messages": [{"content": [{"type": "image_url", "image_url": "private"}]}]}
        )


def test_gemini_estimator_preserves_saved_book_routing_controls():
    from app.services.provider_tokens import ARTIFACTS, artifact_dir, estimate_gemini_request

    if any(not (artifact_dir() / name).exists() for name in ARTIFACTS):
        pytest.skip("Run python -m app.services.provider_tokens once during setup")

    request = {
        "messages": [{"role": "user", "content": "bounded"}],
        "max_tokens": 100,
        "extra_body": {
            "provider": {
                "require_parameters": True,
                "max_price": {"prompt": 0.30, "completion": 2.50},
                "sort": "throughput",
            },
            "reasoning": {"max_tokens": 128},
        },
    }
    estimate = estimate_gemini_request("google/gemini-2.5-flash", request)
    assert estimate.output_bound == 228
    assert request["extra_body"]["provider"] == {
        "require_parameters": True,
        "max_price": {"prompt": 0.30, "completion": 2.50},
        "sort": "throughput",
    }


def test_final_dispatch_preserves_saved_book_routing_controls(ledger, monkeypatch):
    from app.services import provider_usage

    _factory, budget = ledger
    captured = {}

    def offline_bound(model, request, feature):
        assert model == "google/gemini-2.5-flash"
        assert feature == "generation"
        assert request["extra_body"]["provider"] == {
            "require_parameters": True,
            "max_price": {"prompt": 0.30, "completion": 2.50},
            "sort": "throughput",
        }
        # Test-only admission proves the request delivered after the real local
        # adapter. Production keeps the CP3 uncalibrated gate closed.
        return D("0.001")

    def create(**request):
        captured.update(request)
        return SimpleNamespace(
            id="cp8-final-routing",
            usage={"cost": 0, "prompt_tokens": 1, "completion_tokens": 1},
        )

    monkeypatch.setattr(provider_usage, "verified_request_bound", offline_bound)
    request = {
        "messages": [{"role": "user", "content": "bounded"}],
        "max_tokens": 100,
        "extra_body": {
            "provider": {
                "require_parameters": True,
                "max_price": {"prompt": 0.30, "completion": 2.50},
                "sort": "throughput",
            },
            "reasoning": {"max_tokens": 128},
        },
    }
    context = ProviderCallContext(
        job_id="job",
        worker_id="worker",
        job_attempt=1,
        course_id="course",
        user_id="user",
        version_id="version",
        budget_id=budget,
        feature="book",
        stage="chapter",
    )
    with usage_context(context):
        dispatch_provider(
            create,
            model="google/gemini-2.5-flash",
            request=request,
            feature="generation",
            attempt=1,
        )
    assert captured["extra_body"]["provider"] == {
        "require_parameters": True,
        "max_price": {"prompt": 0.30, "completion": 2.50},
        "sort": "throughput",
    }


def test_stale_unknown_settlement_cannot_erase_distinct_call_incident(ledger):
    from app.services.provider_usage import _settle

    factory, budget = ledger
    assert reserve_call(budget, "unknown-stale", D(".01"))
    assert reserve_call(budget, "overcharged-other", D(".01"))
    with factory() as stale:
        snapshot = stale.get(BookBudget, budget)
        call = stale.get(ProviderCall, "unknown-stale")
        assert snapshot.state == "active"
        stale.commit()  # Keep stale identity-map snapshot, release SQLite read transaction.
        settle_call("overcharged-other", D(".03"))
        _settle(stale, call, None)
        stale.commit()
    with factory() as db:
        row = db.get(BookBudget, budget)
        assert (row.state, row.incident_code, row.reserved) == ("incident", "PROVIDER_OVERCHARGE", 10_000_000)
    settle_call("unknown-stale", D(".001"))
    assert not reserve_call(budget, "after-incident-reconciliation", D(".001"))
    with factory() as db:
        assert db.get(BookBudget, budget).state == "incident"


def test_reconciliation_never_reopens_budget_with_historical_incident(ledger):
    factory, budget = ledger
    assert reserve_call(budget, "unknown-historical", D(".01"))
    settle_call("unknown-historical", None)
    with factory.begin() as db:
        db.execute(update(BookBudget).where(BookBudget.id == budget).values(incident_code="PROVIDER_OVERCHARGE"))
    settle_call("unknown-historical", D(".001"))
    assert not reserve_call(budget, "after-historical-incident", D(".001"))
    with factory() as db:
        assert db.get(BookBudget, budget).state != "active"


def _fake_embedding_boundary(create):
    from app.services.vector_store import OpenRouterEmbeddingFunction

    embedding = OpenRouterEmbeddingFunction.__new__(OpenRouterEmbeddingFunction)
    embedding._client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    embedding._model = "openai/text-embedding-3-small"
    embedding._dimensions = 2
    embedding._max_retries = 2
    embedding._max_retry_delay = 0
    embedding._provider_guard = SimpleNamespace(
        acquire=lambda _: None,
        release=lambda _: None,
        record_success=lambda _: None,
        record_failure=lambda *a, **k: 0,
        distributed=False,
    )
    return embedding


def _stub_embedding_bound(monkeypatch):
    monkeypatch.setattr(
        "app.services.provider_usage.verified_request_bound",
        lambda _model, _request, feature: D("0.001")
        if feature == "embedding"
        else D("0.001"),
    )


@pytest.mark.parametrize(
    "interruption",
    ["incident", "unknown", "closed", "course_deleted", "owner_changed", "job_cancelled", "claim_stolen"],
)
def test_embedding_final_dispatch_fence_releases_only_unsent_reservation(ledger, monkeypatch, interruption):
    from app.services import provider_usage

    _stub_embedding_bound(monkeypatch)
    factory, budget = ledger
    assert reserve_call(budget, "other-live", D(".01"))
    sent = []
    reserved_ids = []
    original_reserve = provider_usage.reserve_call

    def reserve_then_interrupt(budget_id, call_id, amount):
        accepted = original_reserve(budget_id, call_id, amount)
        assert accepted
        reserved_ids.append(call_id)
        if interruption == "incident":
            settle_call("other-live", D(".03"))
        elif interruption == "unknown":
            settle_call("other-live", None)
        else:
            with factory.begin() as db:
                if interruption == "closed":
                    db.execute(update(BookBudget).where(BookBudget.id == budget).values(state="closed"))
                elif interruption == "course_deleted":
                    db.execute(update(Course).where(Course.id == "course").values(is_deleted=True))
                elif interruption == "owner_changed":
                    db.add(User(id="other-owner", email="other-owner@example.com", hashed_password="fake"))
                    db.flush()
                    db.execute(update(Course).where(Course.id == "course").values(user_id="other-owner"))
                elif interruption == "job_cancelled":
                    db.execute(update(ProcessingJob).where(ProcessingJob.id == "job").values(cancel_requested=True))
                else:
                    db.execute(update(ProcessingJob).where(ProcessingJob.id == "job").values(worker_id="stolen"))
        return accepted

    def create(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(id="forbidden-response", usage={"cost": 0}, data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])])

    monkeypatch.setattr(provider_usage, "reserve_call", reserve_then_interrupt)
    context = ProviderCallContext(
        job_id="job",
        worker_id="worker",
        job_attempt=1,
        course_id="course",
        user_id="user",
        version_id="version",
        feature="book",
        budget_id=budget,
    )
    with usage_context(context), pytest.raises(BudgetLimitError):
        _fake_embedding_boundary(create)._embed(["Tiếng Việt ∑ √π"])
    assert sent == []
    assert len(reserved_ids) == 1
    with factory() as db:
        call = db.get(ProviderCall, reserved_ids[0])
        assert (call.state, call.cost, call.outcome) == ("not_sent", 0, "no_bill")
        assert db.get(BookBudget, budget).reserved == (0 if interruption == "incident" else 10_000_000)
        if interruption == "unknown":
            assert db.get(ProviderCall, "other-live").state == "unknown"


def test_embedding_incident_after_dispatch_does_not_undo_authorized_call(ledger, monkeypatch):
    _stub_embedding_bound(monkeypatch)
    factory, budget = ledger
    assert reserve_call(budget, "later-incident", D(".01"))
    sent = []

    def create(**kwargs):
        sent.append(kwargs)
        with factory() as db:
            call = db.scalar(select(ProviderCall).where(ProviderCall.call_id != "later-incident"))
            assert call.state == "dispatched"
        settle_call("later-incident", D(".03"))
        return SimpleNamespace(
            id="authorized-response", usage={"cost": 0}, data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])]
        )

    with usage_context(ProviderCallContext(feature="book", budget_id=budget)), pytest.raises(BudgetLimitError):
        _fake_embedding_boundary(create)._embed(["Tiếng Việt ∑ √π"])
    assert len(sent) == 1
    with factory() as db:
        call = db.scalar(select(ProviderCall).where(ProviderCall.response_id == "authorized-response"))
        assert (call.state, call.cost) == ("settled", 0)
        assert db.get(BookBudget, budget).state == "incident"


def test_distinct_call_concurrent_unknown_incident_and_reconciliation(ledger):
    factory, budget = ledger
    assert reserve_call(budget, "parallel-unknown", D(".01"))
    assert reserve_call(budget, "parallel-overcharge", D(".01"))
    ready = Barrier(2)

    def settle_together(item):
        ready.wait(timeout=10)
        settle_call(*item)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(settle_together, [("parallel-unknown", None), ("parallel-overcharge", D(".03"))]))
    settle_call("parallel-unknown", D(".001"))
    with factory() as db:
        row = db.get(BookBudget, budget)
        assert (row.state, row.incident_code, row.spent, row.reserved) == (
            "incident",
            "PROVIDER_OVERCHARGE",
            31_000_000,
            0,
        )
    assert not reserve_call(budget, "parallel-after", D(".001"))
