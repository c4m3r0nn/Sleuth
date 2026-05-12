"""Telegram bot notifications. Just an HTTP POST - no SDK dependency.

For long content, falls back to chunked messages (if the text fits in a
few sends) or a sendDocument attachment (if it's bigger than that). The
runner-facing helper `notify_run_finished` in sleuth.notify.__init__
picks the right strategy automatically.
"""

from __future__ import annotations

import httpx

from sleuth.config import get_settings
from sleuth.notify.chunking import (
    TELEGRAM_LIMIT,
    should_attach_as_file,
    split_for_messenger,
)


class NotifyError(RuntimeError):
    pass


def is_telegram_configured() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_chat_id)


def _post(url: str, *, json=None, data=None, files=None) -> httpx.Response:
    try:
        return httpx.post(url, json=json, data=data, files=files, timeout=30.0)
    except httpx.HTTPError as e:
        raise NotifyError(f"Telegram request failed: {e}") from e


def _send_single(
    text: str, *, parse_mode: str | None = "Markdown", silent: bool = False,
) -> None:
    s = get_settings()
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": s.telegram_chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "disable_notification": silent,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    r = _post(url, json=payload)
    if r.status_code >= 400:
        raise NotifyError(f"Telegram error {r.status_code}: {r.text[:200]}")


def send_telegram_document(
    content: bytes,
    *,
    filename: str = "findings.md",
    caption: str | None = None,
    silent: bool = False,
) -> None:
    """Upload `content` as a Telegram document attachment."""
    s = get_settings()
    if not is_telegram_configured():
        raise NotifyError(
            "Telegram is not set up. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env."
        )
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendDocument"
    data: dict = {
        "chat_id": s.telegram_chat_id,
        "disable_notification": "true" if silent else "false",
    }
    if caption:
        data["caption"] = caption[:1024]  # Telegram cap for captions
    files = {"document": (filename, content, "text/markdown")}
    r = _post(url, data=data, files=files)
    if r.status_code >= 400:
        raise NotifyError(f"Telegram error {r.status_code}: {r.text[:200]}")


def send_telegram(
    text: str,
    *,
    parse_mode: str = "Markdown",
    silent: bool = False,
) -> None:
    """Send a Telegram message. Auto-handles long content.

    - Short (≤ 4096 chars): one sendMessage call with the given parse_mode.
    - Medium (a few message-widths): chunked sendMessage calls. The first
      chunk keeps parse_mode; later chunks drop it so unescaped Markdown
      in long bodies doesn't blow up Telegram's parser.
    - Long (would need many chunks): single sendDocument attachment with
      a short caption.
    """
    if not is_telegram_configured():
        raise NotifyError(
            "Telegram is not set up. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env."
        )

    text = text or ""
    if len(text) <= TELEGRAM_LIMIT:
        _send_single(text, parse_mode=parse_mode, silent=silent)
        return

    if should_attach_as_file(text, per_message_limit=TELEGRAM_LIMIT, max_messages=3):
        send_telegram_document(
            text.encode("utf-8"),
            filename="findings.md",
            caption="(full content attached — exceeds Telegram's per-message cap)",
            silent=silent,
        )
        return

    # Medium: chunk and send sequentially.
    chunks = split_for_messenger(text, limit=TELEGRAM_LIMIT)
    for i, chunk in enumerate(chunks):
        # First chunk: keep parse_mode (likely contains the header).
        # Subsequent chunks: drop parse_mode to avoid escape issues.
        _send_single(
            chunk,
            parse_mode=parse_mode if i == 0 else None,
            silent=silent,
        )
