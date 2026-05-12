"""Chunk long text into messenger-sized pieces, respecting boundaries."""

import pytest


class TestSplitForMessenger:
    def test_empty_returns_empty_list(self):
        from sleuth.notify.chunking import split_for_messenger
        assert split_for_messenger("", limit=100) == []
        assert split_for_messenger("   ", limit=100) == []

    def test_short_returns_one_chunk(self):
        from sleuth.notify.chunking import split_for_messenger
        chunks = split_for_messenger("hello world", limit=100)
        assert chunks == ["hello world"]

    def test_each_chunk_within_limit(self):
        from sleuth.notify.chunking import split_for_messenger
        text = "A paragraph.\n\n" * 200
        chunks = split_for_messenger(text, limit=500)
        for c in chunks:
            assert len(c) <= 500

    def test_prefers_paragraph_breaks(self):
        from sleuth.notify.chunking import split_for_messenger
        # Three paragraphs, each fits, total exceeds limit
        text = "a" * 90 + "\n\n" + "b" * 90 + "\n\n" + "c" * 90
        chunks = split_for_messenger(text, limit=100)
        # We should NOT break inside a paragraph; we should see three
        # chunks roughly aligned to paragraph boundaries.
        assert len(chunks) == 3
        assert chunks[0].startswith("a")
        assert chunks[1].startswith("b")
        assert chunks[2].startswith("c")

    def test_falls_back_to_line_break(self):
        from sleuth.notify.chunking import split_for_messenger
        # No paragraph breaks; split on newlines
        text = "\n".join(["x" * 40] * 5)
        chunks = split_for_messenger(text, limit=100)
        for c in chunks:
            assert len(c) <= 100

    def test_falls_back_to_hard_split(self):
        from sleuth.notify.chunking import split_for_messenger
        # No newlines at all, just one giant line
        text = "z" * 250
        chunks = split_for_messenger(text, limit=100)
        assert len(chunks) >= 3
        for c in chunks:
            assert len(c) <= 100

    def test_preserves_content(self):
        """Concatenating chunks should give back the original (modulo trimming)."""
        from sleuth.notify.chunking import split_for_messenger
        text = "first paragraph here.\n\nsecond paragraph here.\n\nthird."
        chunks = split_for_messenger(text, limit=50)
        joined = "\n\n".join(c.strip() for c in chunks)
        # The original content (sans extra whitespace) should be recoverable.
        # We strip per-chunk because we trim chunk boundaries.
        for word in ("first paragraph here", "second paragraph here", "third"):
            assert word in joined

    def test_default_limits(self):
        from sleuth.notify.chunking import TELEGRAM_LIMIT, DISCORD_LIMIT
        # Sanity: these match the documented per-message caps.
        assert TELEGRAM_LIMIT == 4096
        assert DISCORD_LIMIT == 2000

    def test_attach_threshold(self):
        from sleuth.notify.chunking import should_attach_as_file
        short = "small"
        long_ = "x" * 50000
        assert should_attach_as_file(short, per_message_limit=4096, max_messages=3) is False
        assert should_attach_as_file(long_, per_message_limit=4096, max_messages=3) is True
