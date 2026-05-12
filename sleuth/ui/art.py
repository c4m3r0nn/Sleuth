"""ASCII art bits. No emojis - just letters, slashes, and vibes."""

from rich.text import Text

LOGO = r"""
   ____  _            _   _
  / ___|| | ___ _   _| |_| |__
  \___ \| |/ _ \ | | | __| '_ \
   ___) | |  __/ |_| | |_| | | |
  |____/|_|\___|\__,_|\__|_| |_|
       a pocket research gremlin
"""


TAG_LINES = [
    "asks the right questions to the wrong people, and writes it all down.",
    "yanks footnotes out of the internet so you don't have to.",
    "collects citations the way magpies collect bottle caps.",
    "rummages through the web on your behalf and reports back.",
    "small dog, big notebook.",
]


def banner() -> Text:
    t = Text()
    t.append(LOGO, style="header")
    return t


def divider(label: str | None = None) -> Text:
    bar = "  " + ("-" * 60)
    if label:
        bar = f"  ---  {label}  " + ("-" * (52 - len(label)))
    return Text(bar, style="rule")
