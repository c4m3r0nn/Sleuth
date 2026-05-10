"""Discord webhook notifications. Just an HTTP POST."""

from __future__ import annotations

import httpx

from sleuth.config import get_settings
from sleuth.notify.telegram import NotifyError


# Discord caps content at 2000 chars. We trim slightly under to leave room
# for any small additions the caller might make later.
DISCORD_MAX = 1990


def is_discord_configured() -> bool:
    return bool(get_settings().discord_webhook_url)


def send_discord(text: str, *, username: str | None = "sleuth") -> None:
    s = get_settings()
    if not is_discord_configured():
        raise NotifyError(
            "Discord is not set up. Set DISCORD_WEBHOOK_URL in .env."
        )
    payload: dict = {"content": text[:DISCORD_MAX]}
    if username:
        payload["username"] = username
    try:
        r = httpx.post(s.discord_webhook_url, json=payload, timeout=20.0)
    except httpx.HTTPError as e:
        raise NotifyError(f"Discord request failed: {e}") from e
    # Webhooks return 204 No Content on success.
    if r.status_code >= 400:
        raise NotifyError(f"Discord error {r.status_code}: {r.text[:200]}")
