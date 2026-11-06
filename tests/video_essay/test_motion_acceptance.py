"""Motion checks use real encoded clips, including a deceptive exposure pulse."""

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from openjarvis.video_essay import verificacion

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

pytestmark = pytest.mark.skipif(
    not FFMPEG or not FFPROBE, reason="needs FFmpeg and FFprobe"
)


def _shot(tmp_path, graph, duration):
    path = tmp_path / "clip.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-filter_complex_threads",
            "1",
            "-f",
            "lavfi",
            "-i",
            graph,
            "-t",
            str(duration),
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return SimpleNamespace(
        kind="broll", asset=str(path), dur=duration, notes=["imagen: video con IA"]
    )


def test_a_brightness_pulse_is_not_animation(tmp_path):
    shot = _shot(
        tmp_path,
        "nullsrc=s=144x256:r=30,geq=lum='80+40*gte(X,W/2)+25*sin(2*PI*T)':cb=128:cr=128",
        2,
    )
    with pytest.raises(verificacion.InvalidShot, match="solo luz"):
        verificacion.require_shots([shot], FFMPEG, FFPROBE)


def test_motion_after_the_opening_hold_is_still_detected(tmp_path):
    shot = _shot(
        tmp_path,
        "nullsrc=s=144x256:r=30,geq=lum='80+60*gte(X,W/2+25*sin(8*max(T-3.5,0)))':cb=128:cr=128",
        5,
    )
    assert verificacion.require_shots([shot], FFMPEG, FFPROBE) == 1
