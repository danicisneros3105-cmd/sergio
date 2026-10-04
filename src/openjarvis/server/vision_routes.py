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


SCENE_PROMPT = """Eres los ojos de Sergio. Detecta en esta foto de la cámara \
hasta {limit} elementos: TODAS las personas y animales, y los objetos que \
destaquen (lo que alguien sostiene primero).
Para cada uno da:
- box_2d: [ymin, xmin, ymax, xmax] normalizado de 0 a 1000,
- etiqueta: el nombre concreto en español ("persona", "perro", "taza", \
"celular", "guitarra"); nunca "objeto" ni "animal",
- tipo: "persona", "animal" u "objeto",
- especie: para seres vivos ("humano", "perro", "gato", "loro"...), si no "",
- detalle: hasta 6 palabras. Personas: si parece hombre o mujer, edad \
aproximada y algo visible ("hombre, unos 25 años, suéter gris"). Animales: \
raza o color. Objetos: color, material o marca visible.
{people}Responde SOLO con una lista JSON de objetos, sin texto alrededor."""


def parse_scene(text: str) -> list[dict[str, Any]]:
    """Gemini's detections -> [{box: [x, y, w, h] 0..1, label, kind, ...}]."""
    found = re.search(r"\[.*\]", text, re.S)
    try:
        items = json.loads(found.group(0)) if found else []
    except ValueError:
        items = []
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        box = item.get("box_2d") or item.get("box")
        try:
            ymin, xmin, ymax, xmax = (float(v) / 1000.0 for v in box)
        except (TypeError, ValueError):
            continue
        xmin, xmax = sorted((max(0.0, xmin), min(1.0, xmax)))
        ymin, ymax = sorted((max(0.0, ymin), min(1.0, ymax)))
        if xmax - xmin < 0.01 or ymax - ymin < 0.01:
            continue
        kind = str(item.get("tipo") or item.get("kind") or "objeto").lower()
        label = str(item.get("etiqueta") or item.get("label") or "").strip()
        detail = str(item.get("detalle") or item.get("detail") or "").strip()
        species = str(item.get("especie") or "").strip()
        if label.lower() in ("", "objeto", "animal", "cosa", "elemento"):
            # A vague label: name it by its species or its description.
            label = species or (detail.split()[0] if detail else label or kind)
        out.append(
            {
                "box": [xmin, ymin, xmax - xmin, ymax - ymin],
                "label": label[:40],
                "kind": kind if kind in ("persona", "animal", "objeto") else "objeto",
                "species": species[:30],
                "detail": detail[:80],
            }
        )
    return out


def _inside(face: list[float], box: list[float]) -> bool:
    cx, cy = face[0] + face[2] / 2, face[1] + face[3] / 2
    return box[0] <= cx <= box[0] + box[2] and box[1] <= cy <= box[1] + box[3]


def scene(image: bytes, limit: int = 12) -> dict[str, Any]:
    """Everything in a camera photo, with boxes, species and known names."""
    from openjarvis.tools.vision_look import ask_image

    faces: list[dict[str, Any]] = []
    try:
        import cv2
        import numpy as np

        from openjarvis.faces.routes import _get_book

        frame = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        height, width = frame.shape[:2]
        for match in _get_book().identify(image):
            x, y, w, h = match.box
            faces.append(
                {
                    "name": match.name,
                    "guest": match.guest,
                    "score": round(match.score, 3),
                    "box": [x / width, y / height, w / width, h / height],
                }
            )
    except Exception:  # noqa: BLE001 — names are a bonus
        faces = []
    known = [f["name"] for f in faces if f["name"]]
    people = (
        f"(Reconocidos por su cara: {', '.join(known)}. No inventes otros "
        "nombres.)\n"
        if known
        else ""
    )
    items = parse_scene(ask_image(image, SCENE_PROMPT.format(limit=limit, people=people)))
    for item in items:
        if item["kind"] != "persona":
            continue
        for face in faces:
            if _inside(face["box"], item["box"]):
                item["name"] = face["name"] or ""
                item["guest"] = face["guest"] or 0
                break
    return {"items": items, "faces": faces}


@router.post("/scene")
async def scene_route(image: UploadFile = File(...)) -> dict[str, Any]:
    """Camera "Analizar": people, animals and objects with boxes and details."""
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        return await asyncio.to_thread(scene, data)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = [
    "format_elements",
    "parse_reply",
    "parse_scene",
    "router",
    "scene",
    "screen_help",
]
