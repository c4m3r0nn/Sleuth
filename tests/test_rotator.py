"""VerbRotator: a tiny background ticker that swaps the spinner verb."""

import threading
import time

import pytest


def test_rotator_calls_callback_until_stopped():
    from sleuth.ui.rotator import VerbRotator

    seen: list[str] = []
    lock = threading.Lock()

    def on_verb(v: str) -> None:
        with lock:
            seen.append(v)

    rot = VerbRotator(phase="search", on_verb=on_verb, interval=0.05)
    rot.start()
    time.sleep(0.25)
    rot.stop()

    # We should have seen multiple ticks in 0.25s with a 0.05s interval.
    with lock:
        assert len(seen) >= 3
        # All should be valid verbs from the search pool.
        from sleuth.ui.verbs import VERBS
        for v in seen:
            assert v in VERBS["search"]


def test_rotator_avoids_immediate_repeats():
    from sleuth.ui.rotator import VerbRotator

    seen: list[str] = []

    def on_verb(v: str) -> None:
        seen.append(v)

    rot = VerbRotator(phase="search", on_verb=on_verb, interval=0.02)
    rot.start()
    time.sleep(0.25)
    rot.stop()

    # No two consecutive verbs should match (we have 10 search verbs to draw from).
    consecutive = [a == b for a, b in zip(seen, seen[1:])]
    assert not any(consecutive), f"got back-to-back duplicate: {seen}"


def test_rotator_stop_is_idempotent():
    from sleuth.ui.rotator import VerbRotator

    rot = VerbRotator(phase="search", on_verb=lambda v: None, interval=0.05)
    rot.start()
    rot.stop()
    rot.stop()  # should not raise


def test_rotator_can_be_used_as_context_manager():
    from sleuth.ui.rotator import VerbRotator

    seen: list[str] = []
    with VerbRotator(phase="think", on_verb=seen.append, interval=0.02):
        time.sleep(0.1)
    assert len(seen) >= 2


def test_rotator_with_unknown_phase_falls_back():
    from sleuth.ui.rotator import VerbRotator

    seen: list[str] = []
    with VerbRotator(phase="garbage", on_verb=seen.append, interval=0.02):
        time.sleep(0.05)
    # Falls back to the 'think' pool per verbs.pick.
    from sleuth.ui.verbs import VERBS
    for v in seen:
        assert v in VERBS["think"]
