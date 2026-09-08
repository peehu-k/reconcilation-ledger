"""Tolerant JSON extraction from an LLM reply. Never uses eval."""
from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def loads_lenient(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("empty response")
    s = text.strip()
    m = _FENCE.search(s)
    if m:
        s = m.group(1).strip()
    # trim to the outermost {...}
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    s = re.sub(r",\s*([}\]])", r"\1", s)          # trailing commas
    s = s.replace("“", '"').replace("”", '"')  # smart quotes on keys/strings
    return json.loads(s)
