"""Command line entry point.

  rlx init                          create / migrate the database
  rlx ingest FILE [FILE ...]        ingest one or more PDFs
  rlx ingest-dir DIR                ingest every *.pdf under DIR
  rlx reconcile                     rebuild all pairwise relations
  rlx stats                         print counts
  rlx serve [--host --port]         run the FastAPI app + report UI
  rlx reset                         drop and recreate the database

Common flags: --provider {ollama,replay,gemini,null}
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import CONFIG
from .store.db import get_conn, reset_db


def _p_provider(p):
    p.add_argument("--provider", default=None,
                   help="ollama (default) | replay | gemini | null")


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(prog="rlx", description="Reconciliation Ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sp = sub.add_parser("ingest"); sp.add_argument("files", nargs="+"); _p_provider(sp)
    sp = sub.add_parser("ingest-dir"); sp.add_argument("dir"); _p_provider(sp)
    sub.add_parser("reconcile")
    sub.add_parser("stats")
    sp = sub.add_parser("serve")
    sp.add_argument("--host", default="127.0.0.1"); sp.add_argument("--port", type=int, default=8000)
    sub.add_parser("reset")

    args = ap.parse_args(argv)

    if args.cmd == "init":
        get_conn().close()
        print(f"database ready at {CONFIG.db_path}")
        return 0

    if args.cmd == "reset":
        reset_db()
        print(f"database reset at {CONFIG.db_path}")
        return 0

    if args.cmd == "stats":
        from .store import queries as Q
        conn = get_conn()
        for k, v in Q.counts(conn).items():
            print(f"{k:>18}: {v}")
        conn.close()
        return 0

    if args.cmd == "reconcile":
        from .pipeline import reconcile_all
        print(f"built {reconcile_all()} relations")
        return 0

    if args.cmd in ("ingest", "ingest-dir"):
        from .pipeline import ingest_document
        files: list[Path]
        if args.cmd == "ingest":
            files = [Path(f) for f in args.files]
        else:
            files = sorted(Path(args.dir).glob("**/*.pdf"))
        if not files:
            print("no PDFs found"); return 1
        for f in files:
            if not f.exists():
                print(f"! missing: {f}"); continue
            rep = ingest_document(f, provider_name=args.provider)
            print(f"{f.name:45s} doc#{rep.doc_id:<3} {rep.status:11s} "
                  f"facts={rep.facts} rejected={rep.rejected} errors={rep.errors} relations={rep.relations}"
                  + (f"  ({rep.note})" if rep.note else ""))
        return 0

    if args.cmd == "serve":
        import uvicorn
        from .api.app import app
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
