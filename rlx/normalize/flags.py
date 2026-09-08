"""Deterministic extraction of basis / scope flags from the qualifier text + quote.
Open-ended qualifiers are slugified rather than forced into a fixed vocabulary."""
from __future__ import annotations

import re

from .text import casefold_key

_BASIS = [
    ("pro_forma", r"pro[\s-]?forma"),
    ("restated", r"restated|as\s+restated"),
    ("adjusted", r"\badjusted\b|\badj\.?\b|non-gaap"),
    ("reported", r"\breported\b|on\s+a\s+reported\s+basis"),
    ("nominal", r"\bnominal\b"),
    ("real", r"\breal\s+terms\b|at\s+constant\s+prices|\breal\b(?=\s+(gdp|gva|growth|terms))"),
    ("standalone", r"\bstandalone\b"),
    ("consolidated", r"\bconsolidated\b"),
    ("gross", r"\bgross\b(?!\s+(domestic\s+product|value\s+added|national|fixed\s+capital|savings?))"),
    ("net", r"\bnet\s+of\b"),
    ("annualised", r"annuali[sz]ed"),
    ("seasonally_adjusted", r"seasonally[\s-]adjusted|\bsa\b"),
]

_SCOPE = [
    ("excl_traded_goods", r"exclud\w*\s+(revenue\s+from\s+)?traded\s+goods|excl\.?\s+traded\s+goods"),
    ("incl_traded_goods", r"includ\w*\s+(revenue\s+from\s+)?traded\s+goods"),
    ("since_inception", r"since\s+inception"),
    ("per_period", r"for\s+the\s+(quarter|period|year)"),
]

_SLUG = re.compile(r"[^a-z0-9]+")


def _match_all(patterns, text: str) -> list[str]:
    out = []
    for tag, rx in patterns:
        if re.search(rx, text, re.IGNORECASE):
            out.append(tag)
    return out


def basis_flags(basis_text: str | None, quote: str | None) -> list[str]:
    blob = f"{basis_text or ''} || {quote or ''}"
    return sorted(set(_match_all(_BASIS, blob)))


def scope_flags(scope_text: str | None, quote: str | None) -> list[str]:
    blob = f"{scope_text or ''} || {quote or ''}"
    tags = set(_match_all(_SCOPE, blob))
    st = casefold_key(scope_text or "")
    if st and not tags:
        slug = _SLUG.sub("_", st).strip("_")[:40]
        if slug:
            tags.add(f"scope:{slug}")
    return sorted(tags)
