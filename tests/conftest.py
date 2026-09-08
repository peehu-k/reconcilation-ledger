import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# keep tests off any real ledger; use the offline provider
os.environ.setdefault("RLX_DB", "data/test_rlx.db")
os.environ.setdefault("RLX_PROVIDER", "replay")

# the bundled example PDFs the integration tests run against
STARTER_DIR = ROOT / "sample-pdfs"


def starter_pdfs():
    if not STARTER_DIR.is_dir():
        return []
    return sorted(STARTER_DIR.glob("*.pdf"))
