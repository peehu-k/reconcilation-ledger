"""Pydantic schema for the LLM's extraction output. Also the JSON Schema handed to
Ollama / Gemini for constrained decoding."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class RawFactModel(BaseModel):
    fact_kind: Literal["numeric", "status", "attribute", "event"] = "attribute"
    entity_text: str = Field(..., min_length=1)
    attribute_label: str = Field(..., min_length=1)
    value_text: str = Field(..., min_length=1)
    quote: str = Field(..., min_length=1)
    unit_text: Optional[str] = None
    period_text: Optional[str] = None
    as_of_text: Optional[str] = None
    estimate_status_text: Optional[str] = None
    basis_text: Optional[str] = None
    scope_text: Optional[str] = None
    attributed_to_text: Optional[str] = None
    self_confidence: float = 0.7

    @field_validator("self_confidence")
    @classmethod
    def _clip(cls, v: float) -> float:
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0.7
        return max(0.0, min(1.0, v))

    @field_validator("*", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if isinstance(v, str) and v.strip().lower() in {"", "null", "none", "n/a", "na"}:
            return None
        return v


class RawFactList(BaseModel):
    facts: list[RawFactModel] = Field(default_factory=list)


def json_schema() -> dict:
    return RawFactList.model_json_schema()
