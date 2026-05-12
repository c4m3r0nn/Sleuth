"""Discord webhook notifications. Just an HTTP POST.

Mirrors the telegram module's behaviour for long content: short → one
message, medium → chunked messages, long → file attachment via the
webhook's multipart form path.
"""

from __future__ import annotations

import json

import httpx

from sleuth.config import get_settings
from sleuth.notify.chunking import (
    DISCORD_LIMIT,
    should_attach_as_file,
    split_for_messenger,
)
from sleuth.notify.telegram import NotifyError


def is_discord_configured() -> bool:
    return bool(get_settings().discord_webhook_url)


def _post(url: str, *, json_body=None, data=None, files=None) -> httpx.Response:
    try:
        return httpx.post(
            url,
            json=json_body if files is None else None,
            data=data,
            files=files,
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        raise NotifyError(f"Discord request failed: {e}") from e


def _send_single(text: str, *, username: str | None = "sleuth") -> None:
    s = get_settings()
    payload: dict = {"content": text[:DISCORD_LIMIT]}
    if username:
        payload["username"] = username
    r = _post(s.discord_webhook_url, json_body=payload)
    if r.status_code >= 400:
        raise NotifyError(f"Discord error {r.status_code}: {r.text[:200]}")


def send_discord_document(
    content: bytes,
    *,
    filename: str = "findings.md",
    caption: str | None = None,
    username: str | None = "sleuth",
) -> None:
    """Upload `content` to the Discord webhook as a file attachment."""
    s = get_settings()
    if not is_discord_configured():
        raise NotifyError(
            "Discord is not set up. Set DISCORD_WEBHOOK_URL in .env."
        )
    payload: dict = {}
    if caption:
        payload["content"] = caption[:DISCORD_LIMIT]
    if username:
        payload["username"] = username
    data = {"payload_json": json.dumps(payload)}
    files = {"files[0]": (filename, content, "text/markdown")}
    r = _post(s.discord_webhook_url, data=data, files=files)
    if r.status_code >= 400:
        raise NotifyError(f"Discord error {r.status_code}: {r.text[:200]}")


def send_discord(text: str, *, username: str | None = "sleuth") -> None:
    """Send a Discord webhook message. Auto-handles long content."""
    if not is_discord_configured():
        raise NotifyError(
            "Discord is not set up. Set DISCORD_WEBHOOK_URL in .env."
        )

    text = text or ""
    if len(text) <= DISCORD_LIMIT:
        _send_single(text, username=username)
        return

    if should_attach_as_file(text, per_message_limit=DISCORD_LIMIT, max_messages=3):
        send_discord_document(
            text.encode("utf-8"),
            filename="findings.md",
            caption="(full content attached — exceeds Discord's per-message cap)",
            username=username,
        )
        return

    for chunk in split_for_messenger(text, limit=DISCORD_LIMIT):
        _send_single(chunk, username=username)
