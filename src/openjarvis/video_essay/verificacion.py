"""Technical acceptance checks for a narrated, fully animated video."""

from __future__ import annotations

import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

_ANIMATION_NOTES = {"imagen: video con IA", "imagen: toma 3D"}


class InvalidShot(RuntimeError):
    def __init__(self, number: int, reason: str) -> None:
        self.number = number
        super().__init__(f"Toma {number}: {reason}.")


def require_voice(samples: Any, sample_rate: int) -> None:
    """Reject a valid WAV containing silence or a single click."""
    signal = np.asarray(samples)
    chunk = max(1, sample_rate // 10)
    blocks = len(signal) // chunk
    if blocks < 3:
        raise RuntimeError("La narración no contiene suficiente voz audible.")
    frames = signal[: blocks * chunk].reshape(blocks, chunk, -1)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=(1, 2)))
    if int(np.count_nonzero(rms > 0.003)) < max(3, blocks // 12):
        raise RuntimeError(
            "La narración quedó en silencio. Revisa el proveedor de voz."
        )


def _streams(path: Path, ffprobe: str) -> list[dict[str, Any]]:
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return json.loads(probe.stdout).get("streams", [])


def require_shots(shots: list[Any], ffmpeg: str, ffprobe: str) -> int:
    """Require generated video sources with enough duration and visual change."""
    if not shots:
        raise RuntimeError("No se planificaron tomas de animación.")
    for i, shot in enumerate(shots, 1):
        path = Path(shot.asset)
        if (
            shot.kind == "card"
            or not path.is_file()
            or not _ANIMATION_NOTES.intersection(shot.notes)
        ):
            raise InvalidShot(
                i, "falta animación generada; revisa el proveedor y el presupuesto"
            )
        try:
            stream = next(
                s for s in _streams(path, ffprobe) if s["codec_type"] == "video"
            )
            if float(stream["duration"]) + 0.12 < shot.dur:
                raise ValueError("duración insuficiente")
            sample = subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-i",
                    str(path),
                    "-an",
                    "-filter_threads",
                    "1",
                    "-t",
                    str(min(3.0, shot.dur)),
                    "-vf",
                    "fps=8,scale=64:64,format=gray",
                    "-f",
                    "rawvideo",
                    "-",
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            pictures = (
                np.frombuffer(sample.stdout, dtype=np.uint8)
                .reshape(-1, 4096)
                .astype(np.int16)
            )
            if len(pictures) < 2 or not np.any(
                np.count_nonzero(np.abs(pictures[1:] - pictures[0]) >= 16, axis=1) >= 32
            ):
                raise ValueError("no se detectó movimiento")
        except (
            OSError,
            subprocess.SubprocessError,
            KeyError,
            ValueError,
            StopIteration,
        ) as exc:
            why = (
                str(exc)
                if isinstance(exc, ValueError)
                else "no se pudo inspeccionar el archivo"
            )
            raise InvalidShot(i, why) from exc
    return len(shots)


def check_delivery(
    path: Path,
    ffprobe: str,
    *,
    aspect: str,
    fps: int,
    subtitles: str,
    shots: int,
    script: str,
    timing: str,
    quality: dict[str, Any],
    requested_seconds: float,
) -> dict[str, Any]:
    """Describe what was actually verified, without assigning a creative grade."""
    if not script.strip() or " --> " not in subtitles:
        raise RuntimeError("Falta el guion o la pista de subtítulos.")
    if not quality.get("ok") or quality.get("lufs") is None:
        detail = (
            "; ".join(quality.get("problemas") or [])
            or "no se pudo verificar la mezcla"
        )
        raise RuntimeError(f"El control del montaje no pasó: {detail}.")
    try:
        streams = _streams(path, ffprobe)
        video = next(s for s in streams if s["codec_type"] == "video")
        audio = next(s for s in streams if s["codec_type"] == "audio")
        w, h = map(int, aspect.split(":"))
        if int(video["width"]) * h != int(video["height"]) * w:
            raise ValueError("formato incorrecto")
        if Fraction(video["avg_frame_rate"]) != fps:
            raise ValueError("FPS incorrectos")
        video_s, audio_s = float(video["duration"]), float(audio["duration"])
        if (
            not all(math.isfinite(s) and s > 0 for s in (video_s, audio_s))
            or abs(video_s - audio_s) > 0.35
        ):
            raise ValueError("duración o sincronía de pistas incorrecta")
        if abs(video_s - requested_seconds) > max(1.5, requested_seconds * 0.2):
            raise ValueError(
                f"duración de {video_s:.1f} s fuera del objetivo de {requested_seconds:g} s"
            )
    except (
        OSError,
        subprocess.SubprocessError,
        KeyError,
        ValueError,
        ZeroDivisionError,
        StopIteration,
    ) as exc:
        why = (
            str(exc)
            if isinstance(exc, ValueError)
            else "faltan pistas válidas o FFprobe"
        )
        raise RuntimeError(f"El archivo final no pasó la verificación: {why}.") from exc
    return {
        "tomas_animadas": shots,
        "fps": fps,
        "aspecto": aspect,
        "segundos": round(video_s, 2),
        "segundos_pedidos": requested_seconds,
        "subtitulos": True,
        "voz_audible": True,
        "guion": True,
        "alineacion": timing,
        "lufs": quality["lufs"],
    }


__all__ = ["InvalidShot", "check_delivery", "require_shots", "require_voice"]
