"""Null provider - extracts nothing. Lets the full pipeline (parse, store, report,
deterministic layers) run and be tested with zero LLM of any kind."""
from __future__ import annotations


class NullProvider:
    name = "null"

    def available(self) -> bool:
        return True

    def complete_json(self, system: str, user: str, *, schema=None, repair_system=None):
        return {"facts": []}, '{"facts": []}'
