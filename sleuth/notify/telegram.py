"""Telegram bot notifications. Just an HTTP POST - no SDK dependency."""

from __future__ import annotations

import httpx

from sleuth.config import get_settings


class NotifyError(RuntimeError):
    pass


def is_telegram_configured() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_chat_id)


def send_telegram(text: str, *, parse_mode: str = "Markdown", silent: bool = False) -> None:
    s = get_settings()
    if not is_telegram_configured():
        raise NotifyError(
            "Telegram is not set up. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env."
        )
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": s.telegram_chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
        "disable_notification": silent,
    }
    try:
        r = httpx.post(url, json=payload, timeout=20.0)
    except httpx.HTTPError as e:
        raise NotifyError(f"Telegram request failed: {e}") from e
    if r.status_code >= 400:
        raise NotifyError(f"Telegram error {r.status_code}: {r.text[:200]}")
