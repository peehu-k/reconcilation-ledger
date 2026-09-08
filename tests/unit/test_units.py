"""Value/unit normalization. Inputs are verbatim strings from the six starter PDFs."""
import math
import pytest

from rlx.normalize.units import parse_quantity


def approx(a, b, rel=1e-6):
    return a is not None and math.isclose(a, b, rel_tol=rel, abs_tol=1e-3)


@pytest.mark.parametrize("value_text,unit_text,attr,exp_num,exp_ccy,exp_unit", [
    ("8,142 Cr", None, "FY24 revenue from services", 8_142e7, "INR", "currency_amount"),
    ("2,076 Cr", None, "revenue from services", 2_076e7, "INR", "currency_amount"),
    ("81,415.38", "million", "revenue from customers", 81_415.38e6, None, "currency_amount"),
    ("US$ 634.6 billion", None, "foreign exchange reserves", 634.6e9, "USD", "currency_amount"),
    ("US$ 668.3 billion", None, "forex reserves", 668.3e9, "USD", "currency_amount"),
    ("$695 billion", None, "fx reserves", 695e9, "USD", "currency_amount"),
    ("US$3.9 trillion", None, "gross domestic product", 3.9e12, "USD", "currency_amount"),
    ("6.4 per cent", None, "real gdp growth", 0.064, None, "ratio"),
    ("6.5 percent", None, "real gdp growth", 0.065, None, "ratio"),
    ("1.6%", None, "ebitda margin", 0.016, None, "ratio"),
    ("(6.3%)", None, "ebitda margin", -0.063, None, "ratio"),
    ("1.4 Mn Tons", None, "ptl freight tonnage", 1.4e6, None, "tonnes"),
    ("1,429K tonnes", None, "ptl freight tonnage", 1.429e6, None, "tonnes"),
    ("740 million", None, "express parcel shipments", 740e6, None, "count"),
    ("(452) Cr", None, "ebitda", -452e7, "INR", "currency_amount"),
    ("0.01x", None, "debt to equity", 0.01, None, "ratio"),
    ("38 days", None, "net working capital days", 38.0, None, "days"),
    ("18,793", None, "pin code reach", 18793.0, None, "number"),
])
def test_parse_quantity(value_text, unit_text, attr, exp_num, exp_ccy, exp_unit):
    q = parse_quantity(value_text, unit_text, attr)
    assert approx(q.value_num, exp_num, rel=1e-4), (q, exp_num)
    assert q.currency == exp_ccy
    assert q.unit_canonical == exp_unit


def test_non_numeric_value_is_text():
    q = parse_quantity("resigned with effect from August 24, 2023", None, "board membership")
    assert q.value_num is None
    assert q.unit_canonical == "text"


def test_crore_million_equivalence():
    a = parse_quantity("8,142 Cr", None, "revenue")
    b = parse_quantity("81,415.38", "million", "revenue")
    # ~0.006% apart -> effectively equal magnitudes
    assert abs(a.value_num - b.value_num) / a.value_num < 0.001
