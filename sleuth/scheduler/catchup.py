"""Catch-up: did we miss a scheduled fire while the machine was off?

The cron daemon does NOT fire missed entries when a powered-off machine
comes back. To make sleuth survive Pi reboots / power loss, we install a
`@reboot` cron line that runs `sleuth catchup`, which:

  1. For every scheduled job, finds the most-recent fire time that should
     have happened (at-or-before now).
  2. Looks up the job's most recent actual run.
  3. If the most recent run is older than that scheduled fire, runs the
     job once now.

We deliberately run a missed job only **once**, not for each missed slot —
research goes stale; what you want is "fresh as of now", not five snapshots
of yesterday.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo


def _resolve_tz(tz: Optional[str]):
    if tz is None:
        local = datetime.now().astimezone().tzinfo
        return local if local is not None else timezone.utc
    return ZoneInfo(tz)


def previous_fire_utc(
    cron_expr: Optional[str],
    *,
    now: datetime,
    tz: Optional[str] = None,
) -> Optional[datetime]:
    """Most recent scheduled fire at-or-before `now`, returned in UTC."""
    if not cron_expr:
        return None

    from croniter import croniter, CroniterBadCronError

    local_tz = _resolve_tz(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=local_tz)
    else:
        now = now.astimezone(local_tz)

    try:
        it = croniter(cron_expr, now)
        prev = it.get_prev(datetime)
    except (CroniterBadCronError, ValueError, KeyError) as e:
        raise ValueError(f"bad cron expression {cron_expr!r}: {e}") from e

    if prev.tzinfo is None:
        prev = prev.replace(tzinfo=local_tz)
    return prev.astimezone(timezone.utc)


def _parse_iso(ts: str) -> datetime:
    """Lenient ISO parser; treats naive as UTC."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def needs_catchup(
    cron_expr: Optional[str],
    *,
    last_run_iso: Optional[str],
    now: datetime,
    tz: Optional[str] = None,
    grace: timedelta = timedelta(seconds=60),
) -> bool:
    """True if the most-recent scheduled fire didn't happen yet.

    `grace` keeps us from racing the cron daemon — if a fire happened
    only `grace` seconds ago, assume cron is still about to run it.
    """
    if not cron_expr:
        return False
    try:
        prev = previous_fire_utc(cron_expr, now=now, tz=tz)
    except ValueError:
        return False
    if prev is None:
        return False
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if (now - prev) < grace:
        return False
    if last_run_iso is None:
        return True
    last_run = _parse_iso(last_run_iso)
    return last_run < prev


def find_missed_jobs(
    store,
    *,
    now: Optional[datetime] = None,
    tz: Optional[str] = None,
    grace: timedelta = timedelta(seconds=60),
):
    """Return all scheduled Jobs whose last scheduled fire was missed."""
    if now is None:
        now = datetime.now(timezone.utc)
    missed = []
    for job in store.list_jobs():
        if not job.cron_expr:
            continue
        runs = store.list_runs(job_id=job.id, limit=1)
        last_iso = runs[0].started_at if runs else None
        if needs_catchup(
            job.cron_expr,
            last_run_iso=last_iso,
            now=now,
            tz=tz,
            grace=grace,
        ):
            missed.append(job)
    return missed
