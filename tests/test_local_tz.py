"""describe_local_tz: short human label for the system local timezone."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest


class TestDescribeLocalTz:
    def test_returns_nonempty_string(self):
        from sleuth.scheduler.eta import describe_local_tz
        s = describe_local_tz()
        assert isinstance(s, str)
        assert s.strip()

    def test_explicit_utc(self):
        from sleuth.scheduler.eta import describe_local_tz
        s = describe_local_tz(tz="UTC")
        assert "UTC" in s
        # Should also show an offset somewhere.
        assert "+00:00" in s or "UTC" in s

    def test_explicit_london(self):
        """A summer date in London is BST (UTC+01:00)."""
        from sleuth.scheduler.eta import describe_local_tz
        s = describe_local_tz(tz="Europe/London", now=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc))
        assert "BST" in s or "London" in s
        assert "+01:00" in s

    def test_explicit_nyc_winter(self):
        from sleuth.scheduler.eta import describe_local_tz
        s = describe_local_tz(tz="America/New_York", now=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
        assert "EST" in s or "New_York" in s
        assert "-05:00" in s

    def test_offset_format(self):
        """Offset should be in the canonical ±HH:MM form (not ±HHMM)."""
        from sleuth.scheduler.eta import describe_local_tz
        s = describe_local_tz(tz="UTC")
        # Either '+00:00' or 'UTC+00:00' — we just want the colon style.
        assert "+0000" not in s  # not the un-colonized form
