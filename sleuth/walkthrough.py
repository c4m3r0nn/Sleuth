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
    ("jobs", "new"): "jobs new",
    ("jobs", "schedule"): "jobs schedule",
    ("jobs", "edit"): "jobs edit",
    ("jobs", "run"): "jobs run",
    ("jobs", "show"): "jobs show",
    ("jobs", "rm"): "jobs rm",
    ("show",): "show",
    ("history",): "history",
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
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.formatted_text import FormattedText

    suffix = "[Y/n]" if default else "[y/N]"
    label = FormattedText([("class:wkq", f"  {question} {suffix} "), ("", "")])
    raw = pt_prompt(label).strip().lower()
    if not raw:
        return default
    return raw[0] == "y"


def _ask_choice(
    question: str,
    options: list[str],
    *,
    default: Optional[str] = None,
    allow_freeform: bool = True,
    show_blurbs: Optional[list[str]] = None,
) -> str:
    """Print a numbered list and accept either a number or the typed value."""
    from prompt_toolkit import prompt as pt_prompt
    from sleuth.ui import console

    console.print(f"  {question}")
    for i, opt in enumerate(options, 1):
        marker = " <-" if opt == default else "   "
        blurb = ""
        if show_blurbs and i - 1 < len(show_blurbs):
            blurb = f"  {show_blurbs[i - 1]}"
        console.print(f"    {marker} [{i}] {opt}{blurb}")

    default_token = ""
    if default:
        try:
            default_token = str(options.index(default) + 1)
        except ValueError:
            default_token = default

    raw = pt_prompt("    > ", default=default_token).strip()
    if not raw and default:
        return default
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
    if allow_freeform:
        return raw
    if default:
        return default
    return options[0]


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
        # let them pick an id from the saved jobs
        from sleuth.storage import get_store
        rows = get_store().list_jobs()
        if not rows:
            from sleuth.ui.console import bonk
            bonk("no saved jobs to schedule. run `jobs new` first.")
            return None
        ids = [j.id for j in rows]
        labels = [f"{j.name} ({j.id})" for j in rows]
        # Use ask_choice on labels but return id
        pick = _ask_choice("which job?", labels, default=labels[0], allow_freeform=False)
        job_id = ids[labels.index(pick)] if pick in labels else ids[0]

    kinds = ["daily", "weekly", "hourly", "every (interval)", "monthly", "raw cron"]
    kind = _ask_choice("schedule kind?", kinds, default="daily", allow_freeform=False)

    if kind == "daily":
        at = _ask_text("time (HH:MM, 24h)", default="09:00")
        return build_jobs_schedule_argv(job_id, daily=at)
    if kind == "weekly":
        days = _ask_text("days (e.g. mon,wed,fri)", default="mon,wed,fri")
        at = _ask_text("time (HH:MM, 24h)", default="09:00")
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
        at = _ask_text("time (HH:MM, 24h)", default="09:00")
        return build_jobs_schedule_argv(job_id, monthly=True, day=day, at=at)
    # raw cron
    expr = _ask_text("cron expression (5 fields)", default="0 9 * * *")
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
    pick = _ask_choice(prompt_question, labels, default=labels[0], allow_freeform=False)
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
    job_id = _pick_job_id("which job to edit?")
    if not job_id:
        return None

    fields: dict = {}
    if _ask_yesno("change the prompt?", default=False):
        fields["prompt"] = _ask_text("new prompt")
    if _ask_yesno("change the model?", default=False):
        from sleuth.config import get_settings
        from sleuth.providers import MODEL_CATALOG, PROVIDERS
        provider = _ask_choice(
            "provider?", list(PROVIDERS.keys()), default=get_settings().default_provider
        )
        options = [m for m, _ in MODEL_CATALOG.get(provider, [])]
        fields["provider"] = provider
        fields["model"] = _ask_choice("model?", options, default=options[0])
    if _ask_yesno("toggle drive sync?", default=False):
        fields["drive"] = _ask_yesno("turn drive sync ON?", default=False)
    if _ask_yesno("toggle notifications?", default=False):
        fields["notify"] = _ask_yesno("turn notifications ON?", default=True)
    if _ask_yesno("rename the job?", default=False):
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
    pick = _ask_choice("which run?", labels, default=labels[0], allow_freeform=False)
    run_id = ids[labels.index(pick)] if pick in labels else ids[0]
    return build_show_argv(run_id)


def walk_history() -> Optional[list[str]]:
    limit_str = _ask_text("how many entries?", default="15")
    try:
        limit = int(limit_str)
    except ValueError:
        limit = 15
    return build_history_argv(limit=limit)


WALK_DISPATCH = {
    "ask": walk_ask,
    "jobs new": walk_jobs_new,
    "jobs schedule": walk_jobs_schedule,
    "jobs edit": walk_jobs_edit,
    "jobs run": walk_jobs_run,
    "jobs show": walk_jobs_show,
    "jobs rm": walk_jobs_rm,
    "show": walk_show,
    "history": walk_history,
}
