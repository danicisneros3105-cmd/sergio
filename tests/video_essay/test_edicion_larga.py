"""Longer videos, more clips, rolling captions, one colour, a better voice
(owner, 27 Oct 2026: «mejora la edición mucho más, videos más largos, más
clips, mejores subtítulos, más coherencia. Y la voz es una mierda»)."""

from __future__ import annotations

import io
import json
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from openjarvis.video_essay import color, director, media, modes, render, script
from openjarvis.video_essay import plan as P
from openjarvis.video_essay import sources as S

# -- voice ---------------------------------------------------------------------------


def test_the_own_voice_never_falls_back_to_kokoro_unless_asked(monkeypatch):
    from openjarvis.speech import voz_propia as V

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("SERGIO_VOZ", raising=False)
    assert V.engine() == ""  # Gemini Live speaks
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    assert V.engine() == "elevenlabs"
    monkeypatch.setenv("SERGIO_VOZ", "gemini")
    assert V.engine() == ""
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    monkeypatch.setenv("SERGIO_VOZ", "propia")
    assert V.engine() in ("kokoro", "")  # only when forced (and installed)


def test_the_own_voice_speaks_each_phrase_with_elevenlabs(monkeypatch):
    from openjarvis.speech import elevenlabs_voice as E
    from openjarvis.speech import voz_propia as V

    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.delenv("SERGIO_VOZ", raising=False)
    asked = []
    monkeypatch.setattr(
        E, "pcm", lambda text, **kw: asked.append((text, kw)) or b"\1\0" * 10
    )
    assert V.speak_pcm("Hola, señor.", previous="Claro,") == b"\1\0" * 10
    assert asked[0][0] == "Hola, señor." and asked[0][1]["previous"] == "Claro,"


def _wav(seconds: float = 0.2, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return buf.getvalue()


def test_the_narrator_is_directed_and_elevenlabs_goes_first(monkeypatch):
    from openjarvis.speech import elevenlabs_voice as E
    from openjarvis.speech import gemini_voice as G

    told = {}

    def gemini(text, voice, style="", models=None):
        told.update(style=style, models=models)
        return _wav()

    monkeypatch.setattr(G, "speak", gemini)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    script.narrator()("Hola.", "")
    assert told["style"] == script.NARRATOR and told["models"][0].startswith(
        "gemini-2.5-pro"
    )
    assert "monótono" in script.NARRATOR and "narrador" in script.NARRATOR
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    used = []
    monkeypatch.setattr(
        E, "pcm", lambda text, **kw: used.append(kw["model_id"]) or b"\0\0" * 2400
    )
    script.narrator()("Hola.", "antes")
    assert used == [E.QUALITY_MODEL]


def test_a_long_narration_is_made_in_parallel_and_in_order(monkeypatch):
    text = " ".join(f"Frase número {i} del guion largo." for i in range(400))
    parts = script.chunks(text)
    assert len(parts) > 3
    lengths = {p: 0.1 + 0.05 * i for i, p in enumerate(parts)}
    wav = script.narrate(text, speak=lambda p: _wav(lengths[p]))
    from openjarvis.video_essay import audio

    total = len(audio.read_wav(wav)) / audio.SR
    assert total == pytest.approx(
        sum(lengths.values()) + 0.28 * (len(parts) - 1) + 0.15 + 0.28, abs=0.05
    )


# -- longer videos -------------------------------------------------------------------


def test_budget_grows_with_the_length_but_not_ai_video():
    basic = modes.get("basic")
    short = modes.limits_for(basic, 60)
    assert short == basic.limits
    ten = modes.limits_for(basic, 600)
    assert ten["downloads"] == round(basic.limits["downloads"] * 600 / 90)
    assert ten["minutes"] > basic.limits["minutes"] and ten["llm"] > basic.limits["llm"]
    assert ten["ai_seconds"] == basic.limits["ai_seconds"]
    assert modes.Budget.from_dict({}, basic, 600).limits == ten


def test_a_long_treatment_has_chapters_and_asks_again_when_too_short():
    prompts = []

    def ask(prompt, **kw):
        prompts.append(prompt)
        words = 60 if len(prompts) == 1 else 500
        return json.dumps({
            "style": "x", "title": "T", "narration": "voice",
            "beats": [{"beat": "hook", "text": " ".join(["palabra"] * words), "seconds": 10}],
        })  # fmt: skip

    data = director.treatment("hábitos", [{"key": "x", "name": "X"}], 300, ask)
    assert "LONG video" in prompts[0] and "chapters" in prompts[0]
    assert "Coherence" in prompts[0]
    assert len(prompts) == 2 and "only 60 words" in prompts[1]
    assert len(data["text"].split()) == 500


def _words(n: int, every: int = 8):
    out = []
    for i in range(n):
        text = f"w{i}." if (i + 1) % every == 0 else f"w{i}"
        out.append(P.Word(text, i * 0.4, i * 0.4 + 0.35))
    return out


def test_a_long_narration_is_planned_in_stretches_that_see_the_last_one():
    words = _words(600)
    segs = P.segments(words)
    assert len(segs) >= 3 and segs[0][0] == 0 and segs[-1][1] == 600
    assert all(b - a <= P.SEGMENT_WORDS for a, b in segs)
    assert all(words[b - 1].text.endswith(".") for a, b in segs[:-1])
    seen = []

    def ask(prompt):
        seen.append(prompt)
        idx = [
            int(t.split(":")[0])
            for t in prompt.split("NARRATION, word by word with their index:")[
                1
            ].split()
            if ":" in t and t.split(":")[0].isdigit()
        ]  # noqa: E501
        a, b = idx[0], idx[-1] + 1
        if len(seen) == 2:
            raise RuntimeError("model down")  # this stretch gets the fallback
        shots = [
            {"from": i, "to": min(b, i + 4), "kind": "broll", "visual": f"picture {i}"}
            for i in range(a, b, 4)
        ]
        return json.dumps({"shots": shots})

    shots = P.plan_shots(words, {"median_shot_s": 1.6}, ask)
    assert len(seen) == len(segs)
    assert (
        "The stretch before ended with these shots" in seen[1] and "picture" in seen[1]
    )
    assert shots[0].first == 0 and shots[-1].last == 600
    assert all(a.last == b.first for a, b in zip(shots, shots[1:]))  # every word once


# -- more clips ----------------------------------------------------------------------


def test_queries_go_from_the_full_picture_to_its_core():
    shot = P.Shot(
        first=0,
        last=1,
        visual="a lonely man walking on a rainy city street at night, wide shot",
    )
    q = media.queries(shot)
    assert (
        q[0].startswith("a lonely man")
        and q[1] == "lonely man walking rainy city"
        and q[2] == "lonely man"
    )


def _filler(tmp_path, searches, fetch):
    budget = modes.Budget({"downloads": 50, "images": 0, "llm": 0, "minutes": 10})
    return media.Filler(tmp_path, modes.get("test"), budget, ffmpeg="ffmpeg", style={}, characters=[],
                        preferred=["stock", "image"], searches=searches, fetch=fetch)  # fmt: skip


def test_a_shot_that_finds_nothing_gets_a_new_piece_of_a_found_clip(tmp_path):
    def search(q, n, landscape):
        for animal in ("dog", "cat", "bird"):
            if animal in q:
                return [
                    S.Candidate(
                        f"https://x/{animal}.mp4", "pexels", "Ana", "Pexels", start=2.0
                    )
                ]
        return []

    cut = []

    def fetch(c, dest, seconds, ff):
        c.path = str(dest / f"{len(cut)}.mp4")
        cut.append((c.url, c.start))
        return c.path

    filler = _filler(tmp_path, {"stock": search}, fetch)
    shots = [
        P.Shot(
            first=0, last=1, start=0, end=2, visual="a happy dog running in the park"
        ),
        P.Shot(first=1, last=2, start=2, end=4, visual="a calm dog sleeping"),
        P.Shot(first=2, last=3, start=4, end=6, visual="a cat on a sofa"),
        P.Shot(first=3, last=4, start=6, end=8, visual="a bird on a wire"),
        P.Shot(first=4, last=5, start=8, end=10, visual="an empty spaceship corridor"),
    ]
    filler.fill(shots)
    assert cut[0] == ("https://x/dog.mp4", 2.0)
    assert cut[1] == ("https://x/dog.mp4", 8.0)  # the same clip again: a later piece
    last = shots[-1]
    assert last.kind == "broll" and "otro trozo" in last.notes[-1]
    assert cut[-1][0] == "https://x/dog.mp4"  # not the clips of the last two shots
    assert len(set(cut)) == len(cut)  # never the same piece twice


# -- captions ------------------------------------------------------------------------


def test_phrases_cut_at_punctuation_and_never_leave_one_word_alone():
    assert media is not None
    groups = render.chunks_of("Uno dos, tres cuatro cinco seis siete".split())
    assert groups == [[0, 1], [2, 3, 4, 5, 6]]
    assert render.chunks_of(["a", "b", "c", "d", "e", "f", "g", "h"]) == [
        [0, 1, 2, 3],
        [4, 5, 6, 7],
    ]


def test_a_long_shot_rolls_its_captions_and_lights_the_word_being_said():
    words = [
        P.Word(w, i * 0.5, i * 0.5 + 0.45)
        for i, w in enumerate("cada mañana elige una cosa pequeña y hazla bien".split())
    ]
    shot = P.Shot(
        first=0, last=len(words), kind="broll", start=0, end=5, accent="#FF2020"
    )
    placed = render.layout_text(shot, words, (1280, 720))
    first = [p for p in placed if p.until == placed[0].until]
    assert 2 <= len(first) <= 4 and placed[0].until < 5
    canvas_at = {}
    for t in (0.2, 2.6):
        visible = [p.text for p in placed if p.start <= t < p.until]
        canvas_at[t] = visible
    assert (
        canvas_at[0.2] == ["cada"] and "cada" not in canvas_at[2.6]
    )  # the phrase was replaced
    lit = [p for p in placed if p.lit_rgb]
    assert lit and lit[0].lit_rgb == (255, 32, 32)
    img = Image.new("RGBA", (1280, 720), (0, 0, 0, 255))
    render.draw_text(img, placed, 1.2, "pop", True)
    a = np.asarray(img)[..., :3]
    assert ((a[..., 0] > 200) & (a[..., 1] < 80)).sum() > 100  # the said word glows red
    card = P.Shot(first=0, last=len(words), kind="card", start=0, end=5)
    assert all(
        p.until == float("inf") for p in render.layout_text(card, words, (1280, 720))
    )


# -- one colour ----------------------------------------------------------------------


def test_shots_from_different_cameras_meet_half_way():
    warm = Image.new("RGB", (160, 90), (200, 120, 60))
    cold = Image.new("RGB", (160, 90), (60, 110, 200))
    a = P.Shot(first=0, last=1, kind="broll")
    b = P.Shot(first=1, last=2, kind="broll")
    card = P.Shot(first=2, last=3, kind="card")
    stills = {id(a): warm, id(b): cold}
    assert color.unify([a, b, card], lambda s: stills[id(s)]) == 2
    assert card.tone == [] and len(a.tone) == 6
    wa = color.mean_rgb(color.apply_tone(warm, a.tone))
    wb = color.mean_rgb(color.apply_tone(cold, b.tone))
    before = abs(200 - 60) + abs(60 - 200)
    after = abs(wa[0] - wb[0]) + abs(wa[2] - wb[2])
    assert after < before * 0.6  # closer, but each keeps its own light
    assert wa[0] > wb[0]
    assert color.unify([a, b], lambda s: stills[id(s)]) == 0  # safe to run again


def test_the_render_applies_the_match(tmp_path):
    pic = tmp_path / "p.png"
    Image.new("RGB", (320, 180), (200, 120, 60)).save(pic)
    shot = P.Shot(first=0, last=1, kind="broll", asset=str(pic), start=0, end=0.2, text_style="none",
                  tone=[1.0, -40.0, 1.0, 0.0, 1.0, 40.0])  # fmt: skip
    frame = next(iter(render.shot_frames(shot, [P.Word("x", 0, 0.1)], (320, 180))))
    r, g, b = color.mean_rgb(frame)
    assert r < 175 and b > 85


def test_the_plan_reads_and_keeps_the_tone():
    s = P.Shot(first=0, last=1, tone=[1.1, -2, 1, 0, 0.9, 3])
    assert P.from_json(P.to_json([s]))[0].tone == [1.1, -2, 1, 0, 0.9, 3]
    assert Path(render.__file__).exists()


def test_his_library_clips_are_cut_again_instead_of_a_black_card(tmp_path):
    class Lib:
        def pick(self, shot):
            return (
                "/clips/hombre-corriendo-calle.mp4"
                if "running" in shot.visual
                else None
            )

    cut = []

    def fetch(c, dest, seconds, ff):
        c.path = str(dest / f"{len(cut)}.mp4")
        cut.append((c.url, c.start))
        return c.path

    budget = modes.Budget({"downloads": 50, "images": 0, "llm": 0, "minutes": 10})
    filler = media.Filler(tmp_path, modes.get("test"), budget, ffmpeg="ffmpeg", style={}, characters=[],
                          preferred=["library", "image"], library=Lib(), searches={}, fetch=fetch)  # fmt: skip
    shots = [
        P.Shot(first=0, last=1, start=0, end=2, visual="a man running at dawn"),
        P.Shot(first=1, last=2, start=2, end=4, visual="a clock on a wall"),
        P.Shot(first=2, last=3, start=4, end=6, visual="a door closing"),
        P.Shot(first=3, last=4, start=6, end=8, visual="sunrise over the city"),
    ]
    filler.fill(shots)
    assert shots[0].asset == "/clips/hombre-corriendo-calle.mp4"
    # no black cards: later moments of the one clip there is
    assert all(s.kind == "broll" for s in shots)
    assert [c[1] for c in cut] == [2.5, 5.0, 7.5]
