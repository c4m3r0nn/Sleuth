"""Split long text into messenger-friendly chunks, respecting boundaries."""

from __future__ import annotations

from typing import Iterable


# Per-message character caps for the messengers we support.
TELEGRAM_LIMIT = 4096
DISCORD_LIMIT = 2000


def split_for_messenger(text: str, *, limit: int) -> list[str]:
    """Break `text` into chunks each ≤ `limit` chars.

    Prefers paragraph boundaries (``\\n\\n``), then line breaks (``\\n``),
    finally falls back to hard character splits. Returns ``[]`` for empty
    input.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    # Greedy packer: keep adding paragraphs/lines/chars to the current chunk
    # until adding the next unit would exceed the limit.
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.rstrip())
        current = ""

    for paragraph in text.split("\n\n"):
        unit = paragraph
        # If the paragraph itself is too big, fall through to per-line.
        if len(unit) > limit:
            flush()
            chunks.extend(_split_on_lines(unit, limit=limit))
            continue
        # Can we tack this paragraph onto current?
        sep = "\n\n" if current else ""
        if len(current) + len(sep) + len(unit) <= limit:
            current += sep + unit
        else:
            flush()
            current = unit
    flush()
    return chunks


def _split_on_lines(text: str, *, limit: int) -> list[str]:
    """Helper: split a too-large paragraph at line breaks, then chars."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        if len(line) > limit:
            # Even a single line is too long; flush and hard-split.
            if current.strip():
                chunks.append(current.rstrip())
                current = ""
            chunks.extend(_hard_split(line, limit=limit))
            continue
        sep = "\n" if current else ""
        if len(current) + len(sep) + len(line) <= limit:
            current += sep + line
        else:
            if current.strip():
                chunks.append(current.rstrip())
            current = line
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def _hard_split(text: str, *, limit: int) -> list[str]:
    """Last resort: chop a long unbroken string every `limit` chars."""
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def should_attach_as_file(
    text: str, *, per_message_limit: int, max_messages: int = 3
) -> bool:
    """True if the text would exceed `max_messages` chunks at this limit.

    Use this to decide whether to send as a document instead of a flood of
    follow-up messages.
    """
    if not text:
        return False
    return len(text) > per_message_limit * max_messages
