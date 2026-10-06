"""Sergio's consulting room: support conversations that remember.

Sergio listens (text or voice), answers with evidence-based techniques
(CBT, ACT, DBT skills, motivational interviewing, solution-focused) and
writes a short DAP note after each thing you say, like a psychologist with
a notebook. Sessions, notes, mood and questionnaires are encrypted on this
PC (Windows DPAPI). It is support, not a licensed professional: it says so
when needed, and any sign of risk brings ECU 911 and the Línea 171
(opción 6) at once.

Questionnaires (with your permission, as a guide, never a diagnosis):
PHQ-9 (mood) and GAD-7 (anxiety), both public domain (Pfizer).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sergio_escritorio import secure

OPTIONS = ("Ningún día", "Varios días", "Más de la mitad de los días", "Casi todos los días")
PERIOD = "Durante las últimas 2 semanas, ¿con qué frecuencia le ha molestado…"


@dataclass(frozen=True)
class Questionnaire:
    key: str
    name: str
    items: tuple[str, ...]
    bands: tuple[tuple[int, str], ...]  # (lowest score, label)
    risk_item: int = -1  # index whose answer > 0 means: ask about safety now


PHQ9 = Questionnaire(
    "phq9",
    "PHQ-9 (ánimo)",
    (
        "Poco interés o placer en hacer cosas",
        "Sentirse decaído, deprimido o sin esperanza",
        "Dificultad para dormir o permanecer dormido, o dormir demasiado",
        "Sentirse cansado o con poca energía",
        "Poco apetito o comer en exceso",
        "Sentirse mal con usted mismo, que es un fracaso o que ha quedado mal con usted o su familia",
        "Dificultad para concentrarse, por ejemplo al leer o ver televisión",
        "Moverse o hablar tan despacio que otros lo notaron, o lo contrario: muy inquieto",
        "Pensamientos de que estaría mejor muerto o de hacerse daño de alguna manera",
    ),
    ((0, "mínimo"), (5, "leve"), (10, "moderado"), (15, "moderadamente grave"), (20, "grave")),
    risk_item=8,
)
GAD7 = Questionnaire(
    "gad7",
    "GAD-7 (ansiedad)",
    (
        "Sentirse nervioso, ansioso o con los nervios de punta",
        "No poder dejar de preocuparse o no poder controlar la preocupación",
        "Preocuparse demasiado por distintas cosas",
        "Dificultad para relajarse",
        "Estar tan inquieto que es difícil quedarse quieto",
        "Molestarse o irritarse fácilmente",
        "Sentir miedo de que algo terrible pueda pasar",
    ),
    ((0, "mínimo"), (5, "leve"), (10, "moderado"), (15, "grave")),
)
QUESTIONNAIRES = {q.key: q for q in (PHQ9, GAD7)}


def score(q: Questionnaire, answers: list[int]) -> dict[str, Any]:
    if len(answers) != len(q.items) or any(a not in (0, 1, 2, 3) for a in answers):
        raise ValueError("Respuestas incompletas")
    total = sum(answers)
    band = [label for low, label in q.bands if total >= low][-1]
    risk = q.risk_item >= 0 and answers[q.risk_item] > 0
    return {"tipo": q.key, "nombre": q.name, "puntos": total, "max": 3 * len(q.items), "nivel": band, "riesgo": risk}


def explain_score(result: dict[str, Any], previous: dict[str, Any] | None = None) -> str:
    text = f"{result['nombre']}: {result['puntos']} de {result['max']}, nivel {result['nivel']}."
    if previous:
        diff = result["puntos"] - previous["puntos"]
        if diff:
            text += f" {'Subió' if diff > 0 else 'Bajó'} {abs(diff)} puntos desde la última vez."
    if result["nivel"] in ("moderado", "moderadamente grave", "grave"):
        text += " Es una orientación, no un diagnóstico; con este nivel vale la pena hablarlo con un psicólogo o médico."
    return text


RISK_WORDS = (
    "suicid", "matarme", "quitarme la vida", "no quiero vivir", "no quiero seguir viviendo",
    "hacerme dano", "hacerme daño", "cortarme", "autolesi", "mejor muerto", "acabar con todo",
    "me quiero morir", "quiero morir", "quiero morirme",
)  # fmt: skip
CRISIS = (
    "Señor, lo que dice me importa y no quiero que lo lleve solo. Si corre peligro "
    "ahora, llame al ECU 911. Para hablar con un psicólogo, la Línea 171, opción 6, "
    "del Ministerio de Salud es gratuita, de 7 de la mañana a 8 de la noche. "
    "Abro la consulta para que hablemos; estoy aquí."
)


def at_risk(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in RISK_WORDS)


class Consult:
    """Sessions, notes, mood and questionnaires (encrypted)."""

    SESSION_GAP = 3 * 3600  # a pause longer than this starts a new session

    def __init__(self, path: Path | None, clock: Callable[[], float] = time.time) -> None:
        self.path, self.clock = path, clock
        self._lock = threading.Lock()
        data = secure.read_json(path, {}) if path is not None else {}
        data = data if isinstance(data, dict) else {}
        self.sessions: list[dict[str, Any]] = list(data.get("sesiones") or [])
        self.tests: list[dict[str, Any]] = list(data.get("cuestionarios") or [])
        self.safety_plan: dict[str, Any] = dict(data.get("plan_seguridad") or {})

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            payload = {"sesiones": self.sessions[-200:], "cuestionarios": self.tests[-100:], "plan_seguridad": self.safety_plan}
        secure.write_json(self.path, payload)

    def current(self) -> dict[str, Any]:
        now = self.clock()
        if self.sessions:
            last = self.sessions[-1]
            stamp = last["mensajes"][-1]["t"] if last["mensajes"] else last["inicio"]
            if now - stamp < self.SESSION_GAP:
                return last
        session = {"inicio": now, "mensajes": [], "notas": [], "animo": [], "temas": []}
        self.sessions.append(session)
        return session

    def said(self, text: str) -> dict[str, Any]:
        session = self.current()
        session["mensajes"].append({"role": "user", "content": text.strip(), "t": self.clock()})
        self.save()
        return session

    def replied(self, reply: dict[str, Any]) -> None:
        session = self.current()
        session["mensajes"].append({"role": "assistant", "content": str(reply.get("respuesta", "")), "t": self.clock()})
        note = reply.get("nota")
        if isinstance(note, dict) and any(note.values()):
            session["notas"].append({**note, "t": self.clock()})
        if isinstance(reply.get("animo"), (int, float)):
            session["animo"].append(float(reply["animo"]))
        for topic in reply.get("temas") or []:
            if topic not in session["temas"]:
                session["temas"].append(str(topic))
        self.save()

    def messages(self) -> list[dict[str, str]]:
        return [{"role": m["role"], "content": m["content"]} for m in self.current()["mensajes"]]

    def notes(self, limit: int = 12) -> list[dict[str, Any]]:
        """The notebook: last notes across sessions (oldest first)."""
        all_notes = [n for s in self.sessions for n in s["notas"]]
        return all_notes[-limit:]

    def add_test(self, result: dict[str, Any]) -> dict[str, Any] | None:
        previous = next((t for t in reversed(self.tests) if t["tipo"] == result["tipo"]), None)
        self.tests.append({**result, "t": self.clock()})
        self.save()
        return previous

    def mood_trend(self) -> list[float]:
        return [round(sum(s["animo"]) / len(s["animo"]), 1) for s in self.sessions if s["animo"]][-12:]

    def summary_for_profile(self) -> dict[str, Any]:
        """Only themes and trend (never what was said) for the profile, and
        only if you allowed it."""
        themes: list[str] = []
        for s in self.sessions[-6:]:
            themes += [t for t in s["temas"] if t not in themes]
        return {"temas": themes[:8], "animo": self.mood_trend()[-4:]}


__all__ = ["CRISIS", "RISK_WORDS", "at_risk", "Consult", "GAD7", "OPTIONS", "PERIOD", "PHQ9", "QUESTIONNAIRES", "explain_score", "score"]
