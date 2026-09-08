import pytest

from rlx.normalize.vintage import parse_estimate_status, maturity_rank, resolve_as_of, days_apart
from rlx.normalize.entities import entity_key, is_self_reference
from rlx.normalize.attributes import attribute_key


@pytest.mark.parametrize("text,expected", [
    ("As per the first advance estimates of national accounts", "first_advance"),
    ("2024-25 (4.4 per cent as per 1st AE over 2023-24)", "first_advance"),
    ("production in 2024-25 (6.7 per cent as per 2nd AE)", "second_advance"),
    ("growth moderated to 6.5 per cent in 2024-25", None),
    ("provisional estimates", "provisional"),
    ("real GDP growth is projected at 6.6 percent in FY2025/26", "projection"),
    ("India's real GDP is estimated to grow by 6.4 per cent", "projection"),
])
def test_estimate_status(text, expected):
    assert parse_estimate_status(text) == expected


def test_maturity_order():
    assert maturity_rank("first_advance") < maturity_rank("provisional") < maturity_rank("actual")


def test_resolve_as_of_prefers_explicit():
    assert resolve_as_of("as on 3 January 2025", "2025-01-30") == "2025-01-03"
    assert resolve_as_of(None, "2025-05-25") == "2025-05-25"
    assert resolve_as_of("FX reserves stood at $695 billion as of October 2025", "2025-11-21") == "2025-10-01"


def test_days_apart():
    assert days_apart("2025-01-30", "2025-05-25") == 115


@pytest.mark.parametrize("name,expected", [
    ("Delhivery Limited", "delhivery"),
    ("DELHIVERY LIMITED", "delhivery"),
    ("Delhivery Ltd.", "delhivery"),
    ("Reserve Bank of India", "reserve bank of india"),
    ("Mr. Suvir Suren Sujan", "suvir suren sujan"),
    ("Suvir Sujan", "suvir sujan"),
])
def test_entity_key(name, expected):
    assert entity_key(name) == expected


def test_self_reference_resolves_to_primary():
    assert is_self_reference("the Company")
    assert entity_key("the Company", primary_entity_key="delhivery") == "delhivery"
    assert entity_key("your Company", primary_entity_key="delhivery") == "delhivery"


@pytest.mark.parametrize("label,expected", [
    ("Revenue from services", "revenue"),
    ("Revenues from customers", "revenue"),
    ("PAT", "profit after tax"),
    ("Loss for the year", "profit after tax"),
    ("Adj. EBITDA", "adjusted ebitda"),
    ("real GDP growth", "real gdp growth"),
    ("forex reserves", "foreign exchange reserves"),
    ("CIN", "corporate identity number"),
    ("corporate address", "corporate office address"),
    ("clinical trial enrolment", "clinical trial enrolment"),  # unseen vocab -> its own key
])
def test_attribute_key(label, expected):
    assert attribute_key(label) == expected
