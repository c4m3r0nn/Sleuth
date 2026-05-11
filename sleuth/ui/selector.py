"""Inline arrow-key selectors.

Two layers:

  - State machines (SelectorState, MultiSelectorState) - pure, testable.
  - run_select_one / run_select_many - prompt_toolkit Applications that drive
    those state machines from real keypresses. Exercised by hand.

The selectors render inline (no fullscreen modal): the question and the list
appear in your scrollback, you navigate with arrow keys, and on confirm the
final choice replaces the live list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


# --------------------------------------------------------------------------- #
# state machines
# --------------------------------------------------------------------------- #


@dataclass
class SelectorState:
    options: list[str]
    initial_index: int = 0
    index: int = field(init=False)
    chosen: Optional[str] = None
    cancelled: bool = False
    done: bool = False

    def __post_init__(self) -> None:
        if not self.options:
            self.index = 0
        else:
            self.index = max(0, min(self.initial_index, len(self.options) - 1))

    def current(self) -> Optional[str]:
        if not self.options:
            return None
        return self.options[self.index]

    def move_up(self) -> None:
        if not self.options:
            return
        self.index = (self.index - 1) % len(self.options)

    def move_down(self) -> None:
        if not self.options:
            return
        self.index = (self.index + 1) % len(self.options)

    def confirm(self) -> None:
        self.chosen = self.current()
        self.done = True

    def cancel(self) -> None:
        self.cancelled = True
        self.done = True


CONTINUE_SENTINEL = "__sleuth_continue__"


@dataclass
class MultiSelectorState:
    options: list[str]
    default_selected: Iterable[str] = field(default_factory=list)
    continue_label: str = "continue"
    index: int = 0
    selected: set = field(default_factory=set)
    cancelled: bool = False
    done: bool = False

    def __post_init__(self) -> None:
        self.options = list(self.options)
        self.selected = set(self.default_selected)
        # the "continue" row is virtual — we manage it via on_continue()

    @property
    def total_rows(self) -> int:
        """Options + the continue row."""
        return len(self.options) + 1

    def on_continue(self) -> bool:
        return self.index == len(self.options)

    def current_label(self) -> str:
        if self.on_continue():
            return self.continue_label
        return self.options[self.index]

    def move_up(self) -> None:
        self.index = (self.index - 1) % self.total_rows

    def move_down(self) -> None:
        self.index = (self.index + 1) % self.total_rows

    def toggle(self) -> None:
        """If on an option, flip its membership. If on continue, finish."""
        if self.on_continue():
            self.done = True
            return
        opt = self.options[self.index]
        if opt in self.selected:
            self.selected.remove(opt)
        else:
            self.selected.add(opt)

    def confirm(self) -> None:
        """Enter: same as toggle (so 'enter on continue' finishes)."""
        self.toggle()

    def cancel(self) -> None:
        self.cancelled = True
        self.done = True

    def result(self) -> list[str]:
        """Selected options in their original list order."""
        return [o for o in self.options if o in self.selected]


# --------------------------------------------------------------------------- #
# inline prompt_toolkit applications
# --------------------------------------------------------------------------- #


def _format_select_one(
    state: SelectorState,
    question: str,
    blurbs: Optional[list[str]] = None,
):
    from prompt_toolkit.formatted_text import FormattedText

    rows: list[tuple[str, str]] = []
    rows.append(("class:wkq", f"  {question}\n"))
    for i, opt in enumerate(state.options):
        is_cur = i == state.index
        marker = "  >" if is_cur else "   "
        style = "class:sel.current" if is_cur else "class:sel.option"
        rows.append((style, f"  {marker} {opt}"))
        if blurbs and i < len(blurbs) and blurbs[i]:
            blurb_style = "class:sel.current.blurb" if is_cur else "class:sel.blurb"
            rows.append((blurb_style, f"   {blurbs[i]}"))
        rows.append(("", "\n"))
    rows.append(("class:sel.hint", "  use up/down to move, enter to select, esc to cancel"))
    return FormattedText(rows)


def _format_select_many(state: MultiSelectorState, question: str):
    from prompt_toolkit.formatted_text import FormattedText

    rows: list[tuple[str, str]] = []
    rows.append(("class:wkq", f"  {question}\n"))
    for i, opt in enumerate(state.options):
        is_cur = i == state.index
        marker = "  >" if is_cur else "   "
        check = "[x]" if opt in state.selected else "[ ]"
        style = "class:sel.current" if is_cur else "class:sel.option"
        rows.append((style, f"  {marker} {check} {opt}\n"))
    # continue row
    is_cur = state.on_continue()
    marker = "  >" if is_cur else "   "
    style = "class:sel.continue.current" if is_cur else "class:sel.continue"
    rows.append((style, f"  {marker}     {state.continue_label}\n"))
    rows.append((
        "class:sel.hint",
        "  use up/down to move, enter to toggle (or finish on 'continue'), esc to cancel"
    ))
    return FormattedText(rows)


_SEL_STYLE = {
    "wkq":                    "ansibrightcyan",
    "sel.option":             "",
    "sel.current":            "reverse ansibrightyellow bold",
    "sel.blurb":              "ansibrightblack",
    "sel.current.blurb":      "reverse ansiyellow",
    "sel.continue":           "ansigreen bold",
    "sel.continue.current":   "reverse ansibrightgreen bold",
    "sel.hint":               "ansibrightblack italic",
}


def run_select_one(
    question: str,
    options: list[str],
    *,
    default: Optional[str] = None,
    blurbs: Optional[list[str]] = None,
) -> Optional[str]:
    """Inline single-select. Returns the chosen option, or None if cancelled."""
    if not options:
        return None

    initial = 0
    if default is not None and default in options:
        initial = options.index(default)
    state = SelectorState(options=options, initial_index=initial)

    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    def get_text():
        return _format_select_one(state, question, blurbs)

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        state.move_up()
        event.app.invalidate()

    @kb.add("down")
    def _(event):
        state.move_down()
        event.app.invalidate()

    @kb.add("enter")
    def _(event):
        state.confirm()
        event.app.exit()

    @kb.add("escape")
    @kb.add("c-c")
    def _(event):
        state.cancel()
        event.app.exit()

    app = Application(
        layout=Layout(Window(FormattedTextControl(get_text), always_hide_cursor=True)),
        key_bindings=kb,
        full_screen=False,
        style=Style.from_dict(_SEL_STYLE),
        erase_when_done=True,  # clear the live list after selection
    )
    app.run()

    # Echo a tidy "final" line so scrollback shows what was picked.
    if state.cancelled or state.chosen is None:
        return None
    _echo_final(question, state.chosen)
    return state.chosen


def run_select_many(
    question: str,
    options: list[str],
    *,
    default_selected: Optional[list[str]] = None,
    continue_label: str = "continue",
) -> Optional[list[str]]:
    """Inline multi-select with checkboxes. Returns the chosen list, or None if cancelled."""
    if not options:
        return []
    state = MultiSelectorState(
        options=options,
        default_selected=default_selected or [],
        continue_label=continue_label,
    )

    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    def get_text():
        return _format_select_many(state, question)

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        state.move_up()
        event.app.invalidate()

    @kb.add("down")
    def _(event):
        state.move_down()
        event.app.invalidate()

    @kb.add("space")
    def _(event):
        # explicit toggle for whichever row is highlighted
        state.toggle()
        event.app.invalidate()

    @kb.add("enter")
    def _(event):
        state.confirm()
        if state.done:
            event.app.exit()
        else:
            event.app.invalidate()

    @kb.add("escape")
    @kb.add("c-c")
    def _(event):
        state.cancel()
        event.app.exit()

    app = Application(
        layout=Layout(Window(FormattedTextControl(get_text), always_hide_cursor=True)),
        key_bindings=kb,
        full_screen=False,
        style=Style.from_dict(_SEL_STYLE),
        erase_when_done=True,
    )
    app.run()

    if state.cancelled:
        return None
    chosen = state.result()
    _echo_final(question, ", ".join(chosen) if chosen else "(none)")
    return chosen


def _echo_final(question: str, value: str) -> None:
    """Print a small confirmation in the scrollback after the live UI is gone."""
    from sleuth.ui import console
    from rich.text import Text

    line = Text()
    line.append(f"  {question} ", style="muted")
    line.append(value, style="accent")
    console.print(line)
