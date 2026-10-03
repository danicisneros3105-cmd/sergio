"""Startup banner: Sergio wordmark + tagline."""

from __future__ import annotations

# "Sergio" in the figlet "standard" font. Plain text (no Rich markup) so the
# backslashes in the glyphs don't collide with Rich's [tag] markup; colour is
# applied at print time via a style argument.
_WORDMARK = (
    " ____                 _       ",
    "/ ___|  ___ _ __ __ _(_) ___  ",
    "\\___ \\ / _ \\ '__/ _` | |/ _ \\ ",
    " ___) |  __/ | | (_| | | (_) |",
    "|____/ \\___|_|  \\__, |_|\\___/ ",
    "                |___/         ",
)

_TAGLINE = "Tu asistente, en tu computadora"


def print_banner(quiet: bool = False) -> None:
    """Print the Sergio startup banner. No-op when quiet."""
    if quiet:
        return
    try:
        from rich.console import Console

        console = Console()
        for line in _WORDMARK:
            console.print(line, style="bold bright_blue", highlight=False, markup=False)
        console.print(f"      {_TAGLINE}", style="cyan", highlight=False, markup=False)
        console.print()
    except ImportError:
        for line in _WORDMARK:
            print(line)
        print(f"      {_TAGLINE}")
        print()
