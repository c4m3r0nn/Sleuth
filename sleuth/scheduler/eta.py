"""When does this cron next fire? Pure helpers, no side effects."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo


def _resolve_tz(tz: Optional[str]) -> ZoneInfo | timezone:
    if tz is None:
        # use the system's local timezone (matches cron's behaviour)
        local = datetime.now().astimezone().tzinfo
        return local if local is not None else timezone.utc
    return ZoneInfo(tz)


def next_run_utc(
    cron_expr: Optional[str],
    *,
    now: Optional[datetime] = None,
    tz: Optional[str] = None,
) -> Optional[datetime]:
    """Compute the next fire time for a cron expression, returned in UTC.

    Cron expressions are interpreted in the **system local timezone** (that's
    what the cron daemon does). Pass `tz` to override that for testing or
    when displaying for a particular locale.

    Returns None for empty/None input. Raises ValueError on a malformed
    expression.
    """
    if not cron_expr:
        return None

    from croniter import croniter, CroniterBadCronError

    local_tz = _resolve_tz(tz)
    if now is None:
        now = datetime.now(local_tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=local_tz)
    else:
        now = now.astimezone(local_tz)

    try:
        it = croniter(cron_expr, now)
        nxt: datetime = it.get_next(datetime)
    except (CroniterBadCronError, ValueError, KeyError) as e:
        raise ValueError(f"bad cron expression {cron_expr!r}: {e}") from e

    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=local_tz)
    return nxt.astimezone(timezone.utc)


def humanize_delta(delta: timedelta) -> str:
    """Render a timedelta as 'in Xd Yh' / 'in Nm' / 'in Ns'."""
    total = int(delta.total_seconds())
    if total == 0:
        return "now"
    if total < 0:
        return "overdue"
    if total < 60:
        return f"in {total}s"
    mins, _ = divmod(total, 60)
    if mins < 60:
        return f"in {mins}m"
    hours, mins = divmod(mins, 60)
    if hours < 24:
        return f"in {hours}h {mins}m"
    days, hours = divmod(hours, 24)
    return f"in {days}d {hours}h"


def format_next_run(
    cron_expr: Optional[str],
    *,
    now: Optional[datetime] = None,
    tz: Optional[str] = None,
) -> str:
    """One-line summary suitable for `jobs show`. Always in UTC."""
    if not cron_expr:
        return "-"
    try:
        nxt = next_run_utc(cron_expr, now=now, tz=tz)
    except ValueError:
        return "(invalid cron expression)"
    if nxt is None:
        return "-"
    if now is None:
        ref = datetime.now(timezone.utc)
    else:
        ref = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        ref = ref.astimezone(timezone.utc)
    stamp = nxt.strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{stamp}  ({humanize_delta(nxt - ref)})"
