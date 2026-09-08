"""FastAPI app + Jinja report UI. Localhost, no auth, read-only except upload."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, RedirectResponse)
from fastapi.templating import Jinja2Templates

from ..config import CONFIG
from ..pipeline import ingest_document
from ..store import queries as Q
from ..store.db import get_conn
from . import report as R

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="Reconciliation Ledger")
_SAMPLES = CONFIG.root / "sample-pdfs"


def db():
    return get_conn()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request):
    # the upload-driven demo UI; the engineering views live at /report and /view/*
    return TEMPLATES.TemplateResponse("app.html", {"request": request})


@app.get("/healthz")
def healthz():
    from ..extract.providers import get_provider
    prov = get_provider(CONFIG.provider)
    return {"ok": True, "provider": CONFIG.provider, "provider_available": prov.available()}


@app.get("/stats")
def stats():
    conn = db()
    try:
        return Q.counts(conn)
    finally:
        conn.close()


@app.post("/documents")
async def upload(file: UploadFile = File(...), provider: str | None = Form(default=None),
                 published_date: str | None = Form(default=None)):
    CONFIG.ensure_dirs()
    name = (file.filename or "upload.pdf").strip() or "upload.pdf"
    if not name.lower().endswith(".pdf"):
        return JSONResponse({"error": "Only PDF files are accepted."}, status_code=415)
    dest = CONFIG.pdf_dir / Path(name).name
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    try:
        rep = ingest_document(dest, provider_name=provider, published_date=published_date)
    except Exception as e:  # noqa: BLE001 - surface a clean message to the UI instead of a 500
        return JSONResponse(
            {"error": f"Could not process this document: {type(e).__name__}: {e}"[:400]},
            status_code=422)
    return JSONResponse(rep.__dict__)


@app.get("/documents")
def list_documents():
    conn = db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM documents ORDER BY id")]
    finally:
        conn.close()


@app.get("/documents/{doc_id}")
def document_detail(doc_id: int):
    conn = db()
    try:
        r = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(r) if r else JSONResponse({"error": "not found"}, 404)
    finally:
        conn.close()


@app.get("/documents/{doc_id}/summary")
def document_summary(doc_id: int):
    conn = db()
    try:
        s = R.doc_summary(conn, doc_id)
        return s if s else JSONResponse({"error": "not found"}, 404)
    finally:
        conn.close()


@app.get("/documents/{doc_id}/rejected")
def document_rejected(doc_id: int):
    conn = db()
    try:
        return R.doc_rejected(conn, doc_id)
    finally:
        conn.close()


@app.get("/samples")
def list_samples():
    """Bundled example PDFs, for convenience only. Any PDF may be uploaded."""
    if not _SAMPLES.is_dir():
        return []
    return [p.name for p in sorted(_SAMPLES.glob("*.pdf"))]


@app.get("/samples/{name}")
def get_sample(name: str):
    p = (_SAMPLES / name).resolve()
    if _SAMPLES.resolve() not in p.parents or p.suffix.lower() != ".pdf" or not p.is_file():
        return JSONResponse({"error": "not found"}, 404)
    return FileResponse(p, media_type="application/pdf", filename=p.name)


@app.get("/documents/{doc_id}/pages/{page_no}", response_class=PlainTextResponse)
def page_text(doc_id: int, page_no: int):
    conn = db()
    try:
        return Q.get_page_text(conn, doc_id, page_no) or ""
    finally:
        conn.close()


@app.get("/facts")
def facts(entity: str | None = None, attribute: str | None = None, doc: int | None = None,
          limit: int = Query(200, le=2000)):
    conn = db()
    try:
        q = "SELECT * FROM facts WHERE 1=1"
        args: list = []
        if entity:
            q += " AND entity_key=?"; args.append(entity)
        if attribute:
            q += " AND attribute_key=?"; args.append(attribute)
        if doc:
            q += " AND doc_id=?"; args.append(doc)
        q += " ORDER BY id LIMIT ?"; args.append(limit)
        return [R._fact_brief(conn, r["id"]) for r in conn.execute(q, args)]
    finally:
        conn.close()


@app.get("/relations")
def relations(bucket: str | None = None, doc: int | None = None):
    conn = db()
    try:
        rows = [R.relation_view(conn, r) for r in Q.relations(conn, bucket)]
        if doc is not None:
            rows = [rv for rv in rows
                    if rv["a"].get("doc_id") == doc or rv["b"].get("doc_id") == doc]
        return rows
    finally:
        conn.close()


@app.get("/relations/{rid}")
def relation_detail(rid: int):
    conn = db()
    try:
        r = conn.execute("SELECT * FROM relations WHERE id=?", (rid,)).fetchone()
        return R.relation_view(conn, r) if r else JSONResponse({"error": "not found"}, 404)
    finally:
        conn.close()


# --------------------------------------------------------------------- HTML views

@app.get("/report", response_class=HTMLResponse)
def report(request: Request):
    conn = db()
    try:
        ctx = R.overview(conn)
    finally:
        conn.close()
    return TEMPLATES.TemplateResponse("report.html", {"request": request, **ctx})


@app.get("/view/facts", response_class=HTMLResponse)
def view_facts(request: Request, bucket: str | None = None):
    conn = db()
    try:
        rows = [R._fact_brief(conn, r["id"]) for r in conn.execute(
            "SELECT id FROM facts ORDER BY doc_id, source_page LIMIT 1500")]
    finally:
        conn.close()
    return TEMPLATES.TemplateResponse("facts.html", {"request": request, "facts": rows})


@app.get("/view/relations", response_class=HTMLResponse)
def view_relations(request: Request, bucket: str | None = None):
    conn = db()
    try:
        rows = [R.relation_view(conn, r) for r in Q.relations(conn, bucket)]
    finally:
        conn.close()
    return TEMPLATES.TemplateResponse("relations.html",
                                      {"request": request, "relations": rows, "bucket": bucket or "all"})


@app.get("/view/unresolved", response_class=HTMLResponse)
def view_unresolved(request: Request):
    conn = db()
    try:
        data = R.unresolved_items(conn)
    finally:
        conn.close()
    return TEMPLATES.TemplateResponse("unresolved.html", {"request": request, **data})
