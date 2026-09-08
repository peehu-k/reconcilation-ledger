"""Convenience: ingest every PDF in a directory (defaults to ./sample-pdfs) and
print a summary. Usage:

    python scripts/ingest_starter.py [DIR] [--provider replay|ollama|gemini|null]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rlx.pipeline import ingest_document  # noqa: E402
from rlx.store.db import get_conn  # noqa: E402
from rlx.store import queries as Q  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default="sample-pdfs")
    ap.add_argument("--provider", default=None)
    args = ap.parse_args()

    pdfs = sorted(Path(args.dir).glob("**/*.pdf"))
    if not pdfs:
        print(f"no PDFs under {args.dir}")
        return 1
    for p in pdfs:
        r = ingest_document(p, provider_name=args.provider)
        print(f"{p.name:48s} doc#{r.doc_id:<3} {r.status:11s} "
              f"facts={r.facts} rejected={r.rejected} errors={r.errors} relations={r.relations}")
    conn = get_conn()
    print("\n== ledger ==")
    for k, v in Q.counts(conn).items():
        print(f"  {k:>18}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
