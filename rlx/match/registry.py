"""Link near-duplicate entity / attribute keys so that lexical variants the seed
lexicon missed still land in the same block. rapidfuzz first; optional embeddings
as a second signal. Every link is recorded (decided_by) so it is auditable."""
from __future__ import annotations

from rapidfuzz import fuzz

from ..config import CONFIG
from ..store import queries as Q
from . import embeddings as emb


def _fuzzy_link(candidate: str, known: list[str], threshold: int) -> tuple[str | None, float]:
    """Plain ratio + token_sort_ratio only. token_set_ratio is deliberately avoided:
    it scores a subset match ("delhivery" in "delhivery bangladesh logistics") as 100
    and would merge distinct entities."""
    best, best_s = None, 0.0
    for k in known:
        if k == candidate:
            return candidate, 100.0
        s = max(fuzz.ratio(candidate, k), fuzz.token_sort_ratio(candidate, k))
        if s > best_s:
            best, best_s = k, s
    if best_s >= threshold:
        return best, best_s
    return None, best_s


def resolve_attribute_key(conn, key: str, display: str, doc_id: int | None) -> str:
    known = Q.known_attribute_keys(conn)
    if key in known:
        return key
    linked, score = _fuzzy_link(key, known, CONFIG.t.attribute_fuzz)
    if not linked and CONFIG.embeddings_enabled and known:
        linked, score = emb.best_match(key, known, CONFIG.t.embedding_sim)
    if linked:
        Q.add_alias(conn, "attribute_registry", linked, key)
        return linked
    Q.upsert_attribute(conn, key, display, doc_id=doc_id)
    return key


def resolve_entity_key(conn, key: str, display: str, doc_id: int | None) -> str:
    known = Q.known_entity_keys(conn)
    if key in known:
        return key
    linked, score = _fuzzy_link(key, known, CONFIG.t.entity_fuzz)
    if linked:
        Q.add_alias(conn, "entity_registry", linked, key)
        return linked
    Q.upsert_entity(conn, key, display, doc_id=doc_id)
    return key
