"""Assemble data structures for the HTML views. No business logic here - just
selecting and shaping rows the templates render."""
from __future__ import annotations

import json

from ..store import queries as Q


def _fact_brief(conn, fact_id: int) -> dict:
    r = conn.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone()
    if not r:
        return {}
    d = conn.execute("SELECT title, published_date, published_date_source FROM documents WHERE id=?",
                     (r["doc_id"],)).fetchone()
    return {
        "id": r["id"], "doc_id": r["doc_id"],
        "doc_title": d["title"] if d else "?",
        "published_date": d["published_date"] if d else None,
        "entity": r["entity_display"] or r["entity_key"],
        "attribute": r["attribute_display"] or r["attribute_key"],
        "attribute_key": r["attribute_key"],
        "value_text": r["value_text"],
        "value_num": r["value_num"],
        "unit": r["unit_canonical"], "currency": r["currency"],
        "period": r["period_canonical"], "as_of": r["as_of_date"],
        "estimate_status": r["estimate_status"],
        "basis": json.loads(r["basis_flags"] or "[]"),
        "scope": json.loads(r["scope_flags"] or "[]"),
        "attributed_to": r["attributed_to"],
        "quote": r["quote"], "quote_match": r["quote_match"],
        "page": r["source_page"], "printed": r["printed_label"],
        "confidence": r["extraction_confidence"],
        "sanity_flags": json.loads(r["sanity_flags"] or "[]"),
    }


def relation_view(conn, row) -> dict:
    return {
        "id": row["id"], "bucket": row["bucket"], "rule_code": row["rule_code"],
        "explanation": row["explanation"], "explanation_source": row["explanation_source"],
        "confidence": row["relation_confidence"],
        "trace": json.loads(row["rule_trace"] or "[]"),
        "entity": row["entity_key"], "attribute": row["attribute_key"],
        "a": _fact_brief(conn, row["fact_a"]),
        "b": _fact_brief(conn, row["fact_b"]),
    }


def overview(conn) -> dict:
    counts = Q.counts(conn)
    docs = [dict(r) for r in conn.execute(
        "SELECT id,title,page_count,published_date,published_date_source,primary_entity_display,"
        "(SELECT COUNT(*) FROM facts f WHERE f.doc_id=documents.id) AS facts "
        "FROM documents ORDER BY id")]
    jobs = {r["doc_id"]: dict(r) for r in conn.execute("SELECT * FROM ingest_jobs")}
    for d in docs:
        j = jobs.get(d["id"])
        d["job_status"] = j["status"] if j else "?"
        d["job_stage"] = j["stage"] if j else "?"

    def best(bucket, n=3, want_rule=None, cross_doc=False, diversify=True):
        rows = Q.relations(conn, bucket)
        out, seen_attr = [], set()
        for r in rows:
            if want_rule and r["rule_code"] not in ({want_rule} if isinstance(want_rule, str) else set(want_rule)):
                continue
            rv = relation_view(conn, r)
            if cross_doc and rv["a"].get("doc_id") == rv["b"].get("doc_id"):
                continue
            if diversify and rv["attribute"] in seen_attr:
                continue
            seen_attr.add(rv["attribute"])
            out.append(rv)
            if len(out) >= n:
                break
        return out

    cases = {
        "corroboration": best("corroborated", 4, cross_doc=True),
        "contradiction": best("contradiction", 3, diversify=False),
        "reconciled_vintage": best("reconciled", 2, want_rule="ESTIMATE_VINTAGE"),
        "reconciled_period": best("reconciled", 2, want_rule="PERIOD"),
        "reconciled_basis": best("reconciled", 2, want_rule=("BASIS", "SCOPE", "IDENTIFIER_REVISION", "UNIT_SCALE")),
        "reconciled_temporal": best("reconciled", 1, want_rule="TEMPORAL_STATUS"),
    }
    return {"counts": counts, "docs": docs, "cases": cases}


def doc_summary(conn, doc_id: int) -> dict | None:
    """Per-document counts for the upload UI's results header. All values from the DB."""
    d = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not d:
        return None
    nfacts = conn.execute("SELECT COUNT(*) FROM facts WHERE doc_id=?", (doc_id,)).fetchone()[0]
    rej = conn.execute("SELECT COUNT(*) FROM rejected_facts WHERE doc_id=?", (doc_id,)).fetchone()[0]
    errs = conn.execute("SELECT COUNT(*) FROM extraction_errors WHERE doc_id=?", (doc_id,)).fetchone()[0]
    buckets = {"corroborated": 0, "contradiction": 0, "reconciled": 0, "unresolved": 0}
    rows = conn.execute(
        "SELECT rel.bucket FROM relations rel JOIN facts fa ON fa.id=rel.fact_a "
        "JOIN facts fb ON fb.id=rel.fact_b WHERE fa.doc_id=? OR fb.doc_id=?", (doc_id, doc_id)).fetchall()
    for r in rows:
        buckets[r["bucket"]] = buckets.get(r["bucket"], 0) + 1
    job = conn.execute("SELECT status, stage FROM ingest_jobs WHERE doc_id=?", (doc_id,)).fetchone()
    return {
        "doc_id": doc_id, "title": d["title"], "page_count": d["page_count"] or 0,
        "published_date": d["published_date"], "published_date_source": d["published_date_source"],
        "primary_entity": d["primary_entity_display"], "model": d["model_name"],
        "facts": nfacts, "rejected": rej, "errors": errs, "relations": len(rows),
        "corroborated": buckets["corroborated"], "contradiction": buckets["contradiction"],
        "reconciled": buckets["reconciled"], "unresolved": buckets["unresolved"],
        "job_status": job["status"] if job else None, "job_stage": job["stage"] if job else None,
    }


def doc_rejected(conn, doc_id: int) -> list[dict]:
    out = []
    for r in conn.execute(
            "SELECT * FROM rejected_facts WHERE doc_id=? ORDER BY id", (doc_id,)):
        try:
            p = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            p = {}
        out.append({"page_no": r["page_no"], "reason": r["reason"],
                    "value_text": p.get("value_text"), "attribute_label": p.get("attribute_label"),
                    "entity_text": p.get("entity_text"), "quote": p.get("quote"),
                    "guard_score": p.get("_quote_guard_score")})
    return out


def unresolved_items(conn) -> dict:
    rej = [dict(r) for r in conn.execute(
        "SELECT rf.*, d.title FROM rejected_facts rf JOIN documents d ON d.id=rf.doc_id "
        "ORDER BY rf.id DESC LIMIT 200")]
    for r in rej:
        try:
            r["payload_obj"] = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            r["payload_obj"] = {}
    errs = [dict(r) for r in conn.execute(
        "SELECT e.*, d.title FROM extraction_errors e JOIN documents d ON d.id=e.doc_id "
        "ORDER BY e.id DESC LIMIT 100")]
    rels = [relation_view(conn, r) for r in Q.relations(conn, "unresolved")]
    flagged = [_fact_brief(conn, r["id"]) for r in conn.execute(
        "SELECT id FROM facts WHERE sanity_flags NOT IN ('[]','') ORDER BY id DESC LIMIT 100")]
    return {"rejected": rej, "errors": errs, "relations": rels, "flagged": flagged}
