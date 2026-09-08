"""Golden fixtures - normalization and reconciliation, offline (no LLM)."""
from pathlib import Path

import pytest
import yaml

from rlx.normalize.pipeline import DocContext, normalize_fact
from rlx.store.models import Fact, RawFact
from rlx.reconcile import reconcile

GOLDEN = Path(__file__).parent / "golden"


def _load(name):
    return yaml.safe_load((GOLDEN / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load("facts.yaml"), ids=lambda c: c["name"])
def test_golden_facts(case):
    rf = RawFact(**case["raw"])
    ctx = DocContext(**case.get("ctx", {}))
    f = normalize_fact(rf, ctx, structural_confidence=0.9)
    for k, v in case["expect"].items():
        got = getattr(f, k)
        if isinstance(v, float):
            assert got == pytest.approx(v, rel=1e-4), f"{k}: {got} != {v}"
        else:
            assert got == v, f"{k}: {got!r} != {v!r}"


def _mkfact(d: dict) -> Fact:
    base = dict(entity_display=d.get("entity_key", "e"), attribute_display=d.get("attribute_key", "a"),
                quote="q")
    base.update(d)
    return Fact(**base)


@pytest.mark.parametrize("case", _load("relations.yaml"), ids=lambda c: c["name"])
def test_golden_relations(case):
    a, b = _mkfact(case["a"]), _mkfact(case["b"])
    res = reconcile(a, b)
    exp = case["expect"]
    assert res.bucket == exp["bucket"], f"{case['name']}: bucket {res.bucket} != {exp['bucket']} (rule {res.rule_code})"
    if "rule_code" in exp:
        assert res.rule_code == exp["rule_code"], f"{case['name']}: rule {res.rule_code} != {exp['rule_code']}"
    # every relation carries a non-empty trace and explanation
    assert res.rule_trace and res.explanation
