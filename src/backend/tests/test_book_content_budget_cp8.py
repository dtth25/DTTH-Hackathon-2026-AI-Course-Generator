import pytest

from app.schemas.source_plan import CanonicalEquation, SourceObjective, SourcePlan, SourcePlanUnit
from app.services.book_content_budget import (
    BookCoverageInfeasible,
    ChapterCompletion,
    allocate_book_budget,
    classify_chapter_completion,
)


def _plan(unit_count=5, *, math=False):
    objectives = [
        SourceObjective(id=f"o{i}", text=f"Mục tiêu {i}", evidence_ids=[f"e{i}"])
        for i in range(unit_count)
    ]
    units = [
        SourcePlanUnit(id=f"u{i}", title=f"Chủ đề {i}", objective_ids=[f"o{i}"], evidence_ids=[f"e{i}"])
        for i in range(unit_count)
    ]
    equations = (
        [CanonicalEquation(name="Định luật", latex=r"E=mc^2", evidence_ids=["e0"])]
        if math else []
    )
    return SourcePlan(
        revision=1, source_digest="a" * 64, objectives=objectives,
        units=units, equations=equations,
    )


@pytest.mark.parametrize(
    ("plan", "input_tokens", "output_tokens", "detail"),
    [(_plan(1), 4_000, 5_000, "Tóm tắt"), (_plan(5), 32_000, 18_000, "Tiêu chuẩn"),
     (_plan(6, math=True), 40_000, 22_000, "Chuyên sâu")],
)
def test_allocation_covers_objectives_and_stays_inside_envelope(plan, input_tokens, output_tokens, detail):
    chapters = allocate_book_budget(plan, input_tokens, output_tokens, detail)
    assert {item.id for item in plan.objectives} == {
        objective for chapter in chapters for objective in chapter.objective_ids
    }
    assert sum(chapter.input_bound for chapter in chapters) <= input_tokens
    assert sum(chapter.visible_output_allowance + chapter.reasoning_allowance for chapter in chapters) <= output_tokens
    assert len({evidence for chapter in chapters for evidence in chapter.evidence_ids}) == len(plan.units)
    if plan.equations:
        assert max(chapter.reasoning_allowance for chapter in chapters) == 1024


def test_deep_coverage_reports_infeasible_instead_of_summarizing():
    with pytest.raises(BookCoverageInfeasible):
        allocate_book_budget(_plan(8, math=True), 5_000, 7_000, "Chuyên sâu")


def test_objective_evidence_is_included_in_its_chapter_context_budget():
    plan = SourcePlan(
        revision=1,
        source_digest="b" * 64,
        objectives=[SourceObjective(id="objective", text="Explain", evidence_ids=["definition"])],
        units=[
            SourcePlanUnit(
                id="unit", title="Topic", objective_ids=["objective"], evidence_ids=["example"]
            )
        ],
    )
    chapter = allocate_book_budget(plan, 4_000, 5_000, "Tóm tắt")[0]
    assert chapter.evidence_ids == ("example", "definition")


def test_unassigned_evidenced_objective_is_rejected():
    plan = SourcePlan(
        revision=1,
        source_digest="c" * 64,
        objectives=[
            SourceObjective(id="assigned", text="Assigned", evidence_ids=["e1"]),
            SourceObjective(id="orphan", text="Required too", evidence_ids=["e2"]),
        ],
        units=[
            SourcePlanUnit(
                id="unit", title="Topic", objective_ids=["assigned"], evidence_ids=["e1"]
            )
        ],
    )
    with pytest.raises(BookCoverageInfeasible, match="unassigned"):
        allocate_book_budget(plan, 10_000, 10_000, "Chuyên sâu")


def test_measured_prompt_bound_controls_input_feasibility():
    with pytest.raises(BookCoverageInfeasible, match="input"):
        allocate_book_budget(
            _plan(1),
            32_000,
            5_000,
            "Tiêu chuẩn",
            measured_input_bounds={"u0": 32_497},
        )


@pytest.mark.parametrize(
    ("finish_reason", "missing", "equation", "expected"),
    [
        ("length", [], False, ChapterCompletion.TRUNCATED),
        ("stop", ["u2"], False, ChapterCompletion.MISSING_UNIT),
        ("stop", [], True, ChapterCompletion.INCOMPLETE_EQUATION),
        ("stop", [], False, ChapterCompletion.COMPLETE),
    ],
)
def test_incomplete_chapter_classification(finish_reason, missing, equation, expected):
    assert classify_chapter_completion(finish_reason, missing, equation) is expected
