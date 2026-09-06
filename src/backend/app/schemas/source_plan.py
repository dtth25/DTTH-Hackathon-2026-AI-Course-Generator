"""Internal shared curriculum plan for one indexed source revision."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator


NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SourceObjective(BaseModel):
    id: NonBlank
    text: NonBlank
    evidence_ids: list[NonBlank] = Field(min_length=1)


class GlossaryEntry(BaseModel):
    term: NonBlank
    definition: NonBlank
    evidence_ids: list[NonBlank] = Field(min_length=1)


class CanonicalEquation(BaseModel):
    name: NonBlank
    latex: NonBlank
    meaning: str = ""
    evidence_ids: list[NonBlank] = Field(min_length=1)


class SourcePlanUnit(BaseModel):
    id: NonBlank
    title: NonBlank
    objective_ids: list[NonBlank] = Field(default_factory=list)
    evidence_ids: list[NonBlank] = Field(min_length=1)


class SourcePlan(BaseModel):
    revision: int = Field(ge=1)
    source_digest: str = Field(min_length=16)
    objectives: list[SourceObjective] = Field(min_length=1)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    equations: list[CanonicalEquation] = Field(default_factory=list)
    units: list[SourcePlanUnit] = Field(min_length=1)

    @field_validator("units")
    @classmethod
    def unit_ids_are_unique(cls, units: list[SourcePlanUnit]) -> list[SourcePlanUnit]:
        ids = [unit.id for unit in units]
        if len(ids) != len(set(ids)):
            raise ValueError("Source plan unit IDs must be unique")
        return units

    @model_validator(mode="after")
    def objective_references_are_unambiguous(self):
        objective_ids = [objective.id for objective in self.objectives]
        if len(objective_ids) != len(set(objective_ids)):
            raise ValueError("Source plan objective IDs must be unique")
        known = set(objective_ids)
        unknown = {
            objective_id
            for unit in self.units
            for objective_id in unit.objective_ids
            if objective_id not in known
        }
        if unknown:
            raise ValueError("Source plan units reference unknown objectives")
        return self
