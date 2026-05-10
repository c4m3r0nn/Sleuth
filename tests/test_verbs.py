"""Verb dictionary helpers."""

from sleuth.ui import verbs


def test_pick_returns_known_phrase():
    v = verbs.pick("search")
    assert v in verbs.VERBS["search"]


def test_pick_unknown_phase_falls_back_to_think():
    v = verbs.pick("nonsense")
    assert v in verbs.VERBS["think"]


def test_cycle_yields_all_then_repeats():
    pool = verbs.VERBS["save"]
    gen = verbs.cycle("save")
    first_round = {next(gen) for _ in range(len(pool))}
    assert first_round == set(pool)
    # Continues yielding (no StopIteration).
    next(gen)


def test_every_phase_has_at_least_three_phrases():
    """Keep the vocabulary varied so it doesn't feel like a single canned line."""
    for phase, options in verbs.VERBS.items():
        assert len(options) >= 3, f"phase '{phase}' has only {len(options)} options"
