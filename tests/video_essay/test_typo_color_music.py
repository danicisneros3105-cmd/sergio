"""Typefaces by role, colour theory and composition, and free music from the
internet (owner, 27 Oct 2026: «subtítulos en diferentes partes con diferentes
tipografías, teoría del color y composición, clips y música de internet»)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from openjarvis.video_essay import captions, color, media, music, render, sources, typo
from openjarvis.video_essay import plan as P

# -- colour --------------------------------------------------------------------------


def test_wcag_contrast_matches_the_standard():
    assert color.contrast((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0, abs=0.01)
    assert color.contrast((119, 119, 119), (255, 255, 255)) == pytest.approx(
        4.48, abs=0.02
    )
    assert color.contrast((10, 10, 10), (10, 10, 10)) == pytest.approx(1.0)
    assert color.text_colour((250, 240, 220)) == (12, 12, 12)
    assert color.text_colour((20, 30, 60)) == (255, 255, 255)
    assert color.text_on_block((255, 0, 0)) == (255, 255, 255)  # white on red
    assert color.text_on_block((255, 220, 0)) == (12, 12, 12)  # black on yellow


def test_harmonies_turn_the_hue_on_the_wheel():
    red = (230, 30, 30)
    comp = color.harmony(red, "complementary")[0]
    assert comp[2] > 150 and comp[0] < 80  # red's complement is cyan
    assert len(color.harmony(red, "triadic")) == 2
    assert len(color.harmony(red, "analogous")) == 2
    assert color.hex_of((255, 0, 16)) == "#FF0010"
    assert color.rgb_of("#ff0010") == (255, 0, 16) and color.rgb_of("nope") is None


def test_palette_finds_the_colours_of_the_frame():
    img = Image.new("RGB", (200, 100), (20, 40, 160))
    ImageDraw.Draw(img).rectangle((0, 0, 59, 99), fill=(240, 200, 30))
    pal = color.palette(img, 3)
    assert pal[0][1] == pytest.approx(0.7, abs=0.05)  # blue takes 70%
    assert pal[0][0][2] > 120
    assert any(c[0] > 200 and c[1] > 160 for c, _ in pal)


def test_accent_keeps_the_brand_when_it_reads_and_answers_the_picture_when_not():
    night = Image.new("RGB", (160, 90), (14, 14, 18))
    assert color.accent_for(night, (232, 38, 42)) == (232, 38, 42)
    # red on deep blue is only 2.7:1: the brand would not stand out there
    blue = Image.new("RGB", (160, 90), (20, 40, 160))
    assert color.contrast(color.accent_for(blue, (232, 38, 42)), (20, 40, 160)) >= 3
    red = Image.new("RGB", (160, 90), (225, 40, 40))
    got = color.accent_for(red, (232, 38, 42))
    assert got != (232, 38, 42) and color.contrast(got, (225, 40, 40)) >= 2.5


def _subject_left() -> Image.Image:
    """A bright busy subject on the left third, an empty right side."""
    img = Image.new("RGB", (320, 180), (18, 18, 22))
    rng = np.random.default_rng(1)
    noise = (rng.random((150, 110, 3)) * 255).astype(np.uint8)
    img.paste(Image.fromarray(noise), (20, 15))
    return img


def test_text_goes_where_the_subject_is_not():
    img = _subject_left()
    x, _y = color.subject(img)
    assert x < 0.45
    zone = color.best_zone(img)
    assert "left" not in zone
    scores = color.zone_scores(color.saliency(img))
    assert scores["left"] > scores["right"]
    comp = color.composition(img)
    assert comp["free_side"] == "right"
    # never twice in the same place in a row when another place is as good
    assert color.best_zone(img, avoid=[zone]) != zone


def test_legibility_asks_for_a_block_on_mid_grey_noise():
    rng = np.random.default_rng(2)
    grey = (rng.random((90, 160)) * 200 + 30).astype(np.uint8)
    busy = Image.fromarray(np.stack([grey] * 3, axis=-1))
    seen = color.legible(busy, "center", (232, 38, 42))
    assert seen["box"] is True
    calm = Image.new("RGB", (160, 90), (10, 10, 10))
    assert color.legible(calm, "center", (232, 38, 42))["box"] is False


# -- typography ----------------------------------------------------------------------


def test_every_face_is_there_with_its_licence_and_spanish_letters():
    for name, face in typo.FACES.items():
        path = typo.FONTS / face.file
        assert path.exists(), name
        f = typo.font(name, 40)
        assert f.getlength("ñÁ¿¡") > 0
    names = {p.name for p in typo.FONTS.iterdir()}
    for lic in ("OFL-Anton.txt", "OFL-ArchivoBlack.txt", "OFL-DMSerifDisplay.txt", "OFL-SpaceMono.txt",
                "LICENSE-PermanentMarker.txt", "OFL.txt"):  # fmt: skip
        assert lic in names


def test_each_line_gets_the_face_its_words_ask_for():
    allowed = ("base", "impacto", "elegante", "tecnica", "mano")
    assert typo.face_for("58.500 suscriptores", allowed) == "tecnica"
    assert typo.face_for("¡Ahora!", allowed) == "impacto"
    assert typo.face_for("«Imagina tu vida en un año»", allowed) == "elegante"
    assert typo.face_for("ojo con esto", allowed) == "mano"
    assert (
        typo.face_for("y esto lo cambia todo para siempre jamás amigo", ("base",))
        == "base"
    )
    # the same face twice in a row only when the line asks for it
    assert typo.face_for("nadie lo vio venir", allowed, prev="base") == "impacto"


def test_pairing_follows_the_style_and_stays_small():
    nextcore = json.loads(
        (
            Path(typo.__file__).parents[1] / "tools/video_styles/nextcore.json"
        ).read_text()
    )
    faces = typo.pairing(nextcore)
    assert faces[0] == "base" and "impacto" in faces and len(faces) <= 4
    assert "elegante" in typo.pairing({"text": {"style": "elegant serif editorial"}})


def _words(text: str, step: float = 0.4):
    return [
        P.Word(w, i * step, i * step + step * 0.9) for i, w in enumerate(text.split())
    ]


def test_dress_moves_words_off_the_subject_and_varies_faces(tmp_path):
    words = _words("Ganó 58.500 suscriptores ¡en tres meses! nadie lo vio venir")
    shots = [
        P.Shot(first=0, last=3, kind="broll", start=0, end=1.2),
        P.Shot(first=3, last=6, kind="broll", start=1.2, end=2.4, highlight="meses"),
        P.Shot(first=6, last=10, kind="card", card="black", start=2.4, end=4.0),
    ]
    for s in shots:
        s.text = " ".join(w.text for w in words[s.first : s.last])
    profile = {"text": {"style": "Bold, sans-serif, white on red", "accent": "#FF0000"}}
    n = typo.dress(shots, words, lambda shot: _subject_left(), profile)
    assert n == 3
    assert shots[0].font == "tecnica"
    assert shots[1].font == "impacto"
    assert "left" not in shots[0].position
    assert shots[0].position != shots[1].position  # different parts of the screen
    assert shots[1].box in ("word", "all")  # the highlight on a block
    assert shots[2].accent == "#FF0000"  # cards keep the brand colour
    before = [(s.font, s.position, s.accent) for s in shots]
    assert typo.dress(shots, words, lambda shot: _subject_left(), profile) == 0
    # one accent for the whole video (the brand's here)
    assert {s.accent for s in shots} == {"#FF0000"}
    assert [
        (s.font, s.position, s.accent) for s in shots
    ] == before  # safe to run again


def test_the_editor_choice_is_kept():
    words = _words("uno dos tres")
    shot = P.Shot(first=0, last=3, kind="broll", start=0, end=1.2, font="elegante",
                  position="upper_left", accent="#00AAFF", box="word")  # fmt: skip
    typo.dress([shot], words, lambda s: _subject_left(), {})
    assert (shot.font, shot.position, shot.accent) == (
        "elegante",
        "upper_left",
        "#00AAFF",
    )


def test_the_plan_reads_faces_places_accents_and_blocks():
    words = _words("hola mundo de verdad")
    raw = json.dumps({"shots": [
        {"from": 0, "to": 2, "font": "impacto", "position": "lower_right", "accent": "#12ab34", "box": True},
        {"from": 2, "to": 4, "font": "comic-sans", "accent": "red", "source": "film"},
    ]})  # fmt: skip
    a, b = P.from_model(raw, words, min_s=0.1, max_s=6)
    assert (a.font, a.position, a.accent, a.box) == (
        "impacto",
        "lower_right",
        "#12AB34",
        "word",
    )
    assert (b.font, b.accent, b.box, b.source) == ("", "", "", "film")
    assert P.from_json(P.to_json([a]))[0].font == "impacto"


def test_layout_uses_the_face_the_corner_and_the_block():
    words = _words("dinero rápido ya")
    shot = P.Shot(first=0, last=3, kind="broll", start=0, end=1.2, text="dinero rápido ya",
                  highlight="rápido", font="impacto", position="lower_right", accent="#FF0000", box="word")  # fmt: skip
    placed = render.layout_text(shot, words, (1280, 720))
    assert [p.text for p in placed] == [
        "DINERO",
        "RÁPIDO",
        "YA",
    ]  # Anton is all capitals
    assert all(p.kind == "impacto" for p in placed)
    lit = [p for p in placed if p.text == "RÁPIDO"][0]
    assert lit.bg == (255, 0, 0) and lit.rgb == (255, 255, 255)
    assert min(p.x for p in placed) > 1280 * 0.35  # on the right
    assert max(p.y for p in placed) > 720 * 0.55  # at the bottom
    canvas = Image.new("RGBA", (1280, 720), (0, 0, 0, 255))
    render.draw_text(canvas, placed, 5.0, shot.text_style, True)
    reds = np.asarray(canvas)[..., :3]
    assert (
        (reds[..., 0] > 200) & (reds[..., 1] < 40)
    ).sum() > 500  # the red block is drawn


# -- captions ------------------------------------------------------------------------


def test_quick_captions_change_face_and_place_by_what_is_said():
    doc = captions.ass_document(
        ["¡Mira!", "Ganó 58.500 en 3 meses.", "«Imagina tu vida»"],
        [1, 2, 2],
        1080,
        1920,
    )
    styles = [ln.split(",")[0] for ln in doc.splitlines() if ln.startswith("Style:")]
    assert styles == [
        "Style: Pop",
        "Style: Impacto",
        "Style: Elegante",
        "Style: Tecnica",
    ]
    events = [ln for ln in doc.splitlines() if ln.startswith("Dialogue:")]
    assert ",Impacto,," in events[0] and "{\\an5}" in events[0]
    assert any(",Tecnica,," in e and "{\\an8}" in e for e in events)
    assert any(
        ",Elegante,," in e and "Imagina" in e for e in events
    )  # no capitals for the italic
    plain = captions.ass_document(["¡Mira!"], [1], 1080, 1920, varied=False)
    assert "Style: Impacto" not in plain


# -- clips: film and series scenes ---------------------------------------------------


def test_scenes_search_films_and_series_and_are_credited_as_not_free(monkeypatch):
    monkeypatch.setenv("SERGIO_CLIPS_WEB", "1")
    asked = []

    def runner(args):
        asked.append(args[-1])
        return json.dumps(
            {"id": f"v{len(asked)}", "duration": 140, "channel": "Movieclips"}
        )

    found = sources.search_scenes("a man looks at the city at night", 2, runner=runner)
    assert len(found) == 2 and all("no libre" in c.licence for c in found)
    assert "movie scene" in asked[0] and "film clip" in asked[1]
    monkeypatch.setenv("SERGIO_CLIPS_WEB", "0")
    assert sources.search_scenes("x", 2, runner=runner) == []
    assert media.SEARCH_ORDER["film"] == ("film", "archive")


# -- music ---------------------------------------------------------------------------


def test_mood_comes_from_the_style_music_line():
    nextcore = {"audio": {"music": "Upbeat, motivational, cinematic electronic music."}}
    q = music.mood_query(nextcore)
    assert "upbeat" in q and "motivational" in q
    assert music.mood_query({}, "piano triste") == "piano triste"
    assert music.mood_query({}) == "cinematic"


def test_openverse_keeps_only_licences_that_allow_money(monkeypatch):
    data = {"results": [
        {"url": "https://x/a.mp3", "title": "A", "creator": "Ana", "license": "by", "license_version": "4.0",
         "license_url": "https://cc/by/4.0", "foreign_landing_url": "https://jamendo/a", "duration": 120000},
        {"url": "https://x/b.mp3", "title": "B", "creator": "Beto", "license": "by-nc", "duration": 120000},
        {"url": "https://x/c.mp3", "title": "C", "creator": "Cami", "license": "cc0", "duration": 5000},
    ]}  # fmt: skip
    seen = {}

    def fake_get(url, **kw):
        seen.update(kw.get("params") or {})
        return data

    monkeypatch.setattr(music, "_get", fake_get)
    got = music.search_openverse("cinematic", 3)
    assert [t.title for t in got] == ["A"]  # NC refused, a 5-second sting skipped
    assert seen["license_type"] == "commercial"
    assert got[0].licence == "CC BY 4.0"
    credit = got[0].credit()
    assert (
        credit["kind"] == "música"
        and "Ana" in credit["credit"]
        and credit["url"] == "https://jamendo/a"
    )
    assert "Música: «A» — Ana — CC BY 4.0" in sources.credits_text([credit])
    assert [
        t.title for t in music.search_openverse("cinematic", 3, for_money=False)
    ] == ["A", "B"]


def test_ccmixter_and_archive_parse_and_refuse_non_commercial(monkeypatch):
    def fake_get(url, **kw):
        if "ccmixter" in url:
            return [
                {"upload_name": "Rise", "user_name": "dj", "license_url": "http://creativecommons.org/licenses/by/3.0/",
                 "files": [{"download_url": "https://cc/rise.mp3"}], "file_page_url": "https://cc/rise"},
                {"upload_name": "Nope", "user_name": "x", "license_url": "http://creativecommons.org/licenses/by-nc/3.0/",
                 "files": [{"download_url": "https://cc/nope.mp3"}]},
            ]  # fmt: skip
        if "advancedsearch" in url:
            pd = "http://creativecommons.org/publicdomain/mark/1.0/"
            doc = {
                "identifier": "old78",
                "title": "Old record",
                "creator": ["Band"],
                "licenseurl": pd,
            }
            return {"response": {"docs": [doc]}}
        return {"files": [{"name": "side-a.mp3", "title": "Side A"}]}

    monkeypatch.setattr(music, "_get", fake_get)
    cc = music.search_ccmixter("epic orchestral", 3)
    assert [t.title for t in cc] == ["Rise"] and cc[0].licence == "CC BY 3.0"
    ar = music.search_archive_audio("jazz", 2)
    assert ar[0].url == "https://archive.org/download/old78/side-a.mp3"
    assert ar[0].licence.startswith("Dominio público") and ar[0].creator == "Band"


def test_a_named_song_is_used_only_when_asked_and_never_replaced(monkeypatch, tmp_path):
    got_free = []
    song = music.Track(
        "https://youtu.be/x",
        "web",
        "Song",
        "Artist",
        "Con derechos de autor (no libre)",
    )
    picked = music.pick(
        "canción: Blinding Lights", {}, tmp_path, 10, "ffmpeg",
        searches={"openverse": lambda q, n, m: got_free.append(q) or []},
        song=lambda q, n: [song] if "Blinding" in q else [],
        fetcher=lambda t, d, total, ff: "ok",
    )  # fmt: skip
    assert picked is song and not got_free
    missing = music.pick("song: nothing", {}, tmp_path, 10, "ffmpeg", song=lambda q, n: [],
                         searches={"openverse": lambda q, n, m: [song]}, fetcher=lambda *a: "ok")  # fmt: skip
    assert missing is None  # not a different song in its place
    free = music.Track("https://x/a.mp3", "openverse", "A", "Ana", "CC BY 4.0")
    tries = []
    chosen = music.pick(
        "", {"audio": {"music": "lofi"}}, tmp_path, 10, "ffmpeg",
        searches={"openverse": lambda q, n, m: tries.append(q) or [free]},
        fetcher=lambda t, d, total, ff: "ok",
    )  # fmt: skip
    assert chosen is free and tries == ["lofi chill"]


def test_named_song_search_goes_through_ytdlp(monkeypatch):
    monkeypatch.setenv("SERGIO_CLIPS_WEB", "1")
    monkeypatch.setattr(sources, "ytdlp", lambda: ["yt-dlp"])
    out = music.search_song(
        "Blinding Lights",
        1,
        runner=lambda a: json.dumps(
            {"id": "abc", "title": "Blinding Lights", "duration": 200}
        ),
    )
    assert out[0].url.endswith("abc") and "no libre" in out[0].licence


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_fetch_loops_a_short_track_to_the_video_length(tmp_path):
    src = tmp_path / "short.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    str(src)], check=True)  # fmt: skip
    t = music.Track(str(src), "openverse", "Tone", "Test", "CC0")
    out = music.fetch(t, tmp_path / "m", 6.0, "ffmpeg")
    assert out and Path(out).exists()
    from openjarvis.video_essay import audio

    samples = audio.read_wav(Path(out).read_bytes())
    assert len(samples) / audio.SR == pytest.approx(6.5, abs=0.1)  # looped, not 2 s
    assert abs(samples[-200:]).max() < 0.05  # faded out


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_the_job_uses_internet_music_and_credits_it(tmp_path, monkeypatch):
    from openjarvis.video_essay import job as J

    track_wav = tmp_path / "bed.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=3",
                    "-ar", "48000", "-ac", "1", str(track_wav)], check=True)  # fmt: skip

    def fetcher(t, dest, total, ff):
        t.path = str(track_wav)
        return t.path

    deps = J.Deps(stock=True, music_searches={"openverse": lambda q, n, m: [
        music.Track("https://x/a.mp3", "openverse", "Bed", "Ana", "CC BY 4.0", page="https://j/a")]},
        music_fetch=fetcher)  # fmt: skip
    job = J.create({"topic": "x"}, tmp_path / "jobs")
    filler = media.Filler.__new__(media.Filler)
    filler.credits = []
    samples = J._music_online(job, deps, {}, {"audio": {"music": "epic"}}, 3.0, filler)
    assert samples is not None and len(samples) > 1000
    assert filler.credits[0]["kind"] == "música"
    st = job.state()
    assert st["music"]["title"] == "Bed" and st["credits"][0]["licence"] == "CC BY 4.0"


def test_a_face_is_never_under_the_words_even_to_vary_the_place(monkeypatch):
    """The last shot's place costs a little; a face costs everything."""
    img = Image.new("RGB", (320, 180), (40, 40, 44))
    monkeypatch.setattr(
        color, "_faces", lambda g: [(200, 40, 112, 112)]
    )  # a face in the middle
    sal = color.saliency(img)
    h, w = sal.shape
    assert (
        sal[int(h * 0.5), int(w * 0.5)] > 1.0
    )  # the chin and beard count too, above all else
    zone = color.best_zone(img, avoid=["lower_left"])
    assert zone in (
        "left",
        "right",
        "upper_left",
        "upper_right",
        "lower_left",
        "lower_right",
    )


def test_ink_blocks_when_white_would_not_read():
    words = _words("en el cielo claro")
    shot = P.Shot(first=0, last=4, kind="broll", start=0, end=1.6, text="en el cielo claro",
                  highlight="cielo", accent="#FF0000", box="all", position="lower")  # fmt: skip
    placed = render.layout_text(shot, words, (1280, 720))
    lit = [p for p in placed if p.text.lower() == "cielo"][0]
    rest = [p for p in placed if p is not lit]
    assert lit.bg == (255, 0, 0)
    assert all(p.bg == render.INK and p.rgb == (255, 255, 255) for p in rest)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_quality_check_does_not_flag_a_planned_black_card(tmp_path):
    from openjarvis.video_essay import pro

    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=2",
                    "-f", "lavfi", "-i", "color=c=black:s=320x180:d=1.5", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=2",
                    "-f", "lavfi", "-i", "sine=d=5.5", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1[v]",
                    "-map", "[v]", "-map", "3:a", "-shortest", str(clip)], check=True)  # fmt: skip
    assert "1 tramo(s) en negro" in pro.quality_check(clip, "ffmpeg")["problemas"]
    planned = pro.quality_check(clip, "ffmpeg", cards=[(2.0, 3.5)])
    assert not any("negro" in p for p in planned["problemas"])
