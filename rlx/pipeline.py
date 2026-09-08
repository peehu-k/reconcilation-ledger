"""End-to-end orchestration.

ingest_document(): parse -> chunk -> extract -> quote-guard -> normalize -> store
                   -> incremental reconcile. Idempotent (content hash), resumable
                   (per-chunk job cursor), and degrades gracefully when the LLM is
                   unavailable (keeps partial results, marks the job 'paused_llm').
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import PIPELINE_VERSION
from .adjudicate.adjudicator import polish_explanation
from .config import CONFIG
from .extract.extractor import extract_chunk
from .extract.providers import LLMUnavailable, get_provider
from .ingest import jobs
from .ingest.chunk import build_chunks
from .ingest.parse import parse_pdf
from .ingest.registry import (clean_title, guess_primary_entity, register_document,
                              resolve_published_date, sha256_file)
from .match.blocking import candidate_pairs
from .match.registry import resolve_attribute_key, resolve_entity_key
from .normalize.pipeline import DocContext, normalize_fact
from .reconcile.cascade import reconcile
from .store import queries as Q
from .store.db import get_conn


@dataclass
class IngestReport:
    doc_id: int
    created: bool
    status: str
    facts: int = 0
    rejected: int = 0
    errors: int = 0
    relations: int = 0
    note: str = ""
    # descriptive fields for the UI (do not affect pipeline behaviour)
    title: str = ""
    page_count: int = 0
    provider: str = ""


def ingest_document(path: str | Path, *, provider_name: str | None = None,
                    title: str | None = None, published_date: str | None = None,
                    conn=None) -> IngestReport:
    CONFIG.ensure_dirs()
    own_conn = conn is None
    conn = conn or get_conn()
    provider = get_provider(provider_name)
    try:
        return _ingest(conn, provider, Path(path), title, published_date)
    finally:
        if own_conn:
            conn.close()


def _ingest(conn, provider, path: Path, title, published_date) -> IngestReport:
    sha = sha256_file(path)
    existing = conn.execute("SELECT id FROM documents WHERE content_sha256=?", (sha,)).fetchone()
    if existing:
        job = jobs.get_job(conn, existing["id"])
        st = job["status"] if job else "done"
        if st in ("done",):
            d = conn.execute("SELECT title, page_count FROM documents WHERE id=?", (existing["id"],)).fetchone()
            return IngestReport(existing["id"], False, "exists",
                                facts=_count_doc_facts(conn, existing["id"]),
                                relations=conn.execute(
                                    "SELECT COUNT(*) FROM relations rel JOIN facts fa ON fa.id=rel.fact_a "
                                    "JOIN facts fb ON fb.id=rel.fact_b WHERE fa.doc_id=? OR fb.doc_id=?",
                                    (existing["id"], existing["id"])).fetchone()[0],
                                rejected=conn.execute(
                                    "SELECT COUNT(*) FROM rejected_facts WHERE doc_id=?", (existing["id"],)).fetchone()[0],
                                title=d["title"] if d else "", page_count=(d["page_count"] if d else 0) or 0,
                                provider=getattr(provider, "name", ""),
                                note="identical content already ingested - showing existing results")
        # a previous run stopped early: resume it
        return _run_extraction(conn, provider, existing["id"], resume=True)

    pages, meta = parse_pdf(path)
    first_pages_text = "\n".join(p.text for p in pages[:4])
    pub, pub_src = resolve_published_date(published_date, first_pages_text, meta.get("creationDate"))
    pe_key, pe_disp = guess_primary_entity(first_pages_text)

    doc_id, created = register_document(
        conn, path=str(path), title=title or clean_title(meta.get("title"), path.stem), sha=sha,
        page_count=meta["page_count"], published_date=pub, published_date_source=pub_src,
        primary_entity_key=pe_key, primary_entity_display=pe_disp,
        model_name=getattr(provider, "name", "?"),
    )

    # persist pages + blocks
    block_id_map: dict[tuple[int, int], int] = {}
    for pp in pages:
        Q.insert_page(conn, doc_id, pp.page_no, pp.printed_label, pp.text, pp.width, pp.height)
        for b in pp.blocks:
            bid = Q.insert_block(conn, doc_id, b)
            block_id_map[(pp.page_no, b.idx)] = bid
    conn.execute("UPDATE documents SET model_name=? WHERE id=?", (getattr(provider, "name", "?"), doc_id))

    chunks = build_chunks(doc_id, pages, block_id_map)
    jobs.start_job(conn, doc_id, getattr(provider, "name", "?"), total=len(chunks))
    jobs.update_job(conn, doc_id, stage="parsed")
    # stash chunk plan so a resume does not need to re-parse identically
    conn.execute("UPDATE documents SET source_path=? WHERE id=?", (str(path), doc_id))

    return _run_extraction(conn, provider, doc_id, resume=False, chunks=chunks,
                           pages=pages, block_id_map=block_id_map)


def _rebuild_plan(conn, doc_id):
    """Reconstruct pages + block map + chunks from stored rows (for a resume)."""
    from .ingest.parse import ParsedBlock, ParsedPage
    prows = conn.execute("SELECT * FROM pages WHERE doc_id=? ORDER BY page_no", (doc_id,)).fetchall()
    brows = conn.execute("SELECT * FROM blocks WHERE doc_id=? ORDER BY page_no, idx", (doc_id,)).fetchall()
    by_page: dict[int, ParsedPage] = {}
    for r in prows:
        by_page[r["page_no"]] = ParsedPage(r["page_no"], r["text"], r["printed_label"],
                                           r["width"] or 0.0, r["height"] or 0.0, [])
    block_id_map = {}
    for r in brows:
        pp = by_page.get(r["page_no"])
        if not pp:
            continue
        blk = ParsedBlock(r["page_no"], r["idx"], r["kind"], r["text"],
                          tuple(json.loads(r["bbox"] or "[0,0,0,0]")),
                          r["char_start"] or 0, r["char_end"] or 0, r["structural_confidence"])
        pp.blocks.append(blk)
        block_id_map[(r["page_no"], r["idx"])] = r["id"]
    pages = [by_page[k] for k in sorted(by_page)]
    chunks = build_chunks(doc_id, pages, block_id_map)
    return chunks, pages, block_id_map


def _run_extraction(conn, provider, doc_id, *, resume: bool, chunks=None, pages=None, block_id_map=None):
    if chunks is None:
        chunks, pages, block_id_map = _rebuild_plan(conn, doc_id)
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    ctx = DocContext(doc_id=doc_id, doc_title=doc["title"],
                     primary_entity_key=doc["primary_entity_key"],
                     published_date=doc["published_date"])
    struct_by_block = {r["id"]: r["structural_confidence"]
                       for r in conn.execute("SELECT id,structural_confidence FROM blocks WHERE doc_id=?", (doc_id,))}

    job = jobs.get_job(conn, doc_id)
    start = job["cursor"] if (job and resume) else 0
    jobs.update_job(conn, doc_id, stage="extracting", status="running")

    n_facts = n_rej = n_err = 0
    new_fact_ids: set[int] = set()
    llm_paused = False

    for ci, ch in enumerate(chunks):
        if ci < start:
            continue
        try:
            cr = extract_chunk(provider, title=doc["title"], page=ch.page_no,
                               printed=ch.printed_label, text=ch.text)
        except LLMUnavailable as e:
            jobs.update_job(conn, doc_id, status="paused_llm", cursor=ci,
                            error=f"LLM unavailable at chunk {ci}: {e}")
            llm_paused = True
            break

        if cr.error:
            first_block = ch.block_ids[0] if ch.block_ids else None
            Q.insert_extraction_error(conn, doc_id, first_block, ch.page_no, cr.error, cr.raw_output)
            n_err += 1

        for payload in cr.rejected:
            Q.insert_rejected(conn, doc_id, ch.block_ids[0] if ch.block_ids else None,
                              ch.page_no, "quote_not_found", payload)
            n_rej += 1

        for rf in cr.raw_facts:
            rf.doc_id = doc_id
            rf.block_id = ch.block_ids[0] if ch.block_ids else None
            rf_id = Q.insert_raw_fact(conn, rf)
            sc = struct_by_block.get(rf.block_id, ch.structural_confidence)
            fact = normalize_fact(rf, ctx, structural_confidence=sc, printed_label=ch.printed_label)
            fact.entity_key = resolve_entity_key(conn, fact.entity_key, fact.entity_display, doc_id)
            fact.attribute_key = resolve_attribute_key(conn, fact.attribute_key, fact.attribute_display, doc_id)
            fid = Q.insert_fact(conn, fact, rf_id)
            if fid:
                new_fact_ids.add(fid)
                n_facts += 1

        jobs.update_job(conn, doc_id, cursor=ci + 1)

    _desc = dict(title=doc["title"], page_count=(doc["page_count"] or 0),
                 provider=getattr(provider, "name", ""))

    if llm_paused:
        rel = _reconcile_incremental(conn, provider, new_fact_ids)  # still reconcile what we have
        return IngestReport(doc_id, True, "paused_llm", facts=n_facts, rejected=n_rej,
                            errors=n_err, relations=rel, **_desc,
                            note="LLM became unavailable mid-run; partial results kept, resumable")

    jobs.update_job(conn, doc_id, stage="extracted")
    rel = _reconcile_incremental(conn, provider, new_fact_ids)
    jobs.update_job(conn, doc_id, stage="done", status="done")
    return IngestReport(doc_id, True, "done", facts=n_facts, rejected=n_rej, errors=n_err,
                        relations=rel, **_desc)


def _reconcile_incremental(conn, provider, new_fact_ids: set[int]) -> int:
    if not new_fact_ids:
        return 0
    # only touch blocks that a new fact landed in
    keys = set()
    for fid in new_fact_ids:
        r = conn.execute("SELECT entity_key, attribute_key FROM facts WHERE id=?", (fid,)).fetchone()
        if r:
            keys.add((r["entity_key"], r["attribute_key"]))
    made = 0
    for ekey, akey in keys:
        facts = Q.facts_in_block(conn, ekey, akey)
        for a, b in candidate_pairs(facts, new_ids=new_fact_ids):
            if Q.relation_exists(conn, a.id, b.id):
                continue
            res = reconcile(a, b)
            res = polish_explanation(provider, res, a, b)
            if Q.insert_relation(conn, a.id, b.id, ekey, akey, res):
                made += 1
    return made


def _count_doc_facts(conn, doc_id) -> int:
    return conn.execute("SELECT COUNT(*) FROM facts WHERE doc_id=?", (doc_id,)).fetchone()[0]


def reconcile_all(conn=None) -> int:
    """Rebuild every pairwise relation from scratch (used by tests / --rebuild)."""
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM relations")
        facts = Q.all_facts(conn)
        made = 0
        prov = get_provider("null")
        # group and pair
        seen_keys = {(f.entity_key, f.attribute_key) for f in facts}
        for ekey, akey in seen_keys:
            block = [f for f in facts if f.entity_key == ekey and f.attribute_key == akey]
            for a, b in candidate_pairs(block):
                res = reconcile(a, b)
                if Q.insert_relation(conn, a.id, b.id, ekey, akey, res):
                    made += 1
        return made
    finally:
        if own:
            conn.close()
