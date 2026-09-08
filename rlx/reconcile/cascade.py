"""The single deterministic decision point: compare two facts, then run the ordered
rule cascade. Produces an explicit rule trace so the report can show *why*."""
from __future__ import annotations

from ..config import CONFIG
from ..store.models import Fact, RelationResult
from .compare import compare, CompareResult
from .confidence import score
from .rules import CASCADE


def _template_corroborated(a: Fact, b: Fact, near: bool) -> str:
    how = "agree" if not near else "agree within rounding"
    return (f"Independent sources {how}: “{a.value_text}” "
            f"({a.doc_title or 'doc A'}, p.{a.source_page}) and “{b.value_text}” "
            f"({b.doc_title or 'doc B'}, p.{b.source_page}).")


def _template_contradiction(a: Fact, b: Fact) -> str:
    return (f"No contextual difference (period, scope, basis, unit, vintage) explains the gap: "
            f"“{a.value_text}” ({a.doc_title or 'doc A'}, p.{a.source_page}) vs "
            f"“{b.value_text}” ({b.doc_title or 'doc B'}, p.{b.source_page}).")


def reconcile(a: Fact, b: Fact, t=None) -> RelationResult:
    t = t or CONFIG.t
    trace: list[dict] = []

    ci = compare(a, b, t)
    trace.append({"step": "compare", "result": ci.result.value, "mode": ci.mode,
                  "rel_diff": ci.rel_diff, "note": ci.note})

    same_doc_page = (a.doc_id == b.doc_id and a.source_page == b.source_page)

    if ci.result == CompareResult.EQUAL:
        if same_doc_page:
            return RelationResult("unresolved", "DUPLICATE",
                                  "Same value on the same page - treated as a duplicate, not a relation.",
                                  0.3, trace)
        conf = score("EXACT", a, b, t.rule_base)
        return RelationResult("corroborated", "EXACT",
                              _template_corroborated(a, b, near=False), conf, trace)

    if ci.result == CompareResult.INCOMPARABLE:
        return RelationResult("unresolved", "INCOMPARABLE",
                              f"The two facts are not directly comparable ({ci.note}).",
                              0.3, trace)

    # ci.result == DIFFERENT -> run the cascade
    for rule in CASCADE:
        out = rule(a, b, t)
        trace.append({"step": out.rule_code, "applies": out.applies, "detail": out.detail})
        if out.applies:
            conf = score(out.rule_code, a, b, t.rule_base)
            bucket = out.bucket
            if bucket == "corroborated" and same_doc_page:
                bucket = "unresolved"
            return RelationResult(bucket, out.rule_code, out.explanation, conf, trace)

    # nothing explained the difference
    conf = score("NONE", a, b, t.rule_base)
    if min(a.extraction_confidence or 0, b.extraction_confidence or 0) >= t.tau_contradiction \
            and not (a.sanity_flags or b.sanity_flags):
        return RelationResult("contradiction", "NONE",
                              _template_contradiction(a, b), conf, trace)
    return RelationResult("unresolved", "NONE_LOWCONF",
                          "Values differ and no rule explains it, but extraction confidence "
                          "is too low (or a sanity flag is set) to call it a contradiction.",
                          conf, trace)
