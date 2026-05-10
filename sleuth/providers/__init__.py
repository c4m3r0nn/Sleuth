"""Provider registry."""

from __future__ import annotations

from typing import Type

from sleuth.providers.base import Provider, ResearchResult, Citation
from sleuth.providers.openai_p import OpenAIProvider
from sleuth.providers.anthropic_p import AnthropicProvider
from sleuth.providers.google_p import GoogleProvider


PROVIDERS: dict[str, Type[Provider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
}


# Curated, accurate as of 2026-05-10. Each entry is (model_id, blurb).
MODEL_CATALOG: dict[str, list[tuple[str, str]]] = {
    "openai": [
        ("gpt-5.5", "frontier, fast - default"),
        ("gpt-5.5-pro", "frontier with deeper reasoning, slower & pricier"),
        ("gpt-5.4", "previous frontier, still solid"),
        ("gpt-5.4-mini", "cheap & quick"),
        ("gpt-5-nano", "tiny, very cheap"),
        ("o3", "reasoning-heavy o-series"),
        ("o3-pro", "reasoning at depth, pricey"),
    ],
    "anthropic": [
        ("claude-opus-4-7", "frontier - 1M ctx"),
        ("claude-sonnet-4-6", "balanced workhorse"),
        ("claude-haiku-4-5", "small, snappy"),
    ],
    "google": [
        ("gemini-3.1-pro-preview", "frontier preview"),
        ("gemini-3-flash-preview", "fast frontier"),
        ("gemini-3.1-flash-lite", "GA, cheap"),
        ("gemini-2.5-pro", "previous gen, still grounded"),
    ],
}


def provider_for_model(model: str) -> str:
    """Best-effort guess of provider given a bare model id."""
    m = model.lower()
    if m.startswith("gpt") or m.startswith("o3") or m.startswith("o1"):
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "google"
    raise ValueError(f"Cannot infer provider for model '{model}'.")


def get_provider(name: str) -> Provider:
    name = name.lower()
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider '{name}'. Try one of: {', '.join(PROVIDERS)}."
        )
    return PROVIDERS[name]()


__all__ = [
    "Provider",
    "ResearchResult",
    "Citation",
    "PROVIDERS",
    "MODEL_CATALOG",
    "provider_for_model",
    "get_provider",
]
