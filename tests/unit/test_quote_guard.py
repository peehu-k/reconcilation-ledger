from rlx.extract.quote_guard import verify_quote

SRC = ("FY24 revenue from services 8,142 Cr YoY: 12.7%  "
       "EBITDA / EBITDA margin 127 Cr / 1.6%  FY23: (452) Cr / (6.3%)")


def test_exact_substring():
    r = verify_quote("8,142 Cr", SRC)
    assert r.match == "exact"
    assert SRC[r.char_start:r.char_end] == "8,142 Cr"


def test_whitespace_normalized_match():
    r = verify_quote("revenue from   services   8,142 Cr", SRC)
    assert r.match in ("exact", "fuzzy")


def test_missing_quote_fails():
    r = verify_quote("net profit was 5,000 crore", SRC)
    assert r.match == "FAIL"


def test_empty_quote_fails():
    assert verify_quote("", SRC).match == "FAIL"
    assert verify_quote("   ", SRC).match == "FAIL"


def test_fuzzy_tolerates_minor_ocr_noise():
    r = verify_quote("FY24 revenue from servlces 8,142 Cr", SRC, fuzz_threshold=88)
    assert r.match in ("fuzzy", "exact")
