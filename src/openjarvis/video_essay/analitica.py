"""Evidence-based post-publication and technical video analytics."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def channel_metrics(platform: str, published_id: str, *, home: Path | None = None, http: Any = None) -> dict[str, Any]:
    """Fetch only metrics exposed by the connected official platform API."""
    from openjarvis.automatiza import canales

    if not published_id:
        return {"available": False, "reason": "Falta el identificador de publicacion."}
    if platform == "youtube":
        account = canales.account("youtube", home)
        if not account.get("refresh_token"):
            return {"available": False, "reason": "YouTube no esta conectado."}
        http = http or canales._http()
        token = canales._yt_token(account, http, home)
        response = http.get(
            f"{canales.YT_API}/videos",
            params={"part": "statistics,snippet", "id": published_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        items = response.json().get("items") or []
        if not items:
            return {"available": False, "reason": "YouTube no devolvio ese video."}
        row = items[0]
        stats = row.get("statistics") or {}
        return {
            "available": True, "platform": "youtube", "id": published_id,
            "title": (row.get("snippet") or {}).get("title", ""),
            "views": _int_or_none(stats.get("viewCount")),
            "likes": _int_or_none(stats.get("likeCount")),
            "comments": _int_or_none(stats.get("commentCount")),
            "retention": None,
            "retention_note": "La retencion de audiencia no esta disponible con el acceso actual.",
        }
    if platform == "instagram":
        account = canales.account("instagram", home)
        if not account.get("token"):
            return {"available": False, "reason": "Instagram no esta conectado."}
        http = http or canales._http()
        response = http.get(
            f"{canales.IG_API}/{published_id}",
            params={
                "fields": "like_count,comments_count,plays,views,reach,timestamp",
                "access_token": account["token"],
            },
        )
        response.raise_for_status()
        row = response.json()
        return {
            "available": True, "platform": "instagram", "id": published_id,
            "views": _int_or_none(row.get("views") or row.get("plays")),
            "plays": _int_or_none(row.get("plays")),
            "reach": _int_or_none(row.get("reach")),
            "likes": _int_or_none(row.get("like_count")),
            "comments": _int_or_none(row.get("comments_count")),
            "retention": None,
            "retention_note": "La retencion de audiencia no esta disponible con el acceso actual.",
        }
    raise ValueError("El canal debe ser youtube o instagram.")


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _probe_scene_changes(path: Path, ffmpeg: str) -> int | None:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-v", "info", "-t", "3", "-i", str(path),
         "-vf", "select='gt(scene,0.35)',showinfo", "-an", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode:
        return None
    return len(re.findall(r"\bpts_time:", result.stderr or ""))


def analyze_job(
    job_id: str,
    *,
    platform: str = "",
    published_id: str = "",
    home: Path | None = None,
    http: Any = None,
) -> dict[str, Any]:
    """Combine published metrics with measured output diagnostics and learn."""
    from openjarvis.video_essay import job as jobs
    from openjarvis.video_essay import render

    job = jobs.get(job_id, root=home)
    if job is None:
        raise ValueError("No encuentro ese trabajo de video.")
    state = job.state()
    result = state.get("result") or {}
    path = Path(str(result.get("path") or ""))
    if not path.is_file():
        raise ValueError("El archivo final de ese trabajo ya no esta disponible.")
    ffmpeg = render.ffmpeg()
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("La analitica tecnica necesita FFprobe.")
    from openjarvis.video_essay.boost import _probe

    media = _probe(path, ffprobe)
    technical: dict[str, Any] = {
        "duration_seconds": round(media["duration"], 2),
        "width": media["width"], "height": media["height"],
        "audio": media["has_audio"],
        "scene_changes_first_3s": _probe_scene_changes(path, ffmpeg),
    }
    try:
        from openjarvis.video_essay import pro
        technical["quality_check"] = pro.quality_check(path, ffmpeg)
    except Exception as exc:
        technical["quality_check"] = {"available": False, "reason": str(exc)[:180]}
    if media["has_audio"]:
        try:
            from openjarvis.video_essay import mezcla
            technical["audio"] = {"present": True, **mezcla.measure(path, ffmpeg)}
        except Exception as exc:
            technical["audio"] = {"present": True, "measurement_error": str(exc)[:160]}
    else:
        technical["audio"] = {"present": False}

    try:
        script_data = job.read("script.json")
    except Exception:
        script_data = {}
    words = len(str(script_data.get("text") or "").split())
    if media["duration"] > 0 and words:
        technical["script_words_per_minute"] = round(words * 60 / media["duration"])
    try:
        plan = job.read("plan.json")
        technical["planned_shots"] = len(plan)
        durations = [float(item.get("dur", 0)) for item in plan if isinstance(item, dict)]
        if durations:
            technical["median_shot_seconds"] = round(sorted(durations)[len(durations) // 2], 2)
    except Exception:
        technical["planned_shots"] = result.get("shots")

    channel = {"available": False, "reason": "No se indico un canal publicado."}
    if platform or published_id:
        if not platform or not published_id:
            raise ValueError("Indica canal e identificador de publicacion juntos.")
        channel = channel_metrics(platform, published_id, http=http)

    recommendations = []
    audio = technical.get("audio") or {}
    loudness = audio.get("I")
    if not media["has_audio"]:
        recommendations.append("El archivo no tiene pista de audio; revisa la mezcla antes de publicar.")
    elif isinstance(loudness, (int, float)) and abs(loudness + 14) > 1.5:
        recommendations.append(f"El audio mide {loudness:.1f} LUFS; acercalo a -14 LUFS y controla el pico antes de publicar.")
    qc = technical.get("quality_check") or {}
    if qc.get("available") is False:
        recommendations.append("No se pudo completar el control tecnico; revisa FFmpeg y sus filtros.")
    elif qc.get("problemas"):
        recommendations.extend(f"Control tecnico: {item}." for item in qc["problemas"][:3])
    if technical.get("scene_changes_first_3s") == 0:
        recommendations.append("No se detectaron cambios de escena en los primeros 3 segundos; revisa visualmente si el gancho abre con accion.")
    if not recommendations:
        recommendations.append("Las comprobaciones disponibles no detectaron incidencias tecnicas; la calidad del gancho requiere revision editorial.")

    passes = [item for item in state.get("passes") or [] if isinstance(item, dict) and isinstance(item.get("score"), (int, float))]
    review_score = passes[-1]["score"] if passes else None
    analysis = {
        "job_id": job_id, "title": state.get("title", ""),
        "technical": technical, "published_metrics": channel,
        "creative_review_score": review_score,
        "recommendations": recommendations,
        "causal_claim": False,
    }
    brief = str((state.get("params") or {}).get("prompt") or (state.get("params") or {}).get("topic") or "video")[:300]
    metric_note = ""
    if channel.get("available"):
        metric_note = " Metricas reales del canal: " + ", ".join(
            f"{key}={channel[key]}" for key in ("views", "plays", "reach", "likes", "comments") if channel.get(key) is not None
        ) + ". No atribuyo causalidad a un solo video."
    lesson = f"Video: {brief}. Lecciones medibles: " + " ".join(recommendations) + metric_note
    try:
        from openjarvis.evolution.memory import shared
        analysis["memory_id"] = shared().remember("video", lesson, job_id=job_id, platform=platform, published_id=published_id)
        analysis["memory_saved"] = bool(analysis["memory_id"])
    except Exception as exc:
        analysis["memory_saved"] = False
        analysis["memory_error"] = str(exc)[:160]

    specialist = state.get("specialist") or {}
    if review_score is not None and specialist.get("kind") and specialist.get("techniques"):
        try:
            from openjarvis.video_essay import specialists
            analysis["specialist_learning"] = specialists.learn_from_video(
                specialist["kind"], specialist.get("brief", brief), specialist["techniques"], review_score
            )
        except Exception as exc:
            analysis["specialist_learning_error"] = str(exc)[:160]
    return analysis


__all__ = ["analyze_job", "channel_metrics"]
