"""Genres: the brief picks the kind of video, and the kind changes the
style, the clip searches, the sources and the motion graphics."""

from __future__ import annotations

from PIL import Image

from openjarvis.video_essay import genres, media, render, style
from openjarvis.video_essay.plan import Shot, Word


def test_the_brief_picks_the_genre():
    assert genres.detect("Hazme un cortometraje cinematográfico de terror") == "cine"
    assert genres.detect("un video tipo MrBeast: sobrevivir 24 horas") == "pesada"
    assert genres.detect("una animación 2D sobre el ciclo del agua") == "animacion"
    assert genres.detect("motivación y disciplina para madrugar") == "inspiracional"
    assert genres.detect("explica cómo funciona un agujero negro") == "documental"
    assert genres.detect("hola") == ""


def test_every_genre_has_a_real_style():
    keys = {s["key"] for s in style.available()}
    for g in genres.GENRES.values():
        assert g.style in keys, g.key
        assert style.load(g.style)["key"] == g.style


def test_the_genre_turns_the_clip_search_towards_its_look():
    shot = Shot(0, 1, visual="a lonely man walking in the rain at night")
    plain = media.queries(shot)
    cine = media.queries(shot, genres.search_words("cine"))
    assert "cinematic" in cine[0] and cine[1:] == plain


def test_sources_follow_the_genre_but_only_the_allowed_ones():
    allowed = ["library", "stock", "web", "archive", "image"]
    assert genres.sources("cine", allowed)[0] == "library"  # film not allowed here
    assert genres.sources("animacion", allowed)[0] == "archive"
    assert sorted(genres.sources("pesada", allowed)) == sorted(allowed)


def _plan(n):
    words = [Word(f"w{i}", i * 1.0, i * 1.0 + 0.9) for i in range(n)]
    words[3] = Word("1000000", 3.0, 3.9)
    return [Shot(i, i + 1, kind="broll") for i in range(n)], words


def test_heavy_edit_puts_sounds_on_moments_and_motion_graphics_everywhere():
    shots, words = _plan(32)
    assert genres.finish(shots, words, "pesada") == 32
    assert all(s.effect != "none" for s in shots)
    with_sound = sum(s.sfx != "none" for s in shots)
    assert 12 <= with_sound < 32  # the moments, not every cut
    assert shots[3].overlay == "1000000"  # the number gets a counter
    assert any(s.overlay.startswith("arrow") for s in shots)
    assert any(s.overlay.startswith("bar:") for s in shots)
    assert sum(s.transition != "cut" for s in shots) >= 20


def test_a_short_film_breathes():
    shots, words = _plan(12)
    genres.finish(shots, words, "cine")
    assert all(s.frame == "letterbox" for s in shots)
    assert sum(s.text_style == "none" for s in shots) >= 6
    assert any(s.transition == "fade" for s in shots)


def test_the_editors_own_choices_stay():
    shots, words = _plan(6)
    shots[0].transition, shots[0].overlay, shots[0].sfx = "fade", "DÍA 1", "ding"
    genres.finish(shots, words, "pesada")
    assert (shots[0].transition, shots[0].overlay, shots[0].sfx) == (
        "fade",
        "DÍA 1",
        "ding",
    )


def test_motion_graphics_draw_and_grow_over_time():
    def frame(kind, t):
        img = Image.new("RGBA", (640, 360), (20, 20, 20, 255))
        assert render.draw_motion(img, kind, t)
        return sum(1 for p in img.getdata() if p[0] > 200 and p[1] < 100)

    for kind in ("circle", "arrow:MIRA", "bar:80"):
        assert frame(kind, 0.4) > frame(kind, 0.05) > 0 or kind.startswith("arrow"), (
            kind
        )
        assert frame(kind, 0.4) > 0
    assert not render.draw_motion(Image.new("RGBA", (64, 36)), "DÍA 1", 0.2)


def test_letterbox_only_on_a_wide_frame():
    wide = Image.new("RGBA", (1920, 1080), (255, 255, 255, 255))
    render.letterbox(wide)
    assert wide.getpixel((10, 5))[:3] == (0, 0, 0) and wide.getpixel((10, 540))[:3] == (
        255,
        255,
        255,
    )
    tall = Image.new("RGBA", (1080, 1920), (255, 255, 255, 255))
    render.letterbox(tall)
    assert tall.getpixel((10, 5))[:3] == (255, 255, 255)
