"""Clips con sentido, gráficos animados, 2.5D, render en paralelo y videos
largos (dueño, 2 nov. 2026: «mejora la selección de clips… motion graphics…
coherencia… 0 retraso… animaciones… hasta 8 minutos»)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from openjarvis.video_essay import genres, render
from openjarvis.video_essay import sources as S
from openjarvis.video_essay.plan import Shot, Word


def test_rank_puts_the_official_relevant_scene_first():
    wanted = "astronaut walking on the moon surface"
    fan = S.Candidate(
        "u1", "web", "Random Guy", title="Moon landing REACTION video", seconds=900
    )
    official = S.Candidate(
        "u2",
        "web",
        "Movieclips",
        title="First Man (2018) - Walking on the Moon Scene",
        seconds=180,
    )
    stock = S.Candidate("u3", "pexels", "Pexels", title="")
    got = S.rank([fan, stock, official], wanted)
    assert got[0] is official and got[-1] is fan


def test_whole_films_uploaded_by_others_are_never_taken():
    lines = [
        {
            "id": "a",
            "title": "Interstellar FULL MOVIE english",
            "channel": "x",
            "duration": 9000,
        },
        {
            "id": "b",
            "title": "Interstellar docking scene",
            "channel": "Movieclips",
            "duration": 160,
        },
    ]
    got = S.search_web(
        "interstellar", 4, runner=lambda args: "\n".join(map(json.dumps, lines))
    )
    assert [c.title for c in got] == ["Interstellar docking scene"]
    assert got[0].seconds == 160


def test_new_motion_graphics_draw():
    from PIL import Image

    for kind in (
        "lower:Marie Curie|Física",
        "pin:Cuenca",
        "vs:Tesla|Edison",
        "year:1969",
        "frame",
    ):
        canvas = Image.new("RGBA", (640, 360), (30, 30, 30, 255))
        assert render.draw_motion(canvas, kind, 1.0, (255, 59, 48), (0.5, 0.5)), kind
        assert canvas.getbbox() is not None


def _words(text: str) -> list:
    return [Word(w, i * 0.4, i * 0.4 + 0.4) for i, w in enumerate(text.split())]


def test_graphics_follow_what_is_said():
    words = _words(
        "En 1969 el hombre llegó a la Luna . "
        "Fue Tesla contra Edison por la corriente . "
        "Todo empezó en Cuenca hace años . "
        "Lo explicó Marie Curie en su laboratorio"
    )
    cut = [0, 8, 16, 22, 29]
    shots = [Shot(first=a, last=b) for a, b in zip(cut, cut[1:] + [len(words)])]
    shots = shots[:4] + [Shot(first=22, last=len(words))]
    for s in shots:
        s.overlay = ""
    genres.story_graphics(shots, words, "documental")
    overlays = [s.overlay for s in shots]
    assert overlays[0] == "year:1969"
    assert overlays[2] == "pin:Cuenca" and overlays[4] == "lower:Marie Curie"
    vs_words = _words("Fue Tesla contra Edison por la corriente")
    vs_shot = [Shot(first=0, last=len(vs_words))]
    genres.story_graphics(vs_shot, vs_words, "pesada")
    assert vs_shot[0].overlay == "vs:Tesla|Edison"
    assert not any(
        a and b for a, b in zip(overlays, overlays[1:])
    )  # never two in a row
    assert genres.story_graphics(shots, words, "cine") == 0  # a film breathes


def test_photos_of_documentaries_and_animations_get_the_2_5d_move(tmp_path):
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"x")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    shots = [
        Shot(first=0, last=1, asset=str(photo)),
        Shot(first=1, last=2, asset=str(clip)),
    ]
    genres.after_fill(shots, "animacion")
    assert shots[0].effect == "parallax" and shots[1].effect == "none"


def test_parallax_without_the_cut_out_model_is_a_plain_push(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(render, "depth_layers", lambda img: None)
    path = tmp_path / "p.png"
    Image.new("RGB", (400, 300), (10, 120, 200)).save(path)
    still = render.Still(str(path), (320, 180), "parallax")
    frames = list(still.frames(10))
    assert len(frames) == 10 and frames[0].size == (320, 180)


def _card_shots(n: int, each: float):
    words, shots, t = [], [], 0.0
    for i in range(n):
        words.append(Word(f"w{i}", t, t + each))
        shots.append(
            Shot(
                first=i,
                last=i + 1,
                kind="card",
                card="black",
                text="",
                start=t,
                end=t + each,
            )
        )
        t += each
    return words, shots


def test_long_videos_are_split_in_balanced_stretches():
    _w, shots = _card_shots(40, 1.5)
    pieces = render._stretches(shots, 3)
    assert len(pieces) == 3
    assert [k for p in pieces for k, _s in p] == list(range(40))  # in order, none lost
    _w, short = _card_shots(10, 1.5)
    assert len(render._stretches(short, 3)) == 1  # short: one stretch


def test_parallel_render_keeps_the_exact_length(tmp_path, monkeypatch):
    import shutil

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        import pytest

        pytest.skip("ffmpeg not installed")
    monkeypatch.setenv("SERGIO_VIDEO_HILOS", "2")
    monkeypatch.setattr(render, "ffmpeg", lambda: shutil.which("ffmpeg"))
    words, shots = _card_shots(32, 1.5)  # 48 s
    out = render.render_video(
        shots, words, tmp_path / "v.mp4", size=(160, 90), preset="ultrafast"
    )
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    assert abs(float(dur) - 48.0) < 0.1
    assert not list(Path(tmp_path).glob("*.part*"))


def test_a_long_quick_video_becomes_the_full_production(monkeypatch):
    from openjarvis.tools import video_essay_tool
    from openjarvis.tools.video_create import VideoCreateTool

    seen = {}

    def fake(self, **params):
        seen.update(params)
        from openjarvis.core.types import ToolResult

        return ToolResult(tool_name="video_essay", content="en marcha", success=True)

    monkeypatch.setattr(video_essay_tool.VideoEssayTool, "execute", fake)
    out = VideoCreateTool().execute(
        topic="la historia del primer auto eléctrico", seconds=480
    )
    assert out.success and seen["seconds"] == 480.0 and seen["action"] == "start"
