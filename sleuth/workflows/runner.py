"""End-to-end research workflow: call provider, save, sync, ping."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from sleuth.config import get_settings
from sleuth.providers import get_provider, provider_for_model
from sleuth.providers.base import ResearchResult
from sleuth.storage import Job, Run, get_store, new_id
from sleuth.storage.sqlite_store import utcnow
from sleuth.ui import console, verbs as verb_dict
from sleuth.ui.console import (
    bonk,
    fact,
    header,
    phase as ui_phase,
    tick,
)


def _slugify(s: str, max_len: int = 50) -> str:
    s = re.sub(r"\s+", "-", s.strip().lower())
    s = re.sub(r"[^a-z0-9_-]", "", s)
    s = re.sub(r"-+", "-", s)
    return (s[:max_len] or "run").strip("-") or "run"


def _markdown_for_run(
    *, prompt: str, result: ResearchResult, started_at: str
) -> str:
    lines = [
        f"# {prompt[:80]}",
        "",
        f"_Run on {started_at} by sleuth using **{result.provider}/{result.model}**._",
        "",
        "## Prompt",
        "",
        prompt,
        "",
        "## Findings",
        "",
        result.text or "_(empty)_",
    ]
    if result.citations:
        lines.append("")
        lines.append("## Sources")
        lines.append("")
        for i, c in enumerate(result.citations, 1):
            title = c.title or c.url
            lines.append(f"{i}. [{title}]({c.url})")
    lines.append("")
    lines.append(
        f"_tokens in/out: {result.tokens_in}/{result.tokens_out} - "
        f"web searches: {result.search_calls}_"
    )
    return "\n".join(lines)


def _write_output_file(slug: str, run_id: str, body: str) -> Path:
    settings = get_settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = settings.output_dir / f"{stamp}_{slug}_{run_id}.md"
    path.write_text(body, encoding="utf-8")
    return path


def render_result(
    *,
    prompt: str,
    result: ResearchResult,
    output_path: Optional[Path] = None,
    gdrive_url: Optional[str] = None,
    run_id: Optional[str] = None,
    quiet: bool = False,
) -> None:
    """Pretty-print a finished research result to the console."""
    if quiet:
        return
    c = console
    c.print()
    c.print(Panel(Markdown(result.text or "_(no content)_"), title=Text(prompt[:80], style="header"), border_style="rule"))
    if result.citations:
        c.print()
        c.print(Text("  sources", style="muted"))
        for i, cit in enumerate(result.citations, 1):
            label = cit.title or cit.url
            line = Text()
            line.append(f"  {i:>2}. ", style="muted")
            line.append(label[:80], style="paper")
            line.append("  ")
            line.append(cit.url, style="citation")
            c.print(line)
    c.print()
    line = Text("  ")
    line.append(f"tokens {result.tokens_in}/{result.tokens_out}  ", style="muted")
    line.append(f"searches {result.search_calls}  ", style="muted")
    if run_id:
        line.append(f"run {run_id}  ", style="muted")
    c.print(line)
    if output_path:
        c.print(Text(f"  filed at {output_path}", style="ok"))
    if gdrive_url:
        c.print(Text(f"  on Drive at {gdrive_url}", style="ok"))


def run_research(
    *,
    prompt: str,
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
    system: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: Optional[float] = None,
    web_search: bool = True,
    job: Optional[Job] = None,
    sync_drive: bool = False,
    notify: bool = False,
    quiet: bool = False,
    write_file: bool = True,
) -> Run:
    """Run a research turn end-to-end. Returns the persisted Run."""
    settings = get_settings()

    # Resolve provider/model
    if model is None:
        model = settings.default_model
    if provider_name is None:
        try:
            provider_name = provider_for_model(model)
        except ValueError:
            provider_name = settings.default_provider

    store = get_store()
    run_id = new_id()
    started = utcnow()
    run = Run(
        id=run_id,
        job_id=job.id if job else None,
        prompt=prompt,
        provider=provider_name,
        model=model,
        started_at=started,
    )
    store.start_run(run)

    if not quiet:
        header("sleuth", verb_dict.pick("wakeup"))
        fact("provider", provider_name)
        fact("model", model)
        if web_search:
            fact("web search", "on")
        if job and job.name:
            fact("job", f"{job.name} ({job.id})")

    result: Optional[ResearchResult] = None
    error: Optional[str] = None

    try:
        provider = get_provider(provider_name)
        if quiet:
            result = provider.run(
                prompt,
                model=model,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                web_search=web_search,
            )
        else:
            with ui_phase("search") as p:
                # We don't get streaming events from these tool calls, so
                # we rotate the verb a few times for life. The actual call
                # blocks, so we just kick off and wait.
                result = provider.run(
                    prompt,
                    model=model,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    web_search=web_search,
                )
                p.update("compose", verb_dict.pick("compose"))
    except Exception as e:  # noqa: BLE001 - we want to log any failure
        error = f"{type(e).__name__}: {e}"
        store.finish_run(run_id, status="error", error=error)
        if not quiet:
            bonk(f"{verb_dict.pick('error')}: {error}")
        # Optional notify on failure (fan out to whatever's configured)
        if notify:
            try:
                from sleuth.notify import notify_all
                notify_all(
                    f"*sleuth* {verb_dict.pick('error').lower()} on "
                    f"`{provider_name}/{model}`\n```\n{error[:400]}\n```",
                    silent=True,
                )
            except Exception:
                pass
        raise

    assert result is not None
    if not quiet:
        tick(f"{verb_dict.pick('compose')}.")

    output_path: Optional[Path] = None
    if write_file:
        slug = _slugify(prompt)
        body_md = _markdown_for_run(prompt=prompt, result=result, started_at=started)
        output_path = _write_output_file(slug, run_id, body_md)
        if not quiet:
            tick(f"{verb_dict.pick('save')}: {output_path.name}")

    gdrive_url: Optional[str] = None
    if sync_drive:
        try:
            from sleuth.storage import gdrive  # noqa: WPS433
            title = f"sleuth - {prompt[:60]} - {started}"
            body_md = _markdown_for_run(prompt=prompt, result=result, started_at=started)
            gdrive_url = gdrive.upload_doc(title, body_md)
            if not quiet:
                tick(f"{verb_dict.pick('drive')}: {gdrive_url}")
        except Exception as e:  # noqa: BLE001
            if not quiet:
                bonk(f"drive sync skipped: {e}")

    store.finish_run(
        run_id,
        status="done",
        output=result.text,
        citations=[c.to_dict() for c in result.citations],
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        search_calls=result.search_calls,
        gdrive_url=gdrive_url,
        output_path=str(output_path) if output_path else None,
    )

    if notify:
        try:
            from sleuth.notify import notify_run_finished
            delivered = notify_run_finished(
                provider=provider_name,
                model=model,
                prompt=prompt,
                body=(result.text or "").strip(),
                gdrive_url=gdrive_url,
            )
            if delivered and not quiet:
                tick(f"{verb_dict.pick('ping')} via {', '.join(delivered)}.")
        except Exception as e:  # noqa: BLE001
            if not quiet:
                bonk(f"notify skipped: {e}")

    fresh = store.get_run(run_id) or run
    if not quiet:
        render_result(
            prompt=prompt,
            result=result,
            output_path=output_path,
            gdrive_url=gdrive_url,
            run_id=run_id,
        )
    return fresh
