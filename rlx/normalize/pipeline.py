"""RawFact (what the LLM proposed) -> Fact (canonical, comparable).

Pure function: no DB, no network. Registry linking of near-duplicate entity/attribute
keys happens afterwards in match/registry against the persisted registries.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

from ..store.models import Fact, RawFact
from .attributes import attribute_display, attribute_key
from .entities import entity_key, person_display
from .flags import basis_flags, scope_flags
from .footnotes import strip_footnote_markers
from .periods import parse_period
from .sanity import sanity_flags
from .text import norm_ws
from .units import parse_quantity
from .vintage import parse_estimate_status, resolve_as_of

QUOTE_WEIGHT = {"exact": 1.0, "fuzzy": 0.8, "FAIL": 0.0, None: 0.6}


@dataclass
class DocContext:
    doc_id: Optional[int] = None
    doc_title: Optional[str] = None
    primary_entity_key: Optional[str] = None
    published_date: Optional[str] = None


def _content_hash(f: Fact) -> str:
    # NB: source_page is deliberately NOT part of the hash - the same figure repeated
    # on several pages of one document is one fact, not many (keeps the ledger clean).
    key = json.dumps({
        "e": f.entity_key, "a": f.attribute_key, "k": f.fact_kind,
        "v": round(f.value_num, 3) if f.value_num is not None else norm_ws(f.value_text).lower(),
        "u": f.unit_canonical, "c": f.currency, "p": f.period_canonical,
        "as_of": f.as_of_date, "vin": f.estimate_status,
        "basis": f.basis_flags, "scope": f.scope_flags, "att": f.attributed_to,
        "doc": f.doc_id,
    }, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()


def normalize_fact(rf: RawFact, ctx: DocContext, *, structural_confidence: float = 0.9,
                   printed_label: str | None = None) -> Fact:
    value_clean = strip_footnote_markers(norm_ws(rf.value_text or ""))
    quote_clean = norm_ws(rf.quote or "")

    q = parse_quantity(value_clean, rf.unit_text, rf.attribute_label or "",
                       fact_kind=rf.fact_kind or "numeric")

    ekey = entity_key(rf.entity_text or "", ctx.primary_entity_key)
    edisp = person_display(rf.entity_text or "") or (rf.entity_text or "")
    if not ekey and ctx.primary_entity_key:
        ekey = ctx.primary_entity_key

    akey = attribute_key(rf.attribute_label or "")
    adisp = attribute_display(rf.attribute_label or "")

    period = parse_period(rf.period_text) or parse_period(quote_clean)
    estimate_status = parse_estimate_status(rf.estimate_status_text, rf.basis_text, quote_clean)
    as_of = resolve_as_of(rf.as_of_text or quote_clean, ctx.published_date)

    bflags = basis_flags(rf.basis_text, quote_clean)
    sflags = scope_flags(rf.scope_text, quote_clean)
    attributed = norm_ws(rf.attributed_to_text) or None

    qweight = QUOTE_WEIGHT.get(rf.quote_match, 0.6)
    self_conf = rf.self_confidence if rf.self_confidence is not None else 0.7
    extraction_conf = max(0.0, min(1.0, self_conf * structural_confidence * qweight))

    sflags_bad = sanity_flags(
        fact_kind=rf.fact_kind or "attribute",
        attribute_label=rf.attribute_label or "",
        value_text=value_clean,
        value_num=q.value_num,
        unit_canonical=q.unit_canonical,
        structural_confidence=structural_confidence,
    )

    f = Fact(
        entity_key=ekey or "unknown",
        entity_display=edisp,
        attribute_key=akey or "unknown",
        attribute_display=adisp,
        fact_kind=rf.fact_kind or ("numeric" if q.value_num is not None else "attribute"),
        value_text=value_clean,
        quote=quote_clean,
        value_num=q.value_num,
        currency=q.currency,
        unit_canonical=q.unit_canonical,
        scale_applied=q.scale_applied,
        period_canonical=period,
        as_of_date=as_of,
        estimate_status=estimate_status,
        basis_flags=bflags,
        scope_flags=sflags,
        attributed_to=attributed,
        extraction_confidence=extraction_conf,
        sanity_flags=sflags_bad,
        doc_id=ctx.doc_id,
        doc_title=ctx.doc_title,
        source_page=rf.page_no,
        printed_label=printed_label,
        quote_match=rf.quote_match,
    )
    f.content_hash = _content_hash(f)
    return f
