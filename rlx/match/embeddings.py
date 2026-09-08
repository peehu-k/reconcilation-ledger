"""Optional local sentence embeddings for fuzzy attribute linking.

Guarded import: if sentence-transformers / numpy are absent or RLX_EMBEDDINGS=0,
every function degrades to "no signal" and the system relies on lexical + rapidfuzz.
Never a hard dependency for correctness.
"""
from __future__ import annotations

import hashlib

_MODEL = None
_OK = None


def _available() -> bool:
    global _OK
    if _OK is None:
        try:
            import numpy  # noqa: F401
            import sentence_transformers  # noqa: F401
            _OK = True
        except Exception:
            _OK = False
    return _OK


def _model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _MODEL


def embed(text: str):
    if not _available():
        return None
    import numpy as np
    v = _model().encode([text], normalize_embeddings=True)[0]
    return np.asarray(v, dtype="float32")


def best_match(candidate: str, known: list[str], threshold: float) -> tuple[str | None, float]:
    if not _available() or not known:
        return None, 0.0
    import numpy as np
    cv = embed(candidate)
    if cv is None:
        return None, 0.0
    kv = _model().encode(known, normalize_embeddings=True)
    sims = np.asarray(kv, dtype="float32") @ cv
    i = int(sims.argmax())
    return (known[i], float(sims[i])) if sims[i] >= threshold else (None, float(sims[i]))


def cache_key(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()
