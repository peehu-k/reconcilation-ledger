"""Deterministic post-normalization sanity checks. Any flag lowers trust; a flagged
low-confidence fact is routed to the Unresolved queue rather than asserted."""
from __future__ import annotations

import re

_LOSS_WORDS = re.compile(r"\b(loss|deficit|decline|decrease|contraction|fell|drop|de-?growth)\b", re.I)
_SIGN_TOKEN = re.compile(r"[-−(]")


def sanity_flags(*, fact_kind: str, attribute_label: str, value_text: str,
                 value_num: float | None, unit_canonical: str | None,
                 structural_confidence: float) -> list[str]:
    flags: list[str] = []

    if unit_canonical == "ratio" and value_num is not None and abs(value_num) > 1.5:
        flags.append("implausible_percent")

    if (value_num is not None and value_num > 0
            and _LOSS_WORDS.search(attribute_label or "")
            and not _SIGN_TOKEN.search(value_text or "")):
        flags.append("sign_suspect")

    if fact_kind == "numeric" and structural_confidence <= 0.45:
        flags.append("low_structural")

    if unit_canonical == "currency_amount" and value_num is not None and abs(value_num) > 1e15:
        flags.append("huge_magnitude")

    if (unit_canonical in (None, "number") and value_num is not None
            and 1900 <= value_num <= 2100 and value_num == int(value_num)
            and not re.search(r"\d", (attribute_label or ""))):
        flags.append("year_as_value")

    return flags
