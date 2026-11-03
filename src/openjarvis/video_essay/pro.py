"""What a professional editor does after the edit (owner, 27 Oct 2026: «mejora
la edición de video, hazla más pro, con más skills»).

* :func:`voice_chain` — the narration like a broadcast voice: rumble cut,
  noise reduction, de-esser, presence, a gentle compressor and a limiter.
* :func:`beat_times` / :func:`snap_cuts` — cuts that land on the music's
  beat (only where no word is cut in half).
* :func:`reframe` — the same video for other screens (9:16, 1:1, 16:9),
  following the faces or what moves instead of a blind centre crop.
* :func:`srt` / :func:`chapters_text` — subtitles and YouTube chapters.
* :func:`quality_check` — before delivery: loudness against the platforms'
  −14 LUFS, true peak, black and frozen stretches, silence.

Every step only uses ffmpeg, numpy and OpenCV (already with Sergio). Each
fails soft: the video that was already made is never lost.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

SR = 48000
# No noise reduction (afftdn): the narration is synthetic and has no room noise to
# remove, and spectral denoising on a clean voice leaves the watery, warbling
# sound of «bajo el agua» (owner, 3 Nov 2026).
VOICE_FILTERS = (
    "highpass=f=80",  # rumble
    "deesser=i=0.4:m=0.5:f=0.5",  # sharp «s»
    "equalizer=f=200:t=q:w=1:g=-2",  # boxiness
    "equalizer=f=3500:t=q:w=1.2:g=2.5",  # presence: words easy to follow
    "highshelf=f=8500:g=2.5",  # air: a 24 kHz voice has little above 10 kHz
    "acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2dB",
    # The compressor lifts the room between words too: a soft gate puts it
    # back down (only by 10 dB, so breaths stay natural).
    "agate=threshold=0.05:ratio=3:range=0.3:attack=4:release=180",
    "alimiter=limit=0.89:level=false",
)
TARGET_LUFS = -14.0  # YouTube, Spotify, TikTok, Instagram normalise here
MAX_TRUE_PEAK = -1.0


def _run(cmd: List[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# -- the voice -----------------------------------------------------------------
def voice_chain(voice: np.ndarray, ffmpeg: str, sr: int = SR) -> np.ndarray:
    """The narration through the broadcast chain (unchanged if ffmpeg fails)."""
    if not len(voice):
        return voice
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.f32", Path(tmp) / "out.f32"
        np.asarray(voice, dtype="<f4").tofile(src)
        res = _run(
            [ffmpeg, "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", str(src),
             "-af", ",".join(VOICE_FILTERS), "-f", "f32le", "-ar", str(sr), "-ac", "1", str(out)]
        )  # fmt: skip
        if res.returncode != 0 or not out.exists():
            return voice
        cleaned = np.fromfile(out, dtype="<f4")
    if len(cleaned) < len(voice) * 0.98:  # a filter swallowed audio: keep the original
        return voice
    return cleaned[: len(voice)].astype(np.float32)


# -- the beat ------------------------------------------------------------------
def beat_times(music: np.ndarray, sr: int = SR, bpm_range=(60, 180)) -> List[float]:
    """Where the beats fall: onset strength, tempo by autocorrelation, then
    the phase that hits the most onsets."""
    if len(music) < sr * 2:
        return []
    hop = 512
    frames = len(music) // hop
    x = np.asarray(music[: frames * hop], dtype=np.float32).reshape(frames, hop)
    energy = np.log1p(np.sum(x * x, axis=1) * 100)
    onset = np.maximum(np.diff(energy, prepend=energy[0]), 0)
    if not onset.any():
        return []
    onset = onset - onset.mean()
    fps = sr / hop
    lags = np.arange(int(fps * 60 / bpm_range[1]), int(fps * 60 / bpm_range[0]) + 1)
    ac = np.array([np.dot(onset[:-lag], onset[lag:]) for lag in lags])
    period = int(lags[int(np.argmax(ac))])
    phases = [onset[p::period].sum() for p in range(period)]
    start = int(np.argmax(phases))
    return [round(f / fps, 3) for f in range(start, frames, period)]


def bed_beats(total: float, bpm: float) -> List[float]:
    """The beats of Sergio's own music bed, known exactly."""
    step = 60.0 / bpm
    return [round(i * step, 3) for i in range(int(total / step) + 1)]


def snap_cuts(
    cuts: Sequence[float],
    beats: Sequence[float],
    words: Sequence[Tuple[float, float]] = (),
    tolerance: float = 0.12,
) -> List[float]:
    """Each cut moved onto the nearest beat when it is close, unless that
    would land inside a spoken word."""
    if not beats:
        return list(cuts)
    b = np.asarray(beats)
    out = []
    for cut in cuts:
        near = float(b[int(np.argmin(np.abs(b - cut)))])
        inside = any(s + 0.02 < near < e - 0.02 for s, e in words)
        out.append(near if abs(near - cut) <= tolerance and not inside else cut)
    for i in range(1, len(out)):  # never out of order or empty shots
        if out[i] <= out[i - 1] + 0.2:
            out[i] = cuts[i]
    return out


# -- other screens -------------------------------------------------------------
ASPECTS = {"9:16": (9, 16), "1:1": (1, 1), "16:9": (16, 9), "4:5": (4, 5)}


def _probe(path: Path, ffprobe: str) -> Dict[str, Any]:
    res = _run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(path)]
    )  # fmt: skip
    data = json.loads(res.stdout or "{}")
    st = (data.get("streams") or [{}])[0]
    return {
        "w": int(st.get("width", 0)),
        "h": int(st.get("height", 0)),
        "dur": float((data.get("format") or {}).get("duration", 0) or 0),
    }


def interest_track(path: Path, every: float = 0.5) -> List[Tuple[float, float]]:
    """(time, x from 0 to 1) of what matters in the frame: faces first, else
    where things move, else the centre. Smoothed so the frame glides."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(fps * every))
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    track: List[Tuple[float, float]] = []
    prev = None
    i = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            small = cv2.resize(frame, (320, int(320 * frame.shape[0] / frame.shape[1])))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(24, 24))
            if len(faces):
                x, _, w, _ = max(faces, key=lambda f: f[2] * f[3])
                cx = (x + w / 2) / gray.shape[1]
            elif prev is not None:
                diff = cv2.absdiff(gray, prev).astype(np.float32)
                col = diff.sum(axis=0)
                cx = float(np.average(np.arange(len(col)), weights=col + 1e-3)) / len(
                    col
                )
            else:
                cx = 0.5
            prev = gray
            track.append((i / fps, cx))
        i += 1
    cap.release()
    if not track:
        return [(0.0, 0.5)]
    xs = np.array([x for _, x in track])
    k = min(len(xs), 7)  # glide: a moving average over ~3 s
    smooth = np.convolve(
        np.pad(xs, (k // 2, k - 1 - k // 2), mode="edge"), np.ones(k) / k, "valid"
    )
    return [(t, float(x)) for (t, _), x in zip(track, smooth)]


def reframe(
    src: Path, aspect: str, ffmpeg: str, ffprobe: str, out: Optional[Path] = None
) -> Optional[Path]:
    """*src* recut for another screen, the frame following what matters."""
    if aspect not in ASPECTS:
        return None
    info = _probe(src, ffprobe)
    w, h = info["w"], info["h"]
    if not w or not h:
        return None
    aw, ah = ASPECTS[aspect]
    cw, ch = (
        (int(h * aw / ah) // 2 * 2, h)
        if w / h > aw / ah
        else (w, int(w * ah / aw) // 2 * 2)
    )
    out = out or src.with_name(f"{src.stem}-{aspect.replace(':', 'x')}{src.suffix}")
    if cw < w:
        span = w - cw
        pts = [(t, min(max(x * w - cw / 2, 0.0), span)) for t, x in interest_track(src)]
        vf = f"crop={cw}:{ch}:'{_scale_expr(pts)}':0"
    else:
        vf = f"crop={cw}:{ch}:0:(ih-{ch})/2"
    res = _run(
        [ffmpeg, "-y", "-v", "error", "-i", str(src), "-vf", vf + ",format=yuv420p",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "copy",
         "-movflags", "+faststart", str(out)]
    )  # fmt: skip
    return out if res.returncode == 0 and out.exists() else None


def _scale_expr(pts: List[Tuple[float, float]]) -> str:
    """Piecewise-linear left edge in pixels over time, as an ffmpeg expression."""
    if not pts:
        return "0"
    expr = f"{pts[-1][1]:.1f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(pts, pts[1:]))):
        slope = (x1 - x0) / max(t1 - t0, 1e-3)
        expr = f"if(lt(t\\,{t1:.2f})\\,{x0:.1f}+({slope:.2f})*(t-{t0:.2f})\\,{expr})"
    return expr


# -- subtitles and chapters ----------------------------------------------------
def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(words: Iterable[Any], max_words: int = 7, max_gap: float = 0.6) -> str:
    """Subtitles from the timed words: short lines that break at pauses and
    sentence ends, as a professional subtitler would."""
    lines: List[List[Any]] = []
    for w in words:
        text = getattr(w, "text", None) or (
            w.get("text") if isinstance(w, dict) else ""
        )
        if not text:
            continue
        start = getattr(w, "start", None)
        start = w["start"] if start is None else start
        if (
            not lines
            or len(lines[-1]) >= max_words
            or start - _end(lines[-1][-1]) > max_gap
            or re.search(r"[.!?]$", _text(lines[-1][-1]))
        ):
            lines.append([])
        lines[-1].append(w)
    out = []
    for i, line in enumerate(lines, 1):
        out.append(
            f"{i}\n{_ts(_start(line[0]))} --> {_ts(_end(line[-1]))}\n"
            + " ".join(_text(w) for w in line)
            + "\n"
        )
    return "\n".join(out)


def _start(w: Any) -> float:
    return float(w["start"] if isinstance(w, dict) else w.start)


def _end(w: Any) -> float:
    return float(w["end"] if isinstance(w, dict) else w.end)


def _text(w: Any) -> str:
    return str(w["text"] if isinstance(w, dict) else w.text)


def chapters_text(chapters: Iterable[Tuple[float, str]]) -> str:
    """YouTube chapters: the first at 0:00, each at least 10 s long."""
    out: List[Tuple[float, str]] = []
    for t, title in sorted(chapters):
        if not out:
            out.append((0.0, title))
        elif t - out[-1][0] >= 10:
            out.append((t, title))
    return "\n".join(f"{int(t // 60)}:{int(t % 60):02d} {title}" for t, title in out)


# -- quality control -----------------------------------------------------------
def quality_check(
    path: Path, ffmpeg: str, cards: Iterable[Tuple[float, float]] = ()
) -> Dict[str, Any]:
    """What a finishing editor checks before delivery. *cards*: the spans
    the plan puts on a dark card on purpose (not a black hole in the cut)."""
    res = _run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
         "-filter_complex", "[0:a]ebur128=peak=true[a];[0:v]blackdetect=d=0.5:pix_th=0.08,freezedetect=n=0.0005:d=3[v]",
         "-map", "[a]", "-map", "[v]", "-f", "null", "-"]
    )  # fmt: skip
    log = res.stderr or ""
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", log)
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
    freezes = re.findall(r"freeze_start: ([\d.]+)", log)
    report: Dict[str, Any] = {
        "lufs": float(lufs[-1]) if lufs else None,
        "pico_dbtp": float(peak[-1]) if peak else None,
        "negros": [(float(a), float(b)) for a, b in blacks],
        "congelados": [float(a) for a in freezes],
    }
    problems = []
    if report["lufs"] is not None and abs(report["lufs"] - TARGET_LUFS) > 1.5:
        problems.append(f"volumen {report['lufs']} LUFS (se pide {TARGET_LUFS})")
    if report["pico_dbtp"] is not None and report["pico_dbtp"] > MAX_TRUE_PEAK + 0.5:
        problems.append(f"picos de {report['pico_dbtp']} dBTP (máx. {MAX_TRUE_PEAK})")
    planned = [(a - 0.2, b + 0.2) for a, b in cards]
    inner_blacks = [
        b
        for b in report["negros"]
        if b[0] > 0.3 and not any(a <= b[0] and b[1] <= z for a, z in planned)
    ]
    if inner_blacks:
        problems.append(f"{len(inner_blacks)} tramo(s) en negro")
    if report["congelados"]:
        problems.append(f"{len(report['congelados'])} imagen(es) congelada(s)")
    report["problemas"] = problems
    report["ok"] = not problems
    return report


__all__ = [
    "ASPECTS",
    "bed_beats",
    "beat_times",
    "chapters_text",
    "interest_track",
    "quality_check",
    "reframe",
    "snap_cuts",
    "srt",
    "voice_chain",
]
