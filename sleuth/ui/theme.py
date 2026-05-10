"""Colour palette and Rich theme. Keep it muted and a bit detective-y."""

from rich.theme import Theme


# muted, slightly dusty palette - feels like an old case file
PALETTE = {
    "ink": "#2b2b2b",
    "paper": "#e8e3d3",
    "rust": "#b85c38",
    "moss": "#6a8e7f",
    "amber": "#c8a45a",
    "plum": "#7a4f7e",
    "smoke": "#8a8a8a",
}

THEME = Theme(
    {
        # general
        "info": "italic #8a8a8a",
        "muted": "#8a8a8a",
        "ok": "#6a8e7f",
        "warn": "#c8a45a",
        "bad": "#b85c38",
        "accent": "#7a4f7e",
        # phases
        "phase.search": "#c8a45a",
        "phase.think": "#7a4f7e",
        "phase.wait": "#8a8a8a",
        "phase.save": "#6a8e7f",
        "phase.send": "#b85c38",
        # text bits
        "verb": "italic #c8a45a",
        "model": "bold #7a4f7e",
        "provider": "bold #6a8e7f",
        "prompt": "italic #e8e3d3",
        "citation": "underline #6a8e7f",
        "header": "bold #b85c38",
        "rule": "#8a8a8a",
        "kbd": "reverse #c8a45a",
    }
)
