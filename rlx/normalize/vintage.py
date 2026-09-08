"""Estimate vintage - the signature reconciliation axis.

A macroeconomic figure for the same period legitimately changes as it matures:
  first advance estimate -> second advance estimate -> provisional -> revised -> actual
and a forward-looking 'projection' is a different thing again. Publishers also report
the same time-series stock at different as-of dates.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from .text import norm_ws

_RANK = {
    "projection": 0,      # forward-looking, not a measurement of the past
    "first_advance": 1,
    "second_advance": 2,
    "provisional": 3,
    "revised": 4,
    "actual": 5,
}

_PATTERNS = [
    ("second_advance", re.compile(r"\bsecond\s+advance\s+estimate|2nd\s*ae\b", re.I)),
    ("first_advance", re.compile(r"\bfirst\s+advance\s+estimate|1st\s*ae\b|\badvance\s+estimate", re.I)),
    ("revised", re.compile(r"\b(first\s+)?revised\s+estimate|\bre\b|\(re\)|partially\s+revised|\(pr\)", re.I)),
    ("provisional", re.compile(r"\bprovisional(\s+estimate)?\b|\bpe\b|\(p\)", re.I)),
    ("projection", re.compile(
        r"\bproject(ed|ion)?\b|\bforecast\b|\bestimated\s+to\s+(grow|expand|be)\b|"
        r"\bexpected\s+to\s+(grow|be)\b|\boutlook\b|\bbudget\s+estimate\b|\(be\)|\bbaseline\b|"
        r"\bis\s+projected\b|\bto\s+grow\s+(by|at)\b", re.I)),
]


def parse_estimate_status(*texts: Optional[str]) -> Optional[str]:
    blob = norm_ws(" ".join(t for t in texts if t))
    if not blob:
        return None
    for label, rx in _PATTERNS:
        if rx.search(blob):
            return label
    return None


def maturity_rank(status: Optional[str]) -> int:
    return _RANK.get(status or "", 3)  # unknown treated as mid ('provisional'-ish)


def is_projection(status: Optional[str]) -> bool:
    return status == "projection"


_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _extract_explicit_date(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = norm_ws(text).lower()
    m = _DATE_ISO.search(t)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})\b", t)
    if m:
        return f"{int(m.group(3)):04d}-{_MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})\b", t)
    if m:
        return f"{int(m.group(3)):04d}-{_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    # bare "October 2025" / "as of October" with a nearby year -> first of month
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})\b", t)
    if m:
        return f"{int(m.group(2)):04d}-{_MONTHS[m.group(1)]:02d}-01"
    return None


def resolve_as_of(as_of_text: Optional[str], doc_published_date: Optional[str]) -> Optional[str]:
    """Explicit 'as on <date>' in the quote wins; otherwise fall back to the document date."""
    return _extract_explicit_date(as_of_text) or (doc_published_date or None)


def days_apart(a: Optional[str], b: Optional[str]) -> Optional[int]:
    try:
        da = date.fromisoformat(a[:10]); db = date.fromisoformat(b[:10])
        return abs((da - db).days)
    except Exception:
        return None
