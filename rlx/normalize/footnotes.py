"""Strip footnote reference markers glued to tokens ("platform(1)", "12.7%(2)")
without eating real negatives ("(452)") or parenthesised quantities ("(1,008 Cr)")."""
from __future__ import annotations

import re

from .text import to_ascii_digits

# a parenthesised group we must NEVER treat as a footnote marker (it is a value / a negative)
_PROTECT = re.compile(
    r"""\(\s*
        (?:
            \d{3,}                     # (452) style numbers -> accounting negative
          | \d{1,3},\d{3}              # (1,008) thousands
          | \d+\.\d+                   # (6.3) decimals
          | [\d,]+\s*(?:%|per\s?cent|cr|crore|mn|million|bn|billion|lakh|k|tn|trillion|tonnes?|days?|bps)
        )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# footnote marker: one or more 1-2 digit refs in parens ("(1)", "(1,2)", "(1, 3)"),
# glued (no leading space) to a word char, %, or ).
_MARKER = re.compile(r"(?<=[A-Za-z%\)\d])\(\s*([0-9]{1,2}(?:\s*,\s*[0-9]{1,2})*)\s*\)")
_TRAILING_SUP = re.compile(r"(?<=[A-Za-z%\)\d])[⁰-⁹]{1,2}")


def strip_footnote_markers(text: str) -> str:
    if not text:
        return text
    text = to_ascii_digits(text)  # superscripts -> digits first
    protected_spans = [m.span() for m in _PROTECT.finditer(text)]

    def _in_protected(pos: int) -> bool:
        return any(a <= pos < b for a, b in protected_spans)

    out = []
    i = 0
    for m in _MARKER.finditer(text):
        refs = [int(x) for x in m.group(1).split(",")]
        # only strip small marker numbers, and never inside a protected numeric paren
        if all(r <= 20 for r in refs) and not _in_protected(m.start()):
            out.append(text[i:m.start()])
            i = m.end()
    out.append(text[i:])
    cleaned = "".join(out)
    cleaned = _TRAILING_SUP.sub("", cleaned)
    return cleaned
