"""The final sound of a video, mixed like a post-production studio does.

The owner (3 Nov 2026): «el audio de los videos falla». What was wrong:

* **Everything was mono.** The music (recorded in stereo) was folded to one
  channel; wide reverbs cancel when folded and the music sounded thin and far.
* **Loudness was normalised twice, in one pass each** (``loudnorm`` on the mix
  and again when muxing). One-pass loudnorm rides the volume up and down as it
  goes: under a voice the music «breathed». Twice made it worse.
* **Ducking was an envelope on the samples** with no attack or release, so the
  music jumped in the gaps between words.
* **Resampling was linear interpolation**, which adds hiss and harsh highs.

Now: voice in the centre, music in stereo with a dip at 2-4 kHz so the words
cut through, a real sidechain compressor (the voice pushes the music down with
a 15 ms attack and a 350 ms release), effects in stereo, a limiter, and the
loudness set **once**: measured, then one linear gain to -14 LUFS with a
limiter that keeps the peaks under -1.5 dBTP, at 48 kHz in stereo. The measures are returned so
the job can say what came out.
"""

from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

SR = 48_000
TARGET = {"I": -14.0, "TP": -1.5, "LRA": 11.0}
LIMIT = 0.8  # -1.9 dBFS sample peak: true peak stays under -1.5 dBTP


@lru_cache(maxsize=4)
def resampler(ffmpeg: str) -> str:
    """``aresample`` with the SoX resampler when this ffmpeg has it."""
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-buildconf"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if "libsoxr" in out.stdout:
            return f"aresample={SR}:resampler=soxr:precision=28"
    except Exception:  # noqa: BLE001
        pass
    return f"aresample={SR}:filter_size=64:phase_shift=10:cutoff=0.97"


def measure(path: Path, ffmpeg: str) -> Dict[str, float]:
    """Integrated loudness (LUFS), true peak (dBTP) and range (LU) of a file."""
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af",
         "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, timeout=900,
    )  # fmt: skip
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError("no pude medir el volumen")
    d = json.loads(m.group(0))
    return {
        "I": float(d["input_i"]),
        "TP": float(d["input_tp"]),
        "LRA": float(d["input_lra"]),
        "thresh": float(d["input_thresh"]),
        "offset": float(d["target_offset"]),
    }


def _graph(
    has_voice: bool,
    has_music: bool,
    has_fx: bool,
    total: float,
    music_db: float,
    rs: str,
) -> tuple:
    """The filter graph and the output label."""
    parts, mix = [], []
    i = 0
    if has_voice:
        parts.append(
            f"[{i}:a]{rs},aformat=sample_fmts=fltp:channel_layouts=stereo,asplit=2[v][vkey]"
        )
        mix.append("[v]")
        i += 1
    if has_music:
        fade = min(3.0, max(0.8, total * 0.06))
        chain = (
            f"[{i}:a]{rs},aformat=sample_fmts=fltp:channel_layouts=stereo,atrim=0:{total:.2f},"
            f"afade=t=in:d=0.8,afade=t=out:st={max(0.0, total - fade):.2f}:d={fade:.2f},"
            f"volume={music_db:.1f}dB"
        )
        if has_voice:  # room for the words: a dip where speech lives
            chain += ",equalizer=f=2800:t=q:w=1.4:g=-4,equalizer=f=250:t=q:w=1:g=-2"
            parts.append(chain + "[mraw]")
            parts.append(
                "[mraw][vkey]sidechaincompress=threshold=0.06:ratio=3:attack=15:release=350:"
                "knee=4:makeup=1:mix=1[m]"
            )
        else:
            parts.append(chain + "[m]")
        mix.append("[m]")
        i += 1
    elif has_voice:
        parts.append("[vkey]anullsink")
    if has_fx:
        parts.append(
            f"[{i}:a]{rs},aformat=sample_fmts=fltp:channel_layouts=stereo,volume=-3dB[f]"
        )
        mix.append("[f]")
        i += 1
    n = len(mix)
    if n == 1:
        parts.append(
            f"{mix[0]}alimiter=limit=0.94:attack=3:release=60:level=false[out]"
        )
    else:
        parts.append(
            "".join(mix)
            + f"amix=inputs={n}:normalize=0:duration=longest:dropout_transition=0,"
            "alimiter=limit=0.94:attack=3:release=60:level=false[out]"
        )
    return ";".join(parts), "[out]"


def master(
    out: Path,
    *,
    voice: Optional[Path],
    music: Optional[Path],
    fx: Optional[Path],
    total: float,
    ffmpeg: str,
    music_db: Optional[float] = None,
) -> Dict[str, Any]:
    """Mixes, limits and sets the loudness once (two passes). Returns the
    measures of the result (LUFS, true peak, channels)."""
    inputs = [p for p in (voice, music, fx) if p is not None and Path(p).is_file()]
    if not inputs:
        raise ValueError("no hay sonido que mezclar")
    has_voice = voice is not None and Path(voice).is_file()
    has_music = music is not None and Path(music).is_file()
    has_fx = fx is not None and Path(fx).is_file()
    level = music_db if music_db is not None else (-15.0 if has_voice else -4.0)
    graph, label = _graph(has_voice, has_music, has_fx, total, level, resampler(ffmpeg))
    raw = out.with_suffix(".premaster.wav")
    cmd = [ffmpeg, "-y", "-v", "error"]
    for p in inputs:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", graph, "-map", label, "-t", f"{total + 0.3:.2f}", "-ar", str(SR), "-ac", "2",
            "-c:a", "pcm_f32le", str(raw)]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
    first = measure(raw, ffmpeg)
    # One linear gain to the target and a true-peak-safe limiter (what a
    # mastering engineer does). A second, smaller gain only if the limiter
    # had to take more than half a LU away.
    gain = TARGET["I"] - first["I"]
    for _ in range(2):
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(raw), "-af",
             f"volume={gain:.2f}dB,alimiter=limit={LIMIT}:attack=2:release=80:level=false,{resampler(ffmpeg)}",
             "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s24le", str(out)],
            check=True, capture_output=True, timeout=1800,
        )  # fmt: skip
        got = measure(out, ffmpeg)
        if got["I"] >= TARGET["I"] - 0.5 or gain > 30:
            break
        gain += TARGET["I"] - got["I"]
    raw.unlink(missing_ok=True)
    final = measure(out, ffmpeg)
    return {"lufs": round(final["I"], 1), "pico_dbtp": round(final["TP"], 1), "rango_lu": round(final["LRA"], 1),
            "canales": 2, "antes_lufs": round(first["I"], 1)}  # fmt: skip


__all__ = ["TARGET", "master", "measure", "resampler"]
