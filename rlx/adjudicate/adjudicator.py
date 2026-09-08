"""Narrow LLM adjudication. The adjudicator NEVER decides a bucket. It only:
  - writes a one-sentence human explanation from an already-decided structured result
It degrades to a template string if the LLM is unavailable or misbehaves (adds a
number that was not in the inputs).
"""
from __future__ import annotations

import re

from ..store.models import Fact, RelationResult

_EXPLAIN_SYSTEM = (
    "You write ONE plain sentence (<=40 words) explaining a pre-decided relationship "
    "between two figures extracted from documents. Do not introduce any number that is "
    "not already in the inputs. Do not change the verdict. Return only the sentence."
)


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d[\d,]*\.?\d*", s or ""))


def polish_explanation(provider, res: RelationResult, a: Fact, b: Fact) -> RelationResult:
    if provider is None or getattr(provider, "name", "") in ("null", "replay"):
        return res
    allowed = _numbers(a.value_text) | _numbers(b.value_text) | _numbers(res.explanation)
    user = (
        f"Verdict: {res.bucket} (rule {res.rule_code}).\n"
        f"A: “{a.value_text}” — {a.attribute_display or a.attribute_key} — {a.doc_title}, p.{a.source_page}\n"
        f"B: “{b.value_text}” — {b.attribute_display or b.attribute_key} — {b.doc_title}, p.{b.source_page}\n"
        f"Draft: {res.explanation}\n"
        f"Rewrite as one clear sentence."
    )
    try:
        obj, raw = provider.complete_json(_EXPLAIN_SYSTEM, user)
        cand = (obj.get("sentence") if isinstance(obj, dict) else None) or raw
        cand = cand.strip().strip('"')
        if cand and _numbers(cand) <= allowed and len(cand) < 400:
            res.explanation = cand
            res.explanation_source = "llm"
    except Exception:  # noqa: BLE001
        pass
    return res
