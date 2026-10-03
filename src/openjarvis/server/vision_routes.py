"""Screen help, Clicky-style: look at the user's screen and point at things.

The cursor companion sends a screenshot plus the numbered list of buttons,
fields and links it found (Windows accessibility). A vision model answers the
question out loud and says which element (or which spot) to point at; the
companion then flies there and highlights it.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/v1/vision", tags=["vision"])

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_ELEMENTS = 150

SCREEN_PROMPT = """Eres Sergio, un compañero que vive junto al cursor del usuario \
y le enseña a usar lo que tiene en pantalla, como un amigo paciente que mira por \
encima de su hombro (al estilo de Clicky).
Mira la captura y responde a lo que dijo, en español hablado: cálido, casual y \
breve (1 o 2 frases; más solo si lo pide). Escribe para el oído, no para la vista: \
sin listas, sin markdown, sin emojis, sin leer rutas ni URLs largas. Si le estás \
enseñando algo, di el siguiente paso concreto ("pulsa Exportar, aquí arriba"). \
Cuando ayude, señala el lugar exacto: él verá volar el cursor hasta ahí.

Elementos de la pantalla que puedes señalar (id. tipo 'nombre' @x,y en píxeles de \
la captura):
{elements}

Lo que dijo: {question}

Responde SOLO con JSON, sin texto alrededor:
{{"answer": "lo que dirás en voz alta",
  "element": id del elemento a señalar o null,
  "x": píxel x en la captura si no hay elemento adecuado (o null),
  "y": píxel y en la captura (o null),
  "label": "nombre corto de lo que señalas (o vacío)"}}"""


def format_elements(elements: list[dict[str, Any]]) -> str:
    lines = []
    for el in elements[:MAX_ELEMENTS]:
        name = str(el.get("name") or "(sin nombre)")[:60]
        lines.append(
            f"{el.get('id')}. {el.get('type')} '{name}' @{el.get('x')},{el.get('y')}"
        )
    return "\n".join(lines) or "(no se encontraron elementos; usa x,y)"


def parse_reply(text: str) -> dict[str, Any]:
    """The model's JSON (tolerating code fences or chatter); plain text if not."""
    found = re.search(r"\{.*\}", text, re.S)
    data: dict[str, Any] = {}
    if found:
        try:
            data = json.loads(found.group(0))
        except ValueError:
            data = {}
    if not isinstance(data, dict) or not data.get("answer"):
        return {
            "answer": text.strip(),
            "element": None,
            "x": None,
            "y": None,
            "label": "",
        }

    def _int(value: Any) -> int | None:
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None

    return {
        "answer": str(data["answer"]).strip(),
        "element": _int(data.get("element")),
        "x": _int(data.get("x")),
        "y": _int(data.get("y")),
        "label": str(data.get("label") or "")[:40],
    }


def screen_help(image: bytes, question: str, elements: list[dict[str, Any]]) -> dict:
    from openjarvis.tools.vision_look import ask_image

    prompt = SCREEN_PROMPT.format(
        elements=format_elements(elements), question=question or "¿Qué ves?"
    )
    return parse_reply(ask_image(image, prompt, mime="image/png"))


@router.post("/screen")
async def screen(
    question: str = Form(...),
    elements: str = Form("[]"),
    image: UploadFile = File(...),
) -> dict[str, Any]:
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        listed = json.loads(elements)
        listed = listed if isinstance(listed, list) else []
    except ValueError:
        listed = []
    try:
        return await asyncio.to_thread(screen_help, data, question, listed)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = ["format_elements", "parse_reply", "router", "screen_help"]
