"""A professional editor's skills: broadcast voice, cuts on the beat,
reframing for other screens, subtitles, chapters and quality control."""

import shutil
import subprocess

import numpy as np
import pytest

from openjarvis.video_essay import pro

FF = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(not FF, reason="ffmpeg")


def _clicks(bpm, seconds=12, sr=48000):
    x = np.zeros(sr * seconds, np.float32)
    for k in range(int(seconds * bpm / 60)):
        i = int(k * 60 / bpm * sr)
        x[i : i + 600] += np.hanning(600) * np.random.default_rng(k).normal(0, 0.6, 600)
    return x


@pytest.mark.parametrize("bpm", [90, 128])
def test_the_beat_is_found(bpm):
    found = 60 / np.median(np.diff(pro.beat_times(_clicks(bpm))))
    assert abs(found - bpm) < 2


def test_cuts_land_on_the_beat_but_never_inside_a_word():
    beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    assert pro.snap_cuts([0.95, 1.6], beats) == [1.0, 1.5]
    assert pro.snap_cuts([0.95], beats, words=[(0.9, 1.2)]) == [0.95]
    assert pro.snap_cuts([3.0], beats) == [3.0]  # too far from any beat


def test_subtitles_break_at_pauses_and_sentence_ends():
    words = [
        {"text": "Hola,", "start": 0, "end": 0.4},
        {"text": "señor.", "start": 0.4, "end": 0.9},
        {"text": "Listo", "start": 2.0, "end": 2.4},
    ]
    out = pro.srt(words)
    assert "1\n00:00:00,000 --> 00:00:00,900\nHola, señor." in out
    assert "2\n00:00:02,000 --> 00:00:02,400\nListo" in out


def test_chapters_start_at_zero_and_last_ten_seconds():
    text = pro.chapters_text([(3, "Intro"), (8, "corto"), (40, "Voz")])
    assert text.splitlines() == ["0:00 Intro", "0:40 Voz"]


@needs_ffmpeg
def test_the_voice_chain_keeps_length_and_lowers_hiss_between_words():
    sr = 48000
    t = np.arange(sr * 4) / sr
    voice = (
        0.3 * np.sin(2 * np.pi * 180 * t) * (np.sin(2 * np.pi * 1.5 * t) > 0)
    ).astype(np.float32)
    hiss = np.random.default_rng(1).normal(0, 0.01, len(t)).astype(np.float32)
    out = pro.voice_chain(voice + hiss, FF)
    assert len(out) == len(t)
    gap = (np.sin(2 * np.pi * 1.5 * t) < -0.5) & (
        t > 1.0
    )  # silence after the denoiser learned
    assert np.sqrt(np.mean(out[gap] ** 2)) < np.sqrt(np.mean(hiss[gap] ** 2))


@needs_ffmpeg
def test_reframe_and_quality_check(tmp_path):
    src = tmp_path / "t.mp4"
    subprocess.run(
        [FF, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=3",
         "-f", "lavfi", "-i", "sine=f=440:d=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)],
        check=True,
    )  # fmt: skip
    vertical = pro.reframe(src, "9:16", FF, shutil.which("ffprobe") or "ffprobe")
    info = pro._probe(vertical, shutil.which("ffprobe") or "ffprobe")
    assert info["h"] == 360 and abs(info["w"] / info["h"] - 9 / 16) < 0.02
    report = pro.quality_check(src, FF)
    assert report["lufs"] is not None and not report["ok"]  # a quiet test tone
    assert any("LUFS" in p for p in report["problemas"])
