"""Thin data-access helpers. Plain SQL, explicit columns."""
from __future__ import annotations

import json
import sqlite3
from typing import Iterable

from .. import PIPELINE_VERSION
from ..ingest.registry import now_iso
from .models import Fact, RelationResult

# ---------------------------------------------------------------- pages / blocks

def insert_page(conn, doc_id, page_no, printed_label, text, width, height) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO pages(doc_id,page_no,printed_label,text,width,height) VALUES(?,?,?,?,?,?)",
        (doc_id, page_no, printed_label, text, width, height),
    )


def insert_block(conn, doc_id, b) -> int:
    cur = conn.execute(
        "INSERT INTO blocks(doc_id,page_no,idx,kind,text,bbox,char_start,char_end,structural_confidence) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (doc_id, b.page_no, b.idx, b.kind, b.text, json.dumps(list(b.bbox)),
         b.char_start, b.char_end, b.structural_confidence),
    )
    return cur.lastrowid


def get_page_text(conn, doc_id, page_no) -> str | None:
    r = conn.execute("SELECT text FROM pages WHERE doc_id=? AND page_no=?", (doc_id, page_no)).fetchone()
    return r["text"] if r else None


# ---------------------------------------------------------------- raw facts / facts

def insert_raw_fact(conn, rf) -> int:
    cur = conn.execute(
        """INSERT INTO raw_facts(doc_id,block_id,page_no,fact_kind,entity_text,attribute_label,value_text,
             unit_text,period_text,as_of_text,estimate_status_text,basis_text,scope_text,attributed_to_text,
             quote,llm_self_confidence,quote_match,quote_char_start,quote_char_end,prompt_version,model_name,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rf.doc_id, rf.block_id, rf.page_no, rf.fact_kind, rf.entity_text, rf.attribute_label, rf.value_text,
         rf.unit_text, rf.period_text, rf.as_of_text, rf.estimate_status_text, rf.basis_text, rf.scope_text,
         rf.attributed_to_text, rf.quote, rf.self_confidence, rf.quote_match, rf.quote_char_start,
         rf.quote_char_end, "extract.v1", None, now_iso()),
    )
    return cur.lastrowid


def insert_fact(conn, f: Fact, raw_fact_id: int) -> int | None:
    row = f.to_row()
    try:
        cur = conn.execute(
            """INSERT INTO facts(raw_fact_id,doc_id,page_no,fact_kind,entity_key,entity_display,attribute_key,
                 attribute_display,value_num,value_text,currency,unit_canonical,scale_applied,period_canonical,
                 as_of_date,estimate_status,basis_flags,scope_flags,attributed_to,quote,quote_match,source_page,
                 printed_label,extraction_confidence,sanity_flags,content_hash,pipeline_version,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (raw_fact_id, f.doc_id, f.source_page, f.fact_kind, f.entity_key, f.entity_display, f.attribute_key,
             f.attribute_display, f.value_num, f.value_text, f.currency, f.unit_canonical, f.scale_applied,
             f.period_canonical, f.as_of_date, f.estimate_status, row["basis_flags"], row["scope_flags"],
             f.attributed_to, f.quote, f.quote_match, f.source_page, f.printed_label, f.extraction_confidence,
             row["sanity_flags"], f.content_hash, PIPELINE_VERSION, now_iso()),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # duplicate content_hash -> idempotent skip


def insert_rejected(conn, doc_id, block_id, page_no, reason, payload: dict) -> None:
    conn.execute(
        "INSERT INTO rejected_facts(doc_id,block_id,page_no,reason,payload,created_at) VALUES(?,?,?,?,?,?)",
        (doc_id, block_id, page_no, reason, json.dumps(payload, default=str), now_iso()),
    )


def insert_extraction_error(conn, doc_id, block_id, page_no, error, raw_output) -> None:
    conn.execute(
        "INSERT INTO extraction_errors(doc_id,block_id,page_no,error,raw_output,created_at) VALUES(?,?,?,?,?,?)",
        (doc_id, block_id, page_no, str(error)[:2000], (raw_output or "")[:8000], now_iso()),
    )


def facts_for_doc(conn, doc_id) -> list[Fact]:
    rows = conn.execute("SELECT * FROM facts WHERE doc_id=?", (doc_id,)).fetchall()
    return [_fact_with_title(conn, r) for r in rows]


def facts_in_block(conn, entity_key, attribute_key) -> list[Fact]:
    rows = conn.execute(
        "SELECT * FROM facts WHERE entity_key=? AND attribute_key=?", (entity_key, attribute_key)
    ).fetchall()
    return [_fact_with_title(conn, r) for r in rows]


def all_facts(conn) -> list[Fact]:
    rows = conn.execute("SELECT * FROM facts").fetchall()
    return [_fact_with_title(conn, r) for r in rows]


def _fact_with_title(conn, row) -> Fact:
    f = Fact.from_row(row)
    tr = conn.execute("SELECT title FROM documents WHERE id=?", (f.doc_id,)).fetchone()
    f.doc_title = tr["title"] if tr else None
    return f


# ---------------------------------------------------------------- relations

def relation_exists(conn, fa: int, fb: int) -> bool:
    lo, hi = sorted((fa, fb))
    return conn.execute("SELECT 1 FROM relations WHERE fact_a=? AND fact_b=?", (lo, hi)).fetchone() is not None


def insert_relation(conn, fa_id: int, fb_id: int, entity_key: str, attribute_key: str,
                    res: RelationResult) -> int | None:
    lo, hi = sorted((fa_id, fb_id))
    try:
        cur = conn.execute(
            """INSERT INTO relations(fact_a,fact_b,entity_key,attribute_key,bucket,rule_code,rule_trace,
                 explanation,explanation_source,relation_confidence,pipeline_version,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (lo, hi, entity_key, attribute_key, res.bucket, res.rule_code, json.dumps(res.rule_trace),
             res.explanation, res.explanation_source, res.confidence, PIPELINE_VERSION, now_iso()),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def relations(conn, bucket: str | None = None) -> list[sqlite3.Row]:
    if bucket:
        return conn.execute("SELECT * FROM relations WHERE bucket=? ORDER BY relation_confidence DESC",
                            (bucket,)).fetchall()
    return conn.execute("SELECT * FROM relations ORDER BY relation_confidence DESC").fetchall()


# ---------------------------------------------------------------- registries

def upsert_entity(conn, key, display, decided_by="lexical", score=1.0, doc_id=None) -> None:
    conn.execute(
        """INSERT INTO entity_registry(entity_key,canonical_display,aliases,decided_by,score,first_seen_doc,decided_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(entity_key) DO NOTHING""",
        (key, display, json.dumps([]), decided_by, score, doc_id, now_iso()),
    )


def upsert_attribute(conn, key, display, unit_hint=None, decided_by="lexical", score=1.0, doc_id=None) -> None:
    conn.execute(
        """INSERT INTO attribute_registry(attribute_key,canonical_display,aliases,unit_hint,decided_by,score,
             first_seen_doc,decided_at)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(attribute_key) DO NOTHING""",
        (key, display, json.dumps([]), unit_hint, decided_by, score, doc_id, now_iso()),
    )


def known_attribute_keys(conn) -> list[str]:
    return [r["attribute_key"] for r in conn.execute("SELECT attribute_key FROM attribute_registry")]


def known_entity_keys(conn) -> list[str]:
    return [r["entity_key"] for r in conn.execute("SELECT entity_key FROM entity_registry")]


def add_alias(conn, table: str, key: str, alias: str) -> None:
    col = "entity_key" if table == "entity_registry" else "attribute_key"
    row = conn.execute(f"SELECT aliases FROM {table} WHERE {col}=?", (key,)).fetchone()
    if not row:
        return
    al = set(json.loads(row["aliases"] or "[]"))
    al.add(alias)
    conn.execute(f"UPDATE {table} SET aliases=? WHERE {col}=?", (json.dumps(sorted(al)), key))


# ---------------------------------------------------------------- stats

def counts(conn) -> dict:
    def one(q, *a):
        return conn.execute(q, a).fetchone()[0]
    return {
        "documents": one("SELECT COUNT(*) FROM documents"),
        "facts": one("SELECT COUNT(*) FROM facts"),
        "raw_facts": one("SELECT COUNT(*) FROM raw_facts"),
        "rejected_facts": one("SELECT COUNT(*) FROM rejected_facts"),
        "extraction_errors": one("SELECT COUNT(*) FROM extraction_errors"),
        "relations": one("SELECT COUNT(*) FROM relations"),
        "corroborated": one("SELECT COUNT(*) FROM relations WHERE bucket='corroborated'"),
        "contradiction": one("SELECT COUNT(*) FROM relations WHERE bucket='contradiction'"),
        "reconciled": one("SELECT COUNT(*) FROM relations WHERE bucket='reconciled'"),
        "unresolved": one("SELECT COUNT(*) FROM relations WHERE bucket='unresolved'"),
    }
