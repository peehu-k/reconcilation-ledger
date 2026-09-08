"""Candidate-pair generation.

Facts only compare within the same (entity_key, attribute_key) block, so the work
is O(k^2) per block, not O(N^2). Large blocks are sub-grouped by period first.
Incremental: when a new document arrives we only build pairs that involve at least
one new fact.
"""
from __future__ import annotations

from itertools import combinations

from ..store.models import Fact

MAX_BLOCK = 60


def _key(f: Fact) -> tuple[str, str]:
    return (f.entity_key, f.attribute_key)


def candidate_pairs(facts: list[Fact], new_ids: set[int] | None = None):
    """Yield (a, b) Fact pairs worth reconciling.

    new_ids: if given, only pairs touching one of these fact ids are yielded
             (incremental mode)."""
    by_block: dict[tuple[str, str], list[Fact]] = {}
    for f in facts:
        by_block.setdefault(_key(f), []).append(f)

    for block, group in by_block.items():
        if len(group) < 2:
            continue
        if len(group) > MAX_BLOCK:
            # sub-block by period to bound the pair count
            subs: dict[str, list[Fact]] = {}
            for f in group:
                subs.setdefault(f.period_canonical or "∅", []).append(f)
            pools = list(subs.values()) + [group[:MAX_BLOCK]]
        else:
            pools = [group]

        seen: set[tuple[int, int]] = set()
        for pool in pools:
            for a, b in combinations(pool, 2):
                if a.id is None or b.id is None or a.id == b.id:
                    continue
                pair = tuple(sorted((a.id, b.id)))
                if pair in seen:
                    continue
                seen.add(pair)
                if new_ids is not None and not (a.id in new_ids or b.id in new_ids):
                    continue
                # identical facts (same content hash) -> skip, that's a dedup not a relation
                if a.content_hash and a.content_hash == b.content_hash:
                    continue
                yield a, b
