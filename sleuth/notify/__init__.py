from typing import Iterable

from sleuth.notify.telegram import (
    send_telegram,
    is_telegram_configured,
    NotifyError,
)
from sleuth.notify.discord import (
    send_discord,
    is_discord_configured,
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


__all__ = [
    "send_telegram",
    "is_telegram_configured",
    "send_discord",
    "is_discord_configured",
    "notify_all",
    "NotifyError",
]
