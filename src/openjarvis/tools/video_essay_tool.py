"""«Haz un video como este»: a video essay at the level of a reference edit.

Not a quick montage (that is ``video_create``): the reference is studied
shot by shot, the script follows its structure, every shot is cut on the
spoken words with kinetic text, cards, archive looks and device frames, an
editor reviews the cut in passes, and it is rendered at full size. It takes
hours, so it runs in the background and survives a restart; Hous posts the
finished video in his chat. It is never published without the owner's OK.
"""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("video_essay")
class VideoEssayTool(BaseTool):
    """Long, reference-level video essays as background jobs."""

    tool_id = "video_essay"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="video_essay",
            description=(
                "Make a professional video essay edited at the level of a reference "
                "video (fast cuts on every phrase, kinetic word-by-word text, colour "
                "cards, black-and-white archive shots in an old TV frame, clips "
                "inside an old computer or phone, sound effects, music that builds). "
                "Use it when the user gives a video or a YouTube link to copy the "
                "EDITING of, or asks for an essay / motivational / explainer video "
                "«de nivel», «como este», «no básico». It takes from minutes to "
                "hours: action 'start' returns at once and Hous posts the video in "
                "his chat when it is done. 'topic' (or 'script' with the user's own "
                "words), 'reference' (a file path or YouTube link; only its editing "
                "is learned, never its footage), 'style' (a style learned before), "
                "'seconds' 30-600 (default 90), 'aspect' 16:9 / 9:16 / 1:1, "
                "'clips' (folder with the user's own clips, used first), 'music' "
                "(a song file of the user's, or 'ninguna'), 'passes' (review "
                "passes, 0-5, default 2). Action 'status' (optional 'job') tells "
                "where it is; 'styles' lists learned styles; 'cancel' and 'retry' "
                "need 'job'. Never publish the video."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "status", "styles", "cancel", "retry"],
                    },
                    "topic": {"type": "string"},
                    "script": {"type": "string"},
                    "reference": {"type": "string"},
                    "style": {"type": "string"},
                    "seconds": {"type": "number"},
                    "aspect": {"type": "string", "enum": ["16:9", "9:16", "1:1"]},
                    "clips": {"type": "string"},
                    "music": {"type": "string"},
                    "passes": {"type": "integer"},
                    "job": {"type": "string"},
                },
                "required": ["action"],
            },
            category="media",
            timeout_seconds=120,
            required_capabilities=["network:fetch"],
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.video_essay import job as jobs
        from openjarvis.video_essay import style

        jobs.resume_unfinished()
        action = str(params.get("action") or "start")
        if action == "styles":
            names = [f"«{s['name']}» ({s['key']})" for s in style.available()]
            return self._ok("Estilos que sé editar: " + ", ".join(names) + ".")
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
            return self._ok(
                f"Lo retomo desde donde se quedó. {jobs.summary(job.state())}",
                job=job.id,
            )
        if action == "status":
            job_id = str(params.get("job") or "")
            found = [jobs.get(job_id)] if job_id else jobs.all_jobs()[:3]
            found = [j for j in found if j is not None]
            if not found:
                return self._ok("No hay videos ensayo en curso.")
            return self._ok(
                "\n\n".join(jobs.summary(j.state()) for j in found), job=found[0].id
            )

        from openjarvis.tools.video_create import ffmpeg_exe

        topic = " ".join(str(params.get("topic") or "").split())[:600]
        own = str(params.get("script") or "").strip()[:20000]
        if len(topic) < 3 and len(own.split()) < 20:
            return self._ok("Dígame de qué trata el video (o deme su guion).", False)
        if not ffmpeg_exe():
            return self._ok(
                "Falta el programa de video (ffmpeg). Actualice Sergio y vuelva a pedirlo.",
                False,
            )
        aspect = str(params.get("aspect") or "16:9")
        order = {
            "topic": topic,
            "script": own,
            "reference": str(params.get("reference") or "").strip(),
            "style": str(params.get("style") or "").strip(),
            "seconds": min(600.0, max(30.0, float(params.get("seconds") or 90))),
            "aspect": aspect if aspect in ("16:9", "9:16", "1:1") else "16:9",
            "clips": str(params.get("clips") or "").strip(),
            "music": str(params.get("music") or "").strip(),
            "passes": max(
                0,
                min(
                    5,
                    int(
                        params.get("passes") if params.get("passes") is not None else 2
                    ),
                ),
            ),
        }
        job = jobs.start(order)
        ref = (
            " Primero estudio la referencia toma por toma."
            if order["reference"]
            else ""
        )
        return self._ok(
            f"Empecé el video ensayo «{topic or 'con su guion'}».{ref} Es trabajo de editor: "
            "guion, voz, cada toma sobre las palabras, revisión y render a tamaño completo, "
            "así que tarda (de minutos a horas). Hous le avisa en su chat cuando esté, "
            "y no lo publico sin su permiso.",
            job=job.id,
        )

    def _ok(self, text: str, success: bool = True, **meta: Any) -> ToolResult:
        return ToolResult(
            tool_name=self.tool_id, content=text, success=success, metadata=meta
        )


__all__ = ["VideoEssayTool"]
