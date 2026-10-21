"""Video Pro as Sergio's skills: learn a style, edit, upload (moved out of app.py).

The work itself lives in ``video_pro`` (the AI cut) and ``video_master``
(sources and finishing); this is the wiring to the app: the server's planner,
the Live Activity, what Sergio says when it is done, YouTube Studio, and the
``video_pro`` skill the agents call.
"""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Any, Callable


class VideoSkills:
    def __init__(
        self,
        *,
        client: Any,
        activities: Any,
        caption: Callable[[str], None],
        tell: Callable[..., None],
        controller: Any,
        last_result: list[str],
    ) -> None:
        self.client = client
        self.activities = activities
        self.caption = caption
        self.tell = tell
        self.controller = controller
        self.last_result = last_result
        self.last: list[dict] = []  # the last edited video, for «súbelo a YouTube»

    def learn_style(self, source: str) -> str:
        """Gemini watches the reference videos and keeps their editing style."""
        client = self.client

        def run() -> None:
            try:
                resp = client.http.post(f"{client.base}/v1/vision/video_style/learn",
                                        json={"source": source}, timeout=1800)
                if resp.status_code != 200:
                    try:
                        why = resp.json().get("detail") or resp.text
                    except ValueError:
                        why = resp.text
                    raise RuntimeError(str(why)[:300])
                done = resp.json()
                answer = (f"Aprendí el estilo. {done['summary']} Para usarlo diga: «edita un video con la "
                          f"carpeta … al estilo {done['style']['name']}».")
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                answer = f"No pude aprender ese estilo: {explain(exc)}"
            self.tell(answer, to_call=f"[Estilo de video] {answer} Cuéntaselo en una frase.")

        threading.Thread(target=run, daemon=True).start()
        return f"Estoy viendo los videos de {source[:60]} para copiar su edición; tardo unos minutos."

    def styles(self) -> str:
        resp = self.client.http.get(f"{self.client.base}/v1/vision/video_style", timeout=30)
        resp.raise_for_status()
        styles = resp.json().get("styles") or []
        if not styles:
            return "Aún no conozco estilos. Dígame: «aprende el estilo de edición de …»."
        return "Conozco estos estilos: " + " ".join(s["summary"] for s in styles[:5])

    def planner(self, request: str) -> Callable[[str, list, list], dict]:
        """Gemini watches the contact sheets and plans the cut (in a style)."""
        import json as _json

        from sergio_escritorio import video_pro

        style = video_pro.style_named(request)
        client = self.client

        def plan(req: str, sheets: list, lengths: list) -> dict:
            resp = client.http.post(
                f"{client.base}/v1/vision/video_plan",
                data={"request": req, "lengths": _json.dumps(lengths), "style": style},
                files=[("sheets", (f"clip{i}.jpg", s, "image/jpeg")) for i, s in enumerate(sheets)],
                timeout=600,
            )
            if resp.status_code != 200:
                try:
                    why = resp.json().get("detail") or resp.text
                except ValueError:
                    why = resp.text
                raise RuntimeError(str(why)[:300])
            return resp.json()

        return plan

    def pipeline(self, request: str, source: str = "", opts: dict | None = None, music: str = "") -> dict:
        """The professional edit (video_master.pipeline), shown as a Live Activity."""
        from sergio_escritorio import video_master

        live = self.activities.start("Video Pro", "video", "mirando los clips")
        steps: list[str] = []

        def log(line: str) -> None:
            steps.append(line)
            self.activities.update(live, detail=line[:60])

        try:
            done = video_master.pipeline(
                source or "Videos", request, self.planner(request), opts=opts, music=music, log=log
            )
        except Exception:
            self.activities.finish(live, False)
            raise
        self.activities.finish(live, True)
        done["steps"] = steps
        return done

    def task(self, request: str, source: str = "") -> str:
        """Video Pro in the background: Gemini watches, plans, ffmpeg renders,
        then the finishing the order asks for (60 fps, ProRes, LUT…)."""

        def run() -> None:
            try:
                self.caption("Video Pro: mirando tus clips…")
                done = self.pipeline(request, source)
                self.last[:] = [done]
                os.startfile(done["path"]) if hasattr(os, "startfile") else None  # noqa: B018
                title = done["plan"]["youtube"]["title"]
                self.last_result[:] = [f"el video «{title}» ({request[:80]})"]
                answer = (
                    f"Video listo: «{title}». Lo abrí para que lo veas; está en Videos, Sergio, "
                    "con el título, la descripción y las etiquetas al lado."
                    + (f" También dejé el máster ({done['master_label']})." if done.get("master") else "")
                    + " Si le gusta, diga «súbelo a YouTube»."
                )
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                answer = f"Video Pro falló: {explain(exc)}"
            self.tell(answer, to_call=f"[Video terminado] {answer} Cuéntaselo en una frase.")

        threading.Thread(target=run, daemon=True).start()
        return "Video Pro en marcha: mira tus clips, elige los mejores momentos y lo monta. Le aviso al terminar."

    def upload(self) -> str:
        """YouTube Studio's upload, ready; publishing stays your click."""
        if not self.last:
            return "Primero hagamos un video: «edita un video con la carpeta…»."
        video = self.last[0]
        yt = video["plan"]["youtube"]
        try:
            import pyperclip

            pyperclip.copy(f"{yt['title']}\n\n{yt['description']}\n\n{', '.join(yt['tags'])}")
        except Exception:  # noqa: BLE001
            pass
        self.controller.act({"action": "open", "target": "https://studio.youtube.com/channel/UC/videos/upload?d=ud"})
        subprocess.Popen(["explorer", "/select,", video["path"]])  # noqa: S603,S607
        return (
            "Abrí YouTube Studio para subirlo y le marqué el video en la carpeta: "
            "arrástrelo a la ventana de subida. El título, la descripción y las etiquetas "
            "están copiados: péguelos con Ctrl+V. Publicar lo decide usted."
        )

    def pro_skill(self, args: dict) -> dict:
        """Agents' professional edit: the same pipeline as «Sergio, Video Pro»."""
        request = str(args.get("request") or "").strip() or "Edita un video profesional con lo mejor de los clips."
        if args.get("aspect"):
            request += f" Formato {args['aspect']}."
        keys = ("silences", "fps", "slow", "master", "lut", "denoise", "sharpen", "contrast_curve")
        opts = {k: args[k] for k in keys if args.get(k) not in (None, "", False)}
        done = self.pipeline(request, str(args.get("source") or ""), opts, str(args.get("music") or ""))
        self.last[:] = [done]
        if hasattr(os, "startfile"):
            os.startfile(done["path"])  # noqa: S606 — the owner reviews it
        plan = done.get("plan") or {}
        return {
            "path": done["path"],
            "meta": done.get("meta", ""),
            "master": done.get("master", ""),
            "master_label": done.get("master_label", ""),
            "interpolated": done.get("interpolated", ""),
            "title": (plan.get("youtube") or {}).get("title", ""),
            "aspect": plan.get("aspect", ""),
            "segments": len(plan.get("segments") or []),
            "steps": done.get("steps", []),
        }


__all__ = ["VideoSkills"]
