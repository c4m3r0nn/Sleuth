"""Schedule grammar -> cron entries, plus crontab management."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional  # noqa: F401  (used below)

from sleuth.config import get_settings


SCHEDULE_TAG = "sleuth"  # entries are tagged "# sleuth:<job_id>"
CATCHUP_COMMENT = "sleuth-catchup"  # the @reboot catchup line


DAY_MAP = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
}


@dataclass
class ScheduleSpec:
    cron_expr: str
    label: str  # human-readable, stored on the job


def _parse_hhmm(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", s)
    if not m:
        raise ValueError(f"Bad time '{s}'. Expected HH:MM (24h).")
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h < 24 and 0 <= mi < 60):
        raise ValueError(f"Time '{s}' out of range.")
    return h, mi


def _parse_days(spec: str) -> list[int]:
    parts = [p.strip().lower()[:3] for p in spec.split(",") if p.strip()]
    out: list[int] = []
    for p in parts:
        if p not in DAY_MAP:
            raise ValueError(f"Unknown day '{p}'. Use mon/tue/.../sun.")
        out.append(DAY_MAP[p])
    return sorted(set(out))


def _parse_every(spec: str) -> tuple[str, str]:
    """e.g. '15m' -> ('*/15 * * * *', 'every 15 min')."""
    m = re.fullmatch(r"\s*(\d+)\s*([mh])\s*", spec.lower())
    if not m:
        raise ValueError(f"Bad --every '{spec}'. Try '15m', '2h'.")
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "m":
        if n < 1 or n >= 60:
            raise ValueError("Minutes interval must be 1..59.")
        return f"*/{n} * * * *", f"every {n} min"
    # hourly
    if n < 1 or n > 23:
        raise ValueError("Hours interval must be 1..23.")
    return f"0 */{n} * * *", f"every {n} h"


def build_schedule(
    *,
    daily: Optional[str] = None,
    weekly_days: Optional[str] = None,
    weekly_at: Optional[str] = None,
    hourly: bool = False,
    every: Optional[str] = None,
    monthly_day: Optional[int] = None,
    monthly_at: Optional[str] = None,
    raw_cron: Optional[str] = None,
) -> ScheduleSpec:
    """Convert friendly options to a cron expression + label.

    Exactly one of the high-level options should be given. `raw_cron` wins.
    """
    if raw_cron:
        return ScheduleSpec(cron_expr=raw_cron.strip(), label=f"cron({raw_cron.strip()})")

    if daily:
        h, mi = _parse_hhmm(daily)
        return ScheduleSpec(
            cron_expr=f"{mi} {h} * * *",
            label=f"daily at {h:02d}:{mi:02d} local time",
        )

    if weekly_days:
        if not weekly_at:
            raise ValueError("--weekly needs --at HH:MM.")
        h, mi = _parse_hhmm(weekly_at)
        days = _parse_days(weekly_days)
        days_str = ",".join(str(d) for d in days)
        names = ",".join(
            name for name, idx in DAY_MAP.items() if idx in days
        )
        return ScheduleSpec(
            cron_expr=f"{mi} {h} * * {days_str}",
            label=f"weekly {names} at {h:02d}:{mi:02d} local time",
        )

    if hourly:
        return ScheduleSpec(cron_expr="0 * * * *", label="hourly")

    if every:
        expr, label = _parse_every(every)
        return ScheduleSpec(cron_expr=expr, label=label)

    if monthly_day is not None:
        if not monthly_at:
            raise ValueError("--monthly needs --at HH:MM.")
        if not (1 <= monthly_day <= 28):
            raise ValueError("--day must be 1..28 (avoiding month-end edges).")
        h, mi = _parse_hhmm(monthly_at)
        return ScheduleSpec(
            cron_expr=f"{mi} {h} {monthly_day} * *",
            label=f"monthly day {monthly_day} at {h:02d}:{mi:02d} local time",
        )

    raise ValueError(
        "Pick a schedule: --daily / --weekly+--at / --hourly / --every / "
        "--monthly+--day+--at / --cron"
    )


def _venv_sleuth_path() -> Optional[Path]:
    """Where the venv's installed `sleuth` console script lives, if any."""
    bin_dir = Path(sys.executable).parent
    candidate = bin_dir / "sleuth"
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def _command_for(job_id: str) -> str:
    """The shell command crontab will run.

    Cron's CWD is the user's $HOME. If $HOME contains a directory named
    `sleuth/` (which it will if the project lives there), then
    `python -m sleuth` treats that directory as an implicit namespace package
    and shadows the real installed `sleuth`. To dodge that:

      - prefer the venv's `sleuth` console script (its own dir doesn't
        shadow the package)
      - fall back to `cd /tmp && python -m sleuth ...` if no script is
        installed for some reason
    """
    settings = get_settings()
    log_path = settings.log_dir / f"{job_id}.log"

    binary = _venv_sleuth_path()
    if binary is not None:
        return f"{binary} _exec {job_id} >> {log_path} 2>&1"

    py = sys.executable
    return f"cd /tmp && {py} -m sleuth _exec {job_id} >> {log_path} 2>&1"


def install_cron(job_id: str, cron_expr: str) -> None:
    """Install (or replace) the crontab entry for this job."""
    from crontab import CronTab  # python-crontab

    cron = CronTab(user=True)
    # Remove any prior entry for this job.
    _remove_for(cron, job_id)
    cmd = _command_for(job_id)
    job = cron.new(command=cmd, comment=f"{SCHEDULE_TAG}:{job_id}")
    job.setall(cron_expr)
    if not job.is_valid():
        raise ValueError(f"Cron expression '{cron_expr}' is not valid.")
    cron.write()


def remove_cron(job_id: str) -> int:
    """Remove the crontab entry for this job. Returns count removed."""
    from crontab import CronTab

    cron = CronTab(user=True)
    n = _remove_for(cron, job_id)
    cron.write()
    return n


def _remove_for(cron, job_id: str) -> int:
    matches = list(cron.find_comment(f"{SCHEDULE_TAG}:{job_id}"))
    for m in matches:
        cron.remove(m)
    return len(matches)


def _catchup_command() -> str:
    """The shell command the @reboot crontab entry will run.

    Same CWD-shadowing concern as _command_for; same mitigation.
    """
    settings = get_settings()
    log_path = settings.log_dir / "catchup.log"

    binary = _venv_sleuth_path()
    if binary is not None:
        return f"{binary} catchup --auto >> {log_path} 2>&1"

    py = sys.executable
    return f"cd /tmp && {py} -m sleuth catchup --auto >> {log_path} 2>&1"


def install_catchup_reboot() -> bool:
    """Ensure a `@reboot sleuth catchup` line exists in the crontab.

    Idempotent: returns True if a new line was installed, False if one
    was already there.
    """
    from crontab import CronTab

    cron = CronTab(user=True)
    for entry in cron:
        if (entry.comment or "") == CATCHUP_COMMENT:
            return False
    job = cron.new(command=_catchup_command(), comment=CATCHUP_COMMENT)
    job.every_reboot()
    cron.write()
    return True


def remove_catchup_reboot() -> int:
    """Remove any @reboot catchup line. Returns the number removed."""
    from crontab import CronTab

    cron = CronTab(user=True)
    matches = list(cron.find_comment(CATCHUP_COMMENT))
    for m in matches:
        cron.remove(m)
    cron.write()
    return len(matches)


def has_catchup_reboot() -> bool:
    from crontab import CronTab

    cron = CronTab(user=True)
    return any((e.comment or "") == CATCHUP_COMMENT for e in cron)


def list_cron() -> list[tuple[str, str, str]]:
    """Return [(job_id, cron_expr, command), ...] for sleuth-tagged entries."""
    from crontab import CronTab

    cron = CronTab(user=True)
    out: list[tuple[str, str, str]] = []
    for entry in cron:
        comment = entry.comment or ""
        if not comment.startswith(f"{SCHEDULE_TAG}:"):
            continue
        job_id = comment.split(":", 1)[1]
        out.append((job_id, str(entry.slices), entry.command))
    return out
