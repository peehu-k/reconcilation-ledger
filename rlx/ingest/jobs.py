"""Resumable ingest job bookkeeping. One row per document; a crash mid-extraction
leaves a cursor so processing resumes instead of restarting."""
from __future__ import annotations

from .registry import now_iso


def start_job(conn, doc_id: int, provider: str, total: int = 0) -> int:
    row = conn.execute("SELECT id FROM ingest_jobs WHERE doc_id=?", (doc_id,)).fetchone()
    if row:
        conn.execute("UPDATE ingest_jobs SET provider=?, total=?, status='running', error=NULL, updated_at=? WHERE id=?",
                     (provider, total, now_iso(), row["id"]))
        return row["id"]
    cur = conn.execute(
        "INSERT INTO ingest_jobs(doc_id,stage,cursor,total,status,provider,updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (doc_id, "registered", 0, total, "running", provider, now_iso()),
    )
    return cur.lastrowid


def update_job(conn, doc_id: int, *, stage: str | None = None, cursor: int | None = None,
               status: str | None = None, error: str | None = None) -> None:
    sets, args = [], []
    for col, val in (("stage", stage), ("cursor", cursor), ("status", status), ("error", error)):
        if val is not None:
            sets.append(f"{col}=?")
            args.append(val)
    sets.append("updated_at=?")
    args.append(now_iso())
    args.append(doc_id)
    conn.execute(f"UPDATE ingest_jobs SET {', '.join(sets)} WHERE doc_id=?", args)


def get_job(conn, doc_id: int):
    return conn.execute("SELECT * FROM ingest_jobs WHERE doc_id=?", (doc_id,)).fetchone()
