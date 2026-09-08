"""LLM provider registry. All providers are free; none require a key by default."""
from __future__ import annotations

from ...config import CONFIG
from .base import LLMUnavailable, Provider  # noqa: F401


def get_provider(name: str | None = None) -> Provider:
    name = (name or CONFIG.provider or "ollama").lower()
    if name == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider()
    if name == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider()
    if name == "replay":
        from .replay import ReplayProvider
        return ReplayProvider()
    if name in ("null", "none", "off"):
        from .null import NullProvider
        return NullProvider()
    raise ValueError(f"unknown provider: {name}")
