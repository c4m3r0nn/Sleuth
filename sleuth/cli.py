"""sleuth's command-line surface."""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from sleuth import __version__
from sleuth.config import get_settings
from sleuth.providers import (
    MODEL_CATALOG,
    PROVIDERS,
    provider_for_model,
)
from sleuth.storage import Job, get_store, new_id
from sleuth.ui import console
from sleuth.ui.art import banner
from sleuth.ui.console import bonk, fact, header, tick


app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    invoke_without_command=True,
    rich_markup_mode="rich",
    help="sleuth - a pocket research gremlin for the terminal.",
)
jobs_app = typer.Typer(no_args_is_help=True, help="Manage saved jobs and schedules.")
drive_app = typer.Typer(no_args_is_help=True, help="Google Drive sync helpers.")
app.add_typer(jobs_app, name="jobs")
app.add_typer(drive_app, name="drive")


def version_callback(value: bool) -> None:
    if value:
        console.print(f"sleuth {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=version_callback, is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """No command? Drop into the interactive shell."""
    if ctx.invoked_subcommand is None:
        from sleuth.repl import repl
        repl()
        raise typer.Exit()


@app.command()
def shell() -> None:
    """Open the interactive sleuth shell (same as bare `sleuth`)."""
    from sleuth.repl import repl
    repl()


# --------------------------------------------------------------------------- #
# top-level: ask, models, history, show, init, ping, _exec
# --------------------------------------------------------------------------- #


@app.command()
def ask(
    prompt: str = typer.Argument(..., help="What you want sleuth to dig up."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model id (default: SLEUTH_DEFAULT_MODEL)."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Force a provider (openai|anthropic|google)."),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System / instructions prompt."),
    max_tokens: int = typer.Option(4096, "--max-tokens", help="Max output tokens."),
    temperature: Optional[float] = typer.Option(None, "--temp", help="Sampling temperature."),
    no_search: bool = typer.Option(False, "--no-search", help="Disable web search for this run."),
    drive: bool = typer.Option(False, "--drive", help="Mirror this run to Google Drive."),
    notify: bool = typer.Option(False, "--notify", help="Ping Telegram when done."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="No fancy UI; just the answer."),
) -> None:
    """One-off research turn."""
    from sleuth.workflows import run_research

    run_research(
        prompt=prompt,
        provider_name=provider,
        model=model,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
        web_search=not no_search,
        sync_drive=drive,
        notify=notify,
        quiet=quiet,
    )


@app.command()
def models() -> None:
    """List the models sleuth knows about."""
    settings = get_settings()
    console.print(banner())
    console.print(Text("  default: ", style="muted") + Text(f"{settings.default_provider}/{settings.default_model}", style="model"))
    console.print()
    for prov, items in MODEL_CATALOG.items():
        table = Table(
            title=Text(prov, style="provider"),
            header_style="muted",
            border_style="rule",
            show_lines=False,
        )
        table.add_column("model")
        table.add_column("notes")
        for mid, blurb in items:
            mark = " <-" if mid == settings.default_model else ""
            table.add_row(f"{mid}{mark}", blurb)
        console.print(table)
        console.print()


@app.command()
def history(
    limit: int = typer.Option(15, "--limit", "-n", help="How many to show."),
    job_id: Optional[str] = typer.Option(None, "--job", help="Filter by job id."),
) -> None:
    """Show recent runs."""
    store = get_store()
    runs = store.list_runs(job_id=job_id, limit=limit)
    if not runs:
        console.print(Text("  the drawer is empty.", style="muted"))
        return
    table = Table(
        header_style="muted", border_style="rule", show_lines=False,
    )
    table.add_column("run")
    table.add_column("when", style="muted")
    table.add_column("model")
    table.add_column("status")
    table.add_column("prompt")
    for r in runs:
        status_style = {"done": "ok", "error": "bad", "running": "warn"}.get(r.status, "muted")
        table.add_row(
            r.id,
            r.started_at.replace("T", " ")[:19],
            f"{r.provider}/{r.model}",
            Text(r.status, style=status_style),
            (r.prompt or "")[:60],
        )
    console.print(table)


@app.command()
def show(run_id: str) -> None:
    """Dump a past run."""
    store = get_store()
    run = store.get_run(run_id)
    if not run:
        bonk(f"no run with id '{run_id}'.")
        raise typer.Exit(1)
    header(f"run {run.id}", f"{run.provider}/{run.model}  -  {run.started_at}")
    console.print(Panel(Markdown(run.output or "_(no output)_"), border_style="rule"))
    if run.citations:
        console.print()
        console.print(Text("  sources", style="muted"))
        for i, c in enumerate(run.citations, 1):
            label = c.get("title") or c.get("url") or "(no title)"
            line = Text()
            line.append(f"  {i:>2}. ", style="muted")
            line.append(label[:80], style="paper")
            line.append("  ")
            line.append(c.get("url", ""), style="citation")
            console.print(line)
    if run.gdrive_url:
        console.print(Text(f"  drive: {run.gdrive_url}", style="ok"))
    if run.output_path:
        console.print(Text(f"  file:  {run.output_path}", style="ok"))


@app.command()
def setup() -> None:
    """Interactive wizard: ask which models you want, paste keys, write .env."""
    from sleuth.setup_wizard import run_wizard

    settings = get_settings()
    env_path = settings.db_path.parent.parent / ".env"
    run_wizard(env_path)


@app.command()
def init() -> None:
    """Show config status. Doesn't change anything; run `sleuth setup` for that."""
    settings = get_settings()
    console.print(banner())
    fact("data dir", str(settings.data_dir))
    fact("output dir", str(settings.output_dir))
    fact("db", str(settings.db_path))
    env_path = settings.db_path.parent.parent / ".env"
    if not env_path.exists():
        bonk("no .env yet. run `sleuth setup` for a guided walk-through.")
    else:
        tick(".env found.")
    keys = {
        "OPENAI_API_KEY": settings.openai_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "GOOGLE_API_KEY": settings.google_api_key,
    }
    for k, v in keys.items():
        if v:
            tick(f"{k} set.")
        else:
            console.print(Text(f"  - {k} missing", style="muted"))
    if settings.telegram_bot_token and settings.telegram_chat_id:
        tick("Telegram configured.")
    else:
        console.print(Text("  - Telegram not set (optional)", style="muted"))


@app.command()
def ping() -> None:
    """Send a test nudge through every configured channel."""
    from sleuth.notify import (
        is_telegram_configured,
        is_discord_configured,
        notify_all,
    )

    if not (is_telegram_configured() or is_discord_configured()):
        bonk(
            "No notifier configured. Set TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID "
            "or DISCORD_WEBHOOK_URL in .env."
        )
        raise typer.Exit(1)
    delivered = notify_all("*sleuth* says hello from your terminal.")
    if delivered:
        tick(f"buzzed: {', '.join(delivered)}.")
    else:
        bonk("notifiers configured but all sends failed - check tokens.")
        raise typer.Exit(1)


@app.command()
def catchup(
    install: bool = typer.Option(False, "--install", help="Also install the @reboot crontab entry."),
    uninstall: bool = typer.Option(False, "--uninstall", help="Remove the @reboot crontab entry."),
    dry_run: bool = typer.Option(False, "--dry-run", help="List missed jobs without running them."),
    auto: bool = typer.Option(False, "--auto", hidden=True, help="Used by the @reboot cron entry; suppresses 'nothing to do' output."),
) -> None:
    """Run any scheduled jobs whose most-recent fire was missed.

    Installed automatically as a @reboot crontab entry by `jobs schedule`,
    so jobs you missed while the Pi was off get caught up the moment the
    machine comes back. Safe to run manually at any time.
    """
    from sleuth.scheduler import (
        install_catchup_reboot,
        remove_catchup_reboot,
        has_catchup_reboot,
    )
    from sleuth.scheduler.catchup import find_missed_jobs
    from sleuth.workflows import run_research

    if uninstall:
        n = remove_catchup_reboot()
        tick(f"removed {n} @reboot catchup entr{'y' if n == 1 else 'ies'}.")
        return

    if install:
        added = install_catchup_reboot()
        if added:
            tick("installed @reboot catchup line in your crontab.")
        else:
            console.print(Text("  @reboot catchup already installed.", style="muted"))

    store = get_store()
    missed = find_missed_jobs(store)
    if not missed:
        if not auto:
            tick("nothing to catch up on.")
        return

    header("catching up", f"{len(missed)} job{'s' if len(missed) != 1 else ''} missed a fire")
    for job in missed:
        console.print(Text(f"  - {job.name} ({job.id})", style="paper"))

    if dry_run:
        console.print(Text("  --dry-run set; not running.", style="muted"))
        return

    for job in missed:
        try:
            run_research(
                prompt=job.prompt,
                provider_name=job.provider,
                model=job.model,
                system=job.system,
                max_tokens=job.max_tokens,
                temperature=job.temperature,
                web_search=job.web_search,
                job=job,
                sync_drive=job.sync_drive,
                notify=job.notify,
                quiet=auto,
                write_file=True,
            )
        except Exception as e:  # noqa: BLE001
            bonk(f"catch-up failed for {job.id}: {type(e).__name__}: {e}")


@app.command(name="_exec", hidden=True)
def _exec(job_id: str) -> None:
    """Internal: run a saved job. Crontab calls this."""
    from sleuth.workflows import run_research

    store = get_store()
    job = store.get_job(job_id)
    if not job:
        # write to stderr-ish via console; cron logs will catch it
        bonk(f"no job '{job_id}'.")
        raise typer.Exit(1)
    run_research(
        prompt=job.prompt,
        provider_name=job.provider,
        model=job.model,
        system=job.system,
        max_tokens=job.max_tokens,
        temperature=job.temperature,
        web_search=job.web_search,
        job=job,
        sync_drive=job.sync_drive,
        notify=job.notify,
        quiet=True,
        write_file=True,
    )


# --------------------------------------------------------------------------- #
# jobs subcommands
# --------------------------------------------------------------------------- #


@jobs_app.command("new")
def jobs_new(
    name: Optional[str] = typer.Option(None, "--name", help="A short label."),
    prompt: Optional[str] = typer.Option(None, "--prompt", help="The research prompt."),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
    system: Optional[str] = typer.Option(None, "--system", "-s"),
    max_tokens: int = typer.Option(4096, "--max-tokens"),
    temperature: Optional[float] = typer.Option(None, "--temp"),
    no_search: bool = typer.Option(False, "--no-search"),
    sync_drive: bool = typer.Option(False, "--drive"),
    notify: bool = typer.Option(True, "--notify/--no-notify"),
) -> None:
    """Define a saved job. If you skip flags you'll be prompted."""
    settings = get_settings()
    if not name:
        name = typer.prompt("Job name (e.g. 'morning-ai-news')")
    if not prompt:
        prompt = typer.prompt("Research prompt")
    if not model:
        model = typer.prompt("Model id", default=settings.default_model)
    if not provider:
        try:
            provider = provider_for_model(model)
        except ValueError:
            provider = typer.prompt("Provider (openai|anthropic|google)", default=settings.default_provider)

    job = Job(
        id=new_id(),
        name=name,
        prompt=prompt,
        provider=provider,
        model=model,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
        web_search=not no_search,
        sync_drive=sync_drive,
        notify=notify,
    )
    get_store().create_job(job)
    tick(f"saved job {job.id} '{job.name}'")
    console.print(Text(f"  next: sleuth jobs schedule {job.id} --daily 09:00", style="muted"))


@jobs_app.command("list")
def jobs_list() -> None:
    store = get_store()
    rows = store.list_jobs()
    if not rows:
        console.print(Text("  no jobs yet. try `sleuth jobs new`.", style="muted"))
        return
    table = Table(header_style="muted", border_style="rule")
    table.add_column("id")
    table.add_column("name")
    table.add_column("model")
    table.add_column("schedule")
    table.add_column("prompt")
    for j in rows:
        table.add_row(
            j.id,
            j.name,
            f"{j.provider}/{j.model}",
            j.schedule_label or Text("-", style="muted"),
            (j.prompt or "")[:60],
        )
    console.print(table)


@jobs_app.command("show")
def jobs_show(job_id: str) -> None:
    from sleuth.scheduler.eta import format_next_run

    job = get_store().get_job(job_id)
    if not job:
        bonk(f"no job '{job_id}'.")
        raise typer.Exit(1)
    header(job.name, f"{job.id}  -  {job.provider}/{job.model}")
    fact("prompt", job.prompt)
    fact("system", job.system or "-")
    fact("schedule", job.schedule_label or "-")
    fact("cron", job.cron_expr or "-")
    fact("next run", format_next_run(job.cron_expr))
    fact("drive", "yes" if job.sync_drive else "no")
    fact("notify", "yes" if job.notify else "no")


@jobs_app.command("edit")
def jobs_edit(
    job_id: str,
    name: Optional[str] = typer.Option(None, "--name"),
    prompt: Optional[str] = typer.Option(None, "--prompt"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="Pass an empty string to clear."),
    max_tokens: Optional[int] = typer.Option(None, "--max-tokens"),
    temperature: Optional[float] = typer.Option(None, "--temp", help="Use -1 to clear."),
    search: Optional[bool] = typer.Option(None, "--search/--no-search"),
    drive: Optional[bool] = typer.Option(None, "--drive/--no-drive"),
    notify: Optional[bool] = typer.Option(None, "--notify/--no-notify"),
) -> None:
    """Patch fields on a saved job. Only passes you give get changed."""
    store = get_store()
    job = store.get_job(job_id)
    if not job:
        bonk(f"no job '{job_id}'.")
        raise typer.Exit(1)

    fields: dict = {}
    if name is not None: fields["name"] = name
    if prompt is not None: fields["prompt"] = prompt
    if model is not None: fields["model"] = model
    if provider is not None: fields["provider"] = provider
    if system is not None:
        fields["system"] = system if system != "" else None
    if max_tokens is not None: fields["max_tokens"] = max_tokens
    if temperature is not None:
        fields["temperature"] = None if temperature < 0 else temperature
    if search is not None: fields["web_search"] = search
    if drive is not None: fields["sync_drive"] = drive
    if notify is not None: fields["notify"] = notify

    if not fields:
        bonk("nothing to change. pass at least one option.")
        raise typer.Exit(1)

    store.update_job(job_id, **fields)
    tick(f"tweaked {job_id}: {', '.join(fields.keys())}")


@jobs_app.command("rm")
def jobs_rm(job_id: str, force: bool = typer.Option(False, "--force", "-f")) -> None:
    store = get_store()
    job = store.get_job(job_id)
    if not job:
        bonk(f"no job '{job_id}'.")
        raise typer.Exit(1)
    if not force:
        ok = typer.confirm(f"Really delete job '{job.name}' ({job_id})?")
        if not ok:
            raise typer.Exit()
    # Best-effort cron cleanup.
    try:
        from sleuth.scheduler import remove_cron
        remove_cron(job_id)
    except Exception:
        pass
    store.delete_job(job_id)
    tick(f"binned {job_id}.")


@jobs_app.command("run")
def jobs_run(
    job_id: str,
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Run a saved job once, right now."""
    from sleuth.workflows import run_research
    job = get_store().get_job(job_id)
    if not job:
        bonk(f"no job '{job_id}'.")
        raise typer.Exit(1)
    run_research(
        prompt=job.prompt,
        provider_name=job.provider,
        model=job.model,
        system=job.system,
        max_tokens=job.max_tokens,
        temperature=job.temperature,
        web_search=job.web_search,
        job=job,
        sync_drive=job.sync_drive,
        notify=job.notify,
        quiet=quiet,
    )


@jobs_app.command("schedule")
def jobs_schedule(
    job_id: str,
    daily: Optional[str] = typer.Option(None, "--daily", help="HH:MM, e.g. 09:00"),
    weekly: Optional[str] = typer.Option(None, "--weekly", help="Comma days, e.g. mon,wed,fri"),
    at: Optional[str] = typer.Option(None, "--at", help="HH:MM (used with --weekly/--monthly)"),
    hourly: bool = typer.Option(False, "--hourly"),
    every: Optional[str] = typer.Option(None, "--every", help="e.g. 15m, 2h"),
    monthly: bool = typer.Option(False, "--monthly"),
    day: Optional[int] = typer.Option(None, "--day", help="Day of month for --monthly (1..28)"),
    cron: Optional[str] = typer.Option(None, "--cron", help="Raw 5-field cron expression."),
) -> None:
    """Hand a job to system cron."""
    from sleuth.scheduler import build_schedule, install_cron

    job = get_store().get_job(job_id)
    if not job:
        bonk(f"no job '{job_id}'.")
        raise typer.Exit(1)

    try:
        spec = build_schedule(
            daily=daily,
            weekly_days=weekly,
            weekly_at=at,
            hourly=hourly,
            every=every,
            monthly_day=day if monthly else None,
            monthly_at=at if monthly else None,
            raw_cron=cron,
        )
    except ValueError as e:
        bonk(str(e))
        raise typer.Exit(1)

    try:
        install_cron(job_id, spec.cron_expr)
    except Exception as e:
        bonk(f"crontab install failed: {e}")
        raise typer.Exit(1)

    get_store().update_job_schedule(job_id, spec.label, spec.cron_expr)
    tick(f"scheduled {job_id}: {spec.label}")
    console.print(Text(f"  cron: {spec.cron_expr}", style="muted"))

    # Also wire @reboot catchup so missed fires get run when the box comes back.
    from sleuth.scheduler import install_catchup_reboot
    try:
        if install_catchup_reboot():
            tick("installed @reboot catchup (handles missed fires after power loss / reboots).")
    except Exception as e:
        console.print(Text(f"  (couldn't install @reboot catchup: {e})", style="muted"))


@jobs_app.command("unschedule")
def jobs_unschedule(job_id: str) -> None:
    from sleuth.scheduler import remove_cron
    job = get_store().get_job(job_id)
    if not job:
        bonk(f"no job '{job_id}'.")
        raise typer.Exit(1)
    n = remove_cron(job_id)
    get_store().update_job_schedule(job_id, None, None)
    tick(f"removed {n} cron entr{'y' if n == 1 else 'ies'}.")


@jobs_app.command("reinstall")
def jobs_reinstall() -> None:
    """Rewrite all sleuth crontab entries using the current command format.

    Use this after upgrading sleuth: existing entries that were installed
    by an older version may use a command form that's vulnerable to CWD
    package-shadowing under cron. This rebuilds every entry from the
    cron_expr stored in the DB.
    """
    from sleuth.scheduler import install_cron, install_catchup_reboot

    store = get_store()
    scheduled = [j for j in store.list_jobs() if j.cron_expr]
    if not scheduled:
        console.print(Text("  no scheduled jobs to refresh.", style="muted"))
    n_jobs = 0
    for job in scheduled:
        try:
            install_cron(job.id, job.cron_expr)
            n_jobs += 1
            tick(f"refreshed {job.id} ({job.name})")
        except Exception as e:  # noqa: BLE001
            bonk(f"failed to refresh {job.id}: {e}")
    # Also re-do the @reboot line.
    try:
        # Remove and reinstall so the command text is rewritten too.
        from sleuth.scheduler import remove_catchup_reboot
        remove_catchup_reboot()
        install_catchup_reboot()
        tick("refreshed @reboot catchup line.")
    except Exception as e:  # noqa: BLE001
        bonk(f"failed to refresh @reboot: {e}")

    console.print(Text(f"  done. {n_jobs} job entr{'y' if n_jobs == 1 else 'ies'} rewritten.", style="muted"))


@jobs_app.command("crontab")
def jobs_crontab() -> None:
    """Show the cron entries sleuth has installed."""
    from sleuth.scheduler import list_cron
    entries = list_cron()
    if not entries:
        console.print(Text("  no sleuth cron entries.", style="muted"))
        return
    table = Table(header_style="muted", border_style="rule")
    table.add_column("job")
    table.add_column("cron")
    table.add_column("command")
    for jid, expr, cmd in entries:
        table.add_row(jid, expr, cmd[:80])
    console.print(table)


@jobs_app.command("logs")
def jobs_logs(
    job_id: str,
    lines: int = typer.Option(40, "--lines", "-n", help="How many trailing lines to show."),
) -> None:
    """Show recent log output from a scheduled job's runs."""
    settings = get_settings()
    log_path = settings.log_dir / f"{job_id}.log"
    if not log_path.exists():
        bonk(f"no log file at {log_path}.")
        console.print(Text(
            "  the cron job probably hasn't fired yet (or cron didn't run it).\n"
            "  try `sleuth jobs check " + job_id + "` for diagnostics.",
            style="muted",
        ))
        raise typer.Exit(1)
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = content[-lines:] if len(content) > lines else content
    header(f"logs: {job_id}", str(log_path))
    if not tail:
        console.print(Text("  (file exists but is empty)", style="muted"))
        return
    for line in tail:
        console.print(Text(f"  {line}", style="paper"))


@jobs_app.command("check")
def jobs_check(job_id: str) -> None:
    """Diagnose a scheduled job: show cron entry, log file status, env sanity."""
    import os
    import platform
    import subprocess

    from sleuth.scheduler import list_cron

    settings = get_settings()
    job = get_store().get_job(job_id)
    if not job:
        bonk(f"no job '{job_id}'.")
        raise typer.Exit(1)

    header(f"check: {job.name}", job_id)
    fact("schedule", job.schedule_label or "(not scheduled)")
    fact("cron expr", job.cron_expr or "-")
    log_path = settings.log_dir / f"{job_id}.log"
    fact("log path", str(log_path))

    entries = {jid: (expr, cmd) for jid, expr, cmd in list_cron()}
    if job_id in entries:
        tick("crontab entry present.")
        expr, cmd = entries[job_id]
        console.print(Text(f"  cron: {expr}", style="muted"))
        console.print(Text(f"  cmd:  {cmd}", style="muted"))
    else:
        bonk("no crontab entry. run `jobs schedule` to install one.")

    if log_path.exists():
        size = log_path.stat().st_size
        if size == 0:
            console.print(Text("  log file exists but is empty (cron may not have fired yet)", style="warn"))
        else:
            tick(f"log file: {size} bytes. tail with `sleuth jobs logs {job_id}`.")
    else:
        console.print(Text("  log file does not exist yet (cron has never run this job)", style="warn"))

    if platform.system() == "Darwin":
        console.print()
        console.print(Text(
            "  macOS gotcha: cron requires Full Disk Access. open System Settings\n"
            "  -> Privacy & Security -> Full Disk Access, click +, navigate to\n"
            "  /usr/sbin/cron (cmd+shift+G to type it), and tick the box.\n"
            "  no FDA = cron entries silently never run.",
            style="warn",
        ))


# --------------------------------------------------------------------------- #
# drive subcommands
# --------------------------------------------------------------------------- #


@drive_app.command("login")
def drive_login(
    client_secrets: Optional[str] = typer.Option(
        None, "--client-secrets", "-c",
        help="(Advanced) path to a client_secret*.json for a custom OAuth client.",
    ),
) -> None:
    """Connect Google Drive. Shows a QR + 8-char code; scan, allow, done.

    Uses sleuth's built-in OAuth client by default. Fall back to env vars
    SLEUTH_GOOGLE_CLIENT_ID/SECRET, or pass `--client-secrets PATH` to
    bring your own.
    """
    from pathlib import Path as _Path
    from sleuth.storage.gdrive import login, DriveNotConfigured, whoami, ensure_sleuth_folder
    from sleuth.storage.drive_client import describe_client

    console.print()
    console.print(Text("  oauth client: ", style="muted") + Text(describe_client(), style="paper"))

    secret_path = _Path(client_secrets) if client_secrets else None
    try:
        login(explicit_client_secret_path=secret_path)
    except DriveNotConfigured as e:
        bonk(str(e))
        raise typer.Exit(1)

    email = whoami()
    if email:
        tick(f"connected as {email}")

    # Offer to create / find a 'Sleuth' folder so output doesn't sprawl in
    # My Drive root.
    settings = get_settings()
    if not settings.gdrive_folder_id:
        if typer.confirm("  put runs in a 'Sleuth' folder in My Drive?", default=True):
            try:
                folder_id = ensure_sleuth_folder()
                # persist the folder id to .env so future runs use it
                from sleuth.setup_wizard import load_env_file, write_env_file, ENV_SECTIONS
                env_path = settings.db_path.parent.parent / ".env"
                env = load_env_file(env_path)
                env["GDRIVE_FOLDER_ID"] = folder_id
                write_env_file(env_path, env, sections=ENV_SECTIONS)
                tick(f"using folder 'Sleuth' (id saved to .env)")
            except Exception as e:  # noqa: BLE001
                bonk(f"couldn't set up folder: {e}")


@drive_app.command("logout")
def drive_logout() -> None:
    """Disconnect Drive by deleting the local token."""
    from sleuth.storage.gdrive import logout
    if logout():
        tick("token removed. you're signed out.")
    else:
        console.print(Text("  no token to remove.", style="muted"))


@drive_app.command("auth")
def drive_auth(
    client_secrets: Optional[str] = typer.Option(
        None, "--client-secrets", "-c",
    ),
) -> None:
    """Alias for `sleuth drive login` (kept for habit / older docs)."""
    drive_login(client_secrets=client_secrets)


@drive_app.command("status")
def drive_status() -> None:
    """Show what's currently set up."""
    from sleuth.storage import gdrive
    from sleuth.storage.drive_client import describe_client

    console.print()
    fact("client", describe_client())
    if gdrive.is_configured():
        tick("token present.")
        email = gdrive.whoami()
        if email:
            fact("account", email)
        settings = get_settings()
        if settings.gdrive_folder_id:
            fact("folder id", settings.gdrive_folder_id)
        else:
            fact("folder", "My Drive root (no folder pinned)")
    else:
        console.print(Text("  no token. run `sleuth drive login`.", style="warn"))


@drive_app.command("doctor")
def drive_doctor() -> None:
    """Diagnose the Drive setup end-to-end."""
    from sleuth.storage import gdrive
    from sleuth.storage.drive_client import has_client, describe_client

    console.print()
    header("drive doctor", "checking each piece")

    if has_client():
        tick(f"oauth client: {describe_client()}")
    else:
        bonk("no oauth client configured.")
        console.print(Text(
            "  fix: set SLEUTH_GOOGLE_CLIENT_ID + SLEUTH_GOOGLE_CLIENT_SECRET in .env,\n"
            "       or run `sleuth drive login --client-secrets PATH`.",
            style="muted",
        ))
        return

    if not gdrive.is_configured():
        bonk("no token. run `sleuth drive login`.")
        return
    tick("token present.")

    email = gdrive.whoami()
    if email:
        tick(f"can talk to drive: {email}")
    else:
        bonk("token exists but can't reach the Drive API. token may be revoked.")
        return

    settings = get_settings()
    if settings.gdrive_folder_id:
        tick(f"folder id pinned: {settings.gdrive_folder_id}")
    else:
        console.print(Text(
            "  no folder pinned; runs will land in My Drive root (or auto-create 'Sleuth').",
            style="muted",
        ))


@drive_app.command("setup")
def drive_setup_alias() -> None:
    """Alias for `sleuth drive login`. Kept so older muscle memory still works."""
    console.print(Text("  `drive setup` is now `drive login`. running login...", style="muted"))
    drive_login(client_secrets=None)


if __name__ == "__main__":
    app()
