"""Confidence scoring for a relation. Deterministic, bounded [0, 1]."""
from __future__ import annotations

from ..store.models import Fact


def _min_ec(a: Fact, b: Fact) -> float:
    return min(a.extraction_confidence or 0.5, b.extraction_confidence or 0.5)


def _metadata_completeness(rule_code: str, a: Fact, b: Fact) -> float:
    need = {
        "PERIOD": [a.period_canonical, b.period_canonical],
        "ESTIMATE_VINTAGE": [a.estimate_status or a.as_of_date, b.estimate_status or b.as_of_date],
        "TEMPORAL_STATUS": [a.as_of_date, b.as_of_date],
        "SCOPE": [a.scope_flags or b.scope_flags],
        "BASIS": [a.basis_flags or b.basis_flags],
    }.get(rule_code)
    if not need:
        return 1.0
    return 1.0 if all(need) else 0.7


def score(rule_code: str, a: Fact, b: Fact, rule_base: dict) -> float:
    base = rule_base.get(rule_code, 0.7)
    v = base * _min_ec(a, b) * _metadata_completeness(rule_code, a, b)
    # a flagged fact drags the relation down
    if a.sanity_flags or b.sanity_flags:
        v *= 0.6
    return max(0.0, min(1.0, v))
