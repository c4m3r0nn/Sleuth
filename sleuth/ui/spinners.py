"""Custom spinner frames for the various phases."""

# Rich's Spinner accepts {"interval": ms, "frames": [...]}.
# We register these as ad-hoc custom spinners.

MAGNIFIER = {
    "interval": 110,
    "frames": [
        "(o   )",
        "( o  )",
        "(  o )",
        "(   o)",
        "(  o )",
        "( o  )",
    ],
}

FOOTSTEPS = {
    "interval": 140,
    "frames": [
        ".      ",
        "..     ",
        ".. .   ",
        ".. ..  ",
        ".. .. .",
        " . .. .",
        "  . .. ",
        "    . .",
        "      .",
        "       ",
    ],
}

PAGES = {
    "interval": 130,
    "frames": ["[   ]", "[.  ]", "[.. ]", "[...]", "[ ..]", "[  .]", "[   ]"],
}

TYPEWRITER = {
    "interval": 90,
    "frames": ["|", "/", "-", "\\"],
}


SPINNERS = {
    "search": MAGNIFIER,
    "think": PAGES,
    "wait": TYPEWRITER,
    "save": FOOTSTEPS,
    "drive": FOOTSTEPS,
    "ping": TYPEWRITER,
}


def frames_for(phase: str) -> dict:
    return SPINNERS.get(phase, PAGES)
