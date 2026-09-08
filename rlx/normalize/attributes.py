"""Attribute key derivation.

There is NO ontology and NO closed list of "known attributes": an unseen PDF's
attributes get their own keys via the general path (lowercase -> drop a few filler
words -> singularise). The table below is a small *seed lexicon* that (a) expands
common abbreviations and (b) folds well-known surface variants of the same
financial-statement / macro line item onto one key so cross-document blocking can
find them. Anything outside the lexicon relies on runtime rapidfuzz + optional
embeddings on the attribute_registry, so behaviour stays visible and tunable.
"""
from __future__ import annotations

import re

from .text import casefold_key, norm_ws

_FILLER = re.compile(r"\b(the|a|an|of|for|to|our|its|their|overall)\b", re.IGNORECASE)
_PUNCT = re.compile(r"[^\w\s%/&-]")

# seed lexicon: surface variant -> canonical key
_SEED = {
    # revenue
    "revenue": "revenue",
    "revenues": "revenue",
    "total revenue": "revenue",
    "revenue from services": "revenue",
    "revenue from service": "revenue",
    "revenues from services": "revenue",
    "revenue from customers": "revenue",
    "revenues from customers": "revenue",
    "total revenues from customers": "revenue",
    "revenue from contracts with customers": "revenue",
    "revenue from operations": "revenue",
    "income from services": "revenue",
    # profit
    "pat": "profit after tax",
    "profit after tax": "profit after tax",
    "net profit": "profit after tax",
    "loss for the year": "profit after tax",
    "profit / (loss) after tax": "profit after tax",
    "profit/(loss) after tax": "profit after tax",
    "profit for the year": "profit after tax",
    # ebitda
    "ebitda": "ebitda",
    "adjusted ebitda": "adjusted ebitda",
    "adj ebitda": "adjusted ebitda",
    "adj. ebitda": "adjusted ebitda",
    # macro
    "gdp growth": "real gdp growth",
    "real gdp growth": "real gdp growth",
    "real gross domestic product growth": "real gdp growth",
    "growth in real gdp": "real gdp growth",
    "gva growth": "real gva growth",
    "forex reserves": "foreign exchange reserves",
    "fx reserves": "foreign exchange reserves",
    "foreign exchange reserves": "foreign exchange reserves",
    "cad": "current account deficit",
    "current account deficit": "current account deficit",
    "cpi inflation": "headline inflation",
    "retail inflation": "headline inflation",
    "headline inflation": "headline inflation",
    "consumer price index inflation": "headline inflation",
    # corporate identifiers
    "cin": "corporate identity number",
    "corporate identity number": "corporate identity number",
    "pincode": "pin code",
    "pin code": "pin code",
    "registered office": "registered office address",
    "registered office address": "registered office address",
    "corporate office": "corporate office address",
    "corporate office address": "corporate office address",
    "corporate address": "corporate office address",
    "board membership": "board membership",
    "directorship": "board membership",
    "board position": "board membership",
    "board seat": "board membership",
}

_PLURALS = [("revenues", "revenue"), ("centres", "centre"), ("centers", "center"),
            ("shipments", "shipment"), ("parcels", "parcel"), ("tonnes", "tonne"),
            ("days", "day"), ("customers", "customer"), ("estimates", "estimate")]


def attribute_key(label: str) -> str:
    n = casefold_key(label or "")
    if not n:
        return ""
    if n in _SEED:
        return _SEED[n]
    n = _PUNCT.sub(" ", n)
    n = norm_ws(n)
    if n in _SEED:
        return _SEED[n]
    n = _FILLER.sub(" ", n)
    n = norm_ws(n)
    for a, b in _PLURALS:
        n = re.sub(rf"\b{a}\b", b, n)
    n = norm_ws(n)
    return _SEED.get(n, n)


def attribute_display(label: str) -> str:
    return norm_ws(label or "")
