"""Shared text helpers used across the deterministic normalizers."""
from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SUPERSCRIPTS = {ord(c): str(i) for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")}


def norm_ws(s: str) -> str:
    """Collapse all whitespace (incl. NBSP / thin spaces) to single ASCII spaces, trim."""
    if s is None:
        return ""
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    s = _CTRL.sub(" ", s)
    return _WS.sub(" ", s).strip()


def deaccent(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def to_ascii_digits(s: str) -> str:
    """Map superscript digits to normal digits (footnote markers) and a few unicode dashes."""
    s = s.translate(_SUPERSCRIPTS)
    return s.replace("−", "-").replace("–", "-").replace("—", "-")


def casefold_key(s: str) -> str:
    return norm_ws(deaccent(s or "")).casefold()
