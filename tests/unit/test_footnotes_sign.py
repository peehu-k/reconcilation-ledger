from rlx.normalize.footnotes import strip_footnote_markers
from rlx.normalize.sign import is_negative


def test_strip_glued_single_marker():
    assert strip_footnote_markers("India's largest integrated logistics platform(1)") == \
        "India's largest integrated logistics platform"


def test_strip_marker_after_percent():
    assert strip_footnote_markers("YoY: 12.7%(2)") == "YoY: 12.7%"


def test_strip_multi_ref_marker():
    assert strip_footnote_markers("Revenue from services(1,2)") == "Revenue from services"


def test_preserve_accounting_negative():
    assert strip_footnote_markers("Rs. (452 Cr) in FY23") == "Rs. (452 Cr) in FY23"
    assert strip_footnote_markers("(1,008 Cr)") == "(1,008 Cr)"
    assert strip_footnote_markers("(6.3%)") == "(6.3%)"


def test_preserve_standalone_footnote_number():
    # separated by a space -> not glued -> left alone
    assert strip_footnote_markers("8,142 Cr (2)") == "8,142 Cr (2)"


def test_sign_detection():
    assert is_negative("(452) Cr")
    assert is_negative("Rs. (452 Cr)")
    assert is_negative("(6.3%)")
    assert is_negative("-452")
    assert not is_negative("452 Cr")
    assert not is_negative("6.4 per cent")
