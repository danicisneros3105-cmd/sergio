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
from pydantic import BaseModel

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
- tamano_cm: su medida real más grande en centímetros (estimada por lo que \
es y por lo que hay alrededor; una taza ~10, un celular ~15, una silla ~95),
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
        try:
            size_cm = float(item.get("tamano_cm") or item.get("tamaño_cm") or 0) or None
        except (TypeError, ValueError):
            size_cm = None
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
                "size_cm": size_cm,
            }
        )
    return out


def _inside(face: list[float], box: list[float]) -> bool:
    cx, cy = face[0] + face[2] / 2, face[1] + face[3] / 2
    return box[0] <= cx <= box[0] + box[2] and box[1] <= cy <= box[1] + box[3]


SPATIAL_MODELS = ("gemini-robotics-er-2-preview",)


def scene(image: bytes, limit: int = 12, lite: bool = False) -> dict[str, Any]:
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
    prompt = SCENE_PROMPT.format(limit=limit, people=people)
    reply = ""
    if not lite:
        # Google's spatial specialist first: in a measured test scene its
        # distances were within ~3 cm; the general models are the backup.
        from openjarvis.tools.vision_look import GEMINI_VISION_MODELS, _gemini

        try:
            reply = _gemini(image, prompt, "image/jpeg", SPATIAL_MODELS + GEMINI_VISION_MODELS)
        except Exception:  # noqa: BLE001 — the usual chain below
            reply = ""
    items = parse_scene(reply or ask_image(image, prompt, lite=lite))
    for item in items:
        if item["kind"] != "persona":
            continue
        for face in faces:
            if _inside(face["box"], item["box"]):
                item["name"] = face["name"] or ""
                item["guest"] = face["guest"] or 0
                item["face_box"] = face["box"]  # the best ruler for depth
                break
    # Where things are and how far apart (and a size check on every name).
    from openjarvis.tools.spatial import describe_relations, locate, relations

    try:
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        height, width = frame.shape[:2]
    except Exception:  # noqa: BLE001
        width, height = 1280, 720
    items = locate(items, width, height)
    pairs = relations(items)
    return {"items": items, "faces": faces, "relations": pairs, "distances": describe_relations(pairs)}


@router.post("/scene")
async def scene_route(
    image: UploadFile = File(...), auto: bool = Form(False)
) -> dict[str, Any]:
    """Camera "Analizar": people, animals and objects with boxes and details.

    *auto*: the camera naming new objects by itself (Flash-Lite first).
    """
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        return await asyncio.to_thread(scene, data, 12, auto)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


NAME_PROMPT = """Esta es una foto de cerca tomada por la cámara de Sergio. \
¿Qué es exactamente el objeto principal (el del centro; si alguien sostiene \
algo en la mano, ese)? Da el nombre concreto y común en español, como lo \
diría una persona: "labial", "bolígrafo", "llave", "control del televisor", \
"celular", "botella de agua", "cubo de Rubik". Nunca "objeto" ni categorías \
vagas. Si no estás seguro, el más probable.
Responde SOLO JSON: {"etiqueta": "...", "detalle": "color, marca o material \
visible en hasta 5 palabras", "seguridad": 0.0-1.0}"""


def parse_name(text: str) -> dict[str, Any]:
    found = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(found.group(0)) if found else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    label = " ".join(str(data.get("etiqueta") or data.get("label") or "").split())
    if label.lower() in ("objeto", "cosa", "elemento", "desconocido"):
        label = ""
    try:
        sure = max(0.0, min(1.0, float(data.get("seguridad") or 0.0)))
    except (TypeError, ValueError):
        sure = 0.0
    return {
        "label": label[:40],
        "detail": " ".join(str(data.get("detalle") or "").split())[:60],
        "confidence": sure,
    }


@router.post("/name")
async def name_route(image: UploadFile = File(...)) -> dict[str, Any]:
    """What one thing is, from a close-up (any object, not just 80 kinds)."""

    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        out = await asyncio.to_thread(name_by_vote, data)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not out["label"]:
        raise HTTPException(status_code=502, detail="No supe qué es.")
    return out


def _same(a: str, b: str) -> bool:
    """«labial rojo» ~ «Labial»: the same thing named twice."""
    import unicodedata

    def norm(x: str) -> set[str]:
        x = unicodedata.normalize("NFKD", x.lower())
        x = "".join(c for c in x if not unicodedata.combining(c))
        return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", x) if len(w) > 2}

    na, nb = norm(a), norm(b)
    return bool(na and nb and (na & nb))


def name_by_vote(image: bytes, ask: Any = None) -> dict[str, Any]:
    """What an object is, decided by two independent looks (a vote).

    Flash-Lite and Flash look at the same photo at the same time; if they
    agree the answer is sure. If they disagree, a third look (Flash, a
    different prompt order) breaks the tie; if nobody agrees, the most
    confident answer is kept but marked unsure, so Sergio says «parece…»
    instead of stating a guess as a fact.
    """
    from concurrent.futures import ThreadPoolExecutor

    from openjarvis.tools.vision_look import GEMINI_LITE_VISION_MODELS, GEMINI_VISION_MODELS, _gemini

    ask = ask or (lambda img, prompt, models: _gemini(img, prompt, "image/jpeg", models))
    looks: list[dict[str, Any]] = []
    with ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(ask, image, NAME_PROMPT, models) for models in (GEMINI_LITE_VISION_MODELS, GEMINI_VISION_MODELS)]
        for job in jobs:
            try:
                looks.append(parse_name(job.result(timeout=25)))
            except Exception:  # noqa: BLE001 — one look failed: the other counts
                continue
    looks = [x for x in looks if x["label"]]
    if not looks:
        raise RuntimeError("Ningún modelo con visión respondió.")
    if len(looks) == 2 and not _same(looks[0]["label"], looks[1]["label"]):
        try:
            third = parse_name(ask(image, NAME_PROMPT + "\nMira con atención la forma y el tamaño real.", GEMINI_VISION_MODELS[1:]))
            if third["label"]:
                looks.append(third)
        except Exception:  # noqa: BLE001 — no tie-breaker: the confidence decides
            pass
    best, votes = looks[0], 1
    for candidate in looks:
        agree = sum(_same(candidate["label"], other["label"]) for other in looks)
        if agree > votes or (agree == votes and candidate["confidence"] > best["confidence"]):
            best, votes = candidate, agree
    out = dict(best)
    out["votes"] = f"{votes}/{len(looks)}"
    out["unsure"] = votes < 2
    if votes >= 2:
        out["confidence"] = max(out["confidence"], 0.85)
    else:
        out["confidence"] = min(out["confidence"], 0.55)
    return out


class VideoRequest(BaseModel):
    request: str


@router.post("/youtube")
async def youtube_route(req: VideoRequest) -> dict[str, Any]:
    """The YouTube video the user describes (thumbnails checked by Gemini)."""
    import httpx

    from openjarvis.tools.vision_look import ask_image
    from openjarvis.tools.youtube_pick import pick

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept-Language": "es-419,es;q=0.9"}

    def run() -> dict[str, Any]:
        with httpx.Client(timeout=15, headers=headers, follow_redirects=True) as http:
            return pick(req.request, http.get, lambda img, prompt: ask_image(img, prompt, lite=True))

    try:
        return await asyncio.to_thread(run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc


# -- using the computer for the user, step by step --------------------------------
OPERATOR_ACTIONS = (
    "click",
    "double_click",
    "right_click",
    "type",
    "key",
    "scroll",
    "open",
    "wait",
    "done",
    "ask",
    "fail",
)

OPERATOR_PROMPT = """You operate the user's Windows computer for them, one step at a \
time, like a careful person with the mouse and keyboard. The screenshot shows the \
screen they are using right now.

GOAL: {goal}
The user ALREADY CONFIRMED the final send / call / post: {confirmed}
Step {step} of at most {max_steps}. Screenshot size: {width}x{height} pixels.

What happened so far:
{history}

Elements found by Windows accessibility (id. type 'name' @x,y in screenshot pixels):
{elements}

Choose exactly ONE next action and reply with JSON only, no text around it:
{{"thought": "short: what you see and why this step",
  "action": one of {actions},
  "element": id of the element to act on, or null,
  "point": [y, x] normalized 0-1000 on the screenshot (the CENTER of the target), or null,
  "text": "text to type (action type)",
  "keys": "keys to press (action key), e.g. enter, ctrl+l, ctrl+enter, tab, esc",
  "amount": scroll clicks (action scroll, negative = down),
  "target": "web address or app name (action open)",
  "say": "very short phrase IN SPANISH telling the user what you are doing or asking"}}

Rules:
- Look closely. Prefer an element id that matches; otherwise give point.
- To write in a field, click it first unless it is clearly focused; then type.
- Use open for web addresses and apps (instant); keyboard shortcuts when faster.
- Goal reached and verified on screen -> done (say: what was done). Impossible \
(not found after trying another way) -> fail with the reason. The user must act \
(log in, solve a captcha, pick between options) -> ask.
- SAFETY: never type passwords, card numbers or verification codes. If the next \
step would SEND a message or email, PLACE a call, POST, BUY or DELETE and the user \
has NOT confirmed, stop with ask and, in say, read back exactly what will be sent \
and to whom, ending with "¿Lo envío?". If they confirmed, do it and then check it \
was sent.
- Never repeat the same failing action more than twice: try another way."""


def _png_size(image: bytes) -> tuple[int, int]:
    if image[:8] == b"\x89PNG\r\n\x1a\n" and len(image) >= 24:
        return int.from_bytes(image[16:20], "big"), int.from_bytes(image[20:24], "big")
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(image)) as im:
        return im.size


def parse_action(
    text: str, width: int, height: int, elements: list[dict[str, Any]]
) -> dict[str, Any]:
    """The model's step -> a safe, complete action (x, y in screenshot pixels)."""
    found = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(found.group(0)) if found else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    action = str(data.get("action") or "").strip().lower()
    if action not in OPERATOR_ACTIONS:
        return {"action": "fail", "say": "No entendí qué hacer en la pantalla.", "thought": text[:300]}
    out: dict[str, Any] = {
        "action": action,
        "thought": str(data.get("thought") or "")[:400],
        "say": str(data.get("say") or "")[:300],
        "text": str(data.get("text") or ""),
        "keys": str(data.get("keys") or "").strip().lower(),
        "target": str(data.get("target") or "").strip(),
        "x": None,
        "y": None,
    }
    try:
        out["amount"] = int(data.get("amount") or 0)
    except (TypeError, ValueError):
        out["amount"] = 0
    chosen = data.get("element")
    for el in elements:
        if chosen is not None and str(el.get("id")) == str(chosen):
            out["x"], out["y"] = int(el["x"]), int(el["y"])
            out["element"] = el.get("id")
            break
    point = data.get("point")
    if out["x"] is None and isinstance(point, (list, tuple)) and len(point) == 2:
        try:
            py, px = float(point[0]), float(point[1])
            out["x"] = round(min(max(px, 0), 1000) / 1000 * width)
            out["y"] = round(min(max(py, 0), 1000) / 1000 * height)
        except (TypeError, ValueError):
            pass
    if action in ("click", "double_click", "right_click") and out["x"] is None:
        return {**out, "action": "fail", "say": "No encontré dónde hacer clic."}
    return out


def next_action(
    image: bytes,
    goal: str,
    history: list[str],
    elements: list[dict[str, Any]],
    *,
    step: int = 1,
    max_steps: int = 20,
    confirmed: bool = False,
    ask: Any = None,
) -> dict[str, Any]:
    from openjarvis.tools.vision_look import ask_image

    width, height = _png_size(image)
    prompt = OPERATOR_PROMPT.format(
        goal=goal,
        confirmed="yes" if confirmed else "no",
        step=step,
        max_steps=max_steps,
        width=width,
        height=height,
        history="\n".join(f"- {h}" for h in history[-12:]) or "- (nothing yet)",
        elements=format_elements(elements),
        actions=" | ".join(OPERATOR_ACTIONS),
    )
    reply = (ask or ask_image)(image, prompt, mime="image/png")
    return parse_action(reply, width, height, elements)


@router.post("/act")
async def act_route(
    goal: str = Form(...),
    history: str = Form("[]"),
    elements: str = Form("[]"),
    step: int = Form(1),
    max_steps: int = Form(20),
    confirmed: bool = Form(False),
    image: UploadFile = File(...),
) -> dict[str, Any]:
    """One step of using the computer for the user (the companion acts it out)."""
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        done = json.loads(history)
        done = [str(h) for h in done] if isinstance(done, list) else []
        listed = json.loads(elements)
        listed = listed if isinstance(listed, list) else []
    except ValueError:
        done, listed = [], []
    try:
        return await asyncio.to_thread(
            next_action,
            data,
            goal,
            done,
            listed,
            step=step,
            max_steps=max_steps,
            confirmed=confirmed,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/blender")
async def blender_route(
    save_path: str = Form(...),
    note: str = Form(""),
    image: UploadFile = File(...),
    preview_path: str = Form(""),
    pro: bool = Form(False),
) -> dict[str, Any]:
    """The object in the user's hands -> a detailed, checked Blender script.

    *pro*: Blender Pro's way — a blueprint sheet of the same object is drawn
    first and the script is written from the photo plus the sheet."""
    from openjarvis.tools.blender_model import model_object

    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    if not save_path.lower().endswith(".blend"):
        raise HTTPException(status_code=400, detail="save_path must end in .blend")
    if pro:
        from openjarvis.tools.blender_pro import from_photo

        try:
            return await asyncio.to_thread(from_photo, data, save_path, note, preview_path)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    try:
        return await asyncio.to_thread(
            model_object, data, save_path, note, image.content_type or "image/jpeg", None, 2, preview_path
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/video_plan")
async def video_plan_route(
    request: str = Form(...),
    lengths: str = Form(...),
    sheets: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Video Pro: Gemini watches the contact sheets and plans the edit."""
    from openjarvis.tools.video_pro import plan

    try:
        lens = [float(x) for x in json.loads(lengths)]
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="lengths must be a JSON list") from exc
    images = [await f.read(MAX_IMAGE_BYTES + 1) for f in sheets]
    try:
        return await asyncio.to_thread(plan, request, images, lens)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc


class BlenderTask(BaseModel):
    request: str
    save_path: str
    preview_path: str = ""


class HoloRequest(BaseModel):
    request: str


@router.post("/holo_model")
async def holo_model_route(req: HoloRequest) -> dict[str, Any]:
    """A hologram of anything: its real parts, designed by Gemini."""
    from openjarvis.tools.holo_model import design

    try:
        return await asyncio.to_thread(design, req.request)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc


@router.post("/blender/text")
async def blender_text_route(task: BlenderTask) -> dict[str, Any]:
    """Any Blender job in words -> a checked script (Blender Pro)."""
    from openjarvis.tools.blender_pro import from_text

    if not task.save_path.lower().endswith(".blend"):
        raise HTTPException(status_code=400, detail="save_path must end in .blend")
    try:
        def run() -> dict[str, Any]:
            from concurrent.futures import ThreadPoolExecutor

            from openjarvis.tools.blender_pro import reference_sheet

            def designed() -> str:
                if "distribución de piezas" in task.request:  # already seeded
                    return ""
                try:
                    from openjarvis.tools.holo_model import design, recipe_brief

                    return recipe_brief(design(task.request))
                except Exception:  # noqa: BLE001 — without the parts, as before
                    return ""

            # The parts list and the blueprint sheet at the same time.
            with ThreadPoolExecutor(2) as pool:
                parts = pool.submit(designed)
                sheet = pool.submit(reference_sheet, task.request)
                return from_text(
                    task.request, task.save_path, task.preview_path,
                    parts=parts.result(), sheet=sheet.result(),
                )

        return await asyncio.to_thread(run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc


@router.post("/blender/refine")
async def blender_refine_route(
    request: str = Form(...),
    raw_script: str = Form(...),
    save_path: str = Form(...),
    log: str = Form(""),
    preview_path: str = Form(""),
    preview: UploadFile = File(...),
    reference: UploadFile | None = File(None),
    sheet: UploadFile | None = File(None),
    target_cm: str = Form(""),
) -> dict[str, Any]:
    """Blender Pro's review round: look at the four views, fix the script."""
    from openjarvis.tools.blender_pro import refine

    shot = await preview.read(MAX_IMAGE_BYTES + 1)
    ref = await reference.read(MAX_IMAGE_BYTES + 1) if reference is not None else b""
    board = await sheet.read(MAX_IMAGE_BYTES + 1) if sheet is not None else b""
    try:
        target = [float(v) for v in json.loads(target_cm)] if target_cm else None
    except (ValueError, TypeError):
        target = None
    try:
        return await asyncio.to_thread(
            refine, request, raw_script, log, shot, save_path, preview_path, ref, None, target, board
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc


__all__ = [
    "OPERATOR_ACTIONS",
    "format_elements",
    "next_action",
    "parse_action",
    "parse_reply",
    "parse_scene",
    "router",
    "scene",
    "screen_help",
]
