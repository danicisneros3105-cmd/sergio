"""«Haz un video sobre…»: script, pictures, voice and the real ffmpeg."""

from __future__ import annotations

import io
import json
import subprocess
import wave

import pytest
from PIL import Image

from openjarvis.creator import studio
from openjarvis.tools import video_create
from openjarvis.tools.video_create import VideoCreateTool, ffmpeg_exe, plan, render

pytestmark = pytest.mark.skipif(not ffmpeg_exe(), reason="ffmpeg not available")


def _png(colour: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (640, 480), colour).save(out, "PNG")
    return out.getvalue()


def _wav(seconds: float) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24000 * seconds))
    return out.getvalue()


def _length(path) -> float:
    probe = subprocess.run(
        [ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True
    ).stderr
    stamp = probe.split("Duration: ")[1].split(",")[0]
    h, m, s = stamp.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def test_render_makes_a_playable_video_with_voice(tmp_path):
    out = render(
        [_png((200, 40, 40)), _png((40, 40, 200))],
        ["Primera escena del video.", "Y la segunda, para cerrar."],
        [1.5, 1.5],
        tmp_path / "v.mp4",
        aspect="9:16",
        voice=_wav(3.0),
    )
    assert out.stat().st_size > 1000
    assert 2.5 < _length(out) < 3.6
    info = subprocess.run(
        [ffmpeg_exe(), "-i", str(out)], capture_output=True, text=True
    ).stderr
    assert "720x1280" in info and "Audio: aac" in info


def test_the_script_is_checked():
    def ask(prompt, json_mode, check):
        assert "contaminación" in prompt
        return json.dumps(
            {"title": "El aire", "scenes": [
                {"say": "El aire de la ciudad.", "picture": "a city in smog"},
                {"say": "Lo que podemos hacer.", "picture": "people planting trees"},
                {"say": "", "picture": "dropped"},
            ]}
        )  # fmt: skip

    script = plan("la contaminación", 3, ask=ask)
    assert script["title"] == "El aire" and len(script["scenes"]) == 2


def test_from_an_idea_to_a_video_in_the_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "projects_root", lambda root=None: tmp_path)
    monkeypatch.setattr(
        video_create,
        "plan",
        lambda topic, n: {
            "title": "Contaminación",
            "scenes": [
                {"say": "Una ciudad con humo.", "picture": "smog"},
                {"say": "Un parque limpio.", "picture": "park"},
            ],
        },
    )
    monkeypatch.setattr(studio, "generate_image", lambda prompt: _png((90, 90, 90)))
    from openjarvis.speech import gemini_voice

    monkeypatch.setattr(gemini_voice, "speak", lambda text, voice: _wav(2.0))
    result = VideoCreateTool().execute(topic="la contaminación", seconds=15)
    assert result.success, result.content
    assert "](/v1/creator/media/video-" in result.content
    from openjarvis.server.auth_middleware import AuthMiddleware

    assert not AuthMiddleware._requires_auth(result.metadata["url"])
    assert list((tmp_path / "videos").glob("video-*.mp4"))


def test_no_pictures_says_why(tmp_path, monkeypatch):
    from openjarvis.creator.llm import CreatorError

    monkeypatch.setattr(studio, "projects_root", lambda root=None: tmp_path)
    monkeypatch.setattr(
        video_create,
        "plan",
        lambda topic, n: {"title": "x", "scenes": [{"say": "a", "picture": "b"}] * 2},
    )

    def fail(prompt):
        raise CreatorError(
            "Su clave de Gemini no tiene cuota para generar imágenes ahora."
        )

    monkeypatch.setattr(studio, "generate_image", fail)
    result = VideoCreateTool().execute(topic="el mar")
    assert not result.success and "cuota" in result.content
