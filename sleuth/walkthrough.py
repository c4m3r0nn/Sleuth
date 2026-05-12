"""Command walkthroughs for the REPL.

Two halves:

  - Pure argv builders (build_*_argv): take answer dicts, return argv tokens
    suitable for handing to the Typer app. Fully unit-tested.

  - Interactive prompt funcs (walk_*): collect answers via prompt_toolkit and
    delegate to the builders. Exercised by hand from the REPL.

Keeping them separate means the prompts can change freely without breaking
the dispatch logic, and we can confirm the dispatch is right with unit tests
even though the prompts themselves aren't.
"""

from __future__ import annotations

from typing import Optional


# --------------------------------------------------------------------------- #
# pure builders
# --------------------------------------------------------------------------- #


def build_ask_argv(
    prompt: str,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    system: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    web_search: bool = True,
    drive: bool = False,
    notify: bool = False,
    quiet: bool = False,
) -> list[str]:
    args: list[str] = ["ask", prompt]
    if model:
        args += ["--model", model]
    if provider:
        args += ["--provider", provider]
    if system:
        args += ["--system", system]
    if max_tokens is not None:
        args += ["--max-tokens", str(max_tokens)]
    if temperature is not None:
        args += ["--temp", str(temperature)]
    if not web_search:
        args.append("--no-search")
    if drive:
        args.append("--drive")
    if notify:
        args.append("--notify")
    if quiet:
        args.append("--quiet")
    return args


def build_jobs_new_argv(
    *,
    name: str,
    prompt: str,
    model: str,
    provider: str,
    system: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    web_search: bool = True,
    sync_drive: bool = False,
    notify: bool = True,
) -> list[str]:
    args: list[str] = [
        "jobs", "new",
        "--name", name,
        "--prompt", prompt,
        "--model", model,
        "--provider", provider,
    ]
    if system:
        args += ["--system", system]
    if max_tokens is not None:
        args += ["--max-tokens", str(max_tokens)]
    if temperature is not None:
        args += ["--temp", str(temperature)]
    if not web_search:
        args.append("--no-search")
    if sync_drive:
        args.append("--drive")
    if not notify:
        args.append("--no-notify")
    return args


def build_jobs_schedule_argv(
    job_id: str,
    *,
    daily: Optional[str] = None,
    weekly: Optional[str] = None,
    at: Optional[str] = None,
    hourly: bool = False,
    every: Optional[str] = None,
    monthly: bool = False,
    day: Optional[int] = None,
    cron: Optional[str] = None,
) -> list[str]:
    args: list[str] = ["jobs", "schedule", job_id]
    if daily:
        args += ["--daily", daily]
    if weekly:
        args += ["--weekly", weekly]
    if at:
        args += ["--at", at]
    if hourly:
        args.append("--hourly")
    if every:
        args += ["--every", every]
    if monthly:
        args.append("--monthly")
    if day is not None:
        args += ["--day", str(day)]
    if cron:
        args += ["--cron", cron]
    return args


def build_jobs_edit_argv(job_id: str, **fields) -> list[str]:
    args: list[str] = ["jobs", "edit", job_id]
    flag_map = {
        "name": "--name",
        "prompt": "--prompt",
        "model": "--model",
        "provider": "--provider",
        "system": "--system",
        "max_tokens": "--max-tokens",
        "temperature": "--temp",
    }
    for k, flag in flag_map.items():
        v = fields.get(k)
        if v is None:
            continue
        args += [flag, str(v)]
    if "search" in fields and fields["search"] is not None:
        args.append("--search" if fields["search"] else "--no-search")
    if "drive" in fields and fields["drive"] is not None:
        args.append("--drive" if fields["drive"] else "--no-drive")
    if "notify" in fields and fields["notify"] is not None:
        args.append("--notify" if fields["notify"] else "--no-notify")
    return args


def build_jobs_run_argv(job_id: str, *, quiet: bool = False) -> list[str]:
    args = ["jobs", "run", job_id]
    if quiet:
        args.append("--quiet")
    return args


def build_jobs_show_argv(job_id: str) -> list[str]:
    return ["jobs", "show", job_id]


def build_jobs_rm_argv(job_id: str, *, force: bool = False) -> list[str]:
    args = ["jobs", "rm", job_id]
    if force:
        args.append("--force")
    return args


def build_show_argv(run_id: str) -> list[str]:
    return ["show", run_id]


def build_history_argv(*, limit: Optional[int] = None, job_id: Optional[str] = None) -> list[str]:
    args = ["history"]
    if limit is not None:
        args += ["--limit", str(limit)]
    if job_id:
        args += ["--job", job_id]
    return args


# --------------------------------------------------------------------------- #
# walkthrough detection
# --------------------------------------------------------------------------- #


_WALKABLE: dict[tuple[str, ...], str] = {
    ("ask",): "ask",
    ("jobs",): "jobs menu",
    ("jobs", "new"): "jobs new",
    ("jobs", "schedule"): "jobs schedule",
    ("jobs", "edit"): "jobs edit",
    ("jobs", "run"): "jobs run",
    ("jobs", "show"): "jobs show",
    ("jobs", "rm"): "jobs rm",
    ("jobs", "logs"): "jobs logs",
    ("jobs", "check"): "jobs check",
    ("jobs", "unschedule"): "jobs unschedule",
    ("show",): "show",
    ("history",): "history",
    ("drive",): "drive menu",
}


def needs_walkthrough(tokens: list[str]) -> Optional[str]:
    """Return a walkthrough kind if the user typed a bare command, else None.

    A 'bare' command is one with no further args after the command name(s).
    Example: 'ask' -> 'ask'; 'ask hi' -> None; 'jobs new' -> 'jobs new'.
    """
    if not tokens:
        return None
    if tuple(tokens) in _WALKABLE:
        return _WALKABLE[tuple(tokens)]
    return None


# --------------------------------------------------------------------------- #
# interactive walkthroughs (uses prompt_toolkit; lazy import-friendly)
# --------------------------------------------------------------------------- #


def _ask_text(question: str, default: str = "") -> str:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.formatted_text import FormattedText

    label = FormattedText([("class:wkq", f"  {question} "), ("", "")])
    answer = pt_prompt(label, default=default)
    return answer.strip()


def _ask_yesno(question: str, *, default: bool = False) -> bool:
    """Yes/no rendered as a two-option arrow-key selector."""
    from sleuth.ui.selector import run_select_one

    yes_label, no_label = "yes", "no"
    options = [yes_label, no_label]
    chosen = run_select_one(
        question, options, default=yes_label if default else no_label,
    )
    if chosen is None:
        return default
    return chosen == yes_label


def _ask_choice(
    question: str,
    options: list[str],
    *,
    default: Optional[str] = None,
    show_blurbs: Optional[list[str]] = None,
    allow_freeform: bool = False,  # kept for back-compat; ignored
) -> Optional[str]:
    """Arrow-key single-select. Returns the chosen option or None if cancelled."""
    from sleuth.ui.selector import run_select_one
    return run_select_one(question, options, default=default, blurbs=show_blurbs)


def _ask_multi(
    question: str,
    options: list[str],
    *,
    default_selected: Optional[list[str]] = None,
) -> Optional[list[str]]:
    """Arrow-key multi-select with checkboxes."""
    from sleuth.ui.selector import run_select_many
    return run_select_many(question, options, default_selected=default_selected)


def walk_ask() -> Optional[list[str]]:
    """Walk the user through `ask`. Returns argv to dispatch, or None to cancel."""
    from sleuth.config import get_settings

    settings = get_settings()
    prompt_text = _ask_text("what should sleuth dig up?")
    if not prompt_text:
        return None

    if not _ask_yesno("tweak provider/model?", default=False):
        return build_ask_argv(prompt_text)

    from sleuth.providers import MODEL_CATALOG, PROVIDERS, provider_for_model

    provider = _ask_choice(
        "which provider?",
        list(PROVIDERS.keys()),
        default=settings.default_provider,
    )
    options = [m for m, _ in MODEL_CATALOG.get(provider, [])]
    blurbs = [b for _, b in MODEL_CATALOG.get(provider, [])]
    suggested = (
        settings.default_model
        if provider_for_model_safe(settings.default_model) == provider
        else (options[0] if options else None)
    )
    model = _ask_choice("which model?", options, default=suggested, show_blurbs=blurbs)

    drive = _ask_yesno("mirror to google drive?", default=False)
    notify = _ask_yesno("ping when done?", default=False)
    return build_ask_argv(
        prompt_text, provider=provider, model=model, drive=drive, notify=notify
    )


def provider_for_model_safe(model: str) -> str:
    from sleuth.providers import provider_for_model
    try:
        return provider_for_model(model)
    except Exception:
        return ""


def walk_jobs_new() -> Optional[list[str]]:
    from sleuth.config import get_settings
    from sleuth.providers import MODEL_CATALOG, PROVIDERS

    settings = get_settings()
    name = _ask_text("job name (e.g. 'morning-news')")
    if not name:
        return None
    prompt_text = _ask_text("research prompt")
    if not prompt_text:
        return None

    provider = _ask_choice(
        "which provider?",
        list(PROVIDERS.keys()),
        default=settings.default_provider,
    )
    options = [m for m, _ in MODEL_CATALOG.get(provider, [])]
    blurbs = [b for _, b in MODEL_CATALOG.get(provider, [])]
    suggested = settings.default_model if provider == settings.default_provider else (options[0] if options else None)
    model = _ask_choice("which model?", options, default=suggested, show_blurbs=blurbs)

    sync_drive = _ask_yesno("mirror finished runs to drive?", default=False)
    notify = _ask_yesno("ping you when it finishes?", default=True)
    return build_jobs_new_argv(
        name=name, prompt=prompt_text, model=model, provider=provider,
        sync_drive=sync_drive, notify=notify,
    )


def walk_jobs_schedule(job_id: Optional[str] = None) -> Optional[list[str]]:
    if not job_id:
        job_id = _pick_job_id("which job to schedule?")
        if not job_id:
            return None

    kinds = ["daily", "weekly", "hourly", "every (interval)", "monthly", "raw cron"]
    kind = _ask_choice("schedule kind?", kinds, default="daily")
    if not kind:
        return None

    # Show the local tz so users know what 09:00 actually means.
    from sleuth.scheduler.eta import describe_local_tz
    from sleuth.ui import console
    console.print(f"  (times are interpreted in your system local timezone: {describe_local_tz()})")

    if kind == "daily":
        at = _ask_text("time (HH:MM, 24h, local time)", default="09:00")
        return build_jobs_schedule_argv(job_id, daily=at)
    if kind == "weekly":
        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        chosen_days = _ask_multi("which days?", day_names, default_selected=["mon"])
        if not chosen_days:
            return None
        days = ",".join(chosen_days)
        at = _ask_text("time (HH:MM, 24h, local time)", default="09:00")
        return build_jobs_schedule_argv(job_id, weekly=days, at=at)
    if kind == "hourly":
        return build_jobs_schedule_argv(job_id, hourly=True)
    if kind == "every (interval)":
        ev = _ask_text("interval (e.g. 15m or 2h)", default="15m")
        return build_jobs_schedule_argv(job_id, every=ev)
    if kind == "monthly":
        day_str = _ask_text("day of month (1-28)", default="1")
        try:
            day = int(day_str)
        except ValueError:
            day = 1
        at = _ask_text("time (HH:MM, 24h, local time)", default="09:00")
        return build_jobs_schedule_argv(job_id, monthly=True, day=day, at=at)
    # raw cron
    expr = _ask_text("cron expression (5 fields, interpreted in local time)", default="0 9 * * *")
    return build_jobs_schedule_argv(job_id, cron=expr)


def _pick_job_id(prompt_question: str = "which job?") -> Optional[str]:
    from sleuth.storage import get_store
    from sleuth.ui.console import bonk

    rows = get_store().list_jobs()
    if not rows:
        bonk("no saved jobs. run `jobs new` first.")
        return None
    ids = [j.id for j in rows]
    labels = [f"{j.name} ({j.id})" for j in rows]
    pick = _ask_choice(prompt_question, labels, default=labels[0])
    if pick is None:
        return None
    return ids[labels.index(pick)] if pick in labels else ids[0]


def walk_jobs_run() -> Optional[list[str]]:
    job_id = _pick_job_id("which job to run now?")
    if not job_id:
        return None
    return build_jobs_run_argv(job_id)


def walk_jobs_show() -> Optional[list[str]]:
    job_id = _pick_job_id()
    if not job_id:
        return None
    return build_jobs_show_argv(job_id)


def walk_jobs_rm() -> Optional[list[str]]:
    job_id = _pick_job_id("which job to delete?")
    if not job_id:
        return None
    return build_jobs_rm_argv(job_id)


def walk_jobs_edit() -> Optional[list[str]]:
    """Pick a job, then check which fields you want to change, then change them."""
    job_id = _pick_job_id("which job to edit?")
    if not job_id:
        return None

    field_choices = [
        "prompt",
        "model",
        "drive sync",
        "notifications",
        "rename (job name)",
    ]
    picked = _ask_multi("which fields to change?", field_choices)
    if picked is None:
        return None
    if not picked:
        from sleuth.ui.console import bonk
        bonk("nothing to change.")
        return None

    fields: dict = {}
    if "prompt" in picked:
        fields["prompt"] = _ask_text("new prompt")
    if "model" in picked:
        from sleuth.config import get_settings
        from sleuth.providers import MODEL_CATALOG, PROVIDERS

        provider = _ask_choice(
            "provider?", list(PROVIDERS.keys()),
            default=get_settings().default_provider,
        )
        if provider:
            options = [m for m, _ in MODEL_CATALOG.get(provider, [])]
            blurbs = [b for _, b in MODEL_CATALOG.get(provider, [])]
            fields["provider"] = provider
            model = _ask_choice(
                "model?", options, default=options[0], show_blurbs=blurbs,
            )
            if model:
                fields["model"] = model
    if "drive sync" in picked:
        fields["drive"] = _ask_yesno("turn drive sync ON?", default=False)
    if "notifications" in picked:
        fields["notify"] = _ask_yesno("turn notifications ON?", default=True)
    if "rename (job name)" in picked:
        fields["name"] = _ask_text("new name")

    if not fields:
        from sleuth.ui.console import bonk
        bonk("nothing to change.")
        return None
    return build_jobs_edit_argv(job_id, **fields)


def walk_show() -> Optional[list[str]]:
    """Pick a past run to inspect."""
    from sleuth.storage import get_store
    from sleuth.ui.console import bonk

    runs = get_store().list_runs(limit=15)
    if not runs:
        bonk("no past runs.")
        return None
    ids = [r.id for r in runs]
    labels = [
        f"{r.id}  {r.started_at[:16].replace('T', ' ')}  {r.provider}/{r.model}  {(r.prompt or '')[:40]}"
        for r in runs
    ]
    pick = _ask_choice("which run?", labels, default=labels[0])
    if pick is None:
        return None
    run_id = ids[labels.index(pick)] if pick in labels else ids[0]
    return build_show_argv(run_id)


def walk_history() -> Optional[list[str]]:
    limit_str = _ask_text("how many entries?", default="15")
    try:
        limit = int(limit_str)
    except ValueError:
        limit = 15
    return build_history_argv(limit=limit)


def walk_jobs_menu() -> Optional[list[str]]:
    """Top-level `jobs` menu when typed bare. Pick a subcommand by arrow keys."""
    actions = [
        "list",
        "new",
        "show",
        "edit",
        "run",
        "schedule",
        "unschedule",
        "logs",
        "check",
        "rm",
        "crontab",
    ]
    pick = _ask_choice("which jobs action?", actions, default="list")
    if not pick:
        return None
    # Most need an id; pass through to the nested walkthrough or to typer.
    if pick == "list":
        return ["jobs", "list"]
    if pick == "crontab":
        return ["jobs", "crontab"]
    if pick == "new":
        return walk_jobs_new()
    if pick == "show":
        return walk_jobs_show()
    if pick == "edit":
        return walk_jobs_edit()
    if pick == "run":
        return walk_jobs_run()
    if pick == "schedule":
        return walk_jobs_schedule()
    if pick == "rm":
        return walk_jobs_rm()
    if pick == "logs":
        jid = _pick_job_id("which job's logs?")
        return ["jobs", "logs", jid] if jid else None
    if pick == "check":
        jid = _pick_job_id("which job to check?")
        return ["jobs", "check", jid] if jid else None
    if pick == "unschedule":
        jid = _pick_job_id("which job to unschedule?")
        return ["jobs", "unschedule", jid] if jid else None
    return None


def walk_drive_menu() -> Optional[list[str]]:
    """Top-level `drive` menu when typed bare."""
    pick = _ask_choice("which drive action?", ["status", "auth"], default="status")
    if not pick:
        return None
    return ["drive", pick]


WALK_DISPATCH = {
    "ask": walk_ask,
    "jobs menu": walk_jobs_menu,
    "jobs new": walk_jobs_new,
    "jobs schedule": walk_jobs_schedule,
    "jobs edit": walk_jobs_edit,
    "jobs run": walk_jobs_run,
    "jobs show": walk_jobs_show,
    "jobs rm": walk_jobs_rm,
    "jobs logs": lambda: (lambda jid: ["jobs", "logs", jid] if jid else None)(
        _pick_job_id("which job's logs?")
    ),
    "jobs check": lambda: (lambda jid: ["jobs", "check", jid] if jid else None)(
        _pick_job_id("which job to check?")
    ),
    "jobs unschedule": lambda: (lambda jid: ["jobs", "unschedule", jid] if jid else None)(
        _pick_job_id("which job to unschedule?")
    ),
    "show": walk_show,
    "history": walk_history,
    "drive menu": walk_drive_menu,
}
