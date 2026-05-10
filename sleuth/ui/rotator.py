"""Rotating verb ticker for spinners. Runs on a daemon thread."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from sleuth.ui import verbs as verb_dict


class VerbRotator:
    """Calls `on_verb(verb)` every `interval` seconds with a fresh phrase.

    Drops back-to-back duplicates so the spinner doesn't look frozen when
    we happen to draw the same word twice in a row.
    """

    def __init__(
        self,
        *,
        phase: str,
        on_verb: Callable[[str], None],
        interval: float = 2.0,
    ) -> None:
        self.phase = phase
        self.on_verb = on_verb
        self.interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def set_phase(self, phase: str) -> None:
        """Change which verb pool the rotator draws from. Takes effect next tick."""
        self.phase = phase

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        last: Optional[str] = None
        while not self._stop.is_set():
            for _ in range(20):  # cap retries so we never spin forever
                v = verb_dict.pick(self.phase)
                if v != last:
                    break
            last = v
            try:
                self.on_verb(v)
            except Exception:
                # If the consumer goes away, just stop gracefully.
                return
            # Wait, but exit early if asked.
            if self._stop.wait(self.interval):
                return

    # context manager sugar
    def __enter__(self) -> "VerbRotator":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
