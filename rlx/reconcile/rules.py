"""The ordered reconciliation rule cascade.

Each rule is a pure function (Fact, Fact, thresholds) -> Outcome. A rule that
`applies` explains why two DIFFERENT values are not actually a contradiction. Order
matters: the first rule that applies wins and is recorded in the rule trace.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from rapidfuzz import fuzz

from ..store.models import Fact
from ..normalize.vintage import days_apart, maturity_rank

_ID_ATTR = re.compile(r"identity|identifier|registration\s*(no|number)|\bcin\b|\bgstin\b|\bdin\b", re.I)


@dataclass
class Outcome:
    rule_code: str
    applies: bool
    explanation: str = ""
    detail: dict = field(default_factory=dict)
    # which bucket this rule implies when it applies
    bucket: str = "reconciled"


def _fy(p: Optional[str]) -> str:
    return p or "an unspecified period"


def _sym_diff(a: list[str], b: list[str]) -> set[str]:
    return set(a or []) ^ set(b or [])


# --------------------------------------------------------------------------- rules

def _sig(x: float, n: int = 3) -> float:
    if x == 0:
        return 0.0
    from math import floor, log10
    return round(x, -int(floor(log10(abs(x)))) + (n - 1))


def rule_rounding(a: Fact, b: Fact, t) -> Outcome:
    if a.value_num is None or b.value_num is None:
        return Outcome("ROUNDING", False)
    denom = max(abs(a.value_num), abs(b.value_num), 1e-9)
    rel = abs(a.value_num - b.value_num) / denom
    # rounding = agree to 3 significant figures, or within a tight relative band.
    # A 0.1pp gap in a growth rate (6.4 vs 6.5) is NOT rounding - it stays DIFFERENT.
    if _sig(a.value_num) == _sig(b.value_num) or rel <= t.rel_tol_equal:
        return Outcome("ROUNDING", True, bucket="corroborated",
                       explanation=(f"The figures agree to 3 significant figures "
                                    f"({rel*100:.3f}% apart) - a rounding / precision difference."),
                       detail={"rel_diff": rel})
    return Outcome("ROUNDING", False, detail={"rel_diff": rel})


def rule_unit_scale(a: Fact, b: Fact, t) -> Outcome:
    if a.value_num is None or b.value_num is None or a.value_num == 0 or b.value_num == 0:
        return Outcome("UNIT_SCALE", False)
    ratio = abs(a.value_num) / abs(b.value_num)
    for k in range(-3, 4):
        if k == 0:
            continue
        if abs(ratio - 10.0 ** k) / (10.0 ** k) <= 0.02:
            return Outcome("UNIT_SCALE", True,
                           explanation=(f"One figure is {10.0**abs(k):g}x the other - a unit / scale "
                                        f"convention that was not fully normalized "
                                        f"({a.unit_canonical}/{a.currency} vs {b.unit_canonical}/{b.currency})."),
                           detail={"factor": 10.0 ** k})
    return Outcome("UNIT_SCALE", False)


def rule_period(a: Fact, b: Fact, t) -> Outcome:
    pa, pb = a.period_canonical, b.period_canonical
    if pa and pb and pa != pb:
        return Outcome("PERIOD", True,
                       explanation=(f"The figures cover different periods: "
                                    f"one is {_fy(pa)}, the other {_fy(pb)}."),
                       detail={"period_a": pa, "period_b": pb})
    return Outcome("PERIOD", False)


def rule_temporal_status(a: Fact, b: Fact, t) -> Outcome:
    temporal_kind = {"status", "event"}
    if not ({a.fact_kind, b.fact_kind} <= temporal_kind):
        return Outcome("TEMPORAL_STATUS", False)
    d = days_apart(a.as_of_date, b.as_of_date)
    if d is not None and d >= t.vintage_min_days:
        older, newer = (a, b) if (a.as_of_date or "") <= (b.as_of_date or "") else (b, a)
        return Outcome("TEMPORAL_STATUS", True,
                       explanation=(f"The status changed over time: as of {older.as_of_date} "
                                    f"“{older.value_text}”; as of {newer.as_of_date} "
                                    f"“{newer.value_text}”."),
                       detail={"older": older.as_of_date, "newer": newer.as_of_date})
    return Outcome("TEMPORAL_STATUS", False)


def rule_vintage(a: Fact, b: Fact, t) -> Outcome:
    # only measured quantities "mature" between publications; codes / addresses do not
    if not ({a.fact_kind, b.fact_kind} <= {"numeric"}):
        return Outcome("ESTIMATE_VINTAGE", False)
    if a.value_num is None or b.value_num is None:
        return Outcome("ESTIMATE_VINTAGE", False)
    # period already established as same-or-unspecified by the time we get here
    sa, sb = a.estimate_status, b.estimate_status
    ra, rb = maturity_rank(sa), maturity_rank(sb)
    status_diff = (sa or sb) and ra != rb
    d = days_apart(a.as_of_date, b.as_of_date)
    date_diff = d is not None and d >= t.vintage_min_days
    if status_diff or date_diff:
        lo, hi = (a, b) if ra <= rb else (b, a)
        bits = []
        if status_diff:
            bits.append(f"{lo.estimate_status or 'earlier estimate'} → {hi.estimate_status or 'later estimate'}")
        if date_diff:
            bits.append(f"as-of {a.as_of_date} vs {b.as_of_date}")
        return Outcome("ESTIMATE_VINTAGE", True,
                       explanation=("Same figure at different vintages: " + "; ".join(bits)
                                    + " - the number matured between publications, not a contradiction."),
                       detail={"status_a": sa, "status_b": sb, "as_of_a": a.as_of_date,
                               "as_of_b": b.as_of_date, "days_apart": d})
    return Outcome("ESTIMATE_VINTAGE", False)


def rule_scope(a: Fact, b: Fact, t) -> Outcome:
    diff = _sym_diff(a.scope_flags, b.scope_flags)
    if diff:
        return Outcome("SCOPE", True,
                       explanation=(f"The figures use a different scope "
                                    f"(A: {a.scope_flags or 'unqualified'}; B: {b.scope_flags or 'unqualified'})."),
                       detail={"scope_a": a.scope_flags, "scope_b": b.scope_flags})
    return Outcome("SCOPE", False)


def rule_basis(a: Fact, b: Fact, t) -> Outcome:
    diff = _sym_diff(a.basis_flags, b.basis_flags)
    if diff:
        return Outcome("BASIS", True,
                       explanation=(f"The figures are on a different basis "
                                    f"(A: {a.basis_flags or 'unqualified'}; B: {b.basis_flags or 'unqualified'})."),
                       detail={"basis_a": a.basis_flags, "basis_b": b.basis_flags})
    return Outcome("BASIS", False)


def rule_identifier_revision(a: Fact, b: Fact, t) -> Outcome:
    """Two near-identical identifiers (CIN / registration no.) across filings of
    different dates: the core number is the same, a prefix/format character changed
    (e.g. an unlisted 'U' -> listed 'L' company classification). Not a conflict."""
    if a.value_num is not None or b.value_num is not None:
        return Outcome("IDENTIFIER_REVISION", False)
    if not (_ID_ATTR.search(a.attribute_key or "") or _ID_ATTR.search(a.attribute_display or "")):
        return Outcome("IDENTIFIER_REVISION", False)
    va, vb = (a.value_text or "").strip(), (b.value_text or "").strip()
    if not va or not vb or va == vb:
        return Outcome("IDENTIFIER_REVISION", False)
    sim = fuzz.ratio(va, vb)
    same_tail = len(va) == len(vb) and sum(x != y for x, y in zip(va, vb)) <= 2
    if sim >= 88 or same_tail:
        return Outcome("IDENTIFIER_REVISION", True,
                       explanation=(f"The identifiers are the same but for a format/prefix change "
                                    f"(“{va}” vs “{vb}”) between filings - a registration-status "
                                    f"reclassification, not a conflicting value."),
                       detail={"similarity": sim})
    return Outcome("IDENTIFIER_REVISION", False)


def rule_attribution(a: Fact, b: Fact, t) -> Outcome:
    aa, ab = (a.attributed_to or "").lower(), (b.attributed_to or "").lower()
    if aa != ab and (aa or ab):
        return Outcome("ATTRIBUTION", True, bucket="unresolved",
                       explanation=(f"One figure is relayed from a third party "
                                    f"(A: {a.attributed_to or 'primary'}; B: {b.attributed_to or 'primary'}); "
                                    f"treat as unverified rather than independent agreement."),
                       detail={"attributed_a": a.attributed_to, "attributed_b": b.attributed_to})
    return Outcome("ATTRIBUTION", False)


CASCADE: list[Callable[[Fact, Fact, object], Outcome]] = [
    rule_rounding,
    rule_unit_scale,
    rule_period,
    rule_temporal_status,
    rule_vintage,
    rule_scope,
    rule_basis,
    rule_identifier_revision,
    rule_attribution,
]
