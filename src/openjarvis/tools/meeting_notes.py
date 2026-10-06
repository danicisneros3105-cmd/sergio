"""Minutes of a meeting, a video call or a conversation, written by Gemini.

The companion records the room (microphone) and the call (what the computer
plays), works out who spoke when from the voiceprints it knows, and sends
the mixed audio plus that timeline here. Gemini listens to the audio and
writes the transcript with the speakers' names, the summary, decisions,
tasks and open questions, as JSON; :func:`to_markdown` turns it into the
minutes the companion saves.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)
INLINE_MAX = 18 * 1024 * 1024  # bigger audio goes through the Files API

PROMPT = """\
Eres el secretario de actas de {owner}. Te paso el audio de {what} (en \
español; puede haber partes en inglés) y una línea de tiempo de QUIÉN HABLA en \
cada tramo, sacada de las huellas de voz: los nombres son fiables; "Persona 1", \
"Persona 2"... son voces distintas que no se conocen; "(videollamada)" son los \
participantes remotos. {owner_line}

Línea de tiempo (mm:ss):
{timeline}

Escucha el audio completo y devuelve SOLO un JSON con esta forma:
{{"titulo": "título corto y concreto",
 "resumen": "5 a 8 frases claras: de qué se habló y a qué se llegó",
 "puntos_clave": ["..."],
 "decisiones": ["..."],
 "tareas": [{{"quien": "nombre", "que": "qué debe hacer", "cuando": "plazo o ''"}}],
 "preguntas_abiertas": ["..."],
 "transcripcion": [{{"t": "mm:ss", "quien": "nombre", "texto": "lo que dijo, literal"}}]}}
Reglas: en "quien" usa los nombres de la línea de tiempo (no inventes otros; \
si alguien se presenta con su nombre dentro de la conversación, puedes \
añadirlo entre paréntesis, p. ej. "Persona 1 (Carlos)"). La transcripción \
completa y literal, sin inventar nada; lo que no se entienda, [inaudible]. \
Listas vacías si no hubo decisiones o tareas.
"""


def _key() -> str:
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY (sergio nube configurar --gemini …)")
    return key


def parse_minutes(text: str) -> dict[str, Any]:
    """Gemini's JSON (maybe inside ``` fences) -> the minutes, checked."""
    raw = text.strip()
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("Gemini no devolvió el acta en JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict) or not str(data.get("resumen") or "").strip():
        raise ValueError("Acta sin resumen")
    for key in ("puntos_clave", "decisiones", "preguntas_abiertas", "tareas", "transcripcion"):
        if not isinstance(data.get(key), list):
            data[key] = []
    data["titulo"] = str(data.get("titulo") or "Reunión").strip()[:120]
    return data


def to_markdown(data: dict[str, Any], *, when: str = "", seconds: float = 0.0, speakers: list[str] | None = None) -> str:
    """The minutes as a Markdown document."""
    lines = [f"# {data.get('titulo') or 'Reunión'}", ""]
    meta = []
    if when:
        meta.append(when)
    if seconds:
        meta.append(f"{int(seconds // 60)} min {int(seconds % 60)} s")
    if speakers:
        meta.append("Participantes: " + ", ".join(speakers))
    if meta:
        lines += ["_" + " · ".join(meta) + "_", ""]
    lines += ["## Resumen", "", str(data.get("resumen") or "").strip(), ""]

    def section(title: str, items: list[Any]) -> None:
        if items:
            lines.extend([f"## {title}", ""] + [f"- {str(i).strip()}" for i in items] + [""])

    section("Puntos clave", data.get("puntos_clave") or [])
    section("Decisiones", data.get("decisiones") or [])
    tasks = data.get("tareas") or []
    if tasks:
        lines += ["## Tareas", "", "| Quién | Qué | Cuándo |", "|---|---|---|"]
        for t in tasks:
            if isinstance(t, dict):
                cells = [str(t.get(k) or "").replace("|", "/").strip() for k in ("quien", "que", "cuando")]
                lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    section("Preguntas abiertas", data.get("preguntas_abiertas") or [])
    transcript = data.get("transcripcion") or []
    if transcript:
        lines += ["## Transcripción", ""]
        for row in transcript:
            if isinstance(row, dict):
                lines.append(f"**[{row.get('t', '')}] {row.get('quien', '')}:** {str(row.get('texto') or '').strip()}  ")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def summarize(
    audio: bytes,
    mime: str,
    timeline: str,
    *,
    owner: str = "",
    kind: str = "reunión",
    client: Any = None,
    types: Any = None,
) -> dict[str, Any]:
    """Audio + who-spoke-when -> the minutes (dict), trying several models."""
    if types is None:
        from google.genai import types
    if client is None:
        from google import genai

        client = genai.Client(api_key=_key())
    what = {
        "reunión": "una reunión",
        "videollamada": "una videollamada",
        "conversación": "una conversación",
    }.get(kind, "una reunión")
    owner_line = (
        f"El dueño de Sergio es {owner}: en el acta llámalo por su nombre." if owner else ""
    )
    prompt = PROMPT.format(owner=owner or "el usuario", what=what, owner_line=owner_line, timeline=timeline or "(sin datos)")
    part: Any
    uploaded = None
    if len(audio) > INLINE_MAX:
        suffix = ".ogg" if "ogg" in mime else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio)
            path = Path(tmp.name)
        try:
            uploaded = client.files.upload(file=str(path), config={"mime_type": mime})
            for _ in range(60):  # the file is processed before it can be used
                state = str(getattr(getattr(uploaded, "state", None), "name", "") or getattr(uploaded, "state", ""))
                if "PROCESSING" not in state.upper():
                    break
                time.sleep(2)
                uploaded = client.files.get(name=uploaded.name)
        finally:
            path.unlink(missing_ok=True)
        part = uploaded
    else:
        part = types.Part.from_bytes(data=audio, mime_type=mime)
    errors = []
    for model in MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[part, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=60000,
                ),
            )
            return parse_minutes(str(resp.text or ""))
        except Exception as exc:  # noqa: BLE001 — the next model
            errors.append(f"{model}: {str(exc)[:120]}")
    raise RuntimeError("No pude escribir el acta: " + " | ".join(errors[-3:]))


__all__ = ["MODELS", "PROMPT", "parse_minutes", "summarize", "to_markdown"]
