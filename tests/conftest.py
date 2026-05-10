"""Shared fixtures. Each test gets its own tmp data dir + fresh singletons."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch, tmp_path: Path):
    """Point sleuth at a fresh tmp dir and forget any cached singletons."""
    # Steer all paths at the tmp dir.
    monkeypatch.setenv("SLEUTH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SLEUTH_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("SLEUTH_LOG_DIR", str(tmp_path / "logs"))

    # Wipe any provider keys that may be lingering in the test runner's env
    # so we don't accidentally hit a real API.
    for var in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "DISCORD_WEBHOOK_URL",
    ):
        monkeypatch.delenv(var, raising=False)

    # Force pydantic-settings to ignore any real .env file in the project.
    import sleuth.config as cfg

    monkeypatch.setitem(
        cfg.Settings.model_config, "env_file", str(tmp_path / "nope.env")
    )

    # Reset module-level singletons.
    cfg._settings = None
    import sleuth.storage.sqlite_store as store_mod
    store_mod._store = None

    yield

    # Tear down singletons so the next test gets a clean slate.
    cfg._settings = None
    store_mod._store = None


@pytest.fixture
def store(isolate_settings):
    from sleuth.storage import get_store
    return get_store()


@pytest.fixture
def settings(isolate_settings):
    from sleuth.config import get_settings
    return get_settings()
