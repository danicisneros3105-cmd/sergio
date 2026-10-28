"""3D explainers and heavy edits at the level of the big channels: their own
genre, a few skills each (never the whole pile) and graphics that aim at the
subject of the shot."""

from __future__ import annotations

import json

from PIL import Image, ImageDraw

from openjarvis.video_essay import genres, render, skillbook, style
from openjarvis.video_essay.plan import Shot, Word


def test_3d_explainers_and_3d_shorts_have_their_genre():
    assert (
        genres.detect("¿Qué pasaría si no duermes en 11 días? explicado en 3D")
        == "explicado3d"
    )
    assert (
        genres.detect("sabías que tu corazón por dentro funciona así") == "explicado3d"
    )
    assert (
        genres.detect("un corto 3D con un personaje que viaja en el tiempo")
        == "corto3d"
    )
    assert style.load("explicado-3d")["production"] == "3d"


def test_the_heavy_edit_follows_the_retention_method():
    note = genres.notes("pesada")
    for rule in (
        "MATCH THE CLICK",
        "first minute",
        "Re-engage",
        "WOW",
        "end within seconds",
    ):
        assert rule in note


def test_each_genre_brings_three_skills_at_most(tmp_path):
    names = {e["name"] for kind in skillbook.catalog().values() for e in kind}
    for g in genres.GENRES.values():
        for kind, picks in g.skills.items():
            assert 0 < len(picks) <= 3, (g.key, kind)
            assert set(picks) <= names, (g.key, set(picks) - names)
    skillbook.sync(tmp_path, get=lambda url: "Hook in 3 seconds. " * 50)
    text = skillbook.guidance(
        "motion", "cuerpo humano", home=tmp_path, genre="explicado3d"
    )
    assert "blender-mcp" in text and "kinetic-cut-video" not in text
    assert "Also known" not in text


def _plan(texts):
    words = [Word(t, i * 1.0, i * 1.0 + 0.9) for i, t in enumerate(texts)]
    return [Shot(i, i + 1, kind="broll") for i in range(len(texts))], words


def test_a_3d_explainer_shows_the_inside_with_labels():
    shots, words = _plan(
        ["así", "late", "tu", "corazón", "por", "dentro", "cada", "segundo", "sangre"]
    )
    genres.finish(shots, words, "explicado3d")
    assert all(s.effect == "push" for s in shots)  # every 3D shot creeps in
    overlays = [s.overlay for s in shots if s.overlay]
    assert any(o == "xray" for o in overlays) or any(
        o.startswith("callout:") for o in overlays
    )
    assert any(s.sfx != "none" for s in shots)


def test_graphics_aim_at_the_subject_not_the_middle():
    img = Image.new("RGBA", (640, 360), (20, 20, 20, 255))
    render.draw_motion(img, "circle", 1.0, at=(0.8, 0.3))
    right = sum(
        1
        for x in range(400, 640)
        for y in range(0, 200)
        if img.getpixel((x, y))[0] > 200
    )
    left = sum(
        1
        for x in range(0, 200)
        for y in range(160, 360)
        if img.getpixel((x, y))[0] > 200
    )
    assert right > 50 and left == 0


def test_new_motion_graphics_draw():
    for kind in ("callout:CORAZÓN", "spot", "xray", "arrow:MIRA"):
        img = Image.new("RGBA", (640, 360), (200, 200, 200, 255))
        ImageDraw.Draw(img).ellipse((280, 120, 360, 200), fill=(250, 250, 250, 255))
        before = img.copy()
        assert render.draw_motion(img, kind, 0.8), kind
        assert img.tobytes() != before.tobytes(), kind


def test_the_3d_arrow_has_a_side_face_and_a_shadow():
    img = Image.new("RGBA", (640, 360), (255, 255, 255, 255))
    render.draw_motion(img, "arrow", 1.0, accent=(255, 59, 48))
    colours = {img.getpixel((x, y))[:3] for x in range(640) for y in range(0, 360, 2)}
    assert (255, 59, 48) in colours  # the face
    assert (140, 32, 26) in colours  # the darker side: it is a solid, not a sticker


def test_explicado_style_file_is_clean_json():
    data = json.loads((style.BUILT_IN / "explicado-3d.json").read_text("utf-8"))
    assert data["key"] == "explicado-3d" and "Zack" not in json.dumps(data)


def test_the_narrator_waits_out_a_rate_limit_instead_of_going_silent(monkeypatch):
    from openjarvis.video_essay import script

    calls, waits = [], []

    def busy_then_ok(part, tone=""):
        calls.append(part)
        if len(calls) < 3:
            raise RuntimeError("429 RESOURCE_EXHAUSTED. 'retryDelay': '7s'")
        return b"RIFFok"

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(script, "_gemini_narrator", busy_then_ok)
    monkeypatch.setattr(script, "sleep", waits.append)
    assert script.narrator()("Hola", "") == b"RIFFok"
    assert waits == [8.0, 8.0] and script._parallel(None) == 1


def test_a_spent_daily_quota_or_a_missing_key_is_not_waited_for():
    from openjarvis.video_essay import script

    assert (
        script._rate_wait(RuntimeError("429 GenerateRequestsPerDay exceeded")) is None
    )
    assert script._rate_wait(RuntimeError("401 API key not valid")) is None
    assert script._rate_wait(RuntimeError("429 RESOURCE_EXHAUSTED")) == 25.0
