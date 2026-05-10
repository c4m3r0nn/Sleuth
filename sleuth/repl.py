"""Interactive shell. Bare `sleuth` opens this.

The pure helpers (parse_line, is_meta, top_level_words, subcommand_words) are
unit-tested. The interactive loop uses prompt_toolkit and is exercised by hand.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Optional


META_COMMANDS = {"exit", "quit", "q", "help", "?", "clear", "cls"}

_TOP_LEVEL = (
    "ask", "models", "history", "show", "setup", "init", "ping",
    "jobs", "drive",
    "help", "?", "exit", "quit", "q", "clear", "cls",
)
_SUBCOMMANDS: dict[str, tuple[str, ...]] = {
    "jobs": ("new", "list", "show", "edit", "rm", "run", "schedule", "unschedule", "crontab"),
    "drive": ("auth", "status"),
}


class ParseError(ValueError):
    """Raised when a line can't be tokenized (e.g. unclosed quote)."""


def parse_line(line: str) -> list[str]:
    """Split a REPL input line into argv tokens. Returns [] for empty/comment."""
    s = line.strip()
    if not s or s.startswith("#"):
        return []
    try:
        tokens = shlex.split(s, posix=True)
    except ValueError as e:
        raise ParseError(str(e)) from e
    # Allow paste of `sleuth ...` from a transcript without breaking.
    if tokens and tokens[0] == "sleuth":
        tokens = tokens[1:]
    return tokens


def is_meta(tokens: list[str]) -> bool:
    return bool(tokens) and tokens[0] in META_COMMANDS


def top_level_words() -> list[str]:
    return list(_TOP_LEVEL)


def subcommand_words(parent: str) -> list[str]:
    return list(_SUBCOMMANDS.get(parent, ()))


# --------------------------------------------------------------------------- #
# interactive loop (lazy imports so unit tests don't need prompt_toolkit)
# --------------------------------------------------------------------------- #


_HELP_TEXT = """\
  built-in commands (type the bare name and i'll walk you through):
    ask                   one-off research turn
    jobs new              save a recurring research job
    jobs list             show saved jobs
    jobs show             inspect a job
    jobs edit             change fields on a job
    jobs run              run a saved job once
    jobs schedule         hand a job to system cron
    jobs unschedule       take it back off cron
    jobs rm               delete a job
    jobs crontab          show installed cron entries
    history               browse past runs
    show                  dump a past run
    drive auth/status     google drive sync
    models                list available models
    setup                 first-run wizard (writes .env)
    init                  status check
    ping                  test telegram/discord nudges

  you can also still pass full args yourself, e.g.:
    ask whats happening today
    jobs schedule abc --daily 09:00

  shell controls:
    help, ?               show this
    clear, cls            wipe the screen
    exit, quit, q, ctrl-d leave
"""


def _make_completer():
    from prompt_toolkit.completion import (
        Completer,
        Completion,
        WordCompleter,
    )

    class TwoLevelCompleter(Completer):
        def __init__(self):
            self._top = WordCompleter(top_level_words(), ignore_case=True)

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor.lstrip()
            tokens = text.split()
            # First word -> top-level
            if not tokens or (len(tokens) == 1 and not text.endswith(" ")):
                yield from self._top.get_completions(document, complete_event)
                return
            # Second word and parent has subcommands
            parent = tokens[0]
            subs = subcommand_words(parent)
            if not subs:
                return
            # offering 2nd-token completions
            current = "" if text.endswith(" ") else tokens[-1]
            for w in subs:
                if w.startswith(current):
                    yield Completion(w, start_position=-len(current))

    return TwoLevelCompleter()


def _make_key_bindings():
    """Bindings: Enter on a highlighted completion accepts it without submitting.

    With complete_while_typing=True we get a popup while you type. If the
    user has used Tab/arrow-down to highlight a suggestion, pressing Enter
    fills it in (and stays on the line so they can keep typing args).
    Pressing Enter on its own (no completion highlighted) submits as normal.
    """
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.filters import completion_is_selected

    kb = KeyBindings()

    @kb.add("enter", filter=completion_is_selected)
    def _accept_completion(event):
        b = event.current_buffer
        if b.complete_state and b.complete_state.current_completion:
            b.apply_completion(b.complete_state.current_completion)
        b.complete_state = None

    return kb


def repl(history_path: Optional[Path] = None) -> None:
    """Run the interactive shell until EOF or `exit`."""
    # Lazy imports — keeps the unit tests independent of prompt_toolkit.
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style
    from prompt_toolkit.formatted_text import FormattedText

    import click

    from sleuth.cli import app
    from sleuth.config import get_settings
    from sleuth.ui import console
    from sleuth.ui.art import banner
    from sleuth.ui.console import bonk
    from sleuth.walkthrough import needs_walkthrough, WALK_DISPATCH

    settings = get_settings()
    if history_path is None:
        history_path = settings.db_path.parent.parent / ".sleuth_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.touch(exist_ok=True)

    style = Style.from_dict({
        "prompt": "ansibrightyellow bold",
        "wkq": "ansibrightcyan",
    })
    session: PromptSession = PromptSession(
        history=FileHistory(str(history_path)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=_make_completer(),
        complete_while_typing=True,
        key_bindings=_make_key_bindings(),
        style=style,
    )
    prompt_text = FormattedText([("class:prompt", "sleuth> ")])

    console.print(banner())
    console.print(
        "  type a command (e.g. `ask` then enter) or `help`. ctrl-d to leave.\n"
        "  hit a bare command on its own and i'll walk you through the inputs.\n"
    )

    def _dispatch(tokens: list[str]) -> None:
        try:
            app(args=tokens, standalone_mode=False)
        except click.exceptions.UsageError as e:
            bonk(f"usage: {e.format_message()}")
        except click.exceptions.Abort:
            console.print("  (aborted)")
        except SystemExit:
            pass
        except KeyboardInterrupt:
            console.print("  (interrupted)")
        except Exception as e:  # noqa: BLE001
            bonk(f"oof: {type(e).__name__}: {e}")

    while True:
        try:
            line = session.prompt(prompt_text)
        except KeyboardInterrupt:
            console.print("  (use `exit` or ctrl-d to leave)")
            continue
        except EOFError:
            break

        try:
            tokens = parse_line(line)
        except ParseError as e:
            bonk(f"parse error: {e}")
            continue
        if not tokens:
            continue

        cmd = tokens[0]
        if cmd in ("exit", "quit", "q"):
            break
        if cmd in ("clear", "cls"):
            console.clear()
            continue
        if cmd in ("help", "?"):
            console.print(_HELP_TEXT)
            continue

        # Bare command? walk the user through it.
        kind = needs_walkthrough(tokens)
        if kind is not None:
            walker = WALK_DISPATCH.get(kind)
            if walker:
                try:
                    argv = walker()
                except (KeyboardInterrupt, EOFError):
                    console.print("  (cancelled)")
                    continue
                if not argv:
                    continue
                _dispatch(argv)
                continue

        _dispatch(tokens)

    console.print("  goodbye, gumshoe.")
