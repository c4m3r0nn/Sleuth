"""Provider registry helpers (the parts that don't need network)."""

import pytest

from sleuth.providers import provider_for_model, MODEL_CATALOG, PROVIDERS


@pytest.mark.parametrize(
    "model, expected",
    [
        ("gpt-5.5", "openai"),
        ("gpt-5.5-pro", "openai"),
        ("gpt-4.1-mini", "openai"),
        ("o3", "openai"),
        ("o3-pro", "openai"),
        ("claude-opus-4-7", "anthropic"),
        ("claude-haiku-4-5", "anthropic"),
        ("gemini-3.1-pro-preview", "google"),
        ("gemini-2.5-flash", "google"),
        # case-insensitive
        ("GPT-5.5", "openai"),
        ("Claude-Opus-4-7", "anthropic"),
    ],
)
def test_provider_for_model(model, expected):
    assert provider_for_model(model) == expected


def test_unknown_model_raises():
    with pytest.raises(ValueError):
        provider_for_model("mistral-medium")


def test_catalog_covers_all_providers():
    assert set(MODEL_CATALOG.keys()) == set(PROVIDERS.keys())
    for prov, items in MODEL_CATALOG.items():
        assert items, f"{prov} catalog is empty"
        for mid, blurb in items:
            assert isinstance(mid, str) and mid
            assert isinstance(blurb, str) and blurb
