"""Central configuration. Every value has a safe default; nothing here requires payment or a key."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = _ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


def _b(name: str, default: bool) -> bool:
    return os.environ.get(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Thresholds:
    # numeric comparison
    rel_tol_equal: float = 0.005          # <=0.5% relative -> EQUAL
    rel_tol_rounding: float = 0.02        # <=2% relative -> ROUNDING reconciliation
    abs_floor: float = 1.0                # absolute floor so tiny magnitudes don't divide-by-noise
    # vintage
    vintage_min_days: int = 45            # as_of dates this far apart count as different vintages
    # bucketing
    tau_corroborate: float = 0.50
    tau_reconcile: float = 0.50
    tau_contradiction: float = 0.45
    # matching
    entity_fuzz: int = 90
    attribute_fuzz: int = 92
    embedding_sim: float = 0.86
    # extraction
    max_facts_per_chunk: int = 25
    chunk_target_chars: int = 4800        # ~1200 tokens
    quote_fuzz: int = 92

    rule_base: dict = field(default_factory=lambda: {
        "EXACT": 0.95,
        "ROUNDING": 0.90,
        "UNIT_SCALE": 0.80,
        "PERIOD": 0.90,
        "ESTIMATE_VINTAGE": 0.85,
        "SCOPE": 0.80,
        "BASIS": 0.80,
        "IDENTIFIER_REVISION": 0.75,
        "ATTRIBUTION": 0.60,
        "NONE": 0.70,
    })


@dataclass
class Config:
    root: Path = _ROOT
    db_path: Path = field(default_factory=lambda: _ROOT / os.environ.get("RLX_DB", "data/rlx.db"))
    pdf_dir: Path = field(default_factory=lambda: _ROOT / os.environ.get("RLX_PDF_DIR", "data/pdfs"))
    pagecache_dir: Path = field(default_factory=lambda: _ROOT / os.environ.get("RLX_PAGECACHE_DIR", "data/pagecache"))

    provider: str = os.environ.get("RLX_PROVIDER", "ollama")
    ollama_url: str = os.environ.get("RLX_OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.environ.get("RLX_OLLAMA_MODEL", "qwen2.5:7b-instruct")
    ollama_fallback_model: str = os.environ.get("RLX_OLLAMA_FALLBACK_MODEL", "phi3:latest")
    gemini_model: str = os.environ.get("RLX_GEMINI_MODEL", "gemini-2.0-flash")

    embeddings_enabled: bool = _b("RLX_EMBEDDINGS", False)
    replay_dir: Path = field(default_factory=lambda: _ROOT / "tests/fixtures/extractions")

    t: Thresholds = field(default_factory=Thresholds)

    def ensure_dirs(self) -> None:
        for d in (self.db_path.parent, self.pdf_dir, self.pagecache_dir):
            d.mkdir(parents=True, exist_ok=True)


CONFIG = Config()
