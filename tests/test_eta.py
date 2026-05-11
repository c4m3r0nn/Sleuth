"""next_run_utc + humanize_delta — pure helpers for scheduling display."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest


UTC = timezone.utc
LON = ZoneInfo("Europe/London")
NYC = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------- #
# next_run_utc
# --------------------------------------------------------------------------- #


class TestNextRunUtc:
    def test_daily_returns_today_at_time_if_in_future(self):
        from sleuth.scheduler.eta import next_run_utc
        now = datetime(2026, 5, 11, 8, 0, tzinfo=UTC)
        nxt = next_run_utc("0 9 * * *", now=now, tz="UTC")
        assert nxt == datetime(2026, 5, 11, 9, 0, tzinfo=UTC)

    def test_daily_returns_tomorrow_if_today_passed(self):
        from sleuth.scheduler.eta import next_run_utc
        now = datetime(2026, 5, 11, 10, 0, tzinfo=UTC)
        nxt = next_run_utc("0 9 * * *", now=now, tz="UTC")
        assert nxt == datetime(2026, 5, 12, 9, 0, tzinfo=UTC)

    def test_weekly_monday(self):
        # Tuesday 2026-05-12; next Monday is 2026-05-18.
        from sleuth.scheduler.eta import next_run_utc
        now = datetime(2026, 5, 12, 0, 0, tzinfo=UTC)
        nxt = next_run_utc("0 9 * * 1", now=now, tz="UTC")
        assert nxt == datetime(2026, 5, 18, 9, 0, tzinfo=UTC)

    def test_hourly(self):
        from sleuth.scheduler.eta import next_run_utc
        now = datetime(2026, 5, 11, 8, 30, tzinfo=UTC)
        nxt = next_run_utc("0 * * * *", now=now, tz="UTC")
        assert nxt == datetime(2026, 5, 11, 9, 0, tzinfo=UTC)

    def test_every_15_minutes(self):
        from sleuth.scheduler.eta import next_run_utc
        now = datetime(2026, 5, 11, 8, 31, tzinfo=UTC)
        nxt = next_run_utc("*/15 * * * *", now=now, tz="UTC")
        assert nxt == datetime(2026, 5, 11, 8, 45, tzinfo=UTC)

    def test_monthly(self):
        from sleuth.scheduler.eta import next_run_utc
        now = datetime(2026, 5, 11, 0, 0, tzinfo=UTC)
        nxt = next_run_utc("0 6 1 * *", now=now, tz="UTC")
        assert nxt == datetime(2026, 6, 1, 6, 0, tzinfo=UTC)

    def test_empty_returns_none(self):
        from sleuth.scheduler.eta import next_run_utc
        assert next_run_utc("") is None
        assert next_run_utc(None) is None

    def test_invalid_expression_raises(self):
        from sleuth.scheduler.eta import next_run_utc
        with pytest.raises(ValueError):
            next_run_utc("not a valid expression")

    def test_local_tz_converts_to_utc(self):
        """Cron is interpreted in local tz - we display the UTC equivalent.

        Europe/London on 2026-05-11 is BST (UTC+1). A "09:00 daily" entry
        fires at 09:00 BST = 08:00 UTC.
        """
        from sleuth.scheduler.eta import next_run_utc
        now = datetime(2026, 5, 11, 7, 30, tzinfo=UTC)  # 08:30 BST
        nxt = next_run_utc("0 9 * * *", now=now, tz="Europe/London")
        # next fire is 09:00 BST same day = 08:00 UTC
        assert nxt == datetime(2026, 5, 11, 8, 0, tzinfo=UTC)

    def test_nyc_tz(self):
        """Same idea, far side of the world. NYC is EDT (UTC-4) on this date."""
        from sleuth.scheduler.eta import next_run_utc
        now = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)  # 08:00 EDT
        nxt = next_run_utc("0 9 * * *", now=now, tz="America/New_York")
        # next is 09:00 EDT same day = 13:00 UTC
        assert nxt == datetime(2026, 5, 11, 13, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# humanize_delta
# --------------------------------------------------------------------------- #


class TestHumanizeDelta:
    def test_seconds(self):
        from sleuth.scheduler.eta import humanize_delta
        assert humanize_delta(timedelta(seconds=5)) == "in 5s"
        assert humanize_delta(timedelta(seconds=59)) == "in 59s"

    def test_minutes(self):
        from sleuth.scheduler.eta import humanize_delta
        assert humanize_delta(timedelta(minutes=1)) == "in 1m"
        assert humanize_delta(timedelta(minutes=45)) == "in 45m"

    def test_hours(self):
        from sleuth.scheduler.eta import humanize_delta
        assert humanize_delta(timedelta(hours=1, minutes=30)) == "in 1h 30m"
        assert humanize_delta(timedelta(hours=23, minutes=59)) == "in 23h 59m"

    def test_days(self):
        from sleuth.scheduler.eta import humanize_delta
        assert humanize_delta(timedelta(days=1, hours=2)) == "in 1d 2h"
        assert humanize_delta(timedelta(days=6, hours=21)) == "in 6d 21h"

    def test_zero(self):
        from sleuth.scheduler.eta import humanize_delta
        assert humanize_delta(timedelta(0)) == "now"

    def test_negative_says_overdue(self):
        from sleuth.scheduler.eta import humanize_delta
        # cron is fixed-fire, but if our 'now' is somehow past the next fire
        # (clock skew, weird state) we should not crash with a negative.
        assert humanize_delta(timedelta(seconds=-5)) == "overdue"


# --------------------------------------------------------------------------- #
# convenience pair
# --------------------------------------------------------------------------- #


class TestFormatNextRun:
    def test_full_line_for_jobs_show(self):
        """The user-facing string used by `jobs show`."""
        from sleuth.scheduler.eta import format_next_run
        # Tuesday at 00:00 UTC. Cron 'Monday 09:00' fires next Monday.
        now = datetime(2026, 5, 12, 0, 0, tzinfo=UTC)
        line = format_next_run("0 9 * * 1", now=now, tz="UTC")
        assert "2026-05-18 09:00:00 UTC" in line
        assert line.endswith(")")
        assert "in " in line
        assert "6d" in line  # 6 days from Tue 00:00 to Mon 09:00 = 6d 9h

    def test_format_when_today_still_to_fire(self):
        """If the cron fires later today, the line should reflect 'in Xh Ym'."""
        from sleuth.scheduler.eta import format_next_run
        # Monday at 00:00 UTC. 'Monday 09:00' fires today at 09:00.
        now = datetime(2026, 5, 11, 0, 0, tzinfo=UTC)
        line = format_next_run("0 9 * * 1", now=now, tz="UTC")
        assert "2026-05-11 09:00:00 UTC" in line
        assert "in 9h" in line

    def test_unscheduled_returns_dash(self):
        from sleuth.scheduler.eta import format_next_run
        assert format_next_run("") == "-"
        assert format_next_run(None) == "-"

    def test_invalid_returns_error_marker(self):
        from sleuth.scheduler.eta import format_next_run
        # we don't want jobs show to crash on garbage; format swallows it
        assert format_next_run("not a cron") == "(invalid cron expression)"
