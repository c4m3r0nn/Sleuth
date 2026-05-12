from typing import Iterable, Optional

from sleuth.notify.telegram import (
    send_telegram,
    send_telegram_document,
    is_telegram_configured,
    NotifyError,
)
from sleuth.notify.discord import (
    send_discord,
    send_discord_document,
    is_discord_configured,
)
from sleuth.notify.chunking import (
    DISCORD_LIMIT,
    TELEGRAM_LIMIT,
    should_attach_as_file,
)


def notify_all(
    text: str,
    *,
    channels: Iterable[str] = ("telegram", "discord"),
    silent: bool = False,
) -> list[str]:
    """Best-effort fan-out. Skips unconfigured channels, swallows per-channel errors.

    Returns the list of channels that were actually delivered to.
    """
    delivered: list[str] = []
    for ch in channels:
        try:
            if ch == "telegram" and is_telegram_configured():
                send_telegram(text, silent=silent)
                delivered.append("telegram")
            elif ch == "discord" and is_discord_configured():
                send_discord(text)
                delivered.append("discord")
        except NotifyError:
            # Don't let one notifier failure block others; the runner will
            # surface the issue elsewhere if it cares.
            continue
    return delivered


def _telegram_header(provider: str, model: str, prompt: str, gdrive_url: Optional[str]) -> str:
    lines = [
        f"*sleuth* done — `{provider}/{model}`",
        "",
        f"_{prompt[:200]}_",
    ]
    if gdrive_url:
        lines.append("")
        lines.append(f"[doc]({gdrive_url})")
    return "\n".join(lines)


def _discord_header(provider: str, model: str, prompt: str, gdrive_url: Optional[str]) -> str:
    lines = [
        f"**sleuth** done — `{provider}/{model}`",
        f"_{prompt[:200]}_",
    ]
    if gdrive_url:
        lines.append(f"<{gdrive_url}>")
    return "\n".join(lines)


def notify_run_finished(
    *,
    provider: str,
    model: str,
    prompt: str,
    body: str,
    gdrive_url: Optional[str] = None,
) -> list[str]:
    """Send the full body of a finished run to every configured channel.

    Picks the right shape automatically:
    - short body fits in one message → header + body together
    - medium body → header message, then body chunked across follow-ups
    - very long body → header (as caption) + .md file attachment
    """
    delivered: list[str] = []
    body = body or ""

    # --- telegram ---
    if is_telegram_configured():
        try:
            tg_header = _telegram_header(provider, model, prompt, gdrive_url)
            if not body:
                send_telegram(tg_header)
            elif len(tg_header) + len(body) + 2 <= TELEGRAM_LIMIT:
                # Header + body fit in a single message.
                # Body goes inside a fenced block so its content doesn't fight
                # with Markdown parsing.
                send_telegram(f"{tg_header}\n\n{body}")
            elif should_attach_as_file(body, per_message_limit=TELEGRAM_LIMIT, max_messages=3):
                # Send the header on its own, then attach the body as a file.
                send_telegram(tg_header)
                send_telegram_document(
                    body.encode("utf-8"),
                    filename="findings.md",
                    caption=None,
                )
            else:
                # Header in markdown, body chunked in plain text.
                send_telegram(tg_header)
                send_telegram(body, parse_mode="")  # parse_mode="" -> falsy -> dropped
            delivered.append("telegram")
        except NotifyError:
            pass

    # --- discord ---
    if is_discord_configured():
        try:
            dc_header = _discord_header(provider, model, prompt, gdrive_url)
            if not body:
                send_discord(dc_header)
            elif len(dc_header) + len(body) + 2 <= DISCORD_LIMIT:
                send_discord(f"{dc_header}\n\n{body}")
            elif should_attach_as_file(body, per_message_limit=DISCORD_LIMIT, max_messages=3):
                send_discord(dc_header)
                send_discord_document(
                    body.encode("utf-8"),
                    filename="findings.md",
                    caption=None,
                )
            else:
                send_discord(dc_header)
                send_discord(body)
            delivered.append("discord")
        except NotifyError:
            pass

    return delivered


__all__ = [
    "send_telegram",
    "send_telegram_document",
    "is_telegram_configured",
    "send_discord",
    "send_discord_document",
    "is_discord_configured",
    "notify_all",
    "notify_run_finished",
    "NotifyError",
]
