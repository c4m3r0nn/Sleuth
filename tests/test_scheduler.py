"""build_schedule maps friendly grammar to cron expressions."""

import pytest

from sleuth.scheduler import build_schedule


class TestDaily:
    def test_basic(self):
        spec = build_schedule(daily="09:00")
        assert spec.cron_expr == "0 9 * * *"
        assert "daily" in spec.label

    def test_late(self):
        spec = build_schedule(daily="23:45")
        assert spec.cron_expr == "45 23 * * *"

    @pytest.mark.parametrize("bad", ["9", "25:00", "09:60", "x:y", ""])
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            build_schedule(daily=bad)


class TestWeekly:
    def test_single_day(self):
        spec = build_schedule(weekly_days="mon", weekly_at="09:00")
        assert spec.cron_expr == "0 9 * * 1"

    def test_multi_days(self):
        spec = build_schedule(weekly_days="mon,wed,fri", weekly_at="18:30")
        assert spec.cron_expr == "30 18 * * 1,3,5"

    def test_unknown_day(self):
        with pytest.raises(ValueError):
            build_schedule(weekly_days="funday", weekly_at="09:00")

    def test_missing_at(self):
        with pytest.raises(ValueError):
            build_schedule(weekly_days="mon")


class TestEveryHourlyMonthly:
    def test_hourly(self):
        spec = build_schedule(hourly=True)
        assert spec.cron_expr == "0 * * * *"

    def test_every_minutes(self):
        spec = build_schedule(every="15m")
        assert spec.cron_expr == "*/15 * * * *"

    def test_every_hours(self):
        spec = build_schedule(every="2h")
        assert spec.cron_expr == "0 */2 * * *"

    @pytest.mark.parametrize("bad", ["", "0m", "60m", "0h", "24h", "abc", "5x"])
    def test_every_bad(self, bad):
        with pytest.raises(ValueError):
            build_schedule(every=bad)

    def test_monthly(self):
        spec = build_schedule(monthly_day=1, monthly_at="06:00")
        assert spec.cron_expr == "0 6 1 * *"

    def test_monthly_day_clamp(self):
        with pytest.raises(ValueError):
            build_schedule(monthly_day=31, monthly_at="06:00")

    def test_raw_cron_passthrough(self):
        spec = build_schedule(raw_cron="*/30 9-17 * * 1-5")
        assert spec.cron_expr == "*/30 9-17 * * 1-5"

    def test_no_args_explodes(self):
        with pytest.raises(ValueError):
            build_schedule()
