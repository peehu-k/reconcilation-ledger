"""Group blocks into extraction chunks. Chunks never cross a page boundary (keeps
quote verification and page references simple)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import CONFIG
from .parse import ParsedBlock, ParsedPage


@dataclass
class Chunk:
    doc_id: int
    page_no: int
    block_ids: list[int]
    text: str
    structural_confidence: float
    idx: int = 0
    printed_label: str | None = None


def build_chunks(doc_id: int, pages: list[ParsedPage], block_id_map: dict[tuple[int, int], int],
                 target_chars: int | None = None) -> list[Chunk]:
    target = target_chars or CONFIG.t.chunk_target_chars
    chunks: list[Chunk] = []
    ci = 0
    for pp in pages:
        buf: list[ParsedBlock] = []
        size = 0
        for blk in pp.blocks:
            buf.append(blk)
            size += len(blk.text) + 1
            if size >= target:
                chunks.append(_mk(doc_id, pp, buf, ci, block_id_map))
                ci += 1
                buf, size = [], 0
        if buf:
            chunks.append(_mk(doc_id, pp, buf, ci, block_id_map))
            ci += 1
    return chunks


def _mk(doc_id, pp: ParsedPage, buf, ci, block_id_map) -> Chunk:
    return Chunk(
        doc_id=doc_id,
        page_no=pp.page_no,
        block_ids=[block_id_map[(pp.page_no, b.idx)] for b in buf if (pp.page_no, b.idx) in block_id_map],
        text="\n".join(b.text for b in buf),
        structural_confidence=min((b.structural_confidence for b in buf), default=0.9),
        idx=ci,
        printed_label=pp.printed_label,
    )
