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
reddit_app = typer.Typer(no_args_is_help=True, help="Reddit pre-fetch helpers.")
app.add_typer(jobs_app, name="jobs")
app.add_typer(drive_app, name="drive")
app.add_typer(reddit_app, name="reddit")


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


@app.command("install-shim")
def install_shim_cmd(
    force: bool = typer.Option(False, "--force", "-f", help="Replace any existing shim."),
) -> None:
    """Create ~/.local/bin/sleuth so the `sleuth` command works anywhere.

    After running this once, you can type `sleuth` from any directory
    without activating the venv first. ~/.local/bin is on PATH by default
    on Pi OS Bookworm and modern macOS.
    """
    from sleuth.installer import (
        default_shim_path,
        install_shim,
        local_bin_on_path,
        sleuth_binary_path,
    )

    source = sleuth_binary_path()
    if source is None:
        bonk("no `sleuth` binary in this venv. did you `pip install -e .`?")
        raise typer.Exit(1)

    shim = default_shim_path()
    try:
        result = install_shim(shim_path=shim, source=source, force=force)
    except FileExistsError as e:
        bonk(str(e))
        console.print(Text("  re-run with --force to replace it.", style="muted"))
        raise typer.Exit(1)

    tick(f"shim ready: {result}  ->  {source}")
    if not local_bin_on_path():
        console.print(Text(
            "  warning: ~/.local/bin is NOT on your $PATH. add this to ~/.bashrc:\n"
            '    export PATH="$HOME/.local/bin:$PATH"\n'
            "  then `exec $SHELL -l` to pick it up.",
            style="warn",
        ))
    else:
        console.print(Text("  ~/.local/bin is on PATH — `sleuth` works from anywhere now.", style="ok"))


@app.command("doctor")
def doctor() -> None:
    """End-to-end health check: install shim, PATH, cron daemon, scheduled jobs."""
    import platform
    from sleuth.installer import (
        cron_status,
        default_shim_path,
        has_cron_binary,
        local_bin_on_path,
        sleuth_binary_path,
    )
    from sleuth.scheduler import has_catchup_reboot, list_cron

    console.print()
    header("sleuth doctor", "checking each piece")

    # 1. shim + PATH
    shim = default_shim_path()
    bin_ = sleuth_binary_path()
    if bin_ is None:
        bonk("no `sleuth` binary in this venv. run `pip install -e .` first.")
        raise typer.Exit(1)
    if shim.exists() and shim.is_symlink() and shim.resolve() == bin_.resolve():
        tick(f"global shim installed: {shim}")
    else:
        bonk(f"global shim NOT installed at {shim}")
        console.print(Text("  fix: sleuth install-shim", style="muted"))

    if local_bin_on_path():
        tick("~/.local/bin is on $PATH.")
    else:
        bonk("~/.local/bin is NOT on $PATH.")
        console.print(Text(
            "  fix: add `export PATH=\"$HOME/.local/bin:$PATH\"` to ~/.bashrc, then\n"
            "       exec $SHELL -l",
            style="muted",
        ))

    # 2. cron
    if platform.system() == "Darwin":
        console.print(Text(
            "  (macOS detected: cron requires Full Disk Access for /usr/sbin/cron.\n"
            "   if scheduled jobs never fire, that's almost certainly why.\n"
            "   System Settings -> Privacy & Security -> Full Disk Access -> +.)",
            style="muted",
        ))
    else:
        if not has_cron_binary():
            bonk("`cron` not installed.")
            console.print(Text("  fix: sudo apt install cron", style="muted"))
        else:
            cs = cron_status()
            if cs == "active":
                tick("cron daemon is active.")
            elif cs == "inactive":
                bonk("cron daemon is INSTALLED but NOT RUNNING.")
                console.print(Text(
                    "  fix: sudo systemctl enable --now cron",
                    style="muted",
                ))
            elif cs == "failed":
                bonk("cron daemon failed to start.")
                console.print(Text(
                    "  fix: sudo systemctl restart cron  &&  systemctl status cron",
                    style="muted",
                ))
            elif cs == "unknown":
                console.print(Text(
                    "  cron status: unknown (systemctl unavailable on this OS).",
                    style="muted",
                ))

    # 3. @reboot catchup
    try:
        if has_catchup_reboot():
            tick("@reboot catchup line installed.")
        else:
            console.print(Text(
                "  no @reboot catchup line. install with: sleuth catchup --install",
                style="muted",
            ))
    except Exception:
        pass  # crontab access failed; don't crash the doctor

    # 4. scheduled jobs sanity
    try:
        entries = list_cron()
        store = get_store()
        scheduled_jobs = [j for j in store.list_jobs() if j.cron_expr]
        if not scheduled_jobs:
            console.print(Text("  no scheduled jobs to check.", style="muted"))
        else:
            tick(f"{len(scheduled_jobs)} scheduled job(s) in the DB.")
            entry_ids = {jid for jid, _, _ in entries}
            db_ids = {j.id for j in scheduled_jobs}
            missing = db_ids - entry_ids
            if missing:
                bonk(f"jobs in DB but missing from crontab: {', '.join(missing)}")
                console.print(Text("  fix: sleuth jobs reinstall", style="muted"))
            # entries pointing at old-style command form?
            from sleuth.scheduler.cron import _venv_sleuth_path
            expected_prefix = str(_venv_sleuth_path() or "")
            if expected_prefix:
                stale = [
                    jid for jid, _, cmd in entries
                    if not cmd.lstrip().startswith(expected_prefix)
                       and " -m sleuth " in cmd and "cd " not in cmd
                ]
                if stale:
                    bonk(f"crontab entries use the old (broken) command form: {', '.join(stale)}")
                    console.print(Text("  fix: sleuth jobs reinstall", style="muted"))
    except Exception as e:  # noqa: BLE001
        console.print(Text(f"  (skipped scheduled-job check: {e})", style="muted"))


# --------------------------------------------------------------------------- #
# top-level: ask, models, history, show, init, ping, _exec
# --------------------------------------------------------------------------- #


def _split_csv(values: Optional[list[str]]) -> list[str]:
    """Accept either ['a,b,c'] or ['a','b','c'] from repeated typer options."""
    out: list[str] = []
    for v in values or []:
        for part in str(v).split(","):
            p = part.strip()
            if p.lower().startswith("r/"):
                p = p[2:].strip()
            if p:
                out.append(p)
    return out


def _build_reddit_spec_from_flags(
    *,
    enabled: bool,
    subs: Optional[list[str]],
    query: Optional[str],
    sort: Optional[str],
    time_filter: Optional[str],
    top_posts: Optional[int],
    comment_strategy: Optional[str],
    max_comments: Optional[int],
    max_depth: Optional[int],
    fallback_query: Optional[str] = None,
):
    """Translate CLI flags into a RedditSearchSpec (or None when disabled)."""
    from sleuth.sources.reddit import RedditSearchSpec

    if not enabled:
        return None
    sublist = _split_csv(subs)
    eff_query = query if query is not None else fallback_query
    if eff_query == "":
        eff_query = None
    # Sensible default sort: if there's a query, use 'relevance'; otherwise 'hot'.
    eff_sort = sort or ("relevance" if eff_query else "hot")
    spec = RedditSearchSpec(
        subreddits=sublist,
        query=eff_query,
        sort=eff_sort,
        time_filter=time_filter or "week",
        top_posts=top_posts if top_posts is not None else 10,
        comment_strategy=comment_strategy or "none",
        max_comments=max_comments if max_comments is not None else 20,
        max_comment_depth=max_depth if max_depth is not None else 3,
    )
    spec.validate()
    return spec


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
    reddit: bool = typer.Option(False, "--reddit", help="Pre-fetch from Reddit and prepend as context."),
    reddit_sub: Optional[list[str]] = typer.Option(
        None, "--reddit-sub", help="Subreddit to pull from (repeatable, or comma-separated). Default: r/all.",
    ),
    reddit_query: Optional[str] = typer.Option(
        None, "--reddit-query", help="Override the search query (default: same as prompt).",
    ),
    reddit_sort: Optional[str] = typer.Option(
        None, "--reddit-sort", help="relevance|top|new|hot|comments (search) or hot|new|top|rising (browse).",
    ),
    reddit_time: Optional[str] = typer.Option(
        None, "--reddit-time", help="hour|day|week|month|year|all (used by top/relevance).",
    ),
    reddit_top: Optional[int] = typer.Option(
        None, "--reddit-top", help="Max posts to include (default 10).",
    ),
    reddit_comments: Optional[str] = typer.Option(
        None, "--reddit-comments", help="none|top_score|top_replies|all (default none).",
    ),
    reddit_max_comments: Optional[int] = typer.Option(
        None, "--reddit-max-comments", help="Cap comments per post (default 20).",
    ),
    reddit_depth: Optional[int] = typer.Option(
        None, "--reddit-depth", help="Max comment thread depth (default 3).",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="No fancy UI; just the answer."),
) -> None:
    """One-off research turn."""
    from sleuth.workflows import run_research

    try:
        reddit_spec = _build_reddit_spec_from_flags(
            enabled=reddit,
            subs=reddit_sub,
            query=reddit_query,
            sort=reddit_sort,
            time_filter=reddit_time,
            top_posts=reddit_top,
            comment_strategy=reddit_comments,
            max_comments=reddit_max_comments,
            max_depth=reddit_depth,
            fallback_query=prompt,
        )
    except ValueError as e:
        bonk(f"bad --reddit options: {e}")
        raise typer.Exit(1)

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
        reddit_spec=reddit_spec,
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
    reddit: bool = typer.Option(False, "--reddit"),
    reddit_sub: Optional[list[str]] = typer.Option(None, "--reddit-sub"),
    reddit_query: Optional[str] = typer.Option(None, "--reddit-query"),
    reddit_sort: Optional[str] = typer.Option(None, "--reddit-sort"),
    reddit_time: Optional[str] = typer.Option(None, "--reddit-time"),
    reddit_top: Optional[int] = typer.Option(None, "--reddit-top"),
    reddit_comments: Optional[str] = typer.Option(None, "--reddit-comments"),
    reddit_max_comments: Optional[int] = typer.Option(None, "--reddit-max-comments"),
    reddit_depth: Optional[int] = typer.Option(None, "--reddit-depth"),
) -> None:
    """Define a saved job. If you skip flags you'll be prompted."""
    from sleuth.sources.reddit import spec_to_dict

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

    reddit_spec_dict = None
    if reddit:
        try:
            spec = _build_reddit_spec_from_flags(
                enabled=True,
                subs=reddit_sub,
                query=reddit_query,
                sort=reddit_sort,
                time_filter=reddit_time,
                top_posts=reddit_top,
                comment_strategy=reddit_comments,
                max_comments=reddit_max_comments,
                max_depth=reddit_depth,
                fallback_query=prompt,
            )
        except ValueError as e:
            bonk(f"bad --reddit options: {e}")
            raise typer.Exit(1)
        reddit_spec_dict = spec_to_dict(spec) if spec else None

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
        reddit_enabled=bool(reddit_spec_dict),
        reddit_spec=reddit_spec_dict,
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
    from sleuth.scheduler.eta import format_next_run, describe_local_tz

    job = get_store().get_job(job_id)
    if not job:
        bonk(f"no job '{job_id}'.")
        raise typer.Exit(1)
    header(job.name, f"{job.id}  -  {job.provider}/{job.model}")
    fact("prompt", job.prompt)
    fact("system", job.system or "-")
    fact("schedule", job.schedule_label or "-")
    if job.cron_expr:
        fact("cron (local)", f"{job.cron_expr}  (interpreted in {describe_local_tz()})")
    else:
        fact("cron", "-")
    fact("next run", format_next_run(job.cron_expr))
    fact("drive", "yes" if job.sync_drive else "no")
    fact("notify", "yes" if job.notify else "no")
    if job.reddit_enabled and job.reddit_spec:
        spec = job.reddit_spec
        subs = spec.get("subreddits") or []
        sub_label = ", ".join(
            f"r/{(s[2:].strip() if s.lower().startswith('r/') else s.strip())}"
            for s in subs
        ) if subs else "r/all"
        fact("reddit", sub_label)
        if spec.get("query"):
            fact("reddit query", spec["query"])
        fact(
            "reddit sort",
            f"{spec.get('sort','?')} (time: {spec.get('time_filter','?')})",
        )
        fact(
            "reddit posts",
            f"top {spec.get('top_posts',10)} — comments: {spec.get('comment_strategy','none')}"
            + (
                f" (cap {spec.get('max_comments',20)}, depth {spec.get('max_comment_depth',3)})"
                if spec.get("comment_strategy") != "none" else ""
            ),
        )
    else:
        fact("reddit", "off")


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
    reddit: Optional[bool] = typer.Option(None, "--reddit/--no-reddit", help="Turn reddit pre-fetch on/off."),
    reddit_sub: Optional[list[str]] = typer.Option(None, "--reddit-sub", help="Replace the subreddit list."),
    reddit_query: Optional[str] = typer.Option(None, "--reddit-query"),
    reddit_sort: Optional[str] = typer.Option(None, "--reddit-sort"),
    reddit_time: Optional[str] = typer.Option(None, "--reddit-time"),
    reddit_top: Optional[int] = typer.Option(None, "--reddit-top"),
    reddit_comments: Optional[str] = typer.Option(None, "--reddit-comments"),
    reddit_max_comments: Optional[int] = typer.Option(None, "--reddit-max-comments"),
    reddit_depth: Optional[int] = typer.Option(None, "--reddit-depth"),
) -> None:
    """Patch fields on a saved job. Only passes you give get changed."""
    from sleuth.sources.reddit import spec_from_dict, spec_to_dict

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

    # Reddit edits: merge any partial flag with whatever's stored.
    reddit_touched = any(
        v is not None for v in (
            reddit, reddit_sub, reddit_query, reddit_sort, reddit_time,
            reddit_top, reddit_comments, reddit_max_comments, reddit_depth,
        )
    )
    if reddit is False:
        fields["reddit_enabled"] = False
        fields["reddit_spec"] = None
    elif reddit_touched:
        existing_spec = spec_from_dict(job.reddit_spec) if job.reddit_spec else None
        merged_subs = (
            _split_csv(reddit_sub)
            if reddit_sub is not None
            else (existing_spec.subreddits if existing_spec else [])
        )
        merged_query = (
            reddit_query
            if reddit_query is not None
            else (existing_spec.query if existing_spec else None)
        )
        if merged_query == "":
            merged_query = None
        merged_sort = reddit_sort or (existing_spec.sort if existing_spec else None) or (
            "relevance" if merged_query else "hot"
        )
        try:
            spec = _build_reddit_spec_from_flags(
                enabled=True,
                subs=[",".join(merged_subs)] if merged_subs else None,
                query=merged_query,
                sort=merged_sort,
                time_filter=reddit_time or (existing_spec.time_filter if existing_spec else None),
                top_posts=reddit_top if reddit_top is not None else (existing_spec.top_posts if existing_spec else None),
                comment_strategy=reddit_comments or (existing_spec.comment_strategy if existing_spec else None),
                max_comments=reddit_max_comments if reddit_max_comments is not None else (existing_spec.max_comments if existing_spec else None),
                max_depth=reddit_depth if reddit_depth is not None else (existing_spec.max_comment_depth if existing_spec else None),
                fallback_query=job.prompt,
            )
        except ValueError as e:
            bonk(f"bad --reddit options: {e}")
            raise typer.Exit(1)
        fields["reddit_enabled"] = True
        fields["reddit_spec"] = spec_to_dict(spec) if spec else None

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
    daily: Optional[str] = typer.Option(None, "--daily", help="HH:MM in LOCAL time, e.g. 09:00"),
    weekly: Optional[str] = typer.Option(None, "--weekly", help="Comma days, e.g. mon,wed,fri"),
    at: Optional[str] = typer.Option(None, "--at", help="HH:MM in LOCAL time (used with --weekly/--monthly)"),
    hourly: bool = typer.Option(False, "--hourly"),
    every: Optional[str] = typer.Option(None, "--every", help="e.g. 15m, 2h"),
    monthly: bool = typer.Option(False, "--monthly"),
    day: Optional[int] = typer.Option(None, "--day", help="Day of month for --monthly (1..28)"),
    cron: Optional[str] = typer.Option(None, "--cron", help="Raw 5-field cron expression (interpreted in LOCAL time)."),
) -> None:
    """Hand a job to system cron.

    All times are interpreted in the system's local timezone — that's what
    the cron daemon itself does. `sleuth jobs show` displays the resolved
    next-fire time in UTC so there's no ambiguity.
    """
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

    from sleuth.scheduler.eta import describe_local_tz, format_next_run
    console.print(Text(
        f"  cron: {spec.cron_expr}   (interpreted in {describe_local_tz()})",
        style="muted",
    ))
    console.print(Text(f"  next run: {format_next_run(spec.cron_expr)}", style="muted"))

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


# --------------------------------------------------------------------------- #
# reddit subcommands
# --------------------------------------------------------------------------- #


@reddit_app.command("status")
def reddit_status() -> None:
    """Show whether Reddit pre-fetch credentials are configured."""
    from sleuth.sources.reddit import DEFAULT_USER_AGENT, is_configured

    settings = get_settings()
    console.print()
    if is_configured():
        tick("reddit credentials present.")
        fact("client id", _short_str(settings.reddit_client_id))
        fact("client secret", _short_str(settings.reddit_client_secret))
        fact("user agent", settings.reddit_user_agent or DEFAULT_USER_AGENT)
    else:
        bonk("reddit not configured.")
        console.print(Text(
            "  set REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET in .env\n"
            "  or run `sleuth setup` and pick the reddit step.",
            style="muted",
        ))


@reddit_app.command("test")
def reddit_test(
    sub: Optional[list[str]] = typer.Option(
        None, "--sub", help="Subreddit (repeatable, comma-separated ok). Default: r/python.",
    ),
    query: Optional[str] = typer.Option(None, "--query", help="Search query (default: browse only)."),
    sort: Optional[str] = typer.Option(None, "--sort"),
    time_filter: Optional[str] = typer.Option(None, "--time"),
    top: int = typer.Option(3, "--top", help="How many posts to pull."),
    comments: str = typer.Option("none", "--comments", help="none|top_score|top_replies|all"),
    max_comments: int = typer.Option(5, "--max-comments"),
    depth: int = typer.Option(2, "--depth"),
    raw: bool = typer.Option(False, "--raw", help="Dump the formatted markdown block."),
) -> None:
    """Smoke test: pull a few posts to confirm credentials and formatting work."""
    from sleuth.sources.reddit import (
        RedditFetchError,
        fetch as reddit_fetch,
        format_for_llm,
        is_configured,
    )

    if not is_configured():
        bonk("reddit not configured. run `sleuth setup` first.")
        raise typer.Exit(1)

    try:
        spec = _build_reddit_spec_from_flags(
            enabled=True,
            subs=sub or ["python"],
            query=query,
            sort=sort,
            time_filter=time_filter,
            top_posts=top,
            comment_strategy=comments,
            max_comments=max_comments,
            max_depth=depth,
        )
    except ValueError as e:
        bonk(str(e))
        raise typer.Exit(1)

    try:
        digest = reddit_fetch(spec)
    except RedditFetchError as e:
        bonk(str(e))
        raise typer.Exit(1)

    tick(f"pulled {len(digest.posts)} post(s).")
    if raw:
        console.print()
        console.print(format_for_llm(digest))
        return
    for i, post in enumerate(digest.posts, 1):
        console.print(Text(f"  {i}. ", style="muted") + Text(post.title[:90], style="paper"))
        console.print(Text(
            f"     r/{post.subreddit} · u/{post.author} · score {post.score} · "
            f"{post.num_comments} comments · {len(post.comments)} pulled",
            style="muted",
        ))


def _short_str(v: Optional[str]) -> str:
    if not v:
        return "(unset)"
    if len(v) <= 12:
        return v
    return f"{v[:6]}...{v[-4:]}"


if __name__ == "__main__":
    app()
