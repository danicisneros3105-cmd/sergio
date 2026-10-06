"""Agents: specialists Sergio hands work to, and the ones you create.

* Pro agents come built in: Investigador, Programador, Analista de datos,
  Diseñador 3D, Editor de video, Organizador de archivos, Viajes, Escritor
  and Tutor. Each has its role, how it works and checks its work, and its
  own toolbox (the planner can only use those tools).
* «Crea un agente que cada lunes a las 8 me resuma las noticias de IA»:
  the server designs it (name, instructions, tools from the real list,
  schedule) and it is saved. Agents with a schedule run by themselves and
  appear in the notch like any other task.
* «Investigador, compara las RTX 5070 y 5080» or «usa el agente Viajes
  para …» gives the job to that agent (it runs in the background).
"""

from __future__ import annotations

import datetime
import json
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any

PRO: tuple[dict[str, Any], ...] = (
    {"nombre": "Investigador", "rol": "Investiga a fondo y compara, con fuentes.",
     "instrucciones": "Busca en varias fuentes fiables, contrasta datos, cita de dónde sale cada cifra y "
                      "entrega una conclusión clara con una tabla si hay opciones. Nada sin fuente.",
     "herramientas": ["web_search", "http_request", "python_run", "file_write", "think"]},
    {"nombre": "Programador", "rol": "Escribe, arregla y prueba código.",
     "instrucciones": "Lee el código antes de tocarlo, hace el cambio mínimo, lo prueba en Ubuntu "
                      "(tests o una ejecución real) y explica qué cambió. Nunca borra sin aprobación.",
     "herramientas": ["terminal_run", "python_run", "file_read", "file_write", "web_search", "think"]},
    {"nombre": "Analista de datos", "rol": "Analiza hojas de cálculo y datos.",
     "instrucciones": "Carga los datos con Python, revisa su calidad, calcula lo pedido, hace un "
                      "gráfico si ayuda y entrega las cifras exactas con el archivo de resultado.",
     "herramientas": ["python_run", "file_read", "file_write", "pdf_extract", "calculator", "think"]},
    {"nombre": "Diseñador 3D", "rol": "Modela en Blender con calidad profesional.",
     "instrucciones": "Usa Blender Pro: planos, modelo, cuatro vistas y revisiones hasta que las "
                      "proporciones y los materiales coincidan con lo pedido.",
     "herramientas": ["blender_create", "web_search", "think"]},
    {"nombre": "Editor de video", "rol": "Edita videos listos para publicar.",
     "instrucciones": "Estudia el estilo pedido, elige los mejores momentos, edita con Video Pro y "
                      "deja título, descripción y etiquetas. Publicar lo decide el dueño.",
     "herramientas": ["video_edit", "web_search", "think"]},
    {"nombre": "Organizador", "rol": "Ordena archivos y carpetas.",
     "instrucciones": "Primero muestra la vista previa del orden, aplica solo lo aprobado y deja "
                      "cómo deshacerlo. Nunca borra.",
     "herramientas": ["files_organize", "file_read", "python_run", "think"]},
    {"nombre": "Viajes", "rol": "Planea viajes: vuelos, clima, itinerario.",
     "instrucciones": "Compara vuelos y fechas, revisa el clima, arma un itinerario día por día con "
                      "costos estimados y fuentes, y lo guarda en un archivo. No compra nada.",
     "herramientas": ["web_search", "get_weather", "live_flights", "globe_view", "file_write", "think"]},
    {"nombre": "Escritor", "rol": "Redacta documentos, correos y textos.",
     "instrucciones": "Pregunta el tono solo si falta, escribe claro y corto, revisa ortografía y "
                      "deja el texto en un archivo. Nunca envía nada.",
     "herramientas": ["file_write", "web_search", "think"]},
    {"nombre": "Tutor", "rol": "Explica y prepara para exámenes.",
     "instrucciones": "Explica con ejemplos, hace preguntas de práctica, corrige y deja un resumen "
                      "con lo que hay que repasar.",
     "herramientas": ["web_search", "pdf_extract", "file_write", "think"]},
)  # fmt: skip


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


class Agents:
    """The pro agents plus the user's own (saved as JSON)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        try:
            self.mine: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.mine = []

    def all(self) -> list[dict[str, Any]]:
        return [*({**a, "pro": True} for a in PRO), *self.mine]

    def find(self, name: str) -> dict[str, Any] | None:
        key = plain(name)
        for agent in self.all():
            if plain(agent["nombre"]) == key:
                return agent
        for agent in self.all():  # «el de viajes», «investigadora»
            n = plain(agent["nombre"])
            if key and (key in n or n in key or n.rstrip("aeo") == key.rstrip("aeo")):
                return agent
        return None

    def add(self, spec: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            spec = {**spec, "creado": datetime.date.today().isoformat(), "ultima": ""}
            self.mine = [a for a in self.mine if plain(a["nombre"]) != plain(spec["nombre"])] + [spec]
            self._save()
        return spec

    def remove(self, name: str) -> bool:
        agent = self.find(name)
        if agent is None or agent.get("pro"):
            return False
        with self.lock:
            self.mine = [a for a in self.mine if a["nombre"] != agent["nombre"]]
            self._save()
        return True

    def due(self, now: datetime.datetime) -> list[dict[str, Any]]:
        """Scheduled agents whose time has come today (once a day)."""
        out = []
        today = now.date().isoformat()
        for agent in self.mine:
            when = agent.get("horario") or {}
            hour = when.get("hora") or ""
            if not hour or not agent.get("tarea") or agent.get("ultima") == today:
                continue
            days = when.get("dias") or list(range(7))
            h, m = (int(x) for x in hour.split(":"))
            if now.weekday() in days and (now.hour, now.minute) >= (h, m):
                out.append(agent)
        return out

    def ran(self, agent: dict[str, Any], now: datetime.datetime) -> None:
        with self.lock:
            for a in self.mine:
                if a["nombre"] == agent["nombre"]:
                    a["ultima"] = now.date().isoformat()
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.mine, ensure_ascii=False, indent=1), encoding="utf-8")


CREATE = re.compile(r"^\s*(?:sergio,?\s*)?(?:crea|creame|hazme|haz|arma|configura)\s+(?:un|una|me un)?\s*agente\b\s*(?P<what>.*)$", re.I)
USE = re.compile(
    r"^\s*(?:sergio,?\s*)?(?:usa|que|pidele a|dile a|pon a)\s+(?:el\s+|la\s+|al\s+)?agente\s+(?P<name>[\w áéíóúñ]+?)"
    r"\s*(?:para|que|a)\s+(?P<task>.+)$",
    re.I,
)
REMOVE = re.compile(r"\b(?:borra|elimina|quita)\s+(?:el\s+)?agente\s+(?P<name>.+)$", re.I)
SHOW = re.compile(r"\b(mis agentes|lista de agentes|que agentes tengo|qu[eé] agentes tienes|abre (los )?agentes)\b", re.I)


def parse(text: str, agents: Agents | None = None) -> tuple[str, str, str] | None:
    """('create', description, '') | ('use', agent, task) | ('remove', name, '') | ('show', '', '')."""
    t = text.strip().rstrip(".")
    if SHOW.search(plain(t)):
        return "show", "", ""
    found = CREATE.match(t)
    if found and found.group("what").strip():
        return "create", found.group("what").strip(" ,:"), ""
    found = USE.match(t)
    if found:
        return "use", found.group("name").strip(), found.group("task").strip()
    found = REMOVE.search(t)
    if found:
        return "remove", found.group("name").strip(), ""
    if agents is not None:  # «Investigador, compara las RTX…»
        head, sep, rest = t.partition(",")
        if sep and rest.strip() and agents.find(head.strip()) is not None and len(head.split()) <= 3:
            return "use", head.strip(), rest.strip()
    return None


def describe(agent: dict[str, Any]) -> str:
    when = agent.get("horario") or {}
    names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    schedule = ""
    if when.get("hora"):
        days = when.get("dias") or []
        which = "todos los días" if not days or len(days) == 7 else ", ".join(names[d] for d in days)
        schedule = f" Se ejecuta {which} a las {when['hora']}."
    return f"{agent['nombre']}: {agent.get('rol', '')}{schedule}"


__all__ = ["PRO", "Agents", "describe", "parse", "plain"]
