"""Real Video Boost renders with plan-aware resolution and measured output."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable


def plan_limits(plan: str) -> dict[str, Any]:
    paid = plan in {"work", "dev", "founders"}
    return {"max_long_edge": 3840 if paid else 1920, "codec": "libx265" if paid else "libx264", "ten_bit": paid}


def _probe(src: Path, ffprobe: str) -> dict[str, Any]:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(src)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    data = json.loads(result.stdout)
    video = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("El archivo no contiene una pista de video valida.")
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in data.get("streams", [])),
        "duration": float((data.get("format") or {}).get("duration") or 0),
    }


def _dimensions(width: int, height: int, edge: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise ValueError("No pude leer la resolucion del video.")
    ratio = edge / max(width, height)
    out_w = max(2, int(round(width * ratio / 2)) * 2)
    out_h = max(2, int(round(height * ratio / 2)) * 2)
    return out_w, out_h


def _encoder_available(ffmpeg: str, encoder: str) -> bool:
    result = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30)
    return encoder in result.stdout


def boost_video(
    src: Path,
    out: Path,
    *,
    ffmpeg: str,
    ffprobe: str | None = None,
    plan: str | None = None,
    lut: str = "",
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Render a genuine denoised, color-graded video and verify its media stats."""
    src, out = Path(src), Path(out)
    if not src.is_file():
        raise FileNotFoundError("No encuentro el video que quieres mejorar.")
    ffprobe = ffprobe or shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("Video Boost necesita FFprobe junto con FFmpeg.")
    if plan is None:
        from openjarvis.tiers import current
        plan = str(current().get("plan") or "free")
    limits = plan_limits(plan)
    before = _probe(src, ffprobe)
    width, height = _dimensions(before["width"], before["height"], limits["max_long_edge"])
    codec = limits["codec"]
    if limits["ten_bit"] and not _encoder_available(ffmpeg, codec):
        raise RuntimeError("Este FFmpeg no incluye codificacion HEVC de 10 bits; no hice una salida degradada.")

    from openjarvis.video_essay.finish import color_chain

    filters = f"hqdn3d=1.5:1.5:6:6,scale={width}:{height}:flags=lanczos,{color_chain(lut)}"
    cmd = [ffmpeg, "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a?",
           "-vf", filters, "-c:v", codec]
    if limits["ten_bit"]:
        cmd += ["-pix_fmt", "yuv420p10le", "-tag:v", "hvc1", "-preset", "medium", "-crf", "20"]
    else:
        cmd += ["-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "18"]

    if before["has_audio"]:
        from openjarvis.video_essay import mezcla

        try:
            measured = mezcla.measure(src, ffmpeg)
            audio_filter = (
                "loudnorm=I=-14:TP=-1.5:LRA=11:"
                f"measured_I={measured['I']}:measured_TP={measured['TP']}:"
                f"measured_LRA={measured['LRA']}:measured_thresh={measured['thresh']}:"
                f"offset={measured['offset']}:linear=true:print_format=summary"
            )
        except Exception:
            audio_filter = "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=summary"
        cmd += ["-af", audio_filter, "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    log_lines: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if "=" not in line:
                log_lines.append(line)
                continue
            key, value = line.split("=", 1)
            if key == "out_time_ms" and progress:
                try:
                    elapsed = max(0.0, float(value) / 1_000_000)
                except ValueError:
                    continue
                fraction = min(0.99, elapsed / before["duration"]) if before["duration"] > 0 else None
                progress({"fraction": fraction, "seconds": elapsed, "stage": "render"})
        proc.stdout.close()
        code = proc.wait(timeout=max(1800, int(before["duration"] * 180)))
    except BaseException:
        proc.kill()
        proc.wait()
        out.unlink(missing_ok=True)
        raise
    if code != 0 or not out.is_file() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError("FFmpeg no pudo completar Video Boost: " + " ".join(log_lines)[-500:])

    after = _probe(out, ffprobe)
    quality: dict[str, Any] | None = None
    if after["has_audio"]:
        from openjarvis.video_essay import pro
        quality = pro.quality_check(out, ffmpeg)
    if progress:
        progress({"fraction": 1.0, "seconds": after["duration"], "stage": "complete"})
    return {
        "path": str(out), "before": before, "after": after,
        "plan": plan, "max_long_edge": limits["max_long_edge"],
        "codec": codec, "ten_bit": limits["ten_bit"], "quality_check": quality,
    }


__all__ = ["boost_video", "plan_limits"]

# Background jobs use persisted state; progress is written only from real FFmpeg output.
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sergio-video-boost")
_LOCK = threading.Lock()
_FUTURES: dict[str, Any] = {}


def _jobs_root() -> Path:
    from openjarvis.core.config import get_config_dir

    root = Path(get_config_dir()) / "video-boost"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _job_dir(boost_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{24}", boost_id or ""):
        raise ValueError("Identificador de Video Boost no valido.")
    return _jobs_root() / boost_id


def _save_state(folder: Path, state: dict[str, Any]) -> None:
    target = folder / "state.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps({**state, "updated": time.time()}, ensure_ascii=False), encoding="utf-8")
    temp.replace(target)


def get_boost(boost_id: str) -> dict[str, Any] | None:
    folder = _job_dir(boost_id)
    target = folder / "state.json"
    if not target.is_file():
        return None
    try:
        state = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if state.get("status") == "done":
        state["download_url"] = f"/v1/video/boost/{boost_id}/file"
    return state


def start_boost(src: Path, *, ffmpeg: str, plan: str | None = None) -> str:
    src = Path(src)
    if src.is_symlink() or not src.is_file():
        raise ValueError("El archivo de entrada no es valido.")
    if src.stat().st_size <= 0 or src.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("El video debe pesar entre 1 byte y 512 MB.")
    boost_id = secrets.token_hex(12)
    folder = _job_dir(boost_id)
    folder.mkdir(parents=True, exist_ok=False)
    incoming = folder / ("entrada" + (src.suffix.lower() if src.suffix.lower() in {".mp4", ".mov", ".mkv", ".m4v", ".webm"} else ".mp4"))
    shutil.copyfile(src, incoming)
    _save_state(folder, {"id": boost_id, "status": "queued", "progress": 0.0, "stage": "queued", "input": incoming.name})

    def work() -> None:
        _save_state(folder, {"id": boost_id, "status": "running", "progress": 0.0, "stage": "starting", "input": incoming.name})
        try:
            output = folder / "video-boost.mp4"

            def update(item: dict[str, Any]) -> None:
                current = get_boost(boost_id) or {}
                _save_state(folder, {
                    **current, "id": boost_id, "status": "running",
                    "progress": item.get("fraction"), "stage": item.get("stage", "render"),
                    "seconds": item.get("seconds"), "input": incoming.name,
                })

            result = boost_video(incoming, output, ffmpeg=ffmpeg, plan=plan, progress=update)
            result.pop("path", None)
            _save_state(folder, {"id": boost_id, "status": "done", "progress": 1.0, "stage": "complete", "input": incoming.name, "result": result})
        except Exception as exc:
            _save_state(folder, {"id": boost_id, "status": "failed", "progress": None, "stage": "failed", "input": incoming.name, "error": str(exc)[:500]})

    with _LOCK:
        _FUTURES[boost_id] = _EXECUTOR.submit(work)
    return boost_id


__all__ = ["boost_video", "get_boost", "plan_limits", "start_boost"]
