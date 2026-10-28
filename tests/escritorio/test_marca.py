"""Sergio's mark (the blue disc with the white ring) is the only logo: every icon comes from assets/marca/sergio.svg."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def marca():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import marca_sergio
    finally:
        sys.path.pop(0)
    return marca_sergio


def test_every_icon_is_drawn_from_the_current_svg(marca):
    # Change the SVG without running scripts/marca_sergio.py and this fails.
    assert marca.main(["--check"]) == 0


def test_the_web_shows_the_fly(marca):
    page = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'href="/sergio.svg?v=' in page  # versioned: browsers drop the old icon
    assert (ROOT / marca.SVG_COPY).read_bytes() == marca.SOURCE.read_bytes()
    toolbar = (ROOT / "frontend/src/components/Shell/Toolbar.tsx").read_text(
        encoding="utf-8"
    )
    assert 'src="/sergio.svg"' in toolbar


def test_the_loading_screen_draws_the_same_fly(marca):
    import re

    page = (ROOT / "windows/sergio_escritorio/resources/cargando.html").read_text(
        encoding="utf-8"
    )
    shapes = re.findall(r"<circle [^>]*/>", marca.SOURCE.read_text(encoding="utf-8"))
    assert shapes and all(shape in page for shape in shapes)


@pytest.mark.parametrize(
    "rel", ["frontend/public/pwa-512x512.png", "installer/sergio.ico"]
)
def test_icons_are_the_blue_disc_with_the_white_ring(rel):
    # A blue disc (transparent corners) with a white ring around a blue centre.
    from PIL import Image

    image = Image.open(ROOT / rel).convert("RGBA")
    w, h = image.size
    assert image.getpixel((1, 1))[3] == 0
    r, g, b, _ = image.getpixel((w // 2, int(h * 0.64)))
    assert min(r, g, b) > 230  # the ring
    r, g, b, _ = image.getpixel((int(w * 0.15), h // 2))
    assert b > 230 and r < 40  # the disc
    r, g, b, _ = image.getpixel((w // 2, h // 2))
    assert b > 230 and r < 40  # the centre


def test_shortcut_icon_is_the_fly_and_grey_when_paused():
    from sergio_escritorio.app import make_icon

    idle = make_icon("idle")
    paused = make_icon("paused")
    assert idle.size == (256, 256)
    r, g, b, a = paused.getpixel((128, 166))
    assert a == 255 and r == g == b
    assert idle.getpixel((128, 166))[:3] != (r, g, b)


def test_tray_icon_draws():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # Qt runtime libraries missing on this machine
        pytest.skip(str(exc))
    from sergio_escritorio.app import tray_icon
    from sergio_escritorio.companion import STATE_COLORS

    QApplication.instance() or QApplication([])
    for state in ("idle", "paused"):
        icon = tray_icon(STATE_COLORS[state])
        assert not icon.isNull()
        assert not icon.pixmap(32, 32).toImage().isNull()
