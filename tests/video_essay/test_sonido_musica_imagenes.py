"""Owner, 28 Oct 2026: «los efectos de sonido están meh, la música debe ser
trending pero acorde al video, las fotos no tienen sentido, faltan clips de
películas». Fewer and better sounds, this week's popular free music for the
genre, footage that shows what is said, and film scenes even when the model
is busy."""

from __future__ import annotations

import json

import numpy as np

from openjarvis.video_essay import audio, films, music
from openjarvis.video_essay import sources as S
from openjarvis.video_essay.assets import Library
from openjarvis.video_essay.plan import Shot, Word

# -- sound effects -------------------------------------------------------------------


def test_effects_are_spaced_and_big_hits_stay_special():
    events = [
        (i * 0.5, "impact" if i % 2 else "pop") for i in range(120)
    ]  # every 0.5 s
    kept = audio.thin(events, 60.0)
    times = [t for t, _ in kept]
    assert len(kept) <= 14
    assert all(b - a >= 1.8 for a, b in zip(times, times[1:]))
    assert sum(k == "impact" for _, k in kept) <= 14 // 3


def test_the_same_effect_never_sounds_identical_twice_in_a_row():
    fx = audio.effects_track([(0.5, "whoosh"), (2.0, "whoosh")], 3.0)
    a = fx[: audio.SR]
    b = fx[int(1.5 * audio.SR) : int(2.5 * audio.SR)]
    assert np.abs(a).max() > 0.1 and np.abs(b).max() > 0.1
    assert not np.allclose(a[: len(b)], b[: len(a)], atol=1e-3)


def test_every_effect_is_clean_and_bounded():
    for name, make in audio.EFFECTS.items():
        x = make()
        assert np.isfinite(x).all() and 0.2 < np.abs(x).max() <= 1.0, name


def test_his_own_sounds_win(tmp_path):
    folder = tmp_path / audio.SOUNDS_DIR
    folder.mkdir()
    tone = (np.sin(np.arange(audio.SR // 4) * 0.3) * 0.5).astype(np.float32)
    (folder / "impact-01.wav").write_bytes(audio.write_wav(tone))
    fx = audio.effects_track([(1.0, "impact")], 2.0, home=tmp_path)
    start = int(audio.SR * 0.92)
    assert np.allclose(
        fx[start : start + 100] / np.abs(fx).max(), tone[:100] / 0.5, atol=0.05
    )


def test_effects_step_back_under_the_voice():
    n = audio.SR * 2
    voice = np.zeros(n, dtype=np.float32)
    voice[: n // 2] = np.sin(np.arange(n // 2) * 0.05) * 0.5
    fx = np.ones(n, dtype=np.float32) * 0.2
    out = audio.mix(voice, None, fx)
    under = np.abs(out[n // 4 : n // 2] - voice[n // 4 : n // 2]).mean()
    alone = np.abs(out[3 * n // 4 :]).mean()
    assert under < alone * 0.8


# -- music ---------------------------------------------------------------------------


def test_the_genre_sets_the_music_when_the_style_says_nothing():
    assert music.mood_query({}, genre="pesada") == music.GENRE_MUSIC["pesada"]
    lofi = {"audio": {"music": "lofi"}}
    assert music.mood_query(lofi, genre="pesada") == "lofi chill"  # the style wins
    assert music.mood_query({}, "piano triste", "pesada") == "piano triste"  # he wins


def test_jamendo_brings_this_weeks_popular_free_instrumentals(monkeypatch):
    seen = {}
    data = {"results": [
        {"name": "Run", "artist_name": "Ana", "audio": "https://j/1.mp3", "duration": 150,
         "license_ccurl": "http://creativecommons.org/licenses/by/3.0/", "shareurl": "https://j/1"},
        {"name": "Calm", "artist_name": "Beto", "audio": "https://j/2.mp3", "duration": 150,
         "license_ccurl": "http://creativecommons.org/licenses/by-nc/3.0/"},
        {"name": "Fixed", "artist_name": "Cami", "audio": "https://j/3.mp3", "duration": 150,
         "license_ccurl": "http://creativecommons.org/licenses/by-nd/3.0/"},
    ]}  # fmt: skip

    def fake_get(url, **kw):
        seen.update(kw.get("params") or {})
        return data

    monkeypatch.setattr(music, "_get", fake_get)
    monkeypatch.delenv("JAMENDO_CLIENT_ID", raising=False)
    assert music.search_jamendo("epic", 3) == []  # no key: nothing, no error
    monkeypatch.setenv("JAMENDO_CLIENT_ID", "k")
    got = music.search_jamendo("energetic hip hop beat", 3)
    assert [t.title for t in got] == ["Run"]  # NC and ND refused for money
    assert (
        seen["order"] == "popularity_week"
        and seen["vocalinstrumental"] == "instrumental"
    )
    assert got[0].licence == "CC BY 3.0" and got[0].source == "jamendo"


def test_ranking_prefers_popular_fitting_and_unsung():
    a = music.Track("u1", "ccmixter", "Quiet piano", seconds=200)
    b = music.Track("u2", "jamendo", "Epic cinematic rise", seconds=200, plays=900)
    c = music.Track(
        "u3", "jamendo", "Epic cinematic (feat. Singer)", seconds=200, plays=1000
    )
    assert music.rank([a, c, b], "epic cinematic", 120)[0] is b


# -- pictures that make sense ----------------------------------------------------------


def test_one_generic_shared_word_does_not_pick_his_clip(tmp_path):
    for name in ("man eating hot dog.mp4", "runner on mountain road at dawn.mp4"):
        (tmp_path / name).write_bytes(b"x")
    lib = Library([str(tmp_path)])
    shot = Shot(0, 1, visual="a tired man running up a mountain road")
    assert lib.pick(shot).endswith("runner on mountain road at dawn.mp4")
    lonely = Shot(0, 1, visual="a man looking at the city at night")
    assert lib.pick(lonely) is None  # «man» alone is chance: not the hot dog


def test_the_editor_can_reject_every_candidate():
    from PIL import Image

    frame = Image.new("RGB", (32, 18))
    rows = [
        {"shot": "a runner", "frames": [frame, frame]},
        {"shot": "fire", "frames": [frame]},
    ]
    picks = S.choose(
        rows, lambda parts, prompt: json.dumps({"picks": {"0": "B", "1": "-"}})
    )
    assert picks == {0: 1, 1: -1}
    assert "makes no sense" in S.CHOOSE_PROMPT


def test_a_rejected_shot_gets_a_made_picture_or_a_card(tmp_path):
    from openjarvis.video_essay import media
    from openjarvis.video_essay.modes import MODES, Budget

    mode = MODES["test"]
    filler = media.Filler(
        tmp_path, mode, Budget(mode.limits), ffmpeg="ffmpeg", style={}, characters=[],
        preferred=["stock"], make_image=None,
    )  # fmt: skip
    filler.broken.add("image")
    filler.pool = [S.Candidate("https://x/hotdog.mp4", "stock", query="hot dog stand")]
    shot = Shot(0, 1, kind="broll", visual="astronaut floating in space")
    filler._replace(shot, [S.Candidate("https://x/dog.mp4", "stock")])
    assert shot.kind == "card" and not shot.asset  # never the hot dog


def test_reuse_only_takes_a_clip_about_the_same_thing(tmp_path):
    from openjarvis.video_essay import media
    from openjarvis.video_essay.modes import MODES, Budget

    mode = MODES["test"]
    got = []
    filler = media.Filler(
        tmp_path, mode, Budget(mode.limits), ffmpeg="ffmpeg", style={}, characters=[],
        preferred=["stock"], fetch=lambda c, d, s, f: got.append(c.url) or "/x.mp4",
    )  # fmt: skip
    filler.pool = [
        S.Candidate("https://x/hotdog.mp4", "stock", query="hot dog stand"),
        S.Candidate("https://x/run.mp4", "stock", query="athlete running stadium"),
    ]
    piece = filler._reuse(Shot(0, 1, visual="a runner on a mountain road"), [])
    assert piece is not None and got == ["https://x/run.mp4"]
    assert filler._reuse(Shot(0, 1, visual="volcano erupting"), []) is None


# -- film scenes even when the model is busy ------------------------------------------


def _film_shots():
    w = [
        Word(t, i, i + 0.9)
        for i, t in enumerate("Nunca te rindas aunque caigas mil veces".split())
    ]
    return [
        Shot(0, 3, kind="broll", source="film"),
        Shot(3, 7, kind="broll", source="film"),
    ], w


def test_a_busy_model_is_asked_again(monkeypatch):
    waits = []
    monkeypatch.setattr(films, "sleep", waits.append)
    calls = []

    def ask(prompt):
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("503 UNAVAILABLE")
        return json.dumps(
            {"scenes": [{"shot": 0, "film": "Rocky", "year": 1976, "scene": "steps"}]}
        )

    shots, words = _film_shots()
    assert films.plan_scenes(shots, words, "t", "l", ask) == 1
    assert waits == [films.RETRY_WAITS[0]] and shots[0].search.startswith(
        "Rocky (1976)"
    )


def test_no_model_at_all_still_gives_famous_real_scenes(monkeypatch):
    monkeypatch.setattr(films, "sleep", lambda s: None)

    def down(prompt):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    shots, words = _film_shots()
    assert films.plan_scenes(shots, words, "t", "l", down) == 2
    named = [s.search for s in shots]
    assert all(
        any(n.startswith(f"{k[1]} ({k[2]})") for k in films.KNOWN_SCENES) for n in named
    )
