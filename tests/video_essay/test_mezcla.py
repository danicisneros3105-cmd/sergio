"""The studio master: stereo, the music ducks under the voice, loudness once."""

from __future__ import annotations

import shutil
import subprocess
import wave

import numpy as np
import pytest

from openjarvis.video_essay import mezcla

FF = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(not FF, reason="needs ffmpeg")


def _wav(path, x, sr, ch):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def _inputs(tmp_path):
    sr = 24000  # a TTS voice: 1 s talking, 1 s pause
    t = np.arange(10 * sr) / sr
    _wav(
        tmp_path / "voz.wav", 0.5 * np.sin(2 * np.pi * 1000 * t) * ((t % 2) < 1), sr, 1
    )
    sr2 = 44100  # a stereo song at another rate
    t2 = np.arange(10 * sr2) / sr2
    lr = np.stack(
        [0.4 * np.sin(2 * np.pi * 200 * t2), 0.4 * np.sin(2 * np.pi * 203 * t2 + 1)], 1
    )
    _wav(tmp_path / "musica.wav", lr.ravel(), sr2, 2)


def _read(path):
    raw = subprocess.run([FF, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", "48000", "-"],
                         capture_output=True, check=True).stdout  # fmt: skip
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)


def _band(seg, f):
    x = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    fr = np.fft.rfftfreq(len(seg), 1 / 48000)
    return x[(fr > f - 15) & (fr < f + 15)].max()


def test_master_is_stereo_at_platform_loudness_with_real_ducking(tmp_path):
    _inputs(tmp_path)
    out = tmp_path / "final.wav"
    got = mezcla.master(
        out,
        voice=tmp_path / "voz.wav",
        music=tmp_path / "musica.wav",
        fx=None,
        total=10,
        ffmpeg=FF,
    )
    assert (
        got["canales"] == 2
        and abs(got["lufs"] + 14) <= 1.0
        and got["pico_dbtp"] <= -1.4
    )
    st = _read(out)
    assert np.abs(st[:, 0] - st[:, 1]).mean() > 0.001  # the music keeps its stereo
    left = st[:, 0]
    talking = np.mean(
        [
            _band(left[int((k * 2 + 0.4) * 48000) : int((k * 2 + 0.9) * 48000)], 200)
            for k in (1, 2, 3)
        ]
    )
    pause = np.mean(
        [
            _band(left[int((k * 2 + 1.4) * 48000) : int((k * 2 + 1.9) * 48000)], 200)
            for k in (1, 2, 3)
        ]
    )
    duck = 20 * np.log10(talking / pause)
    assert -14 < duck < -6  # down under the words, back up in the pauses


def test_music_alone_is_mastered_too_and_nothing_to_mix_is_an_error(tmp_path):
    _inputs(tmp_path)
    got = mezcla.master(
        tmp_path / "m.wav",
        voice=None,
        music=tmp_path / "musica.wav",
        fx=None,
        total=10,
        ffmpeg=FF,
    )
    assert abs(got["lufs"] + 14) <= 1.0
    with pytest.raises(ValueError):
        mezcla.master(
            tmp_path / "x.wav", voice=None, music=None, fx=None, total=5, ffmpeg=FF
        )


# -- clips from the web: yt-dlp with its challenge solver, and why it failed --------


def test_ytdlp_names_a_js_runtime_and_failures_are_explained(monkeypatch):
    import subprocess as sp

    from openjarvis.video_essay import sources

    monkeypatch.setattr(
        sources.shutil, "which", lambda n: "/usr/bin/node" if n == "node" else None
    )
    assert sources.js_runtime() == ["--js-runtimes", "node:/usr/bin/node"]
    assert sources.ytdlp()[1:4] == ["-m", "yt_dlp", "--js-runtimes"]
    assert "robot" in sources.why("ERROR: Sign in to confirm you're not a bot")
    assert "reto" in sources.why("WARNING: n challenge solving failed")
    ok = sources.diagnose(runner=lambda a: sp.CompletedProcess(a, 0, "18 240\n", ""))
    assert ok["ok"] and "jNQXAC9IVRw" not in ok["motivo"]
    bad = sources.diagnose(
        runner=lambda a: sp.CompletedProcess(
            a, 1, "", "ERROR: Sign in to confirm you're not a bot"
        )
    )
    assert not bad["ok"] and "robot" in bad["motivo"]
