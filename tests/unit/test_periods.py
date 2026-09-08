import pytest

from rlx.normalize.periods import parse_period


@pytest.mark.parametrize("text,expected", [
    ("FY24", "FY:2023-24"),
    ("FY 2024", "FY:2023-24"),
    ("fiscal 2024", "FY:2023-24"),
    ("financial year 2024", "FY:2023-24"),
    ("2023-24", "FY:2023-24"),
    ("2023-2024", "FY:2023-24"),
    ("FY2023/24", "FY:2023-24"),
    ("FY2024/25", "FY:2024-25"),
    ("2024-25", "FY:2024-25"),
    ("for the year ended March 31, 2024", "FY:2023-24"),
    ("Q4 FY24", "Q4 FY:2023-24"),
    ("Q4FY24", "Q4 FY:2023-24"),
    ("fourth quarter of FY24", "Q4 FY:2023-24"),
    ("H1 FY25", "H1 FY:2024-25"),
    ("first half of FY25", "H1 FY:2024-25"),
    ("in Q2 FY25", "Q2 FY:2024-25"),
    ("April-December 2024", "RANGE:2024-04..2024-12"),
    ("nine months ended December 31, 2024", "RANGE:2024-04..2024-12"),
    ("as on 3 January 2025", "POINT:2025-01-03"),
    ("January 3, 2025", "POINT:2025-01-03"),
    ("31 March 2024", "POINT:2024-03-31"),
    ("calendar year 2024", "CY:2024"),
    ("in 2024", "CY:2024"),
    ("CY2024", "CY:2024"),
    ("no period here", None),
])
def test_parse_period(text, expected):
    assert parse_period(text) == expected


def test_fy_and_calendar_year_are_distinct():
    assert parse_period("FY24") != parse_period("in 2024")
