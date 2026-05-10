"""Rich Console singleton plus a few helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live
from rich.text import Text

from sleuth.ui.theme import THEME
from sleuth.ui import verbs as verb_dict
from sleuth.ui import spinners as spin_lib


_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=THEME, soft_wrap=False, highlight=False)
    return _console


# convenience
console = get_console()


def say(msg: str, style: str | None = None) -> None:
    get_console().print(msg, style=style)


def header(title: str, subtitle: str | None = None) -> None:
    c = get_console()
    c.print()
    c.print(Text(title, style="header"))
    if subtitle:
        c.print(Text(f"  {subtitle}", style="muted"))
    c.print()


def fact(label: str, value: str) -> None:
    """One-liner factoid like:  provider  openai
                                model     gpt-5.5"""
    c = get_console()
    line = Text()
    line.append(f"  {label:<12}", style="muted")
    line.append(" ", style="muted")
    line.append(value, style="paper")
    c.print(line)


@contextmanager
def phase(
    name: str,
    verb_override: str | None = None,
    *,
    rotate: bool = True,
    rotate_every: float = 2.5,
) -> Iterator["PhaseHandle"]:
    """Live spinner with a random verb that rotates while you wait.

        with phase("search") as p:
            do_work()
            p.update("compose")  # explicit transition
    """
    from sleuth.ui.rotator import VerbRotator

    verb = verb_override or verb_dict.pick(name)
    spin_def = spin_lib.frames_for(name)

    spinner = Spinner("dots")
    spinner.frames = spin_def["frames"]
    spinner.interval = spin_def["interval"] / 1000.0
    spinner.update(text=_phase_text(name, verb))

    live = Live(
        spinner,
        console=get_console(),
        refresh_per_second=12,
        transient=True,
    )
    handle = PhaseHandle(spinner, live, name, verb)

    rotator: VerbRotator | None = None
    if rotate and verb_override is None:
        rotator = VerbRotator(
            phase=name,
            on_verb=lambda v: handle.update(verb=v),
            interval=rotate_every,
        )
        handle._rotator = rotator

    try:
        live.start()
        if rotator is not None:
            rotator.start()
        yield handle
    finally:
        if rotator is not None:
            rotator.stop()
        live.stop()


def _phase_text(phase_name: str, verb: str) -> Text:
    style = f"phase.{phase_name}" if phase_name in {"search", "think", "wait", "save"} else "verb"
    t = Text()
    t.append(f" {verb}", style=style)
    t.append("...", style="muted")
    return t


class PhaseHandle:
    def __init__(self, spinner: Spinner, live: Live, phase_name: str, verb: str):
        self._spinner = spinner
        self._live = live
        self._rotator = None  # set by phase() if rotation is enabled
        self.phase = phase_name
        self.verb = verb

    def update(self, phase_name: str | None = None, verb: str | None = None) -> None:
        if phase_name:
            self.phase = phase_name
            spin_def = spin_lib.frames_for(phase_name)
            self._spinner.frames = spin_def["frames"]
            self._spinner.interval = spin_def["interval"] / 1000.0
            if self._rotator is not None:
                self._rotator.set_phase(phase_name)
        if verb is None:
            verb = verb_dict.pick(self.phase)
        self.verb = verb
        self._spinner.update(text=_phase_text(self.phase, verb))


def tick(message: str) -> None:
    """Inline 'check' for completed steps."""
    c = get_console()
    line = Text()
    line.append("  + ", style="ok")
    line.append(message, style="paper")
    c.print(line)


def bonk(message: str) -> None:
    """Inline complaint."""
    c = get_console()
    line = Text()
    line.append("  ! ", style="bad")
    line.append(message, style="paper")
    c.print(line)
