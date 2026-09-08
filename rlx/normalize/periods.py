"""Parse period expressions into a canonical string.

Handled forms (all present in the starter corpus):
  FY24 / FY 2024 / fiscal 2024 / financial year 2024      -> FY:2023-24
  2023-24 / 2023-2024 / 2023/24 / FY2023/24 / FY2024/25    -> FY:<start>-<end2>
  year ended March 31, 2024                                -> FY:2023-24
  Q4 FY24 / fourth quarter of FY24                         -> Q4 FY:2023-24
  H1 FY25 / first half of FY25                             -> H1 FY:2024-25
  April-December 2024 / nine months ended December 31 2024 -> RANGE:2024-04..2024-12
  as on 3 January 2025 / 31 March 2024 / January 3, 2025   -> POINT:2025-01-03
  in 2024 / CY2024 / calendar year 2024                    -> CY:2024
Anything unrecognised -> None.
"""
from __future__ import annotations

import re
from typing import Optional

from .text import norm_ws, to_ascii_digits

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}


def _y4(y: str) -> int:
    y = int(y)
    if y < 100:
        return 2000 + y if y <= 79 else 1900 + y
    return y


def _fy(end_year: int) -> str:
    return f"FY:{end_year - 1}-{str(end_year)[-2:]}"


def parse_period(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = norm_ws(to_ascii_digits(text)).lower()

    # --- "(financial) year ended March 31, YYYY" -> FY ending that year (before generic date) ---
    m = re.search(rf"year\s+end(?:ed|ing)\s+{_MONTH_RE}\.?\s*\d{{0,2}},?\s*(\d{{4}})", t)
    if m:
        return _fy(int(m.group(2)))

    # --- "N months ended <Month DD>, YYYY" / "April-December YYYY" -> RANGE ---
    if re.search(r"\b(nine|9|six|6|three|3)\s+months?\b", t):
        m = re.search(r"(\d{4})", t)
        if m:
            return f"RANGE:{int(m.group(1))}-04..{int(m.group(1))}-12"
    m = re.search(rf"{_MONTH_RE}\s*(?:to|[-–])\s*{_MONTH_RE}\s+(\d{{4}})", t)
    if m:
        y = int(m.group(3))
        return f"RANGE:{y}-{_MONTHS[m.group(1)[:3]]:02d}..{y}-{_MONTHS[m.group(2)[:3]]:02d}"

    # --- explicit date -> POINT ---
    m = re.search(rf"\b(\d{{1,2}})\s+{_MONTH_RE}\s+(\d{{4}})\b", t)
    if m:
        return f"POINT:{int(m.group(3)):04d}-{_MONTHS[m.group(2)[:3]]:02d}-{int(m.group(1)):02d}"
    m = re.search(rf"\b{_MONTH_RE}\s+(\d{{1,2}}),?\s+(\d{{4}})\b", t)
    if m:
        return f"POINT:{int(m.group(3)):04d}-{_MONTHS[m.group(1)[:3]]:02d}-{int(m.group(2)):02d}"

    # --- quarter ---
    m = re.search(r"q([1-4])\s*[-' ]?\s*fy\s*'?\s*(\d{2,4})", t) or re.search(r"q([1-4])\s*fy(\d{2,4})", t)
    if m:
        return f"Q{m.group(1)} {_fy(_y4(m.group(2)))}"
    m = re.search(r"(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?fy\s*'?\s*(\d{2,4})", t)
    if m:
        return f"Q{_ORD[m.group(1)]} {_fy(_y4(m.group(2)))}"

    # --- half ---
    m = re.search(r"h([12])\s*[-' ]?\s*fy\s*'?\s*(\d{2,4})", t)
    if m:
        return f"H{m.group(1)} {_fy(_y4(m.group(2)))}"
    m = re.search(r"(first|second|1st|2nd)\s+half\s+(?:of\s+)?fy\s*'?\s*(\d{2,4})", t)
    if m:
        return f"H{_ORD[m.group(1)]} {_fy(_y4(m.group(2)))}"

    # --- FY spans: FY2023/24, FY2024/25 (explicit "fy" prefix) ---
    m = re.search(r"\bfy\s*'?\s*(\d{4})\s*[-/]\s*(\d{2,4})\b", t)
    if m:
        return _fy(_y4(m.group(2)))
    # --- bare spans: 2023-24, 2023/24, 2023-2024 -> fiscal only if consecutive years ---
    m = re.search(r"\b(\d{4})\s*[-/]\s*(\d{2,4})\b", t)
    if m:
        start, end = int(m.group(1)), _y4(m.group(2))
        if end - start == 1:
            return _fy(end)

    # --- FY24 / FY 2024 / fiscal 2024 ---
    m = re.search(r"\bfy\s*'?\s*(\d{2,4})\b", t) or re.search(r"\b(?:fiscal|financial\s+year)\s+(\d{2,4})\b", t)
    if m:
        return _fy(_y4(m.group(1)))

    # --- calendar year: "CY2024", "calendar year 2024", "in 2024", "during 2024" ---
    m = re.search(r"\bcy\s*'?\s*(\d{4})\b", t) or re.search(r"calendar\s+year\s+(\d{4})", t)
    if m:
        return f"CY:{int(m.group(1))}"
    m = re.search(r"\b(?:in|during|for|of)\s+(\d{4})\b", t)
    if m and 1990 <= int(m.group(1)) <= 2100:
        return f"CY:{int(m.group(1))}"

    return None
