from __future__ import annotations

from typing import Protocol


class LLMUnavailable(RuntimeError):
    """Raised when a live provider cannot be reached. The pipeline catches this,
    marks the job 'paused_llm', keeps whatever was already extracted, and stays resumable."""


class Provider(Protocol):
    name: str

    def available(self) -> bool: ...

    def complete_json(self, system: str, user: str, *, schema: dict | None = None,
                      repair_system: str | None = None) -> tuple[dict, str]:
        """Return (parsed_json_dict, raw_text). May raise LLMUnavailable."""
        ...
