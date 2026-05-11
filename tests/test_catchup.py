"""Catch-up detection: did we miss the most recent scheduled fire?"""

from datetime import datetime, timedelta, timezone

import pytest


UTC = timezone.utc


# --------------------------------------------------------------------------- #
# previous_fire_utc — utility used by needs_catchup
# --------------------------------------------------------------------------- #


class TestPreviousFireUtc:
    def test_daily_returns_today_if_passed(self):
        from sleuth.scheduler.catchup import previous_fire_utc
        now = datetime(2026, 5, 11, 14, 0, tzinfo=UTC)
        prev = previous_fire_utc("0 9 * * *", now=now, tz="UTC")
        assert prev == datetime(2026, 5, 11, 9, 0, tzinfo=UTC)

    def test_daily_returns_yesterday_if_not_yet_today(self):
        from sleuth.scheduler.catchup import previous_fire_utc
        now = datetime(2026, 5, 11, 6, 0, tzinfo=UTC)
        prev = previous_fire_utc("0 9 * * *", now=now, tz="UTC")
        assert prev == datetime(2026, 5, 10, 9, 0, tzinfo=UTC)

    def test_weekly_monday(self):
        # Tuesday afternoon — most recent Monday-09:00 fire was yesterday.
        from sleuth.scheduler.catchup import previous_fire_utc
        now = datetime(2026, 5, 12, 14, 0, tzinfo=UTC)
        prev = previous_fire_utc("0 9 * * 1", now=now, tz="UTC")
        assert prev == datetime(2026, 5, 11, 9, 0, tzinfo=UTC)

    def test_empty_returns_none(self):
        from sleuth.scheduler.catchup import previous_fire_utc
        assert previous_fire_utc("", now=datetime.now(UTC)) is None
        assert previous_fire_utc(None, now=datetime.now(UTC)) is None

    def test_invalid_raises(self):
        from sleuth.scheduler.catchup import previous_fire_utc
        with pytest.raises(ValueError):
            previous_fire_utc("not a cron", now=datetime.now(UTC))


# --------------------------------------------------------------------------- #
# needs_catchup
# --------------------------------------------------------------------------- #


class TestNeedsCatchup:
    def test_never_run_needs_catchup(self):
        from sleuth.scheduler.catchup import needs_catchup
        now = datetime(2026, 5, 11, 14, 0, tzinfo=UTC)
        assert needs_catchup("0 9 * * *", last_run_iso=None, now=now, tz="UTC") is True

    def test_ran_after_last_fire_no_catchup(self):
        from sleuth.scheduler.catchup import needs_catchup
        # daily 9am, ran today at 9:01 already
        now = datetime(2026, 5, 11, 14, 0, tzinfo=UTC)
        last = "2026-05-11T09:01:00+00:00"
        assert needs_catchup("0 9 * * *", last_run_iso=last, now=now, tz="UTC") is False

    def test_ran_before_last_fire_needs_catchup(self):
        from sleuth.scheduler.catchup import needs_catchup
        # daily 9am, last ran yesterday at 9:00 — today's 9am was missed
        now = datetime(2026, 5, 11, 14, 0, tzinfo=UTC)
        last = "2026-05-10T09:00:00+00:00"
        assert needs_catchup("0 9 * * *", last_run_iso=last, now=now, tz="UTC") is True

    def test_naive_last_run_assumed_utc(self):
        """We store ISO strings - support both naive and tz-aware."""
        from sleuth.scheduler.catchup import needs_catchup
        now = datetime(2026, 5, 11, 14, 0, tzinfo=UTC)
        # tz-naive iso, treated as UTC
        last = "2026-05-11T09:30:00"
        assert needs_catchup("0 9 * * *", last_run_iso=last, now=now, tz="UTC") is False

    def test_unscheduled_never_needs_catchup(self):
        from sleuth.scheduler.catchup import needs_catchup
        now = datetime(2026, 5, 11, tzinfo=UTC)
        assert needs_catchup("", last_run_iso=None, now=now) is False
        assert needs_catchup(None, last_run_iso=None, now=now) is False

    def test_grace_period_skips_just_missed(self):
        """A fire that happened 10 seconds ago shouldn't count as missed yet -
        cron may still be about to run it. We give it a small grace window."""
        from sleuth.scheduler.catchup import needs_catchup
        now = datetime(2026, 5, 11, 9, 0, 5, tzinfo=UTC)  # 5s after 9:00
        last = "2026-05-10T09:00:00+00:00"
        # within the default 60-second grace, we don't claim a miss yet
        assert needs_catchup(
            "0 9 * * *", last_run_iso=last, now=now, tz="UTC", grace=timedelta(seconds=60)
        ) is False


# --------------------------------------------------------------------------- #
# find_missed_jobs — works against a real SqliteStore
# --------------------------------------------------------------------------- #


def _make_job(store, **kwargs):
    from sleuth.storage import Job, new_id
    base = dict(
        id=new_id(),
        name="x",
        prompt="p",
        provider="openai",
        model="gpt-5.5",
    )
    base.update(kwargs)
    job = Job(**base)
    store.create_job(job)
    return job


def _make_run(store, job_id, started_at):
    from sleuth.storage import Run, new_id
    run = Run(
        id=new_id(),
        job_id=job_id,
        prompt="p",
        provider="openai",
        model="gpt-5.5",
        started_at=started_at,
        status="done",
        finished_at=started_at,
    )
    store.start_run(run)
    store.finish_run(run.id, status="done", output="ok")
    return run


class TestFindMissedJobs:
    def test_empty_store_returns_empty(self, store):
        from sleuth.scheduler.catchup import find_missed_jobs
        assert find_missed_jobs(store, now=datetime(2026, 5, 11, tzinfo=UTC), tz="UTC") == []

    def test_unscheduled_job_skipped(self, store):
        from sleuth.scheduler.catchup import find_missed_jobs
        _make_job(store)  # no cron_expr
        assert find_missed_jobs(store, now=datetime(2026, 5, 11, tzinfo=UTC), tz="UTC") == []

    def test_scheduled_never_run(self, store):
        from sleuth.scheduler.catchup import find_missed_jobs
        j = _make_job(store, cron_expr="0 9 * * *", schedule_label="daily")
        missed = find_missed_jobs(
            store, now=datetime(2026, 5, 11, 14, tzinfo=UTC), tz="UTC"
        )
        assert len(missed) == 1
        assert missed[0].id == j.id

    def test_scheduled_ran_after_last_fire_not_missed(self, store):
        from sleuth.scheduler.catchup import find_missed_jobs
        j = _make_job(store, cron_expr="0 9 * * *", schedule_label="daily")
        _make_run(store, j.id, started_at="2026-05-11T09:30:00+00:00")
        missed = find_missed_jobs(
            store, now=datetime(2026, 5, 11, 14, tzinfo=UTC), tz="UTC"
        )
        assert missed == []

    def test_scheduled_ran_before_last_fire_is_missed(self, store):
        from sleuth.scheduler.catchup import find_missed_jobs
        j = _make_job(store, cron_expr="0 9 * * *", schedule_label="daily")
        # ran yesterday at 9:00; today's 9:00 fire was missed
        _make_run(store, j.id, started_at="2026-05-10T09:00:00+00:00")
        missed = find_missed_jobs(
            store, now=datetime(2026, 5, 11, 14, tzinfo=UTC), tz="UTC"
        )
        assert {m.id for m in missed} == {j.id}

    def test_two_scheduled_one_missed(self, store):
        from sleuth.scheduler.catchup import find_missed_jobs
        a = _make_job(store, cron_expr="0 9 * * *", schedule_label="daily", name="a")
        b = _make_job(store, cron_expr="0 9 * * *", schedule_label="daily", name="b")
        # a ran on time, b did not
        _make_run(store, a.id, started_at="2026-05-11T09:30:00+00:00")
        missed = find_missed_jobs(
            store, now=datetime(2026, 5, 11, 14, tzinfo=UTC), tz="UTC"
        )
        assert {m.id for m in missed} == {b.id}
