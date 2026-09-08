"""Replay provider - returns bundled, hand-verified extractions instead of calling a
model. Every returned fact still carries a verbatim `quote` that the quote guard
re-checks against the freshly parsed PDF, so a wrong quote self-rejects.

Purpose: reproduce the documented four cases and run the full pipeline offline with
zero external dependencies (no Ollama, no key, ₹0). Fixtures live in
tests/fixtures/extractions/<doc-slug>.json:

  {"title_contains": "earnings", "pages": {"5": [ {rawfact...}, ... ], "16": [...]}}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ...config import CONFIG

_TITLE_RE = re.compile(r"^Document:\s*(.+)$", re.MULTILINE)
_PAGE_RE = re.compile(r"PDF page\s+(\d+)")


class ReplayProvider:
    name = "replay"

    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory or CONFIG.replay_dir)
        self._fixtures: list[dict] = []
        self._served: set[tuple[str, str]] = set()  # (title_contains, page) served once
        if self.dir.exists():
            for fp in sorted(self.dir.glob("*.json")):
                try:
                    self._fixtures.append(json.loads(fp.read_text(encoding="utf-8")))
                except Exception:  # noqa: BLE001
                    continue

    def available(self) -> bool:
        return True

    def _lookup(self, title: str, page: str) -> list[dict]:
        tl = (title or "").lower()
        for fx in self._fixtures:
            tc = fx.get("title_contains", "").lower()
            if tc and tc in tl:
                key = (tc, str(page))
                if key in self._served:      # each page's facts are served exactly once
                    return []
                self._served.add(key)
                return fx.get("pages", {}).get(str(page), [])
        return []

    def complete_json(self, system: str, user: str, *, schema=None, repair_system=None):
        mt = _TITLE_RE.search(user or "")
        mp = _PAGE_RE.search(user or "")
        title = mt.group(1).strip() if mt else ""
        page = mp.group(1) if mp else ""
        facts = self._lookup(title, page)
        obj = {"facts": facts}
        return obj, json.dumps(obj)
