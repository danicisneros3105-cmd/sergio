"""«Haz un video como este»: videos directed and edited at the level of a
reference — essays, challenge videos, food ads, 3D shorts and animation.

Two AIs make it: a director (the strongest model) writes the treatment and
has the last word, and an editor cuts it shot by shot. It can start from a
topic, the owner's script, a reference (file or YouTube link) or a free
prompt, like briefing a studio. Four modes: Test, Basic, Post quality and
Absolut Cinema. Pictures come from his clips, free stock, public archives,
web and short film clips, AI video, Blender 3D shots and Sergio's images;
the finishing uses Creator's colour and master tools.

It runs in the background (hours for the top modes) with a budget per mode,
one video at a time, and Hous posts the result in his chat. Nothing is ever
posted without the owner's face_approval.
"""

from __future__ import annotations

import re
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

TREND_WORDS = re.compile(r"\b(tendencias?|trends?|trending|viral(es)?|de moda)\b", re.I)


@ToolRegistry.register("video_essay")
class VideoEssayTool(BaseTool):
    """Long, reference-level videos as background jobs."""

    tool_id = "video_essay"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="video_essay",
            description=(
                "Make a professional video directed and edited at the level of a "
                "reference: video essays, high-energy challenge videos with counters, "
                "food/product ads, cinematic 3D shorts (Blender) and complex animation, "
                "with real clips (the user's, free stock, public archives, web and short "
                "film clips), AI-generated shots and Sergio's images. Use it for «haz un "
                "video como este», a YouTube link to copy the EDITING of, «de nivel», "
                "«no básico», or a free prompt describing the video. A director AI plans "
                "it and an editor AI cuts it. 'mode': test (quick, basic but well made), "
                "basic (normal, default), post (very high quality, ready to post, slow), "
                "cinema (Absolut Cinema: the best possible, slowest). 'prompt' (free "
                "brief) or 'topic' or 'script' (the user's own words); 'reference' (file "
                "or YouTube link; only its editing is learned); 'style' (corto-3d, "
                "reto-viral, anuncio-comida, animacion, lanzamiento-producto, metas-grandes or a "
                "learned one); "
                "'seconds' 15-1800 (long videos are fine, in chapters; 120 when not "
                "said); 'aspect' 16:9 / 9:16 / 1:1; 'clips' (folder of the "
                "user's clips, used first); 'music' (a song file or 'ninguna'); "
                "'ai_video' (allow AI video shots in test/basic); 'web_clips' (false to "
                "avoid clips from the web). Action 'start' returns at once (ONE video at "
                "a time: if one is running it returns that one; never call start again "
                "to «retry»), 'status' (optional 'job'), 'styles', 'cancel' and 'retry' "
                "need 'job'. NEVER publish: posting needs the user's face_approval first."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "status", "styles", "cancel", "retry"],
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["test", "basic", "post", "cinema"],
                    },
                    "prompt": {"type": "string"},
                    "topic": {"type": "string"},
                    "script": {"type": "string"},
                    "reference": {"type": "string"},
                    "style": {"type": "string"},
                    "seconds": {"type": "number"},
                    "aspect": {"type": "string", "enum": ["16:9", "9:16", "1:1"]},
                    "clips": {"type": "string"},
                    "music": {
                        "type": "string",
                        "description": "Empty: free music from the internet for the mood "
                        "(credited), or Sergio's own bed. A file path: the owner's song. "
                        "'canción: <name>': that song by name (not free; may be claimed). "
                        "Words ('piano triste'): free music for them. 'ninguna': none.",
                    },
                    "monetize": {
                        "type": "boolean",
                        "description": "False when the video will not earn money "
                        "(non-commercial CC music allowed then).",
                    },
                    "ai_video": {"type": "boolean"},
                    "web_clips": {"type": "boolean"},
                    "job": {"type": "string"},
                    "tendencias": {
                        "type": "boolean",
                        "description": "read real trends, searches and the competition first "
                        "and ride the strongest one (also when the order says trends/viral)",
                    },
                    "pais": {
                        "type": "string",
                        "description": "two letters for the trends (EC)",
                    },
                    "nicho": {"type": "string"},
                },
                "required": ["action"],
            },
            category="media",
            timeout_seconds=120,
            required_capabilities=["network:fetch"],
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.video_essay import job as jobs
        from openjarvis.video_essay import modes, style

        jobs.resume_unfinished()
        action = str(params.get("action") or "start")
        if action == "styles":
            names = [f"«{s['name']}» ({s['key']})" for s in style.available()]
            return self._ok("Estilos que sé dirigir: " + ", ".join(names) + ".")
        if action in ("cancel", "retry"):
            job_id = str(params.get("job") or "")
            if action == "cancel":
                done = jobs.cancel(job_id)
                return self._ok(
                    "Cancelado." if done else "No encuentro ese trabajo.", done
                )
            job = jobs.retry(job_id)
            if job is None:
                return self._ok("No encuentro ese trabajo.", False)
            return self._ok(jobs.summary(job.state()), job=job.id)
        if action == "status":
            job_id = str(params.get("job") or "")
            found = [jobs.get(job_id)] if job_id else jobs.all_jobs()[:3]
            found = [j for j in found if j is not None]
            if not found:
                return self._ok("No hay videos en curso.")
            return self._ok(
                "\n\n".join(jobs.summary(j.state()) for j in found), job=found[0].id
            )

        from openjarvis.tools.video_create import ffmpeg_exe

        prompt = " ".join(str(params.get("prompt") or "").split())[:3000]
        topic = " ".join(str(params.get("topic") or "").split())[:600]
        own = str(params.get("script") or "").strip()[:20000]
        if len(prompt) < 3 and len(topic) < 3 and len(own.split()) < 20:
            return self._ok(
                "Dígame de qué trata el video (o deme su guion o una descripción).",
                False,
            )
        if not ffmpeg_exe():
            return self._ok(
                "Falta el programa de video (ffmpeg). Actualice Sergio y vuelva a pedirlo.",
                False,
            )
        mode = modes.get(str(params.get("mode") or "basic"))
        aspect = str(params.get("aspect") or "16:9")
        order = {
            "mode": mode.key,
            "prompt": prompt,
            "topic": topic,
            "script": own,
            "reference": str(params.get("reference") or "").strip(),
            "style": str(params.get("style") or "").strip(),
            "seconds": min(1800.0, max(15.0, float(params.get("seconds") or 120))),
            "aspect": aspect if aspect in ("16:9", "9:16", "1:1") else "16:9",
            "clips": str(params.get("clips") or "").strip(),
            "music": str(params.get("music") or "").strip(),
            "ai_video": bool(params.get("ai_video", False)),
            "web_clips": bool(params.get("web_clips", True)),
            "monetize": params.get("monetize", True) is not False,
            # the trend radar first: asked for, or the order speaks of trends
            "tendencias": bool(params.get("tendencias"))
            or bool(TREND_WORDS.search(f"{prompt} {topic}")),
            "pais": str(params.get("pais") or "").strip().upper()[:2],
            "nicho": str(params.get("nicho") or "").strip()[:80],
        }
        existing, why = jobs.guard(order)
        if existing is not None:
            st = existing.state()
            lead = {
                "en curso": "Ya estoy haciendo un video; uno a la vez para no gastar de más.",
                "repetido": "Ese mismo video ya está hecho o en camino; no lo repito.",
                "tope diario": "Hoy ya hice el máximo de videos del día (SERGIO_VIDEO_JOBS_DIA).",
            }[why]
            return self._ok(f"{lead} {jobs.summary(st)}", job=existing.id, reused=True)
        job = jobs.start(order)
        ref = (
            " Primero estudio la referencia toma por toma."
            if order["reference"]
            else ""
        )
        time_note = {
            "test": "unos minutos",
            "basic": "un rato",
            "post": "horas",
            "cinema": "muchas horas",
        }[mode.key]
        return self._ok(
            f"Empecé el video en modo {modes.NAMES[mode.key]}.{ref} El director escribe el "
            f"tratamiento y el editor lo corta toma por toma; tarda {time_note}, con un tope "
            "de gasto para este modo. Hous le avisa en su chat cuando esté, y no lo publico "
            "sin su permiso.",
            job=job.id,
        )

    def _ok(self, text: str, success: bool = True, **meta: Any) -> ToolResult:
        return ToolResult(
            tool_name=self.tool_id, content=text, success=success, metadata=meta
        )


__all__ = ["VideoEssayTool"]
