"""The coding agent shows Sergio's name, look and Spanish (scripts/marca_agente.py)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "extensions" / "clacky" / "lib" / "clacky" / "web"


@pytest.fixture(scope="module")
def marca():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import marca_agente
    finally:
        sys.path.pop(0)
    return marca_agente


def _js_object(text: str, marker: str) -> dict:
    start = text.index(marker) + len(marker)
    end = text.index("};", start)
    return json.loads(text[start : end + 1])


def _english_keys() -> list[str]:
    src = (WEB / "i18n.js").read_text(encoding="utf-8")
    block = src[src.index("    en: {") : src.index("    zh: {")]
    return re.findall(r'"([\w.\-]+)"\s*:', block)


def test_the_patch_is_fully_applied(marca):
    assert marca.pending() == []


def test_applying_again_changes_nothing(marca, tmp_path):
    rel = "web/x.js"
    (tmp_path / "web").mkdir()
    (tmp_path / rel).write_text('const a = "OpenClacky";\n', encoding="utf-8")
    patches = [(rel, '"OpenClacky"', '"Sergio"')]
    assert marca.apply(patches, base=tmp_path) == 1
    assert marca.apply(patches, base=tmp_path) == 0
    assert (tmp_path / rel).read_text(encoding="utf-8") == 'const a = "Sergio";\n'


def test_a_missing_anchor_stops_the_patch(marca, tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "x.js").write_text("nothing here\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        marca.apply([("web/x.js", "absent", "present")], base=tmp_path)


def test_every_english_text_has_its_spanish():
    es = _js_object(
        (WEB / "sergio" / "es.js").read_text(encoding="utf-8"), "window.SERGIO_ES = "
    )
    keys = _english_keys()
    assert len(keys) > 1000
    assert set(keys) == set(es)
    assert all(isinstance(v, str) for v in es.values())


def test_spanish_never_names_the_vendor_or_shows_emojis():
    text = (WEB / "sergio" / "es.js").read_text(encoding="utf-8")
    es = _js_object(text, "window.SERGIO_ES = ")
    ext = _js_object(text, "window.SERGIO_ES_EXT = ")
    values = list(es.values()) + [v for group in ext.values() for v in group.values()]
    for value in values:
        shown = re.sub(
            r"https?://\S+", "", value
        )  # a docs address inside a prompt is not shown
        assert "Clacky" not in shown, value
        assert not re.search("[\U0001f300-\U0001faff]", value), value


def test_the_page_loads_sergios_look_and_spanish_first():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert html.index("/sergio/es.js") < html.index('src="/i18n.js"')
    assert '<link rel="stylesheet" href="/sergio/skin.css">' in html
    assert '<html lang="es"' in html and "/sergio/icon.png" in html
    # The original project is named only in the credit line of «Acerca de».
    visible = re.sub(r"<[^>]+>", " ", html)
    lines = [line for line in visible.splitlines() if "OpenClacky" in line]
    assert lines and all("licencia MIT" in line for line in lines)


def test_skin_keeps_to_black_white_and_greys():
    css = (WEB / "sergio" / "skin.css").read_text(encoding="utf-8")
    for hex_colour in re.findall(r"#([0-9a-fA-F]{6})\b", css):
        r, g, b = (int(hex_colour[i : i + 2], 16) for i in (0, 2, 4))
        assert r == g == b, hex_colour
