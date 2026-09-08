"""Turn a written value ("8,142 Cr", "6.4 per cent", "US$ 634.6 billion", "1,429K tonnes")
into a canonical (value_num, currency, unit_canonical, scale_applied).

Deterministic and total: unknown input -> value_num None, unit_canonical 'text'."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .sign import apply_sign
from .text import norm_ws, to_ascii_digits

SCALE = {
    "cr": 1e7, "crore": 1e7, "crores": 1e7, "cr.": 1e7,
    "lakh": 1e5, "lac": 1e5, "lakhs": 1e5, "lacs": 1e5,
    "k": 1e3, "thousand": 1e3, "'000": 1e3, "000s": 1e3,
    "mn": 1e6, "million": 1e6, "millions": 1e6, "mln": 1e6, "m": 1e6,
    "bn": 1e9, "billion": 1e9, "billions": 1e9, "bln": 1e9, "b": 1e9,
    "tn": 1e12, "trillion": 1e12, "trillions": 1e12,
}
_SCALE_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(sorted((re.escape(k) for k in SCALE), key=len, reverse=True)) + r")(?![A-Za-z])",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")
_PERCENT_RE = re.compile(r"%|per\s?cent|percent|\bpc\b|\bpp[t]?\b|percentage\s+points?", re.IGNORECASE)
_BPS_RE = re.compile(r"\bbps\b|basis\s+points?", re.IGNORECASE)
_TONNE_RE = re.compile(r"\b(tonnes?|tons?|mt)\b", re.IGNORECASE)
_DAYS_RE = re.compile(r"\bdays?\b", re.IGNORECASE)
_MULT_RE = re.compile(r"\d\s*x\b", re.IGNORECASE)

_CCY = [
    ("INR", re.compile(r"₹|\brs\.?\b|\binr\b|\brupees?\b|\bcrores?\b|\blakhs?\b|\blacs?\b", re.IGNORECASE)),
    ("USD", re.compile(r"us\$|\bus\s*dollar|\busd\b|(?<![A-Za-z])\$", re.IGNORECASE)),
    ("EUR", re.compile(r"€|\beur\b|\beuros?\b", re.IGNORECASE)),
    ("GBP", re.compile(r"£|\bgbp\b", re.IGNORECASE)),
]

# words that, as an attribute, imply a money amount even without a symbol
_MONEY_ATTR = re.compile(
    r"revenue|income|ebitda|profit|loss|turnover|sales|capex|expenditure|expense|"
    r"deficit|borrowing|debt|net worth|cash|gdp|gva|reserves|fdi|assets|liabilit",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Quantity:
    value_num: Optional[float]
    currency: Optional[str]
    unit_canonical: str          # currency_amount | ratio | tonnes | days | count | number | text
    scale_applied: Optional[float]


def _detect_currency(s: str) -> Optional[str]:
    for code, rx in _CCY:
        if rx.search(s):
            return code
    return None


def _detect_scale(s: str) -> Optional[float]:
    m = _SCALE_RE.search(s)
    return SCALE[m.group(1).lower()] if m else None


def _first_number(s: str) -> Optional[float]:
    m = _NUM_RE.search(s.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


_INDIAN_SCALE = re.compile(r"\b(cr|cr\.|crore|crores|lakh|lakhs|lac|lacs)\b", re.IGNORECASE)
_ALPHA_WORD = re.compile(r"[A-Za-z]{3,}")


def parse_quantity(value_text: str, unit_text: Optional[str] = None,
                   attribute_label: str = "", fact_kind: str = "numeric") -> Quantity:
    raw = norm_ws(to_ascii_digits(value_text or ""))
    combined = norm_ws(f"{raw} {unit_text or ''}")
    if not raw:
        return Quantity(None, None, "text", None)

    currency = _detect_currency(combined)
    if _INDIAN_SCALE.search(combined):
        currency = currency or "INR"

    has_pct = bool(_PERCENT_RE.search(combined) or _BPS_RE.search(combined))
    has_unit_signal = has_pct or bool(currency) or bool(_detect_scale(combined)) or bool(unit_text)
    # status / event values are prose ("resigned w.e.f. ...") - never a number
    if fact_kind in ("status", "event") and not has_pct:
        return Quantity(None, currency, "text", None)
    # attribute values (codes, ids, addresses, names) stay strings unless clearly a quantity
    if fact_kind == "attribute" and not has_unit_signal:
        return Quantity(None, currency, "text", None)

    num = _first_number(raw)

    # --- ratio-like ---
    if _PERCENT_RE.search(combined):
        if num is None:
            return Quantity(None, None, "ratio", None)
        return Quantity(apply_sign(raw, num) / 100.0, None, "ratio", None)
    if _BPS_RE.search(combined):
        if num is None:
            return Quantity(None, None, "ratio", None)
        return Quantity(apply_sign(raw, num) / 10_000.0, None, "ratio", None)
    if _MULT_RE.search(raw):  # "0.01x" debt/equity multiple
        return Quantity(apply_sign(raw, num) if num is not None else None, None, "ratio", None)

    if num is None:
        # non-numeric value (a name, an address, "resigned w.e.f. ...")
        return Quantity(None, currency, "text", None)

    # a number buried in prose (dates, "resigned ... August 24, 2023", CINs) is not a measurement
    if not has_unit_signal and len(_ALPHA_WORD.findall(raw)) >= 3:
        return Quantity(None, currency, "text", None)

    scale = _detect_scale(combined)
    magnitude = num * (scale or 1.0)
    value = apply_sign(raw, magnitude)

    if _TONNE_RE.search(combined):
        return Quantity(value, None, "tonnes", scale)
    if _DAYS_RE.search(combined):
        return Quantity(value, None, "days", scale)

    if currency or scale in (1e7, 1e5) or _MONEY_ATTR.search(attribute_label or ""):
        return Quantity(value, currency, "currency_amount", scale)

    # a scaled bare count ("740 million" parcels) vs an unscaled integer id ("18,793")
    if scale:
        return Quantity(value, None, "count", scale)
    return Quantity(value, None, "number", None)
