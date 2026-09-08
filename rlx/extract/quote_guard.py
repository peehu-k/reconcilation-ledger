"""The hallucination firewall.

A proposed fact is only allowed into the ledger if its `quote` can be re-found in
the source text. Three tiers: exact substring, whitespace-normalized exact, and a
high-threshold fuzzy window match. Anything else FAILS and the fact is rejected.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from ..config import CONFIG
from ..normalize.text import norm_ws


@dataclass
class GuardResult:
    match: str            # "exact" | "fuzzy" | "FAIL"
    char_start: int | None = None
    char_end: int | None = None
    score: float = 0.0


def _norm(s: str) -> str:
    return norm_ws(s).casefold()


def verify_quote(quote: str, source_text: str, *, fuzz_threshold: int | None = None) -> GuardResult:
    fuzz_threshold = fuzz_threshold if fuzz_threshold is not None else CONFIG.t.quote_fuzz
    if not quote or not quote.strip() or not source_text:
        return GuardResult("FAIL")

    # tier 1: exact substring
    idx = source_text.find(quote)
    if idx >= 0:
        return GuardResult("exact", idx, idx + len(quote), 100.0)

    # tier 2: whitespace-normalized exact
    nq, ns = _norm(quote), _norm(source_text)
    j = ns.find(nq)
    if j >= 0 and len(nq) >= 3:
        return GuardResult("exact", None, None, 100.0)

    # tier 3: fuzzy sliding window over the normalized source
    if len(nq) < 8:
        return GuardResult("FAIL")
    win = len(nq)
    best = 0.0
    step = max(1, win // 4)
    for start in range(0, max(1, len(ns) - win + 1), step):
        seg = ns[start:start + win + 10]
        s = fuzz.partial_ratio(nq, seg)
        if s > best:
            best = s
        if best >= 99:
            break
    if best >= fuzz_threshold:
        return GuardResult("fuzzy", None, None, best)
    return GuardResult("FAIL", score=best)
