from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from openjarvis.video_essay import job, modes, render, verificacion
from openjarvis.video_essay.plan import Shot

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
requires_media = pytest.mark.skipif(
    not FFMPEG or not FFPROBE, reason="needs FFmpeg and FFprobe"
)


def test_voice_rejects_silence_even_if_there_is_a_wav_stream():
    with pytest.raises(RuntimeError, match="silencio"):
        verificacion.require_voice(np.zeros(24000), 24000)


@requires_media
def test_a_static_video_is_not_a_verified_animated_shot(tmp_path):
    still = tmp_path / "still.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=144x256:r=30:d=1",
            str(still),
        ],
        check=True,
    )
    shot = Shot(0, 1, start=0, end=1, asset=str(still), notes=["imagen: video con IA"])
    with pytest.raises(verificacion.InvalidShot, match="no se detectó movimiento"):
        verificacion.require_shots([shot], FFMPEG, FFPROBE)


@requires_media
def test_real_export_with_controlled_animation_and_spoken_voice(tmp_path, monkeypatch):
    filters = subprocess.check_output([FFMPEG, "-hide_banner", "-filters"], text=True)
    if "flite" not in filters:
        pytest.skip("needs FFmpeg flite for the local spoken fixture")
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path / "home"))
    monkeypatch.setitem(render.DRAFT_SIZES, "9:16", (144, 256))
    monkeypatch.setitem(
        modes.MODES,
        "post",
        replace(modes.MODES["post"], passes=0, finishing=False, package=False),
    )
    monkeypatch.setattr(job, "_specialist_learns", lambda _state: None)
    text = (
        "The clock stopped at midnight. Then the moon began to move. "
        "A young apprentice watched the shadow cross the town. "
        "She climbed the tower and found a mirror behind the clock."
        " When she tilted the mirror the shadow moved backward. "
        "The town was watching a reflection from the hill across the river."
    )
    treatment = {
        "title": "The moon clock",
        "logline": "A moon moves when a clock stops.",
        "style": "animacion",
        "narration": "voice",
        "sources": ["ai"],
        "beats": [
            {
                "beat": "hook",
                "text": text,
                "seconds": 4,
                "visual": "A moon moves behind a clock",
            }
        ],
    }

    def ask(prompt, **_kwargs):
        return json.dumps(treatment) if "Write the treatment" in str(prompt) else "{}"

    def voice(part):
        return subprocess.check_output(
            [
                FFMPEG,
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"flite=voice=slt:text={part}",
                "-ar",
                "48000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                "-",
            ],
        )

    def moving_shot(_prompt, out, seconds, _aspect):
        subprocess.run(
            [
                FFMPEG,
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=s=144x256:r=30:d={seconds}",
                "-c:v",
                "libx264",
                str(out),
            ],
            check=True,
        )
        return str(out)

    params = {
        "topic": "a moon clock",
        "mode": "post",
        "draft": True,
        "preset": "ultrafast",
        "style": "animacion",
        "seconds": 15,
        "aspect": "9:16",
        "music": "ninguna",
        "web_clips": False,
        "verificar_animacion": True,
    }
    deps = job.Deps(
        ask=ask,
        speak=voice,
        recognise=lambda *_: [],
        ai_provider=moving_shot,
        stock=False,
        videos=tmp_path / "exported",
        styles=tmp_path / "styles",
        notify=lambda *_: None,
    )
    state = job.run(job.create(params, tmp_path / "jobs"), deps)
    assert state["status"] == "listo", state.get("error")
    assert state["voice"] is True
    receipt = state["result"]["verificacion"]
    assert receipt["tomas_animadas"] == state["result"]["shots"] > 0
    assert receipt["fps"] == 30 and receipt["alineacion"] == "energía"
    assert Path(state["result"]["path"]).with_suffix(".srt").is_file()
