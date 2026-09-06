from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.schemas.generator_output import (
    BookChapterContent,
    BookObjectiveCoverage,
    BookOutline,
)
from app.services.book_model_policy import BookModelPolicy, BookPolicyError
from app.services.llm import (
    BookIncompleteError,
    LLMGenerationError,
    LLMService,
    validate_book_chapter_completion,
)
from app.schemas.source_plan import SourceObjective, SourcePlan, SourcePlanUnit
from app.services.generator import Generator
from app.models.course import Course
from app.models.provider_call import BookBudget
from app.services import database
from app.services.provider_usage import (
    BudgetLimitError,
    ensure_book_budget,
    get_book_model_policy,
    get_remaining_book_budget,
    require_estimated_book_capacity,
)
from app.services.provider_tokens import RequestEstimate


def _response(content: str, finish_reason: str = "stop"):
    return SimpleNamespace(
        id="fake-response",
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
        usage={"cost": 0, "prompt_tokens": 1, "completion_tokens": 1},
    )


def test_saved_policy_is_immutable_and_applied_to_retry(monkeypatch):
    policy = BookModelPolicy.default()
    calls = []
    responses = [
        _response("{}"),
        _response('{"title":"T","summary":"S","preface":"","chapters":[]}'),
    ]
    service = LLMService.__new__(LLMService)
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: None)))
    service.model = "google/gemini-2.5-pro"
    service.book_policy = policy
    service._test_mode = False
    service._provider_guard = SimpleNamespace(
        acquire=lambda _feature, **_kwargs: object(), release=lambda _permit: None,
        record_success=lambda _feature: None,
        record_failure=lambda *_args, **_kwargs: 0,
    )

    def fake_dispatch(_create, *, model, request, feature, attempt):
        calls.append({"model": model, "request": request, "attempt": attempt})
        if attempt == 1:
            monkeypatch.setattr("app.core.config.settings.OPENROUTER_BOOK_MODEL", "google/gemini-2.5-pro")
        return responses.pop(0)

    monkeypatch.setattr("app.services.llm.dispatch_provider", fake_dispatch)
    monkeypatch.setattr("app.services.llm.mark_response_outcome", lambda _outcome: None)
    result = service._call_openrouter_strict("prompt", BookOutline, lambda: None, 1800)

    assert result.title == "T"
    assert {call["model"] for call in calls} == {"google/gemini-2.5-flash"}
    assert all(call["request"]["extra_body"] == policy.extra_body() for call in calls)
    assert policy.input_price_ceiling == Decimal("0.30")
    with pytest.raises(Exception):
        policy.model = "google/gemini-2.5-pro"


def test_length_and_unsupported_required_parameters_fail_safely(monkeypatch):
    service = LLMService.__new__(LLMService)
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: None)))
    service.model = "google/gemini-2.5-pro"
    service.book_policy = BookModelPolicy.default()
    service._test_mode = False
    service._provider_guard = SimpleNamespace(
        acquire=lambda _feature, **_kwargs: object(), release=lambda _permit: None,
        record_success=lambda _feature: None,
        record_failure=lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "app.services.llm.dispatch_provider",
        lambda *_args, **_kwargs: _response(
            '{"title":"T","summary":"S","preface":"","chapters":[]}', "length"
        ),
    )
    monkeypatch.setattr("app.services.llm.mark_response_outcome", lambda _outcome: None)
    with pytest.raises(LLMGenerationError, match="cắt"):
        service._call_openrouter_strict("prompt", BookOutline, lambda: None, 1800)

    with pytest.raises(BookPolicyError):
        BookModelPolicy.default().validate_capabilities({"structured_outputs", "max_tokens"})


def test_policy_snapshot_is_saved_once_per_book_version(monkeypatch):
    with database.SessionLocal.begin() as db:
        course = Course(id="policy-course", user_id="owner", filenames=["source.txt"])
        db.add(course)
        db.flush()
        budget_id = ensure_book_budget(db, course, "book-v1")

    monkeypatch.setattr(
        "app.core.config.settings.OPENROUTER_BOOK_MODEL", "google/gemini-2.5-pro"
    )
    with database.SessionLocal() as db:
        policy = get_book_model_policy(db, "policy-course", "book-v1")
        row = db.get(BookBudget, budget_id)
        assert policy.model == "google/gemini-2.5-flash"
        assert row.model_policy["revision"] == "balanced-book-v1"


def test_remaining_book_budget_uses_durable_spent_and_reserved_amounts():
    with database.SessionLocal.begin() as db:
        course = Course(id="remaining-course", user_id="owner", filenames=["source.txt"])
        db.add(course)
        db.flush()
        budget_id = ensure_book_budget(db, course, "book-v1")
        budget = db.get(BookBudget, budget_id)
        budget.spent = 10_000_000
        budget.reserved = 5_000_000

    with database.SessionLocal() as db:
        assert get_remaining_book_budget(db, "remaining-course", "book-v1") == Decimal(
            "0.08"
        )


def test_remaining_capacity_uses_measured_retry_request_not_fixed_fee():
    estimate = RequestEstimate(
        input_bound=0,
        output_bound=4_000,
        input_price=Decimal("0.30"),
        output_price=Decimal("2.50"),
        fixed_fees=Decimal("0"),
        method="local",
        revision="test",
        framing_allowance=0,
        calibration_state="unobserved-router-framing",
    )
    with database.SessionLocal.begin() as db:
        course = Course(id="retry-capacity-course", user_id="owner", filenames=["source.txt"])
        db.add(course)
        db.flush()
        budget_id = ensure_book_budget(db, course, "book-v1")
        budget = db.get(BookBudget, budget_id)
        budget.spent = 80_000_000

    with database.SessionLocal() as db:
        with pytest.raises(BudgetLimitError, match="remaining allowance"):
            require_estimated_book_capacity(
                db,
                "retry-capacity-course",
                "book-v1",
                [estimate],
                retry_request=estimate,
            )


def test_source_plan_is_not_started_without_explicit_residual_capacity(monkeypatch):
    course_id = "source-plan-preflight-course"
    with database.SessionLocal.begin() as db:
        db.add(
            Course(
                id=course_id,
                user_id="owner",
                filenames=["source.txt"],
                status="ready",
            )
        )
    generator = Generator(None, LLMService(model="google/gemini-2.5-pro"))
    version_id = generator.prepare_artifact_version(
        course_id, "book", {"detail_level": "Tiêu chuẩn"}
    )
    with database.SessionLocal.begin() as db:
        budget = db.query(BookBudget).filter_by(
            course_id=course_id, version_id=version_id
        ).one()
        budget.spent = 94_000_000
    monkeypatch.setattr(
        generator,
        "_source_plan_inputs",
        lambda *_args: ("d" * 64, "bounded source", ["e1"]),
    )
    oversized = RequestEstimate(
        input_bound=1_000,
        output_bound=4_000,
        input_price=Decimal("0.30"),
        output_price=Decimal("2.50"),
        fixed_fees=Decimal("0"),
        method="test",
        revision="test",
        framing_allowance=0,
        calibration_state="test",
    )
    monkeypatch.setattr(LLMService, "estimate_source_plan_request", lambda *_args: oversized)
    source_plan_started = False

    def source_plan(*_args, **_kwargs):
        nonlocal source_plan_started
        source_plan_started = True
        raise AssertionError("source plan must not start")

    monkeypatch.setattr(generator, "_get_source_plan", source_plan)

    with pytest.raises(BudgetLimitError, match="remaining allowance"):
        generator.generate_book(course_id, version_id=version_id)
    assert source_plan_started is False


def test_first_use_source_plan_uses_bound_book_policy(monkeypatch):
    policy = BookModelPolicy.default()
    base = LLMService.__new__(LLMService)
    base.model = "google/gemini-2.5-pro"
    base.book_policy = None
    bound = base.with_book_policy(policy)
    captured = {}

    def generate(_context, digest, revision, ids, **_kwargs):
        captured.update(model=bound.model, controls=bound.book_policy.extra_body())
        return SourcePlan(
            revision=revision,
            source_digest=digest,
            objectives=[SourceObjective(id="o1", text="Learn", evidence_ids=ids)],
            units=[SourcePlanUnit(id="u1", title="Unit", objective_ids=["o1"], evidence_ids=ids)],
        )

    bound.generate_source_plan = generate
    generator = Generator(None, base)
    monkeypatch.setattr(
        generator, "_source_plan_inputs", lambda *_args: ("d" * 64, "source", ["e1"])
    )
    with database.SessionLocal.begin() as db:
        db.add(Course(id="bound-plan", user_id="owner", filenames=["source.txt"]))
    plan = generator._get_source_plan(
        "bound-plan",
        "book",
        selected_llm=bound,
        db_session_factory=database.SessionLocal,
    )
    assert plan.units[0].id == "unit-1"
    assert captured == {"model": policy.model, "controls": policy.extra_body()}


def test_empty_assigned_chapter_is_incomplete():
    empty = BookChapterContent(chapter_title="Unit", source_chunk_ids=["e1"])
    with pytest.raises(BookIncompleteError, match="incomplete"):
        validate_book_chapter_completion(
            empty,
            valid_chunk_ids=["e1", "e2"],
            required_objectives=["Explain", "Apply"],
        )


def test_duplicate_objective_cannot_replace_an_assigned_objective():
    chapter = BookChapterContent(
        chapter_title="Unit",
        objectives=["Explain A", "Explain A"],
        sections=[{"title": "A", "content": "Explain A with evidence."}],
        key_points=["A"],
        review_questions=["What is A?"],
        source_chunk_ids=["e1", "e2"],
    )
    with pytest.raises(BookIncompleteError, match="incomplete"):
        validate_book_chapter_completion(
            chapter,
            valid_chunk_ids=["e1", "e2"],
            required_objectives=["Explain A", "Apply B"],
        )


def test_objective_label_without_bound_instructional_content_is_incomplete():
    chapter = BookChapterContent(
        chapter_title="Unit",
        objectives=["Explain A", "Apply B"],
        sections=[{"title": "A", "content": "Explain A only."}],
        objective_coverage=[
            BookObjectiveCoverage(
                objective_id="objective-a",
                objective="Explain A",
                section_indices=[0],
            )
        ],
        key_points=["A"],
        review_questions=["What is A?"],
        source_chunk_ids=["e1", "e2"],
    )
    with pytest.raises(BookIncompleteError, match="incomplete"):
        validate_book_chapter_completion(
            chapter,
            valid_chunk_ids=["e1", "e2"],
            required_objectives={
                "objective-a": "Explain A",
                "objective-b": "Apply B",
            },
        )


def test_objective_identity_preserves_case_sensitive_symbols():
    changed_case = BookChapterContent(
        chapter_title="Unit",
        objectives=["Explain x + y = 2"],
        sections=[{"title": "Equation", "content": "Explain x + y = 2."}],
        objective_coverage=[
            BookObjectiveCoverage(
                objective_id="objective-equation",
                objective="Explain x + y = 2",
                section_indices=[0],
            )
        ],
        key_points=["Equation"],
        review_questions=["Explain it"],
        source_chunk_ids=["e1"],
    )
    with pytest.raises(BookIncompleteError, match="incomplete"):
        validate_book_chapter_completion(
            changed_case,
            valid_chunk_ids=["e1"],
            required_objectives={"objective-equation": "Explain x + Y = 2"},
        )



def test_two_case_distinct_objectives_do_not_collapse():
    distinct = BookChapterContent(
        chapter_title="Unit",
        objectives=["Explain x + Y = 2", "Explain x + y = 2"],
        sections=[
            {"title": "Uppercase", "content": "Explain x + Y = 2."},
            {"title": "Lowercase", "content": "Explain x + y = 2."},
        ],
        objective_coverage=[
            BookObjectiveCoverage(
                objective_id="objective-upper",
                objective="Explain x + Y = 2",
                section_indices=[0],
            ),
            BookObjectiveCoverage(
                objective_id="objective-lower",
                objective="Explain x + y = 2",
                section_indices=[1],
            ),
        ],
        key_points=["Both equations"],
        review_questions=["Compare them"],
        source_chunk_ids=["e1", "e2"],
    )
    validate_book_chapter_completion(
        distinct,
        valid_chunk_ids=["e1", "e2"],
        required_objectives={
            "objective-upper": "Explain x + Y = 2",
            "objective-lower": "Explain x + y = 2",
        },
    )


@pytest.mark.parametrize(
    "coverage",
    [
        [
            BookObjectiveCoverage(
                objective_id="objective-a",
                objective="Explain A",
                section_indices=[0],
            ),
            BookObjectiveCoverage(
                objective_id="objective-a",
                objective="Explain A",
                section_indices=[0],
            ),
        ],
        [
            BookObjectiveCoverage(
                objective_id="objective-unknown",
                objective="Explain A",
                section_indices=[0],
            )
        ],
    ],
)
def test_duplicate_or_unknown_objective_assignment_is_incomplete(coverage):
    chapter = BookChapterContent(
        chapter_title="Unit",
        objectives=["Explain A"],
        sections=[{"title": "A", "content": "Explain A."}],
        objective_coverage=coverage,
        key_points=["A"],
        review_questions=["What is A?"],
        source_chunk_ids=["e1"],
    )
    with pytest.raises(BookIncompleteError, match="incomplete"):
        validate_book_chapter_completion(
            chapter,
            valid_chunk_ids=["e1"],
            required_objectives={"objective-a": "Explain A"},
        )
