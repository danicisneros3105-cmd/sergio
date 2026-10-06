"""Sergio as your coach: anything you are learning, at your own pace.

Tell Sergio what you are learning ("estoy aprendiendo el doble lift con
cartas", "quiero aprender francés", "tengo examen de física el viernes"):

1. the server's coach researches it on the web and plans the practice for
   you (sub-skills, its own metrics, common mistakes, 10-14 short sessions);
2. sessions land in your usual free time (``perfil.Usage``) and pop up;
3. each session brings a lesson made for your level and last mistakes;
4. physical skills (and pronunciation): Sergio records you, the coach
   watches the video and the copy it saves circles what you did well in
   green and what went wrong in red;
5. after each session your results become metrics, error counts and the
   next session's difficulty.

Exams and homework: Sergio reads your school platform (a screenshot of the
page you told it) and turns tasks and exams into reminders and study plans.

Pure logic here (tested); the windows are in ``coach_ui.py``.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

LANGUAGES = {
    "frances": "francés", "ingles": "inglés", "aleman": "alemán", "italiano": "italiano",
    "portugues": "portugués", "japones": "japonés", "chino": "chino", "mandarin": "chino",
    "coreano": "coreano", "ruso": "ruso", "arabe": "árabe", "kichwa": "kichwa", "quechua": "quechua",
}  # fmt: skip
SNOOZE = 30 * 60


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def goal_kind(text: str) -> str:
    """idioma | examen | habilidad."""
    t = _plain(text)
    if any(re.search(rf"\b{k}\b", t) for k in LANGUAGES) or re.search(r"\bidioma\b", t):
        return "idioma"
    if re.search(r"\b(examen|prueba|parcial|final|test|leccion)\b", t):
        return "examen"
    return "habilidad"


def parse_goal(text: str) -> str | None:
    """What you are learning, from "estoy aprendiendo X", "quiero aprender X"..."""
    m = re.search(
        r"\b(?:estoy aprendiendo|quiero aprender|aprendo|estoy practicando|quiero mejorar(?: en)?|"
        r"quiero dominar|ens[eé]ñame a|entr[eé]name en|prep[aá]rame para|tengo (?:un |el )?examen de)\s+(.+)",
        text.strip().rstrip(".!"),
        re.I,
    )
    if not m:
        return None
    goal = m.group(1).strip()
    if re.match(r"(?i)tengo (?:un |el )?examen de", m.group(0)):
        goal = "examen de " + goal
    return goal if len(goal) >= 3 else None


class Coach:
    """Goals, their plans and sessions, metrics and errors (``coach.json``)."""

    def __init__(self, path: Path | None, clock: Callable[[], float] = time.time) -> None:
        self.path, self.clock = path, clock
        self._lock = threading.Lock()
        data: dict[str, Any] = {}
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        self.goals: list[dict[str, Any]] = list(data.get("metas") or [])

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            payload = {"metas": self.goals, "resumen_para_perfil": self.summary_for_profile()}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    # -- goals ------------------------------------------------------------------
    def add_goal(self, text: str, plan: dict[str, Any], place: Callable[[float, int], float]) -> dict[str, Any]:
        """A new goal with its plan; sessions are placed with *place*(after, minutes)."""
        now = self.clock()
        goal = {
            "id": uuid.uuid4().hex[:8],
            "meta": text.strip(),
            "tipo": goal_kind(text),
            "creado": now,
            "plan": plan,
            "sesiones": [],
            "metricas": [],
            "errores": {},
            "nivel": "",
            "feedback": [],
            "activo": True,
        }
        start = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
        last = now
        for i, s in enumerate(plan.get("sesiones") or []):
            day = max(0, int(s.get("dia") or 0))
            minutes = max(5, min(90, int(s.get("minutos") or 20)))
            earliest = max(last + 3600, (start + timedelta(days=day)).timestamp(), now + 600)
            due = place(earliest, minutes)
            last = due
            goal["sesiones"].append({
                "n": i + 1, "objetivo": str(s.get("objetivo") or ""), "pasos": list(s.get("pasos") or []),
                "minutos": minutes, "video": bool(s.get("video")), "due": due, "hecha": False, "resultado": None,
            })  # fmt: skip
        with self._lock:
            self.goals.append(goal)
        self.save()
        return goal

    def get(self, goal_id: str) -> dict[str, Any] | None:
        return next((g for g in self.goals if g["id"] == goal_id), None)

    def find(self, words: str) -> dict[str, Any] | None:
        w = _plain(words)
        active = [g for g in self.goals if g.get("activo", True)]
        return next((g for g in active if w and (w in _plain(g["meta"]) or _plain(g["meta"]) in w)), None)

    def stop_goal(self, goal_id: str) -> None:
        goal = self.get(goal_id)
        if goal is not None:
            goal["activo"] = False
            self.save()

    # -- sessions -----------------------------------------------------------------
    def due_sessions(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        now = self.clock()
        out = []
        for g in self.goals:
            if not g.get("activo", True):
                continue
            for s in g["sesiones"]:
                if not s["hecha"] and s["due"] <= now:
                    out.append((g, s))
                    break  # one at a time per goal
        return out

    def next_session(self, goal: dict[str, Any]) -> dict[str, Any] | None:
        return next((s for s in goal["sesiones"] if not s["hecha"]), None)

    def snooze(self, goal: dict[str, Any], session: dict[str, Any], seconds: float = SNOOZE) -> None:
        session["due"] = self.clock() + seconds
        self.save()

    def finish(self, goal: dict[str, Any], session: dict[str, Any], result: dict[str, Any]) -> None:
        """Results of a session -> metrics, errors, level, difficulty."""
        session["hecha"] = True
        session["resultado"] = {k: result.get(k) for k in ("metricas", "bien", "mal", "feedback", "nota") if k in result}
        metrics = {k: float(v) for k, v in (result.get("metricas") or {}).items() if isinstance(v, (int, float))}
        if metrics:
            goal["metricas"].append({"t": self.clock(), "valores": metrics})
        for kind, count in (result.get("errores_tipo") or {}).items():
            try:
                goal["errores"][kind] = goal["errores"].get(kind, 0) + int(count)
            except (TypeError, ValueError):
                continue
        if result.get("nivel"):
            goal["nivel"] = str(result["nivel"])
        if result.get("feedback"):
            goal["feedback"] = (goal["feedback"] + [str(result["feedback"])])[-20:]
        # Harder or easier: move the next sessions closer or further apart.
        step = int(result.get("dificultad") or 0)
        if step:
            for s in goal["sesiones"]:
                if not s["hecha"]:
                    s["minutos"] = max(10, min(60, s["minutos"] + 5 * step))
        self.save()

    def progress(self, goal: dict[str, Any]) -> dict[str, Any]:
        done = sum(1 for s in goal["sesiones"] if s["hecha"])
        series: dict[str, list[float]] = {}
        for m in goal["metricas"]:
            for k, v in m["valores"].items():
                series.setdefault(k, []).append(v)
        top_errors = sorted(goal["errores"].items(), key=lambda kv: -kv[1])[:3]
        return {"hechas": done, "total": len(goal["sesiones"]), "series": series, "errores": top_errors, "nivel": goal.get("nivel", "")}

    def for_lesson(self, goal: dict[str, Any]) -> dict[str, Any]:
        """What the coach needs to prepare the next lesson (not everything)."""
        nxt = self.next_session(goal) or {}
        plan = goal.get("plan") or {}
        return {
            "meta": goal["meta"], "tipo": goal["tipo"], "nivel": goal.get("nivel", ""),
            "subhabilidades": plan.get("subhabilidades", [])[:10], "metricas_plan": plan.get("metricas", [])[:8],
            "errores_frecuentes": self.progress(goal)["errores"], "ultimos_feedback": goal["feedback"][-4:],
            "ultimas_metricas": goal["metricas"][-5:], "sesion": nxt,
        }  # fmt: skip

    def summary_for_profile(self) -> dict[str, Any]:
        out = {}
        for g in self.goals:
            if g.get("activo", True):
                p = self.progress(g)
                out[g["meta"]] = {"tipo": g["tipo"], "sesiones": f"{p['hechas']}/{p['total']}", "nivel": p["nivel"],
                                  "errores": [k for k, _ in p["errores"]]}  # fmt: skip
        return out

    def describe(self) -> str:
        active = [g for g in self.goals if g.get("activo", True)]
        if not active:
            return "No tiene metas de aprendizaje. Dígame «estoy aprendiendo…» y le armo un plan."
        parts = []
        for g in active[:4]:
            p = self.progress(g)
            nxt = self.next_session(g)
            when = datetime.fromtimestamp(nxt["due"]).strftime("%a %H:%M") if nxt else "plan terminado"
            parts.append(f"{g['meta']}: {p['hechas']} de {p['total']} sesiones, próxima {when}")
        return "; ".join(parts) + "."


# -- practice videos -------------------------------------------------------------------
def record_video(frames: Callable[[], Any], path: Path, seconds: float = 20.0, fps: float = 15.0,
                 stop: Callable[[], bool] | None = None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> Path:  # fmt: skip
    """Record the camera for *seconds* into an MP4 (what the coach will watch)."""
    import cv2

    writer = None
    end = clock() + seconds
    wrote = 0
    try:
        while clock() < end and not (stop and stop()):
            frame = frames()
            if frame is not None:
                if writer is None:
                    h, w = frame.shape[:2]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
                writer.write(frame)
                wrote += 1
            sleep(1.0 / fps)
    finally:
        if writer is not None:
            writer.release()
    if not wrote:
        raise RuntimeError("La cámara no dio imágenes")
    return path


def annotate_video(source: Path, marks: list[dict[str, Any]], out: Path, mirror: bool = False) -> Path:
    """Copy of the practice video with the coach's marks: a green circle where
    it went well, a red one where it went wrong, with a short label."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    try:
        font = ImageFont.truetype("segoeuib.ttf", max(16, h // 28))
    except OSError:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(16, h // 28))
        except OSError:
            font = ImageFont.load_default()
    index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = index / fps
            active = [m for m in marks if m["t"] <= t < m["t"] + m.get("duracion", 1.5)]
            if active:
                if mirror:
                    frame = cv2.flip(frame, 1)
                for m in active:
                    colour = (60, 200, 70) if m["bien"] else (50, 50, 235)  # BGR
                    centre = (int(m["x"] * w), int(m["y"] * h))
                    radius = max(12, int(m["r"] * w))
                    grow = min(1.0, (t - m["t"]) / 0.25)  # the circle draws in
                    cv2.ellipse(frame, centre, (radius, radius), -90, 0, int(360 * grow), colour, max(3, w // 240), cv2.LINE_AA)
                image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                draw = ImageDraw.Draw(image)
                for m in active:
                    if not m.get("texto"):
                        continue
                    text = ("✓ " if m["bien"] else "✗ ") + m["texto"]
                    x = int(m["x"] * w)
                    y = int(m["y"] * h + max(12, m["r"] * w) + 8)
                    box = draw.textbbox((0, 0), text, font=font)
                    tw, th = box[2] - box[0], box[3] - box[1]
                    x = max(6, min(w - tw - 16, x - tw // 2))
                    y = min(h - th - 14, y)
                    fill = (40, 160, 60) if m["bien"] else (210, 40, 40)
                    draw.rounded_rectangle((x - 8, y - 5, x + tw + 8, y + th + 9), radius=10, fill=fill)
                    draw.text((x, y), text, font=font, fill=(255, 255, 255))
                frame = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
                if mirror:
                    frame = cv2.flip(frame, 1)
            writer.write(frame)
            index += 1
    finally:
        cap.release()
        writer.release()
    if index == 0:
        raise RuntimeError("No pude leer el video de la práctica")
    return out


# -- school platform ---------------------------------------------------------------------
def school_reminders(data: dict[str, Any], now: datetime) -> list[tuple[float, str]]:
    """Reminders for homework (the day before, 18:00) and exams (3 days and
    1 day before), only for dates still ahead."""
    out = []

    def when(text: str) -> datetime | None:
        try:
            return datetime.strptime(str(text)[:10], "%Y-%m-%d")
        except ValueError:
            return None

    for t in data.get("tareas") or []:
        day = when(t.get("fecha", ""))
        if day is not None:
            at = (day - timedelta(days=1)).replace(hour=18)
            if at > now:
                out.append((at.timestamp(), f"mañana se entrega {t.get('titulo', 'una tarea')} de {t.get('materia', '')}".strip()))
    for e in data.get("examenes") or []:
        day = when(e.get("fecha", ""))
        if day is None:
            continue
        for before in (3, 1):
            at = (day - timedelta(days=before)).replace(hour=18)
            if at > now:
                out.append((at.timestamp(), f"examen de {e.get('materia', '')} en {before} día{'s' if before > 1 else ''}"))
    return sorted(out)


__all__ = ["Coach", "annotate_video", "goal_kind", "parse_goal", "record_video", "school_reminders"]
