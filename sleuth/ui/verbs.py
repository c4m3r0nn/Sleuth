"""The funny-verb dictionary. Keep it weird, but readable."""

from __future__ import annotations

import random
from typing import Iterable


# verbs keyed by phase. each is a present-continuous phrase that reads as
# "[Verb]ing the [object]..." in a status line. keep them short.
VERBS: dict[str, list[str]] = {
    "search": [
        "Sleuthing",
        "Snooping",
        "Foraging",
        "Rummaging",
        "Poking around",
        "Sniffing about",
        "Casing the joint",
        "Scrying",
        "Trawling",
        "Combing the haystack",
    ],
    "think": [
        "Cogitating",
        "Squinting",
        "Untangling",
        "Noodling",
        "Chewing on it",
        "Pondering",
        "Mulling",
        "Knitting brows",
        "Connecting dots",
    ],
    "wait": [
        "Marinating",
        "Steeping",
        "Letting the tea brew",
        "Twiddling thumbs",
        "Percolating",
        "Awaiting the oracle",
    ],
    "yoink": [
        "Yoinking sources",
        "Pocketing footnotes",
        "Bookmarking",
        "Snipping clippings",
    ],
    "compose": [
        "Brewing the verdict",
        "Whisking findings",
        "Stitching the dossier",
        "Drafting the memo",
        "Inking conclusions",
    ],
    "save": [
        "Filing it away",
        "Tucking it in",
        "Stashing in the drawer",
        "Squirrelling it",
        "Cataloguing",
    ],
    "drive": [
        "Fluttering off to Drive",
        "Posting to the Doc",
        "Mailing it upstairs",
    ],
    "ping": [
        "Pinging your phone",
        "Tapping your shoulder",
        "Buzzing Telegram",
        "Sliding into the chat",
    ],
    "wakeup": [
        "Waking the bloodhound",
        "Lacing the boots",
        "Polishing the monocle",
        "Dusting the magnifying glass",
        "Cracking knuckles",
    ],
    "done": [
        "Case closed",
        "Filed and sealed",
        "Off the desk",
        "Wrapped",
        "Done and dusted",
    ],
    "error": [
        "Tripped over a loose cobble",
        "Got the wibbles",
        "Stumped",
        "Lost the scent",
        "Wandered into a hedge",
    ],
}


def pick(phase: str) -> str:
    """Return a random verb phrase for the given phase."""
    options = VERBS.get(phase) or VERBS["think"]
    return random.choice(options)


def cycle(phase: str) -> Iterable[str]:
    """Yield verbs from a phase in shuffled order, forever."""
    pool = list(VERBS.get(phase) or VERBS["think"])
    while True:
        random.shuffle(pool)
        for v in pool:
            yield v
