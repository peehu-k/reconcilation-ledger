"""Decide whether two normalized facts state the same thing.

Pure and deterministic. Numeric comparison only fires when both facts carry a
value_num AND a compatible quantity unit; identifiers / codes / addresses / names
compare as normalized strings (so PIN 122001 vs 122002 is DIFFERENT, not "equal").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from ..config import CONFIG
from ..store.models import Fact
from ..normalize.text import casefold_key

_QUANT = {"currency_amount", "ratio", "tonnes", "days", "count", "number"}
_PIN = re.compile(r"\b\d{5,6}\b")


class CompareResult(str, Enum):
    EQUAL = "EQUAL"
    DIFFERENT = "DIFFERENT"
    INCOMPARABLE = "INCOMPARABLE"


@dataclass
class CompareInfo:
    result: CompareResult
    rel_diff: float | None = None
    mode: str = ""            # numeric | string
    note: str = ""


def _currencies_compatible(a: Fact, b: Fact) -> bool:
    if a.currency and b.currency:
        return a.currency == b.currency
    return True  # one/both unknown -> treat as compatible


def _canon_string(f: Fact) -> str:
    s = casefold_key(f.value_text or "")
    return s


def compare(a: Fact, b: Fact, t=None) -> CompareInfo:
    t = t or CONFIG.t

    a_num = a.value_num is not None and a.unit_canonical in _QUANT
    b_num = b.value_num is not None and b.unit_canonical in _QUANT

    if a_num and b_num:
        if a.unit_canonical != b.unit_canonical:
            # e.g. ratio vs currency_amount -> not the same kind of quantity
            return CompareInfo(CompareResult.INCOMPARABLE, mode="numeric",
                               note=f"{a.unit_canonical} vs {b.unit_canonical}")
        if not _currencies_compatible(a, b):
            return CompareInfo(CompareResult.INCOMPARABLE, mode="numeric",
                               note=f"{a.currency} vs {b.currency}")
        denom = max(abs(a.value_num), abs(b.value_num), 1e-9)
        rel = abs(a.value_num - b.value_num) / denom
        if rel <= t.rel_tol_equal:
            return CompareInfo(CompareResult.EQUAL, rel_diff=rel, mode="numeric")
        return CompareInfo(CompareResult.DIFFERENT, rel_diff=rel, mode="numeric")

    if a_num != b_num:
        # one numeric quantity, one not -> cannot compare as like-for-like
        return CompareInfo(CompareResult.INCOMPARABLE, mode="mixed",
                           note="one side non-numeric")

    # both non-numeric: compare normalized strings; PIN-aware
    sa, sb = _canon_string(a), _canon_string(b)
    if sa == sb and sa != "":
        return CompareInfo(CompareResult.EQUAL, mode="string")
    pa, pb = _PIN.search(a.value_text or ""), _PIN.search(b.value_text or "")
    if pa and pb:
        return CompareInfo(
            CompareResult.EQUAL if pa.group(0) == pb.group(0) else CompareResult.DIFFERENT,
            mode="string", note="pin")
    if sa == "" or sb == "":
        return CompareInfo(CompareResult.INCOMPARABLE, mode="string", note="empty value")
    # substring containment -> same underlying string written at different length
    if sa in sb or sb in sa:
        return CompareInfo(CompareResult.EQUAL, mode="string", note="containment")
    return CompareInfo(CompareResult.DIFFERENT, mode="string")
