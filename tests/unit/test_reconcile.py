"""Reconciliation cascade. Facts are constructed directly (not dataset-hardcoded in
code paths) but their shapes mirror real figures from the starter PDFs."""
from rlx.store.models import Fact
from rlx.reconcile import reconcile
from rlx.reconcile.compare import compare, CompareResult


def mkfact(**kw) -> Fact:
    base = dict(
        entity_key="e", entity_display="E", attribute_key="a", attribute_display="A",
        fact_kind="numeric", value_text="", quote="q", extraction_confidence=0.8,
        doc_id=1, source_page=1,
    )
    base.update(kw)
    return Fact(**base)


def test_corroboration_across_docs_different_units():
    a = mkfact(value_num=8_142e7, unit_canonical="currency_amount", currency="INR",
               period_canonical="FY:2023-24", value_text="8,142 Cr", doc_id=1, source_page=5)
    b = mkfact(value_num=81_415.38e6, unit_canonical="currency_amount", currency=None,
               period_canonical="FY:2023-24", value_text="81,415.38 million", doc_id=2, source_page=70)
    r = reconcile(a, b)
    assert r.bucket == "corroborated"
    assert r.rule_code in ("EXACT", "ROUNDING")


def test_reconciled_by_period():
    a = mkfact(value_num=8_142e7, unit_canonical="currency_amount", currency="INR",
               period_canonical="FY:2023-24", value_text="8,142 Cr", doc_id=1)
    b = mkfact(value_num=2_076e7, unit_canonical="currency_amount", currency="INR",
               period_canonical="Q4 FY:2023-24", value_text="2,076 Cr", doc_id=1, source_page=6)
    r = reconcile(a, b)
    assert r.bucket == "reconciled"
    assert r.rule_code == "PERIOD"


def test_reconciled_by_estimate_vintage():
    a = mkfact(value_num=0.064, unit_canonical="ratio", period_canonical="FY:2024-25",
               estimate_status="first_advance", as_of_date="2025-01-30",
               value_text="6.4 per cent", doc_id=1)
    b = mkfact(value_num=0.065, unit_canonical="ratio", period_canonical="FY:2024-25",
               estimate_status="provisional", as_of_date="2025-05-25",
               value_text="6.5 per cent", doc_id=2)
    r = reconcile(a, b)
    assert r.bucket == "reconciled"
    assert r.rule_code == "ESTIMATE_VINTAGE"


def test_reconciled_by_asof_only():
    a = mkfact(value_num=634.6e9, unit_canonical="currency_amount", currency="USD",
               attribute_key="foreign exchange reserves", as_of_date="2025-01-03",
               value_text="USD 634.6 billion", doc_id=1)
    b = mkfact(value_num=695e9, unit_canonical="currency_amount", currency="USD",
               attribute_key="foreign exchange reserves", as_of_date="2025-10-01",
               value_text="$695 billion", doc_id=2)
    r = reconcile(a, b)
    assert r.bucket == "reconciled"
    assert r.rule_code == "ESTIMATE_VINTAGE"


def test_reconciled_by_basis_pro_forma():
    a = mkfact(value_num=7_054e7, unit_canonical="currency_amount", currency="INR",
               period_canonical="FY:2021-22", basis_flags=["pro_forma"],
               value_text="7,054 Cr", doc_id=1)
    b = mkfact(value_num=6_900e7, unit_canonical="currency_amount", currency="INR",
               period_canonical="FY:2021-22", basis_flags=[],
               value_text="6,900 Cr", doc_id=2)
    r = reconcile(a, b)
    assert r.bucket == "reconciled"
    assert r.rule_code == "BASIS"


def test_genuine_contradiction_pin_code():
    a = mkfact(fact_kind="attribute", value_num=None, unit_canonical="text",
               attribute_key="corporate office address", value_text="Gurugram, Haryana 122002",
               doc_id=1, source_page=1, extraction_confidence=0.8)
    b = mkfact(fact_kind="attribute", value_num=None, unit_canonical="text",
               attribute_key="corporate office address", value_text="Gurugram, Haryana 122001",
               doc_id=2, source_page=51, extraction_confidence=0.8)
    r = reconcile(a, b)
    assert r.bucket == "contradiction"
    assert r.rule_code == "NONE"


def test_address_same_place_different_wording_corroborates():
    a = mkfact(fact_kind="attribute", value_num=None, unit_canonical="text",
               attribute_key="registered office address", doc_id=1, source_page=1,
               value_text="N24-N34, Air Cargo Logistics Centre-II, Indira Gandhi International Airport, New Delhi 110037")
    b = mkfact(fact_kind="attribute", value_num=None, unit_canonical="text",
               attribute_key="registered office address", doc_id=2, source_page=50,
               value_text="N24-N34, Air Cargo Logistics Centre-II, IGI Airport, New Delhi 110037")
    r = reconcile(a, b)
    assert r.bucket == "corroborated"   # same PIN -> same place


def test_temporal_status_director_resigned():
    a = mkfact(fact_kind="status", value_num=None, unit_canonical="text",
               attribute_key="board membership", entity_key="suvir suren sujan",
               value_text="Non-Executive Nominee Director", as_of_date="2022-05-14", doc_id=1)
    b = mkfact(fact_kind="status", value_num=None, unit_canonical="text",
               attribute_key="board membership", entity_key="suvir suren sujan",
               value_text="resigned from the Board with effect from August 24, 2023",
               as_of_date="2024-08-08", doc_id=2)
    r = reconcile(a, b)
    assert r.bucket == "reconciled"
    assert r.rule_code == "TEMPORAL_STATUS"


def test_vintage_does_not_misfire_on_identical_status():
    a = mkfact(value_num=0.065, unit_canonical="ratio", period_canonical="FY:2024-25",
               estimate_status="provisional", as_of_date="2025-05-25", doc_id=1)
    b = mkfact(value_num=0.065, unit_canonical="ratio", period_canonical="FY:2024-25",
               estimate_status="provisional", as_of_date="2025-05-25", doc_id=2)
    r = reconcile(a, b)
    assert r.bucket == "corroborated"


def test_incomparable_ratio_vs_amount():
    a = mkfact(value_num=0.016, unit_canonical="ratio", doc_id=1)
    b = mkfact(value_num=127e7, unit_canonical="currency_amount", currency="INR", doc_id=2)
    assert compare(a, b).result == CompareResult.INCOMPARABLE
    r = reconcile(a, b)
    assert r.bucket == "unresolved"
