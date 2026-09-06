"""Evidence-driven token allocation and non-truncation checks for Books."""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.source_plan import SourcePlan


class BookCoverageInfeasible(ValueError):
    """Requested depth cannot cover every evidenced objective inside the envelope."""


class ChapterBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    unit_id: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    input_bound: int = Field(gt=0)
    visible_output_allowance: int = Field(gt=0)
    reasoning_allowance: int = Field(ge=0, le=1024)
    expected_learning_objectives: tuple[str, ...] = Field(min_length=1)
    objective_ids: tuple[str, ...] = Field(min_length=1)

    @property
    def max_tokens(self) -> int:
        """Provider visible-output cap; reasoning is reserved separately."""

        return self.visible_output_allowance

    @property
    def output_bound(self) -> int:
        return self.visible_output_allowance + self.reasoning_allowance


class ChapterCompletion(str, Enum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    MISSING_UNIT = "missing_unit"
    INCOMPLETE_EQUATION = "incomplete_equation"


def classify_chapter_completion(
    finish_reason: str | None,
    missing_unit_ids: Iterable[str] = (),
    incomplete_equation: bool = False,
) -> ChapterCompletion:
    if finish_reason == "length":
        return ChapterCompletion.TRUNCATED
    if tuple(missing_unit_ids):
        return ChapterCompletion.MISSING_UNIT
    if incomplete_equation:
        return ChapterCompletion.INCOMPLETE_EQUATION
    return ChapterCompletion.COMPLETE


def repair_fits(*, required_tokens: int, remaining_output_tokens: int) -> bool:
    """Only the incomplete chapter may be repaired, and only from remaining output."""

    return required_tokens > 0 and required_tokens <= remaining_output_tokens


def _detail_key(value: str) -> str:
    text = (value or "").strip().casefold()
    if text in {"chuyên sâu", "deep", "advanced"}:
        return "deep"
    if text in {"tóm tắt", "summary", "short"}:
        return "summary"
    return "standard"


def _normalized_units(units: SourcePlan | Iterable[Any]):
    if isinstance(units, SourcePlan):
        objective_by_id = {item.id: item for item in units.objectives}
        assigned_objectives = {
            objective_id for unit in units.units for objective_id in unit.objective_ids
        }
        unassigned = sorted(set(objective_by_id) - assigned_objectives)
        if unassigned:
            raise BookCoverageInfeasible(
                "Source plan has unassigned required objectives: " + ", ".join(unassigned)
            )
        equation_evidence = {eid for equation in units.equations for eid in equation.evidence_ids}
        raw_units = units.units
    else:
        raw_units = list(units)
        objective_by_id = {}
        equation_evidence = set()

    normalized = []
    seen = set()
    for raw in raw_units:
        value = raw if isinstance(raw, dict) else raw.model_dump()
        unit_id = str(value.get("id") or value.get("unit_id") or "").strip()
        evidence_ids = tuple(dict.fromkeys(str(item) for item in value.get("evidence_ids", ()) if str(item)))
        objective_ids = tuple(dict.fromkeys(str(item) for item in value.get("objective_ids", ()) if str(item)))
        supplied = value.get("expected_learning_objectives") or value.get("objectives") or ()
        objective_texts = tuple(str(item) for item in supplied if str(item))
        if objective_by_id:
            unknown = [item for item in objective_ids if item not in objective_by_id]
            if unknown:
                raise BookCoverageInfeasible(f"Unit {unit_id} references unknown objectives")
            objective_texts = tuple(objective_by_id[item].text for item in objective_ids)
            evidence_ids = tuple(
                dict.fromkeys(
                    [
                        *evidence_ids,
                        *(
                            evidence_id
                            for objective_id in objective_ids
                            for evidence_id in objective_by_id[objective_id].evidence_ids
                        ),
                    ]
                )
            )
        elif not objective_ids:
            objective_ids = tuple(f"{unit_id}:objective:{i}" for i in range(len(objective_texts)))
        if not unit_id or unit_id in seen or not evidence_ids or not objective_ids or not objective_texts:
            raise BookCoverageInfeasible("Every stable unit needs unique identity, evidence, and objectives")
        seen.add(unit_id)
        normalized.append(
            (unit_id, evidence_ids, objective_ids, objective_texts, bool(set(evidence_ids) & equation_evidence))
        )
    if not normalized:
        raise BookCoverageInfeasible("A Book needs at least one evidenced source-plan unit")
    return normalized


def allocate_book_budget(
    units: SourcePlan | Iterable[Any],
    available_input_tokens: int,
    available_output_tokens: int,
    detail_level: str,
    *,
    measured_input_bounds: dict[str, int] | None = None,
) -> list[ChapterBudget]:
    """Allocate complete per-unit calls or reject the requested scope.

    ``available_output_tokens`` includes visible JSON and reasoning. The caller
    reserves outline/review/repair separately before passing the chapter envelope.
    """

    if available_input_tokens <= 0 or available_output_tokens <= 0:
        raise BookCoverageInfeasible("Book token allowances must be positive")
    normalized = _normalized_units(units)
    detail = _detail_key(detail_level)
    minimum_visible = {"summary": 900, "standard": 1800, "deep": 2200}[detail]
    maximum_visible = {"summary": 1600, "standard": 3200, "deep": 4200}[detail]

    reasoning = [1024 if math_heavy else 512 for *_, math_heavy in normalized]
    heuristic_inputs = [
        640 + 320 * len(evidence) + 160 * len(objectives)
        for _, evidence, _, objectives, _ in normalized
    ]
    if measured_input_bounds is None:
        input_weights = heuristic_inputs
    else:
        expected_units = {item[0] for item in normalized}
        if set(measured_input_bounds) != expected_units or any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in measured_input_bounds.values()
        ):
            raise BookCoverageInfeasible("Measured input bounds must cover every source unit")
        input_weights = [measured_input_bounds[item[0]] for item in normalized]
    visible_weights = [
        minimum_visible + 260 * max(0, len(objectives) - 1) + (500 if math_heavy else 0)
        for _, _, _, objectives, math_heavy in normalized
    ]
    if sum(input_weights) > available_input_tokens:
        raise BookCoverageInfeasible("Insufficient input space for targeted evidence coverage")
    if sum(visible_weights) + sum(reasoning) > available_output_tokens:
        raise BookCoverageInfeasible(
            f"Requested {detail} coverage cannot fit every evidenced learning objective"
        )

    # Spend extra capacity in proportion to objective/equation complexity without
    # inventing chapters or repeating the whole source in every prompt.
    extra = available_output_tokens - sum(visible_weights) - sum(reasoning)
    complexities = [len(item[3]) + (2 if item[4] else 0) for item in normalized]
    while extra and any(value < maximum_visible for value in visible_weights):
        progressed = False
        for index in sorted(range(len(normalized)), key=lambda i: (-complexities[i], i)):
            room = maximum_visible - visible_weights[index]
            if room <= 0:
                continue
            grant = min(room, extra, max(1, extra // max(1, len(normalized))))
            visible_weights[index] += grant
            extra -= grant
            progressed = True
            if not extra:
                break
        if not progressed:
            break

    return [
        ChapterBudget(
            unit_id=unit_id,
            evidence_ids=evidence,
            input_bound=input_weights[index],
            visible_output_allowance=visible_weights[index],
            reasoning_allowance=reasoning[index],
            expected_learning_objectives=objective_texts,
            objective_ids=objective_ids,
        )
        for index, (unit_id, evidence, objective_ids, objective_texts, _math) in enumerate(normalized)
    ]


def outline_output_allowance(detail_level: str, available_output_tokens: int) -> int:
    preferred = {"summary": 1500, "standard": 1800, "deep": 2000}[_detail_key(detail_level)]
    if available_output_tokens < preferred:
        raise BookCoverageInfeasible("Outline schema cannot fit the Book output envelope")
    return preferred
