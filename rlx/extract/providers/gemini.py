"""Optional Gemini free-tier provider. Only used when RLX_PROVIDER=gemini AND
GEMINI_API_KEY is set. The project is fully functional without it."""
from __future__ import annotations

import json
import os
import urllib.request

from ...config import CONFIG
from ..jsonio import loads_lenient
from .base import LLMUnavailable

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str | None = None):
        self.model = model or CONFIG.gemini_model
        self.key = os.environ.get("GEMINI_API_KEY", "")

    def available(self) -> bool:
        return bool(self.key)

    def _call(self, system: str, user: str) -> str:
        if not self.key:
            raise LLMUnavailable("GEMINI_API_KEY not set")
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "response_mime_type": "application/json"},
        }
        url = _ENDPOINT.format(model=self.model, key=self.key)
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailable(f"Gemini request failed: {e}") from e
        return payload["candidates"][0]["content"]["parts"][0]["text"]

    def complete_json(self, system: str, user: str, *, schema=None, repair_system=None):
        raw = self._call(system, user)
        try:
            return loads_lenient(raw), raw
        except Exception as err:  # noqa: BLE001
            if not repair_system:
                raise
            raw2 = self._call(repair_system.format(error=str(err)[:300]), raw[:6000])
            return loads_lenient(raw2), raw2
