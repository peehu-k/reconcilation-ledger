"""Chunk -> validated, quote-verified RawFacts.

Reliability posture:
  - schema-constrained call + one repair attempt; still-bad output -> logged, chunk skipped
  - every proposed fact must pass the quote guard against the chunk text or it is
    rejected (recorded in rejected_facts, never promoted to the ledger)
  - a provider that goes away raises LLMUnavailable which the pipeline handles
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from ..store.models import RawFact
from .prompts import EXTRACT_SYSTEM, EXTRACT_USER, REPAIR_SYSTEM
from .quote_guard import verify_quote
from .schema import RawFactList, json_schema


@dataclass
class ChunkResult:
    raw_facts: list[RawFact] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)   # payloads that failed the quote guard
    n_proposed: int = 0
    error: str | None = None
    raw_output: str | None = None


def extract_chunk(provider, *, title: str, page: int, printed: str | None, text: str) -> ChunkResult:
    user = EXTRACT_USER.format(title=title, page=page, printed=printed or "?", text=text[:12000])
    try:
        obj, raw = provider.complete_json(EXTRACT_SYSTEM, user, schema=json_schema(),
                                          repair_system=REPAIR_SYSTEM)
    except ValidationError as e:
        return ChunkResult(error=f"schema: {e}")
    except ValueError as e:  # JSON could not be parsed even after repair
        return ChunkResult(error=f"json: {e}", raw_output=None)

    try:
        parsed = RawFactList.model_validate(obj)
    except ValidationError as e:
        return ChunkResult(error=f"schema: {e}", raw_output=str(obj)[:4000])

    res = ChunkResult(n_proposed=len(parsed.facts))
    for m in parsed.facts:
        g = verify_quote(m.quote, text)
        if g.match == "FAIL":
            payload = m.model_dump()
            payload["_quote_guard_score"] = round(g.score, 1)
            res.rejected.append(payload)
            continue
        res.raw_facts.append(RawFact(
            fact_kind=m.fact_kind,
            entity_text=m.entity_text.strip(),
            attribute_label=m.attribute_label.strip(),
            value_text=m.value_text.strip(),
            quote=m.quote,
            unit_text=m.unit_text,
            period_text=m.period_text,
            as_of_text=m.as_of_text,
            estimate_status_text=m.estimate_status_text,
            basis_text=m.basis_text,
            scope_text=m.scope_text,
            attributed_to_text=m.attributed_to_text,
            self_confidence=m.self_confidence,
            page_no=page,
            quote_match=g.match,
            quote_char_start=g.char_start,
            quote_char_end=g.char_end,
        ))
    return res
