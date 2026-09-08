"""PDF -> pages + blocks, using PyMuPDF. Generic heuristics only; nothing keyed to a
specific document. Slide-deck pages and dense numeric tables get a lower
structural_confidence so facts extracted from them are trusted less."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ..normalize.text import norm_ws

_PAGE_LABEL = re.compile(r"^\s*(\d{1,4}|[ivxlcdm]{1,8})\s*$", re.IGNORECASE)
_NUMISH = re.compile(r"[-+(]?\d[\d,]*\.?\d*%?\)?")


@dataclass
class ParsedBlock:
    page_no: int
    idx: int
    kind: str
    text: str
    bbox: tuple[float, float, float, float]
    char_start: int
    char_end: int
    structural_confidence: float


@dataclass
class ParsedPage:
    page_no: int
    text: str
    printed_label: str | None
    width: float
    height: float
    blocks: list[ParsedBlock] = field(default_factory=list)


def _printed_label(text: str, page_no: int) -> str | None:
    """Best-effort. Accept a lone footer/header number only if it is plausibly a page
    number (roman, or within a sane window of the PDF page index). The curated
    excerpts renumber discontinuously, so a miss just falls back to the PDF page."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for cand in lines[-2:] + lines[:2]:
        m = _PAGE_LABEL.match(cand)
        if not m:
            continue
        tok = m.group(1)
        if tok.isdigit():
            n = int(tok)
            if 1 <= n <= 3000 and abs(n - page_no) <= 12:
                return tok
        else:
            return tok  # roman numeral
    return None


def _classify(block_text: str, bbox, page_w: float, page_h: float, is_deck: bool) -> tuple[str, float]:
    t = block_text.strip()
    lines = [l for l in t.splitlines() if l.strip()]
    n_lines = len(lines)
    tokens = t.split()
    numish = sum(1 for tok in tokens if _NUMISH.fullmatch(tok.strip("().,%")))
    num_ratio = numish / max(1, len(tokens))

    if is_deck:
        # slide text boxes: short, scattered; tables even worse
        if num_ratio > 0.35 or n_lines >= 4:
            return "table_region", 0.40
        return "slide_textbox", 0.50

    if n_lines <= 1 and len(t) < 70 and (t.isupper() or t.istitle()) and not t.endswith(":"):
        return "heading", 0.85
    if num_ratio > 0.45 and n_lines >= 2:
        return "table_region", 0.60
    if t.lstrip().startswith(("•", "-", "", "o ")) or re.match(r"^\s*\(?[a-z0-9]\)\s", t):
        return "list", 0.80
    return "paragraph", 0.90


def parse_pdf(path: str | Path) -> tuple[list[ParsedPage], dict]:
    doc = pymupdf.open(str(path))
    meta = {
        "page_count": doc.page_count,
        "creationDate": doc.metadata.get("creationDate"),
        "title": doc.metadata.get("title") or Path(path).stem,
    }
    pages: list[ParsedPage] = []
    for pno in range(doc.page_count):
        page = doc[pno]
        rect = page.rect
        is_deck = rect.width > rect.height * 1.15
        page_text = page.get_text("text")
        pp = ParsedPage(
            page_no=pno + 1,
            text=page_text,
            printed_label=_printed_label(page_text, pno + 1),
            width=rect.width,
            height=rect.height,
        )
        raw = page.get_text("dict")
        cursor = 0
        idx = 0
        for blk in raw.get("blocks", []):
            if blk.get("type", 0) != 0:
                continue  # image block
            btxt_lines = []
            for line in blk.get("lines", []):
                spans = "".join(s.get("text", "") for s in line.get("spans", []))
                if spans.strip():
                    btxt_lines.append(spans)
            btxt = norm_ws("\n".join(btxt_lines))
            if not btxt:
                continue
            # locate within page_text for offsets (best-effort)
            pos = page_text.find(btxt_lines[0].strip()) if btxt_lines else -1
            cstart = pos if pos >= 0 else cursor
            cend = cstart + len(btxt)
            cursor = cend
            kind, conf = _classify(btxt, blk.get("bbox"), rect.width, rect.height, is_deck)
            pp.blocks.append(ParsedBlock(
                page_no=pno + 1, idx=idx, kind=kind, text=btxt,
                bbox=tuple(round(x, 1) for x in blk.get("bbox", (0, 0, 0, 0))),
                char_start=cstart, char_end=cend, structural_confidence=conf,
            ))
            idx += 1
        if not pp.blocks and page_text.strip():
            pp.blocks.append(ParsedBlock(
                page_no=pno + 1, idx=0, kind="paragraph", text=norm_ws(page_text),
                bbox=(0, 0, rect.width, rect.height),
                char_start=0, char_end=len(page_text), structural_confidence=0.85,
            ))
        pages.append(pp)
    doc.close()
    return pages, meta


def bbox_json(b: tuple) -> str:
    return json.dumps(list(b))
