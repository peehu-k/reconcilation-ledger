"""Decide the sign of a numeric value from how it is written.
Accounting negatives appear as "(452)", "Rs. (452 Cr)", "-452", "(6.3%)"."""
from __future__ import annotations

import re

from .text import to_ascii_digits

_PAREN_NUM = re.compile(r"\(\s*(?:rs\.?|inr|₹|us\$|usd|\$)?\s*[\d,]+(?:\.\d+)?\s*"
                        r"(?:%|per\s?cent|cr|crore|mn|million|bn|billion|lakh|k|bps)?\s*\)",
                        re.IGNORECASE)
_LEADING_MINUS = re.compile(r"^\s*[-]\s*[\d(]")
_NEG_WORD = re.compile(r"\b(loss|deficit|negative|contraction|decline|decrease|de-?growth)\b", re.IGNORECASE)


def is_negative(value_text: str) -> bool:
    if not value_text:
        return False
    t = to_ascii_digits(value_text.strip())
    if _LEADING_MINUS.search(t):
        return True
    # a parenthesised number that spans (most of) the string -> accounting negative
    m = _PAREN_NUM.search(t)
    if m and len(m.group(0)) >= max(3, int(0.6 * len(t))):
        return True
    # explicit "(x)" wrapping the whole token
    if t.startswith("(") and t.rstrip(" .").endswith(")") and any(ch.isdigit() for ch in t):
        return True
    return False


def apply_sign(value_text: str, magnitude: float) -> float:
    return -abs(magnitude) if is_negative(value_text) else magnitude
