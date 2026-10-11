"""The desktop's one look: black, white and one light blue, one typeface.

Bang & Olufsen's logo is drawn in a custom typeface that is not for sale.
The closest free one was measured, not guessed (scripts/font_match.py: the
overlap of B, & and O with the logo across 46 free typefaces): Josefin Sans
(SIL Open Font License, bundled in ``fonts/`` with its licence). Titles use
it the way the B&O wordmark does: light weight, capitals, wide spacing.

Colours: black and white only, with a light blue for what you can press
(buttons, the selected tab, focus). Like ChatGPT and Kimi: flat, calm.

Measurements follow a 4 px grid: every margin, gap and radius here is a
multiple of 4 (hairlines are 1 px), so things line up across windows.
"""

from __future__ import annotations

import logging
from pathlib import Path

FONT_DIR = Path(__file__).with_name("fonts")
FAMILY = "Josefin Sans"
FALLBACK = ["Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Arial"]

# Colours: black, white (and white at lower strength), one light blue.
INK = "#000000"
GLASS = "#0a0a0a"
CARD = "#141414"
CARD_HOT = "#1c1c1c"
LINE = "#262626"
LINE_HOT = "#3d3d3d"
BLUE = "#9fd3ff"  # the one accent: buttons, selection, focus
BLUE_HOT = "#bfe2ff"
ALUMINIUM = BLUE  # older names, same accent
ALUMINIUM_HOT = BLUE_HOT
TEXT = "#ffffff"
SECONDARY = "#8a8a8a"
BRONZE = BLUE

# The 4 px grid.
UNIT = 4
GAP = 8
PAD = 16
MARGIN = 24
RADIUS_S, RADIUS_M, RADIUS_L = 8, 12, 24

_loaded: bool | None = None


def load_fonts() -> bool:
    """Register the bundled typeface once (needs a QGuiApplication)."""
    global _loaded
    if _loaded is not None:
        return _loaded
    try:
        from PySide6.QtGui import QFontDatabase

        ok = False
        for path in sorted(FONT_DIR.glob("*.ttf")):
            ok = QFontDatabase.addApplicationFont(str(path)) >= 0 or ok
        _loaded = ok
    except Exception:  # noqa: BLE001 — no Qt or no fonts: the fallbacks do
        logging.debug("bundled fonts not loaded", exc_info=True)
        _loaded = False
    return _loaded


def families() -> list[str]:
    return [FAMILY, *FALLBACK]


def font(size: float, weight: str = "regular", caps: bool = False, spacing: float = 0.0):  # noqa: ANN201
    """A QFont in the house typeface. ``caps`` + ``spacing`` (in % of the
    size) give the wordmark look: «NIGHT SHIFT»."""
    from PySide6.QtGui import QFont

    load_fonts()
    f = QFont()
    f.setFamilies(families())
    f.setPointSizeF(size)
    f.setWeight({"light": QFont.Weight.Light, "regular": QFont.Weight.Normal, "medium": QFont.Weight.Medium,
                 "semibold": QFont.Weight.DemiBold}.get(weight, QFont.Weight.Normal))
    if caps:
        f.setCapitalization(QFont.Capitalization.AllUppercase)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + spacing)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def css_family() -> str:
    return ", ".join(f"'{name}'" for name in families())


__all__ = [
    "ALUMINIUM", "ALUMINIUM_HOT", "BRONZE", "CARD", "CARD_HOT", "FAMILY", "FONT_DIR", "GAP", "GLASS", "INK", "LINE",
    "LINE_HOT", "MARGIN", "PAD", "RADIUS_L", "RADIUS_M", "RADIUS_S", "SECONDARY", "TEXT", "UNIT", "css_family",
    "families", "font", "load_fonts",
]
