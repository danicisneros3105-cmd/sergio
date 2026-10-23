"""Video essays at the level of a reference: plan, words, sound, review, the
job (real ffmpeg, fake models) and the tool."""

from __future__ import annotations

import io
import json
import shutil
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

SCRIPT = {
    "title": "Metas grandes",
    "beats": [{"beat": "hook", "text": s} for s in TEXT.split(". ")],
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


def _deps(tmp_path: Path, told: list, calls: dict) -> J.Deps:
    def ask(prompt: str, **kw):
        calls["ask"] = calls.get("ask", 0) + 1
        return json.dumps(SCRIPT) if "Structure" in prompt else "{}"

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


@needs_ffmpeg
def test_job_makes_the_video_and_tells_hous(tmp_path: Path) -> None:
    told: list = []
    calls: dict = {}
    job = J.create(
        {
            "topic": "metas grandes",
            "seconds": 15,
            "passes": 2,
            "draft": True,
            "preset": "ultrafast",
        },
        tmp_path / "jobs",
    )
    st = J.run(job, _deps(tmp_path, told, calls))
    assert st["status"] == "listo", st.get("error")
    assert st["done"] == list(J.STAGES)
    assert len(st["passes"]) >= 1 and st["passes"][0]["score"] == 8
    out = Path(st["result"]["path"])
    assert (
        out.is_file() and out.stat().st_size > 10_000 and out.name.startswith("video-")
    )
    assert told and "listo" in J.summary(told[0])
    assert (job.dir / "revision-1.jpg").is_file()
    assert st["result"]["shots"] >= 6


@needs_ffmpeg
def test_job_resumes_where_it_stopped(tmp_path: Path) -> None:
    told: list = []
    calls: dict = {}
    deps = _deps(tmp_path, told, calls)
    deps.make_image = lambda p: (_ for _ in ()).throw(RuntimeError("sin cuota"))
    job = J.create(
        {"topic": "metas", "passes": 0, "draft": True, "preset": "ultrafast"},
        tmp_path / "jobs",
    )
    original = shutil.copy2

    def broken(*a, **k):
        raise OSError("disco lleno")

    J.shutil.copy2 = broken
    try:
        st = J.run(job, deps)
    finally:
        J.shutil.copy2 = original
    assert (
        st["status"] == "error"
        and st["stage"] == "render"
        and "disco lleno" in st["error"]
    )
    asked = calls["ask"]
    st = J.run(job, deps)
    assert st["status"] == "listo"
    assert calls["ask"] == asked  # the script was not written (or paid) twice
    plan = job.read("plan.json")
    assert all(
        s["kind"] == "card" for s in plan
    )  # no picture: black cards, not an error


def test_cancel_stops_before_the_next_stage(tmp_path: Path) -> None:
    job = J.create({"topic": "x"}, tmp_path)
    J._cancel[job.id] = __import__("threading").Event()
    J._cancel[job.id].set()
    st = J.run(job, J.Deps())
    assert st["status"] == "cancelado"


def test_summary_reads_like_a_person() -> None:
    assert "paso 3 de 10" in J.summary(
        {"title": "T", "status": "en curso", "stage": "voz", "stage_progress": 0.5}
    )
    assert "reintentar" in J.summary(
        {"title": "T", "status": "error", "stage": "voz", "error": "x"}
    )


# -- the tool --------------------------------------------------------------------------


def test_tool_starts_a_job_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openjarvis.tools.video_essay_tool import VideoEssayTool

    started = {}

    def fake_start(order, deps=None, root=None):
        started.update(order)
        return J.create(order, tmp_path)

    monkeypatch.setattr(J, "start", fake_start)
    monkeypatch.setattr(J, "resume_unfinished", lambda *a, **k: [])
    monkeypatch.setattr(J, "jobs_dir", lambda: tmp_path)
    tool = VideoEssayTool()
    res = tool.execute(
        action="start",
        topic="metas grandes",
        reference="https://youtu.be/abc",
        seconds=9999,
        passes=9,
    )
    assert res.success and res.metadata["job"]
    assert started["seconds"] == 600 and started["passes"] == 5 and started["reference"]
    assert "no lo publico" in res.content
    status = tool.execute(action="status")
    assert "paso 1 de 10" in status.content
    assert not tool.execute(action="start", topic="").success
    assert "metas-grandes" in tool.execute(action="styles").content


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
