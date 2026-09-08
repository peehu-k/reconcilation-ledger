"""Ollama provider - local, free, no API key. Default.

Uses stdlib urllib (no extra dependency). Sends the JSON schema for constrained
decoding, temperature 0 + fixed seed for determinism. Picks the configured model,
falling back to any pulled instruct-capable model so the project works out of the box.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ...config import CONFIG
from ..jsonio import loads_lenient
from .base import LLMUnavailable

_TIMEOUT = int(os.environ.get("RLX_OLLAMA_TIMEOUT", "600"))
# schema-constrained decoding is highest fidelity but builds a slow GBNF grammar on
# CPU; plain JSON mode + Pydantic validation + the repair loop is the practical default.
_STRICT_SCHEMA = os.environ.get("RLX_OLLAMA_STRICT_SCHEMA", "0").strip().lower() in {"1", "true", "yes"}


class OllamaProvider:
    name = "ollama"

    def __init__(self, url: str | None = None, model: str | None = None):
        self.url = (url or CONFIG.ollama_url).rstrip("/")
        self._model = model or CONFIG.ollama_model
        self._resolved: str | None = None

    # -------------------------------------------------------------- infra
    def _get(self, path: str) -> dict:
        try:
            with urllib.request.urlopen(self.url + path, timeout=5) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailable(f"Ollama not reachable at {self.url}: {e}") from e

    def _tags(self) -> list[str]:
        return [m["name"] for m in self._get("/api/tags").get("models", [])]

    def available(self) -> bool:
        try:
            self._tags()
            return True
        except LLMUnavailable:
            return False

    def model(self) -> str:
        if self._resolved:
            return self._resolved
        tags = self._tags()
        for cand in (self._model, CONFIG.ollama_fallback_model):
            if cand in tags:
                self._resolved = cand
                return cand
        # last resort: any non-embedding model that is not obviously code-only
        prefer = [t for t in tags if not any(k in t for k in ("embed", "code", "coder"))]
        self._resolved = (prefer or tags or [self._model])[0]
        return self._resolved

    def _chat(self, messages: list[dict], schema: dict | None) -> str:
        body = {
            "model": self.model(),
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0, "seed": 7, "num_ctx": 8192},
            "format": (schema if (schema and _STRICT_SCHEMA) else "json"),
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(self.url + "/api/chat", data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                payload = json.loads(r.read())
        except urllib.error.URLError as e:
            raise LLMUnavailable(f"Ollama chat failed: {e}") from e
        except TimeoutError as e:
            raise LLMUnavailable(f"Ollama chat timed out after {_TIMEOUT}s") from e
        return payload.get("message", {}).get("content", "")

    # -------------------------------------------------------------- api
    def complete_json(self, system: str, user: str, *, schema=None, repair_system=None):
        raw = self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            schema,
        )
        try:
            return loads_lenient(raw), raw
        except Exception as first_err:  # noqa: BLE001
            if not repair_system:
                raise
            raw2 = self._chat(
                [{"role": "system", "content": repair_system.format(error=str(first_err)[:300])},
                 {"role": "user", "content": raw[:6000] or user}],
                schema,
            )
            return loads_lenient(raw2), raw2
