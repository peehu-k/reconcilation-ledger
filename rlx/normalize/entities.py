"""Entity key derivation. Purely lexical + generic rules - no dataset-specific alias tables.

- legal-form suffixes are stripped (limited, ltd, pvt, inc, plc, llp ...)
- self-referential pronouns ("the Company", "your Company", "the Group", "the Bank",
  "the government", "we") resolve to the document's primary entity
- honorifics on person names are dropped
"""
from __future__ import annotations

import re

from .text import casefold_key, norm_ws

_LEGAL = re.compile(
    r"\b(private limited|pvt\.? ?ltd\.?|limited|ltd\.?|pvt\.?|plc|inc\.?|incorporated|"
    r"corp\.?|corporation|llp|l\.l\.p\.|company|co\.?|holdings?|group)\b",
    re.IGNORECASE,
)
_HONORIFIC = re.compile(r"^(mr|mrs|ms|miss|dr|prof|shri|smt|sri|hon'?ble|the)\.?\s+", re.IGNORECASE)
_PUNCT = re.compile(r"[^\w\s&/-]")

_PRONOUN = re.compile(
    r"^(the\s+)?(company|group|bank|corporation|firm|issuer|organisation|organization|"
    r"government|nation|country|economy|central bank|reserve bank|board|management|"
    r"we|our company|your company|the parent|it)$",
    re.IGNORECASE,
)


def is_self_reference(name: str) -> bool:
    return bool(_PRONOUN.match(norm_ws(name or "")))


def entity_key(name: str, primary_entity_key: str | None = None) -> str:
    n = norm_ws(name or "")
    if not n:
        return ""
    if is_self_reference(n) and primary_entity_key:
        return primary_entity_key
    n = _HONORIFIC.sub("", n)
    n = _PUNCT.sub(" ", n)
    n = _LEGAL.sub(" ", n)
    n = norm_ws(n)
    n = casefold_key(n)
    # drop trailing possessive 's
    n = re.sub(r"\b(\w+)'s\b", r"\1", n)
    return norm_ws(n)


def person_display(name: str) -> str:
    return norm_ws(_HONORIFIC.sub("", norm_ws(name or "")))
