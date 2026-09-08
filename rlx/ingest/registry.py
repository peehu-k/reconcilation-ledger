"""Document registration: content hashing (idempotency), published-date resolution,
and a generic guess at the document's primary entity (resolves "the Company")."""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .. import PIPELINE_VERSION
from ..normalize.entities import entity_key
from ..normalize.text import norm_ws

_DATED = re.compile(r"\b(?:dated|as at|as on)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})", re.I)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_ORGISH = re.compile(r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,4}\s+"
                     r"(?:Limited|Ltd|Bank|Corporation|Authority|Board|Fund|Company|PLC|Inc))\b")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_creation_date(raw: str | None) -> str | None:
    # PyMuPDF gives "D:20240808140748+05'30'"
    if not raw:
        return None
    m = re.search(r"D:(\d{4})(\d{2})(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _parse_dated_phrase(text: str) -> str | None:
    m = _DATED.search(text)
    if not m:
        return None
    s = norm_ws(m.group(1)).lower().replace(",", "")
    a = re.match(r"([a-z]+)\s+(\d{1,2})\s+(\d{4})", s)
    if a and a.group(1)[:3] in _MONTHS:
        return f"{int(a.group(3)):04d}-{_MONTHS[a.group(1)[:3]]:02d}-{int(a.group(2)):02d}"
    b = re.match(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", s)
    if b and b.group(2)[:3] in _MONTHS:
        return f"{int(b.group(3)):04d}-{_MONTHS[b.group(2)[:3]]:02d}-{int(b.group(1)):02d}"
    return None


def resolve_published_date(explicit: str | None, first_pages_text: str,
                           creation_date_raw: str | None) -> tuple[str | None, str]:
    if explicit:
        return explicit, "explicit"
    d = _parse_dated_phrase(first_pages_text)
    if d:
        return d, "cover_dated_phrase"
    d = _parse_creation_date(creation_date_raw)
    if d:
        return d, "pdf_creation_date"
    return None, "unknown"


def guess_primary_entity(first_pages_text: str) -> tuple[str | None, str | None]:
    cands = Counter(_ORGISH.findall(first_pages_text))
    if not cands:
        return None, None
    display = cands.most_common(1)[0][0]
    return entity_key(display), norm_ws(display)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_title(title: str | None, stem: str) -> str:
    t = (title or "").strip()
    if not t or len(t) > 70 or t.count(";") >= 2:
        return stem
    return t


def register_document(conn, *, path: str, title: str | None, sha: str,
                      page_count: int, published_date: str | None, published_date_source: str,
                      primary_entity_key: str | None, primary_entity_display: str | None,
                      model_name: str) -> tuple[int, bool]:
    row = conn.execute("SELECT id FROM documents WHERE content_sha256=?", (sha,)).fetchone()
    if row:
        return row["id"], False
    cur = conn.execute(
        """INSERT INTO documents(content_sha256,title,source_path,page_count,published_date,
                published_date_source,primary_entity_key,primary_entity_display,
                pipeline_version,model_name,ingested_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (sha, title, str(path), page_count, published_date, published_date_source,
         primary_entity_key, primary_entity_display, PIPELINE_VERSION, model_name, now_iso()),
    )
    return cur.lastrowid, True
