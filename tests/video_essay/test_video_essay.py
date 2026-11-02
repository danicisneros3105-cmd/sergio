"""Video essays at the level of a reference: plan, words, sound, review, the
job (real ffmpeg, fake models) and the tool."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from openjarvis.video_essay import audio, review, script, style
from openjarvis.video_essay import job as J
from openjarvis.video_essay import plan as P

TEXT = (
    "En 1994, nadie creía que una idea pequeña podía cambiarlo todo. "
    "Tenías metas enormes, pero cada mañana elegías la comodidad. "
    "Entonces pasó algo. Hoy, cada día cuenta. Todo empieza contigo."
)


def _words(text: str = TEXT) -> list:
    return P.estimate_words(text, [(0.2, 6.0), (6.4, 14.0)], 14.5)


def test_estimate_words_in_order_inside_the_voice() -> None:
    words = _words()
    assert [w.text for w in words] == TEXT.split()
    assert words[0].start >= 0.2 and words[-1].end <= 14.0 + 1e-6
    assert all(a.start <= b.start for a, b in zip(words, words[1:]))
    assert not any(6.0 < w.start < 6.4 for w in words)  # nothing in the pause


def test_normalise_covers_every_word_once_within_lengths() -> None:
    words = _words()
    shots = P.normalise([P.Shot(first=0, last=len(words))], words, max_s=3.0)
    covered = [i for s in shots for i in range(s.first, s.last)]
    assert covered == list(range(len(words)))
    assert all(s.dur <= 3.0 + 1.0 for s in shots)
    assert shots[0].start == 0.0
    assert all(a.end == b.start for a, b in zip(shots, shots[1:]))


def test_shown_text_never_adds_words() -> None:
    words = _words()
    s = P.Shot(first=0, last=3, text="Hola mundo inventado")
    out = P.normalise([s], words)
    assert out[0].text == "En 1994, nadie"


def test_empty_or_slow_model_plan_falls_back() -> None:
    words = _words()
    with pytest.raises(ValueError):
        P.from_model("{}", words)
    slow = json.dumps({"shots": [{"from": 0, "to": len(words)}]})
    shots = P.plan_shots(words, {"median_shot_s": 1.5}, ask=lambda p: slow)
    assert len(shots) >= 6  # the style's pace, not one long shot


def test_model_plan_is_kept_when_it_has_the_pace() -> None:
    words = _words()
    cuts = list(range(0, len(words), 3)) + [len(words)]
    items = [
        {"from": a, "to": b, "kind": "card", "card": "cream"}
        for a, b in zip(cuts, cuts[1:])
    ]
    shots = P.plan_shots(
        words, {"median_shot_s": 1.5}, ask=lambda p: json.dumps({"shots": items})
    )
    assert shots and all(s.kind == "card" for s in shots)


def test_chunks_keep_everything_under_the_limit() -> None:
    long = " ".join(["Una frase corta y clara."] * 200)
    parts = script.chunks(long, 300)
    assert all(len(p) <= 300 for p in parts)
    assert " ".join(parts).split() == long.split()


def test_align_keeps_the_script_spelling_with_heard_times() -> None:
    heard = [
        P.Word("en", 0.1, 0.3),
        P.Word("mil", 0.3, 0.5),
        P.Word("nadie", 0.9, 1.2),
        P.Word("creia", 1.2, 1.5),
    ]
    out = script.align(["En", "1994,", "nadie", "creía"], heard, 2.0)
    assert [w.text for w in out] == ["En", "1994,", "nadie", "creía"]
    assert out[2].start == 0.9 and out[3].start == 1.2
    assert out[0].start <= out[1].start <= out[2].start


def test_timings_without_recogniser_use_the_voice_energy() -> None:
    sr = audio.SR
    t = np.arange(sr) / sr
    voice = np.concatenate(
        [np.zeros(sr // 2), np.sin(2 * np.pi * 150 * t) * 0.5, np.zeros(sr // 2)]
    )
    words, how = script.timings(
        "uno dos tres",
        audio.write_wav(voice.astype(np.float32)),
        recogniser=lambda wav, lang: [],
    )
    assert how == "energía"
    assert 0.4 < words[0].start < 0.7 and words[-1].end < 1.7


def test_music_ducks_under_the_voice() -> None:
    n = audio.SR * 2
    voice = np.zeros(n, dtype=np.float32)
    voice[: n // 2] = np.sin(np.arange(n // 2) * 0.05) * 0.5
    music = np.ones(n, dtype=np.float32) * 0.5
    out = audio.mix(voice, music, None)
    under = np.abs(out[n // 4 : n // 2] - voice[n // 4 : n // 2]).mean()
    alone = np.abs(out[3 * n // 4 :]).mean()
    assert under < alone


def test_effects_are_placed_and_bounded() -> None:
    fx = audio.effects_track([(0.5, "whoosh"), (1.0, "impact"), (1.5, "nada")], 2.0)
    assert len(fx) == audio.SR * 2 and np.abs(fx).max() > 0.05


def test_review_applies_only_valid_changes() -> None:
    words = _words()
    shots = P.fallback(words, {"median_shot_s": 1.5})
    shots[1].asset = "/x.jpg"
    shots[1].kind = "broll"
    notes = {
        "changes": [
            {
                "shot": 1,
                "set": {
                    "grade": "bw",
                    "frame": "crt",
                    "visual": "an old clock",
                    "effect": "explode",
                },
            },
            {"shot": 999, "set": {"grade": "bw"}},
            {"shot": 0, "set": {"password": "x"}},
        ]
    }
    out, applied = review.apply(shots, words, notes)
    assert applied == 3
    assert out[1].grade == "bw" and out[1].frame == "crt" and out[1].asset == ""
    assert out[1].effect != "explode"


def test_profile_measures_the_reference() -> None:
    analysis = {
        "shots": [
            {"dur": 1.0, "visual": "solid red card", "on_screen_text": "EN"},
            {"dur": 2.0, "visual": "black and white archive", "effect": "CRT frame"},
            {"dur": 1.5, "visual": "clip inside an old computer", "effect": "device"},
            {"dur": 1.2, "visual": "city at night"},
        ],
        "palette": ["#E8262A", "nope"],
        "structure": [{"beat": "hook"}, {"beat": "payoff"}],
    }
    p = style.profile_from(analysis, "k", "Nombre", "ref.mp4")
    assert p["mix"] == {"card": 0.25, "archive": 0.25, "device": 0.25, "broll": 0.25}
    assert p["median_shot_s"] == 1.35 and p["palette_seen"] == ["#E8262A"]
    assert p["structure"] == ["hook", "payoff"]


def test_learn_saves_profile_and_shot_list(tmp_path: Path) -> None:
    fake = {"summary": "x", "shots": [{"dur": 1, "visual": "card"}]}
    p = style.learn(
        "/videos/Mi Referencia.mp4", folder=tmp_path, watcher=lambda s: fake
    )
    assert p["key"] == "mi-referencia"
    assert (tmp_path / "mi-referencia.json").is_file() and (
        tmp_path / "mi-referencia.tomas.json"
    ).is_file()
    assert style.load("mi-referencia", tmp_path)["key"] == "mi-referencia"
    assert style.load("", tmp_path)["key"] == style.DEFAULT
    assert {s["key"] for s in style.available(tmp_path)} >= {
        "mi-referencia",
        style.DEFAULT,
    }


# -- the job ---------------------------------------------------------------------------

TREATMENT = {
    "style": "metas-grandes",
    "title": "Metas grandes",
    "logline": "Por qué las metas grandes ganan.",
    "narration": "voice",
    "beats": [
        {"beat": "hook", "text": s, "seconds": 3, "visual": "a runner at dawn"}
        for s in TEXT.split(". ")
    ],
    "characters": [{"name": "Ana", "look": "30, short black hair, grey hoodie"}],
    "look": "warm, contrasty",
    "music": "builds",
    "sources": ["library", "stock", "image"],
}


def _speak(text: str) -> bytes:
    sr = 24000
    parts = []
    for w in text.split():
        n = int(sr * (0.1 + 0.03 * len(w)))
        parts += [
            np.sin(2 * np.pi * 140 * np.arange(n) / sr) * np.hanning(n) * 0.5,
            np.zeros(int(sr * 0.06)),
        ]
    return audio.write_wav(np.concatenate(parts).astype(np.float32), sr)


def _image(prompt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (640, 360), (60, 80, 100)).save(buf, "JPEG")
    return buf.getvalue()


def _deps(
    tmp_path: Path, told: list, calls: dict, treatment: dict = TREATMENT
) -> J.Deps:
    def ask(prompt, **kw):
        calls["ask"] = calls.get("ask", 0) + 1
        if "Write the treatment" in str(prompt):
            return json.dumps(treatment)
        if "posting package" in str(prompt):
            return json.dumps(
                {
                    "title": "Metas",
                    "description": "d",
                    "tags": ["a"],
                    "thumbnail_text": "METAS",
                }
            )
        return "{}"

    def look(parts, **kw):
        calls["review"] = calls.get("review", 0) + 1
        return json.dumps(
            {
                "score": 8,
                "verdict": "bien",
                "changes": [{"shot": 1, "set": {"grade": "bw"}}],
            }
        )

    return J.Deps(
        ask=ask,
        review=look,
        speak=_speak,
        recognise=lambda wav, lang: [],
        make_image=_image,
        stock=False,
        notify=lambda i, s: told.append(s),
        videos=tmp_path / "videos",
        styles=tmp_path / "estilos",
    )


needs_ffmpeg = pytest.mark.skipif(
    not __import__("openjarvis.tools.video_create", fromlist=["x"]).ffmpeg_exe(),
    reason="sin ffmpeg",
)


@pytest.fixture(autouse=True)
def _own_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path / "home"))


@needs_ffmpeg
def test_job_makes_the_video_and_tells_hous(tmp_path: Path) -> None:
    told: list = []
    calls: dict = {}
    job = J.create(
        {
            "topic": "metas grandes",
            "seconds": 15,
            "mode": "basic",
            "draft": True,
            "preset": "ultrafast",
        },
        tmp_path / "jobs",
    )
    st = J.run(job, _deps(tmp_path, told, calls))
    assert st["status"] == "listo", st.get("error")
    assert st["done"] == list(J.STAGES)
    assert st["mode"] == "basic" and st["style_key"] == "metas-grandes"
    assert len(st["passes"]) == 1 and st["passes"][0]["score"] == 8  # Basic: one review
    out = Path(st["result"]["path"])
    assert (
        out.is_file() and out.stat().st_size > 10_000 and out.name.startswith("video-")
    )
    assert told and "listo" in J.summary(told[0])
    assert st["result"]["shots"] >= 6
    assert st["budget"]["spent"]["llm"] == calls["ask"] + calls["review"]


@needs_ffmpeg
def test_post_quality_finishes_and_packages(tmp_path: Path) -> None:
    told: list = []
    calls: dict = {}
    job = J.create(
        {
            "topic": "metas",
            "seconds": 15,
            "mode": "post",
            "draft": True,
            "preset": "ultrafast",
        },
        tmp_path / "jobs",
    )
    st = J.run(job, _deps(tmp_path, told, calls))
    assert st["status"] == "listo", st.get("error")
    assert st["passes"][-1]["by"] in ("editor", "director")
    pkg = st["result"]["package"]
    assert pkg["title"] == "Metas" and pkg["cover_url"].startswith(
        "/v1/creator/media/portada-"
    )
    assert (job.dir / "final-color.mp4").is_file()  # Creator's colour chain
    assert "Listo para publicar" in J.summary(st)


@needs_ffmpeg
def test_film_without_narration_is_cut_on_its_beats(tmp_path: Path) -> None:
    film = {
        **TREATMENT,
        "style": "anuncio-comida",
        "narration": "none",
        "beats": [
            {"beat": "hook", "text": "", "seconds": 1.2, "visual": f"close-up {i}"}
            for i in range(8)
        ],
    }
    told: list = []
    job = J.create(
        {
            "prompt": "un anuncio de shawarma",
            "seconds": 10,
            "mode": "test",
            "draft": True,
        },
        tmp_path / "jobs",
    )
    st = J.run(job, _deps(tmp_path, told, {}, film))
    assert st["status"] == "listo", st.get("error")
    assert st["voice"] is False and st["timing"] == "ritmo"
    plan = job.read("plan.json")
    assert all(s["text_style"] == "none" for s in plan if s["kind"] != "card")


@needs_ffmpeg
def test_job_resumes_where_it_stopped(tmp_path: Path) -> None:
    told: list = []
    calls: dict = {}
    deps = _deps(tmp_path, told, calls)
    deps.make_image = lambda p: (_ for _ in ()).throw(RuntimeError("sin cuota"))
    job = J.create(
        {"topic": "metas", "mode": "test", "draft": True, "preset": "ultrafast"},
        tmp_path / "jobs",
    )
    original = J.shutil.copy2

    def broken(*a, **k):
        raise OSError("disco lleno")

    J.shutil.copy2 = broken
    try:
        st = J.run(job, deps)
    finally:
        J.shutil.copy2 = original
    assert (
        st["status"] == "error"
        and st["stage"] == "acabado"
        and "disco lleno" in st["error"]
    )
    asked = calls["ask"]
    st = J.run(job, deps)
    assert st["status"] == "listo"
    assert calls["ask"] == asked  # nothing written (or paid) twice
    assert st["attempts"] == 2
    assert all(s["kind"] == "card" for s in job.read("plan.json"))  # no picture: cards


@needs_ffmpeg
def test_budget_stops_paying_and_still_finishes(tmp_path: Path) -> None:
    told: list = []
    calls: dict = {}
    made = []
    deps = _deps(tmp_path, told, calls)
    deps.make_image = lambda p: made.append(p) or _image(p)
    job = J.create(
        {"topic": "metas", "mode": "test", "draft": True, "preset": "ultrafast"},
        tmp_path / "jobs",
    )
    st = J.run(job, deps)
    assert st["status"] == "listo"
    assert len(made) <= 8  # Test mode: at most 8 pictures, the rest are cards
    assert st["budget"]["spent"]["images"] == len(made)


def test_a_mode_without_model_calls_stops_cleanly(tmp_path: Path) -> None:
    calls: dict = {}
    job = J.create({"topic": "metas", "mode": "test"}, tmp_path / "jobs")
    job.update(budget={"limits": {"llm": 0, "minutes": 30}, "spent": {}})
    st = J.run(job, _deps(tmp_path, [], calls))
    assert st["status"] == "error" and "no gastar de más" in st["error"]
    assert "ask" not in calls  # nothing was called once the budget was out


def test_cancel_stops_before_the_next_stage(tmp_path: Path) -> None:
    job = J.create({"topic": "x"}, tmp_path)
    J._cancel[job.id] = __import__("threading").Event()
    J._cancel[job.id].set()
    st = J.run(job, J.Deps())
    assert st["status"] == "cancelado"


def test_summary_reads_like_a_person() -> None:
    assert f"paso 3 de {len(J.STAGES)}" in J.summary(
        {"title": "T", "status": "en curso", "stage": "voz", "stage_progress": 0.5}
    )
    assert "reintentar" in J.summary(
        {"title": "T", "status": "error", "stage": "voz", "error": "x"}
    )


def test_guards_one_at_a_time_no_repeats_daily_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    order = {"topic": "metas", "mode": "basic"}
    assert J.guard(order, tmp_path) == (None, "")
    first = J.create(order, tmp_path)
    # «en curso» with no thread behind it is dead, not «ya está en camino».
    assert J.guard(order, tmp_path) == (None, "")
    first.update(status="listo")
    assert J.guard(order, tmp_path)[1] == "repetido"
    first.update(status="error")
    assert J.guard(order, tmp_path) == (None, "")
    t = threading.Thread(target=lambda: None)
    J._running[first.id] = t
    t.start()
    try:
        t.join()
        J._running[first.id] = threading.Thread(
            target=threading.Event().wait, args=(5,), daemon=True
        )
        J._running[first.id].start()
        assert J.guard({"topic": "otro"}, tmp_path)[1] == "en curso"
    finally:
        J._running.pop(first.id, None)
    monkeypatch.setenv("SERGIO_VIDEO_JOBS_DIA", "1")
    assert J.guard({"topic": "otro"}, tmp_path)[1] == "tope diario"


def test_resume_and_retry_have_a_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = J.create({"topic": "x"}, tmp_path)
    job.update(attempts=J.MAX_ATTEMPTS)
    launched = []
    monkeypatch.setattr(J, "launch", lambda j, d=None: launched.append(j.id) or True)
    assert J.resume_unfinished(root=tmp_path) == []
    assert job.state()["status"] == "error" and not launched
    J.retry(job.id, root=tmp_path)
    assert not launched and "no lo repito" in job.state()["error"]


# -- modes, sources, AI and 3D ---------------------------------------------------------


def test_modes_grow_in_quality_and_budget() -> None:
    from openjarvis.video_essay import modes

    keys = [modes.MODES[k] for k in modes.ORDER]
    assert [m.passes for m in keys] == sorted(m.passes for m in keys)
    assert [m.limits["llm"] for m in keys] == sorted(m.limits["llm"] for m in keys)
    assert (
        modes.get("Absolut Cinema").key == "cinema"
        and modes.get("rápido").key == "test"
    )
    assert modes.get("???").key == "basic"
    b = modes.Budget({"llm": 1, "minutes": 10})
    b.spend("llm")
    with pytest.raises(modes.OverBudget):
        b.spend("llm")
    assert b.spent["llm"] == 1  # a refused spend is not counted


def test_sources_try_in_order_and_web_can_be_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openjarvis.video_essay import sources as S

    seen = []

    def fake(name):
        return lambda q, n, landscape: (
            seen.append(name) or [S.Candidate(f"https://x/{name}", name)]
        )

    table = {k: fake(k) for k in ("stock", "commons", "web")}
    got = S.find("rocket", 2, order=("stock", "commons", "web"), searches=table)
    assert [c.source for c in got] == ["stock", "commons"] and seen == [
        "stock",
        "commons",
    ]
    monkeypatch.setenv("SERGIO_CLIPS_WEB", "0")
    assert (
        S.search_web("rocket", 2, runner=lambda a: '{"id": "abc", "duration": 100}')
        == []
    )
    monkeypatch.setenv("SERGIO_CLIPS_WEB", "1")
    web = S.search_web(
        "rocket",
        2,
        runner=lambda a: (
            '{"id": "abc", "duration": 100, "channel": "C"}\n{"id": "x", "duration": 2}'
        ),
    )
    assert (
        len(web) == 1
        and web[0].start == 35.0
        and web[0].licence.startswith("Uso con cita")
    )
    text = S.credits_text(
        [c.to_dict() for c in web] + [{"source": "library", "url": "/mio.mp4"}]
    )
    assert "youtube.com/watch?v=abc" in text and "mio.mp4" not in text


@needs_ffmpeg
def test_filler_uses_clips_then_ai_then_cards(tmp_path: Path) -> None:
    from openjarvis.video_essay import modes, render
    from openjarvis.video_essay import sources as S
    from openjarvis.video_essay.media import Filler

    words = _words()
    shots = P.fallback(words, {"median_shot_s": 1.5})
    for s in shots:
        s.kind, s.visual = "broll", "a rocket launch"
    clip = tmp_path / "c.mp4"
    import subprocess

    subprocess.run(
        [
            render.ffmpeg(),
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=2",
            str(clip),
        ],
        check=True,
    )

    def fetch(c, dest, secs, ff):
        c.path = str(clip)
        return c.path

    ai_calls = []

    def provider(prompt, out, secs, aspect):
        ai_calls.append(prompt)
        raise RuntimeError("sin Veo")

    budget = modes.Budget(
        {
            "llm": 5,
            "images": 0,
            "downloads": 2,
            "ai_seconds": 100,
            "blender": 0,
            "minutes": 10,
        }
    )
    filler = Filler(
        tmp_path, modes.MODES["basic"], budget, ffmpeg=render.ffmpeg(), style={"look": "warm"},
        characters=[{"name": "Ana", "look": "30, black hair"}], preferred=["stock", "ai", "image"],
        searches={"stock": lambda q, n, landscape: [S.Candidate("https://x/1", "pexels")] * n},
        fetch=fetch, ai_provider=provider,
    )  # fmt: skip
    filler.fill(shots)
    with_clip = [s for s in shots if s.asset == str(clip)]
    assert len(with_clip) == 2  # two downloads allowed
    assert len(ai_calls) == 1  # AI failed once: never asked again in this job
    assert "Ana: 30, black hair" in ai_calls[0] and "five fingers" in ai_calls[0]
    assert all(s.kind == "card" for s in shots if s.asset != str(clip))


def test_blender_scene_is_checked_and_rendered_with_sergios_settings(
    tmp_path: Path,
) -> None:
    from openjarvis.tools.blender_model import UnsafeScript
    from openjarvis.video_essay import blender3d

    good = "import bpy\nbpy.ops.wm.read_factory_settings(use_empty=True)\nkit_box('Mesa', size=(1,1,1))\n"
    assert "kit_box" in blender3d.script_for(
        "a desk", 2.0, "warm", "", lambda p: "```python\n" + good + "```"
    )
    with pytest.raises(UnsafeScript):
        blender3d.script_for("x", 2.0, "", "", lambda p: "import os\nos.remove('/x')\n")
    seen = {}

    def runner(args):
        seen["script"] = Path(args[-1]).read_text()
        return 1

    with pytest.raises(RuntimeError):
        blender3d.render_shot(
            good, tmp_path / "t.mp4", 1.0, (640, 360), "ffmpeg", runner=runner
        )
    assert (
        "render.render(animation=True)" in seen["script"]
        and "kit_box" in seen["script"]
    )


def test_ai_prompt_directs_like_a_film_crew() -> None:
    from openjarvis.video_essay import aivideo

    p = aivideo.shot_prompt(
        "a chef rolls a wrap",
        {"look": "warm macro"},
        [{"name": "Chef", "look": "40, beard"}],
        "100mm macro push-in",
    )
    assert p.startswith("Characters (always identical): Chef: 40, beard")
    assert "100mm macro push-in" in p and "photorealistic" in p
    anim = aivideo.shot_prompt("a fox in a city", {"production": "animation"}, [], "")
    assert "animated film" in anim and "photorealistic" not in anim


def test_director_picks_a_known_style_and_cleans_the_treatment() -> None:
    from openjarvis.video_essay import director, style

    profiles = [style.load(k) for k in ("metas-grandes", "corto-3d", "anuncio-comida")]
    raw = {
        **TREATMENT,
        "style": "inventado",
        "narration": "loud",
        "sources": ["ai", "pirate"],
    }
    t = director.treatment("x", profiles, 30, lambda p, **kw: json.dumps(raw))
    assert (
        t["style"] == "metas-grandes"
        and t["narration"] == "voice"
        and t["sources"] == ["ai"]
    )
    t = director.treatment(
        "x", profiles, 30, lambda p, **kw: json.dumps(raw), fixed_style="corto-3d"
    )
    assert t["style"] == "corto-3d"


def test_the_four_new_references_are_styles() -> None:
    from openjarvis.video_essay import style

    keys = {s["key"] for s in style.available()}
    assert {
        "corto-3d",
        "reto-viral",
        "anuncio-comida",
        "animacion",
        "metas-grandes",
        "lanzamiento-producto",
    } <= keys
    launch = style.load("lanzamiento-producto")
    assert launch["narration_mode"] == "voice" and "3d" in launch["sources"]
    assert "Dyson" not in json.dumps(launch)
    assert style.load("corto-3d")["production"] == "3d"
    assert style.load("anuncio-comida")["narration_mode"] == "none"
    for k in keys:
        text = json.dumps(style.load(k))
        assert "Coca-Cola" not in text and "MrBeast" not in text


@needs_ffmpeg
def test_overlay_counts_up_and_none_hides_text() -> None:
    from openjarvis.video_essay import render

    words = _words()
    s = P.Shot(
        first=0,
        last=3,
        kind="card",
        card="black",
        overlay="$1,000,000",
        text_style="none",
        start=0,
        end=1.5,
    )
    assert render.layout_text(s, words, (640, 360)) == []
    early = render.still_of(s, words, (640, 360), at=0.05)
    late = render.still_of(s, words, (640, 360), at=0.9)
    assert np.asarray(early).sum() != np.asarray(late).sum()
    assert render.size_for("16:9", "2160") == (3840, 2160) and render.size_for(
        "9:16", "720"
    ) == (720, 1280)


def test_finishing_uses_creators_colour_chain() -> None:
    from openjarvis.video_essay import finish

    chain = finish.color_chain()
    assert (
        chain.startswith("format=yuv444p10le")
        and "curves=preset=medium_contrast" in chain
    )


# -- the tool --------------------------------------------------------------------------


def test_tool_starts_a_job_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from openjarvis.tools.video_essay_tool import VideoEssayTool

    started = {}
    hold = threading.Event()

    def fake_start(order, deps=None, root=None):
        started.update(order)
        job = J.create(order, tmp_path)
        J._running[job.id] = threading.Thread(target=hold.wait, args=(5,), daemon=True)
        J._running[job.id].start()  # alive, as a real start would be
        return job

    monkeypatch.setattr(J, "start", fake_start)
    monkeypatch.setattr(J, "resume_unfinished", lambda *a, **k: [])
    monkeypatch.setattr(J, "jobs_dir", lambda: tmp_path)
    monkeypatch.setattr("openjarvis.tools.video_essay_tool.ai_ready", lambda: True)
    tool = VideoEssayTool()
    res = tool.execute(
        action="start",
        prompt="un corto 3D de un reloj que rebobina",
        mode="cinema",
        seconds=9999,
    )
    assert res.success and res.metadata["job"]
    assert (
        started["seconds"] == 1800 and started["mode"] == "cinema" and started["prompt"]
    )
    assert "Absolut Cinema" in res.content and "no lo publico" in res.content
    again = tool.execute(
        action="start", prompt="un corto 3D de un reloj que rebobina", mode="cinema"
    )
    assert (
        again.metadata.get("reused") and again.metadata["job"] == res.metadata["job"]
    )  # no second paid job
    status = tool.execute(action="status")
    assert f"paso 1 de {len(J.STAGES)}" in status.content
    assert not tool.execute(action="start", topic="").success
    assert "corto-3d" in tool.execute(action="styles").content
    assert f"[[video:{res.metadata['job']}]]" in res.content  # the live card
    hold.set()
    J._running.pop(res.metadata["job"], None)


def test_tool_says_at_once_when_no_ai_is_connected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openjarvis.tools.video_essay_tool import VideoEssayTool

    started = []
    monkeypatch.setattr(J, "start", lambda *a, **k: started.append(1))
    monkeypatch.setattr(J, "jobs_dir", lambda: tmp_path)
    monkeypatch.setattr("openjarvis.tools.video_essay_tool.ai_ready", lambda: False)
    res = VideoEssayTool().execute(action="start", topic="metas")
    assert not res.success and not started
    assert "Conectar la IA" in res.content


def test_job_route_shows_a_dead_job_as_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server.personal_routes import router

    monkeypatch.setattr(J, "jobs_dir", lambda: tmp_path)
    job = J.create({"topic": "metas"}, tmp_path)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    d = c.get(f"/v1/personal/videos/trabajos/{job.id}").json()
    assert d["estado"] == "detenido" and d["pasos"] == len(J.STAGES)
    job.update(status="listo", result={"url": "/v.mp4"})
    d = c.get(f"/v1/personal/videos/trabajos/{job.id}").json()
    assert d["estado"] == "listo" and d["video"] == "/v.mp4"
    assert c.get("/v1/personal/videos/trabajos/nada").status_code == 404


def test_tool_is_wired_everywhere() -> None:
    from openjarvis.connectome import neurons
    from openjarvis.nodes import specialty
    from openjarvis.server.tasks_routes import TOOLS
    from openjarvis.speech import gemini_live
    from openjarvis.tools.video_essay_tool import VideoEssayTool

    root = Path(__file__).resolve().parents[2] / "src" / "openjarvis"
    assert (
        "openjarvis.tools.video_essay_tool"
        in (root / "tools" / "__init__.py").read_text()
    )
    assert VideoEssayTool().spec.name == "video_essay"
    assert "video_essay" in neurons.NEURONS["video"].tools
    assert "video_essay" in specialty.SPECIALTIES["hous"].toolkit
    assert "video_essay" in gemini_live.SERVER_TOOLS
    assert "video_essay" in TOOLS


def test_pace_follows_the_reference() -> None:
    assert P.pace({"median_shot_s": 1.5}) == pytest.approx(
        {"min_s": 0.45, "max_s": 3.6}
    )
    assert P.pace({"median_shot_s": 6, "min_shot_s": 0.1})["max_s"] == 6.0


@needs_ffmpeg
def test_video_with_trends_titles_and_three_covers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """«Con tendencias»: the radar runs first and its real signal reaches the
    director; the package gets the titles program and three covers to test."""
    from openjarvis.estudio import radar

    seen: dict = {}

    def fake_radar(nicho, pais, plataforma, **kw):
        seen["nicho"], seen["plataforma"] = nicho, plataforma
        return {"oportunidades": [{"gancho": "Nadie te dice esto", "formato": "short", "por_que": "x",
                                   "dato": {"tema": "metas de año nuevo", "fuente": "Google Trends"}}],
                "patrones": {"palabras_comunes": ["metas", "habitos"]}}  # fmt: skip

    monkeypatch.setattr(radar, "analizar", fake_radar)
    told: list = []
    job = J.create({"topic": "metas", "seconds": 15, "mode": "post", "draft": True, "preset": "ultrafast",
                    "tendencias": True, "pais": "EC"}, tmp_path / "jobs")  # fmt: skip
    st = J.run(job, _deps(tmp_path, told, {}))
    assert st["status"] == "listo", st.get("error")
    assert seen["nicho"] == "metas" and seen["plataforma"] == "youtube"
    assert st["tendencia"]["dato"] == "metas de año nuevo"
    pkg = st["result"]["package"]
    assert 1 <= len(pkg["portadas"]) <= 3
    assert "Tendencia usada: «metas de año nuevo» (Google Trends)" in J.summary(st)


def test_tool_turns_on_trends_when_the_order_says_so() -> None:
    from openjarvis.tools.video_essay_tool import TREND_WORDS

    assert TREND_WORDS.search("hazme un video con los trends de hoy")
    assert TREND_WORDS.search("algo viral sobre ahorro")
    assert not TREND_WORDS.search("un video sobre metas")


@needs_ffmpeg
def test_video_recreates_a_studied_reference(tmp_path: Path) -> None:
    """«molde»: the director hears the skeleton and the plan is cut where the reference cuts."""
    import json as _json

    from openjarvis.video_essay import escuela

    secs = [{"t": t, "cortes": 0, "caras": 0, "texto": {"abajo": 0.3}, "golpes": 1, "palabras": 2,
             "dice": "x", "movimiento": 0.1} for t in range(15)]  # fmt: skip
    data = {"url": "https://www.youtube.com/watch?v=abcdefghijk", "categoria": "shorts-virales",
            "medido": {"cortes": [3.0, 7.5, 11.0], "tomas": [3.0, 4.5, 3.5, 4.0], "segundos": secs,
                       "resumen": {"duracion_s": 15.0, "vertical": True, "gancho": ""}},
            "tomas_modelo": {"shots": [{"t": 7.5, "dur": 3.5, "effect": "zoom"}]}}  # fmt: skip
    folder = escuela.home() / "shorts-virales"
    folder.mkdir(parents=True)
    (folder / "abcdefghijk.json").write_text(_json.dumps(data))
    told: list = []
    calls: dict = {}
    job = J.create({"topic": "metas grandes", "seconds": 15, "mode": "basic", "draft": True, "preset": "ultrafast",
                    "molde": "https://youtube.com/shorts/abcdefghijk"}, tmp_path / "jobs")  # fmt: skip
    st = J.run(job, _deps(tmp_path, told, calls))
    assert st["status"] == "listo", st.get("error")
    assert st["molde"]["tomas"] == 4
    plan = job.read("plan.json")
    assert any("molde: toma" in " ".join(s.get("notes") or []) for s in plan)
    assert any(s.get("position") == "lower" for s in plan)
