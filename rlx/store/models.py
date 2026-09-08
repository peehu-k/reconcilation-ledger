"""Plain dataclasses mirroring stored rows, plus the `Fact` value object used by the
deterministic reconcile layer (which must not import sqlite)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class RawFact:
    """Exactly what the LLM proposed, before normalization."""
    fact_kind: str
    entity_text: str
    attribute_label: str
    value_text: str
    quote: str
    unit_text: Optional[str] = None
    period_text: Optional[str] = None
    as_of_text: Optional[str] = None
    estimate_status_text: Optional[str] = None
    basis_text: Optional[str] = None
    scope_text: Optional[str] = None
    attributed_to_text: Optional[str] = None
    self_confidence: float = 0.7
    # filled in by the pipeline
    doc_id: Optional[int] = None
    block_id: Optional[int] = None
    page_no: Optional[int] = None
    quote_match: Optional[str] = None
    quote_char_start: Optional[int] = None
    quote_char_end: Optional[int] = None


@dataclass
class Fact:
    """Normalized, canonical, comparable. This is the unit the reconcile cascade sees."""
    entity_key: str
    entity_display: str
    attribute_key: str
    attribute_display: str
    fact_kind: str
    value_text: str
    quote: str
    value_num: Optional[float] = None
    currency: Optional[str] = None
    unit_canonical: Optional[str] = None
    scale_applied: Optional[float] = None
    period_canonical: Optional[str] = None
    as_of_date: Optional[str] = None            # ISO yyyy-mm-dd
    estimate_status: Optional[str] = None
    basis_flags: list[str] = field(default_factory=list)
    scope_flags: list[str] = field(default_factory=list)
    attributed_to: Optional[str] = None
    extraction_confidence: float = 0.5
    sanity_flags: list[str] = field(default_factory=list)
    # provenance (present once persisted)
    id: Optional[int] = None
    doc_id: Optional[int] = None
    doc_title: Optional[str] = None
    source_page: Optional[int] = None
    printed_label: Optional[str] = None
    quote_match: Optional[str] = None
    content_hash: Optional[str] = None

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["basis_flags"] = json.dumps(self.basis_flags)
        d["scope_flags"] = json.dumps(self.scope_flags)
        d["sanity_flags"] = json.dumps(self.sanity_flags)
        return d

    @staticmethod
    def from_row(row: Any) -> "Fact":
        g = (lambda k: row[k]) if not isinstance(row, dict) else row.get
        return Fact(
            id=g("id"),
            doc_id=g("doc_id"),
            entity_key=g("entity_key"),
            entity_display=g("entity_display"),
            attribute_key=g("attribute_key"),
            attribute_display=g("attribute_display"),
            fact_kind=g("fact_kind"),
            value_text=g("value_text"),
            quote=g("quote") or "",
            value_num=g("value_num"),
            currency=g("currency"),
            unit_canonical=g("unit_canonical"),
            scale_applied=g("scale_applied"),
            period_canonical=g("period_canonical"),
            as_of_date=g("as_of_date"),
            estimate_status=g("estimate_status"),
            basis_flags=json.loads(g("basis_flags") or "[]"),
            scope_flags=json.loads(g("scope_flags") or "[]"),
            attributed_to=g("attributed_to"),
            extraction_confidence=g("extraction_confidence") or 0.5,
            sanity_flags=json.loads(g("sanity_flags") or "[]"),
            source_page=g("source_page"),
            printed_label=g("printed_label"),
            quote_match=g("quote_match"),
            content_hash=g("content_hash"),
        )


@dataclass
class RelationResult:
    bucket: str                                  # corroborated|contradiction|reconciled|unresolved
    rule_code: str
    explanation: str
    confidence: float
    rule_trace: list[dict] = field(default_factory=list)
    explanation_source: str = "template"
