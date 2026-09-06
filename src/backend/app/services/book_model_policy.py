"""Immutable, persisted request policy for one logical Book version."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BookPolicyError(ValueError):
    """The saved Book controls cannot be honored by an eligible endpoint."""


class BookModelPolicy(BaseModel):
    """All paid Book calls bind this snapshot instead of mutable runtime settings."""

    model_config = ConfigDict(frozen=True)

    model: str = "google/gemini-2.5-flash"
    input_price_ceiling: Decimal = Decimal("0.30")
    output_price_ceiling: Decimal = Decimal("2.50")
    reasoning_budget: int = Field(default=512, ge=0, le=1024)
    revision: str = "balanced-book-v1"
    require_parameters: bool = True
    provider_sort: str = "throughput"
    structured_output: str = "json_schema"
    output_cap_parameter: str = "max_tokens"

    @field_validator("input_price_ceiling", "output_price_ceiling")
    @classmethod
    def valid_price(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("Book price ceilings must be finite and nonnegative")
        return value

    @classmethod
    def default(cls) -> "BookModelPolicy":
        return cls()

    def extra_body(self, *, reasoning_tokens: int | None = None) -> dict:
        reasoning = self.reasoning_budget if reasoning_tokens is None else reasoning_tokens
        if reasoning < 0 or reasoning > 1024:
            raise BookPolicyError("Reasoning allowance is outside the saved Book policy")
        return {
            "provider": {
                "require_parameters": self.require_parameters,
                "max_price": {
                    "prompt": float(self.input_price_ceiling),
                    "completion": float(self.output_price_ceiling),
                },
                "sort": self.provider_sort,
            },
            "reasoning": {"max_tokens": reasoning},
        }

    def validate_capabilities(self, supported_parameters: Iterable[str]) -> None:
        supported = set(supported_parameters)
        required = {self.output_cap_parameter, "reasoning", "structured_outputs", "response_format"}
        missing = sorted(required - supported)
        if missing:
            raise BookPolicyError(
                "No eligible Book endpoint supports all saved required parameters: "
                + ", ".join(missing)
            )


def policy_json(policy: BookModelPolicy) -> dict:
    """Return a JSON-native snapshot suitable for durable database storage."""

    return policy.model_dump(mode="json")

