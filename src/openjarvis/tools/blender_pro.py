"""Blender Pro: a senior 3D artist that checks its own work.

One shot is not professional work. Here Gemini (3.1 Pro first) writes the
scene, Blender renders a quick preview on the laptop, and Gemini *looks at
the render* (next to the reference photo, if there is one) and at Blender's
error log, lists what is wrong and rewrites the script. Two or three rounds
make models with the right proportions, parts and materials, and scripts
that actually run.

Before modelling, an image model draws a blueprint sheet of the object
(front, side, top and 3/4 views, like the reference boards 3D artists work
from), so the script writer and the reviewer see the shape from every side,
not only from a vague sentence or one photo. Each review looks at four
renders (the finished look plus orthographic front, side and top) and at
the real measurements Blender prints, so wrong proportions get caught.

Also for any Blender job said in words: "una casa low poly con techo rojo",
"un logo 3D de Sergio en metal", "una escena de escritorio con iluminación
de estudio".
"""

from __future__ import annotations

from typing import Any, Callable

from openjarvis.tools.blender_model import (
    MODELS,
    UnsafeScript,
    check_script,
    finish_script,
    parse_model,
)

RULES = """Rules for the script:
- Only bpy, bmesh, math, mathutils. No os, sys, subprocess, files, network or exec.
- Start from an empty scene: bpy.ops.wm.read_factory_settings(use_empty=True).
- Real-world scale in metres; the main model on the ground (lowest point z = 0),
  centred at the origin; every part a separate, well-named object, parented to
  one empty named after the model.
- Professional quality: clean topology, bevel modifiers on hard edges,
  subdivision surface on organic shapes, Principled BSDF materials (base
  colour, roughness, metallic, transmission for glass), procedural textures
  (noise, wave, voronoi) where real surfaces have texture.
- Real complexity: never one primitive standing in for the whole object. A
  phone has 20+ parts (body with bevelled edges, screen, bezel, camera bump,
  each lens with its ring, flash, buttons, port, speaker holes); a chair or a
  car 40+. Model every recognisable feature at its real size and place.
- Structure: small helpers (material, bevelled box, ...) and ONE FUNCTION PER
  PART or group of parts, called at the end. A function that fails is
  skipped and reported, so the rest of the model still gets built.
- Use the right technique for each shape, like a pro: lathe/spin (bmesh
  spin or a screw modifier on a profile) for round objects (bottles, lipstick,
  cups, lenses); curves with bevel depth for cables, handles and tubes;
  boolean DIFFERENCE for holes, ports and cut-outs; array modifiers for
  repeated features (keys, holes, slats); mirror for symmetric halves;
  solidify for shells; shade smooth (+ auto smooth / weighted normals) on
  curved parts.
- Materials never block geometry: make them in a helper that always returns
  a usable material (texture extras inside their own try), and parts work
  even if a material is missing.
- Check your numbers: every part's size and position in metres must match
  the real object and touch its neighbours (nothing floating or buried).
- Do NOT add cameras, lights, render settings or save the file (Sergio does).
- Blender 4.x / 5.x API (common mistakes): Principled BSDF inputs are "Base Color",
  "Metallic", "Roughness", "IOR", "Alpha", "Transmission Weight", "Emission Color",
  "Emission Strength", "Subsurface Weight", "Coat Weight", "Specular IOR Level"
  (there is NO "Transmission", "Emission" or "Specular" input); the colour ramp
  node is "ShaderNodeValToRGB"; set material.use_nodes = True before using nodes;
  node_tree belongs to the MATERIAL (mat.node_tree.nodes / .links), never to
  a node; link materials with obj.data.materials.append(mat); the Principled BSDF
  output socket is "BSDF" (not "Shader"); the wave texture has wave_type and
  bands_direction (no "direction"); primitive_*_add operators take size /
  radius / depth / location / rotation / scale only (no "enter_editmode" in
  calls you are unsure of); prefer bmesh or
  bpy.ops.mesh.primitive_* then edit; apply rotation/scale where it matters.
Answer ONLY with JSON:
{"name": "short Spanish name", "description": "one Spanish sentence", \
"dimensions_cm": [width, depth, height], "parts": number of parts, \
"script": "the complete Python script"}"""

TEXT_PROMPT = (
    "You are a senior 3D artist and Blender technical director. Build exactly "
    "what the user asks, in Blender with Python (bpy), with production "
    "detail.\nThe user asks (Spanish): «{request}»\n{images}" + RULES
)

SHEET_NOTE = (
    "Attached: a blueprint reference sheet of the object (front, side, top and "
    "3/4 views at the same scale). Match its silhouette, proportions and "
    "details from every side.\n"
)
PHOTO_NOTE = (
    "Attached: the PHOTO of the real object (first image){sheet}. Be true to "
    "the photo: its exact shape, colours, materials, labels and details.\n"
)

REVIEW_PROMPT = (
    "You are a senior Blender technical director reviewing your own work.\n"
    "Request: «{request}»\n{reference}"
    "Attached (last image): the review sheet of your current scene, 2 x 2: top "
    "left the finished look (3/4 view), top right FRONT, bottom left RIGHT "
    "side, bottom right TOP — the last three orthographic at the same scale.\n"
    "{target}"
    "Blender's log (errors matter most; SERGIO_STEP_ERROR lines are steps that "
    "failed and were SKIPPED, so those parts are missing from the render; "
    "SERGIO_DIMS is the model's real size, SERGIO_PARTS its pieces):\n{log}\n"
    "First list to yourself, view by view, what is wrong or missing versus the "
    "request and the reference (errors, silhouette, proportions, size versus "
    "the target, missing parts, floating or buried parts, materials). Then "
    "rewrite the COMPLETE script fixing all of it with targeted edits: keep "
    "every part and every line that works, never drop parts, and check each "
    "API call you change.\n"
    "Your current script:\n```python\n{script}\n```\n" + RULES
)


SHEET_PROMPT = (
    "Technical reference sheet for a 3D modeller: «{request}». Four views of "
    "the SAME object on a plain white background, in a 2 x 2 grid: top left a "
    "3/4 perspective view, top right the FRONT view, bottom left the RIGHT "
    "side view, bottom right the TOP view; the three flat views orthographic, "
    "aligned and at the same scale. Realistic proportions, materials and "
    "colours, every recognisable detail, soft even studio light, no shadows "
    "on the background, no text, no labels, no people."
)
PHOTO_SHEET_PROMPT = (
    "This photo shows a real object{note}. Make a technical reference sheet "
    "of EXACTLY this object (same shape, colours, materials, labels) for a 3D "
    "modeller: four views on a plain white background in a 2 x 2 grid — top "
    "left a 3/4 perspective view, top right FRONT, bottom left RIGHT side, "
    "bottom right TOP; the three flat views orthographic, aligned, same "
    "scale. Ignore the hands and the room. No text, no labels."
)
SHEET_MODELS = (
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
)


def _client() -> Any:
    import os

    from openjarvis.engine.google_client import SwitchingClient

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY (sergio nube configurar --gemini …)")
    return SwitchingClient(key)


def image_mime(data: bytes) -> str:
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def _ask_gemini(images: list[tuple[bytes, str]], prompt: str) -> str:
    """Gemini Pro first (thinking high), the Flash models as backup.

    Images are read at high resolution: small details (a lens ring, a
    button, a label) decide whether the model looks real."""
    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs

    client = _client()
    parts = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images if data]
    extra: dict[str, Any] = {}
    if parts:
        extra["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_HIGH
    errors: list[str] = []
    for model in MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[*parts, prompt],
                config=types.GenerateContentConfig(
                    **google_config_kwargs(model, 0.4, 32000, "high"),
                    response_mime_type="application/json",
                    **extra,
                ),
            )
            text = str(resp.text or "").strip()
            parse_model(text)
            return text
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {str(exc)[:120]}")
    raise RuntimeError("Gemini no pudo hacer el trabajo de Blender: " + " | ".join(errors))


def _draw_gemini(prompt: str, photo: bytes = b"") -> bytes:
    """One image from Gemini's image models (the first that answers)."""
    from google.genai import types

    client = _client()
    contents: list[Any] = [prompt]
    if photo:
        contents.insert(0, types.Part.from_bytes(data=photo, mime_type=image_mime(photo)))
    errors: list[str] = []
    for model in SHEET_MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio="1:1"),
                ),
            )
            for cand in resp.candidates or []:
                for part in (cand.content.parts if cand.content else None) or []:
                    data = getattr(part.inline_data, "data", None) if part.inline_data else None
                    if data:
                        return bytes(data)
            errors.append(f"{model}: sin imagen")
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {str(exc)[:100]}")
    raise RuntimeError("No pude dibujar la lámina de referencia: " + " | ".join(errors))


Ask = Callable[[list[tuple[bytes, str]], str], str]
Draw = Callable[[str, bytes], bytes]


def reference_sheet(request: str, photo: bytes = b"", draw: Draw | None = None) -> bytes:
    """The blueprint sheet (front, side, top, 3/4) the modeller works from.

    Empty bytes if no image model could draw it: modelling goes on without."""
    if photo:
        prompt = PHOTO_SHEET_PROMPT.replace("{note}", f" ({request})" if request.strip() else "")
    else:
        prompt = SHEET_PROMPT.replace("{request}", request)
    try:
        return (draw or _draw_gemini)(prompt, photo)
    except Exception:  # noqa: BLE001 — a bonus, not a requirement
        return b""


def _checked(text: str, ask: Ask, images: list[tuple[bytes, str]], prompt: str) -> dict[str, Any]:
    """A model whose script passed the safety check (asks again once)."""
    model = parse_model(text)
    try:
        check_script(model["script"])
        return model
    except UnsafeScript as exc:
        model = parse_model(ask(images, prompt + f"\nYour previous script was refused: {exc}. Fix it."))
        check_script(model["script"])
        return model


def _finish(model: dict[str, Any], save_path: str, preview_path: str, sheet: bytes) -> dict[str, Any]:
    model["raw_script"] = model["script"]
    model["script"] = finish_script(model["script"], save_path, model["name"], preview_path)
    if sheet:
        import base64

        model["reference_b64"] = base64.b64encode(sheet).decode("ascii")
    return model


def from_text(
    request: str,
    save_path: str,
    preview_path: str = "",
    ask: Ask | None = None,
    parts: str = "",
    sheet: bytes | None = None,
    draw: Draw | None = None,
) -> dict[str, Any]:
    """Any Blender job said in words -> a checked script (with preview render).

    *parts*: the object's parts already designed (holo_model), so the model
    starts from the real structure instead of a box. *sheet*: a blueprint
    sheet to model from (None: draw one; b"": go without)."""
    ask = ask or _ask_gemini
    if sheet is None:
        sheet = reference_sheet(request, draw=draw)
    images = [(sheet, image_mime(sheet))] if sheet else []
    prompt = TEXT_PROMPT.replace("{request}", request).replace("{images}", SHEET_NOTE if sheet else "")
    if parts:
        prompt += (
            "\nThe object's parts (real sizes, centred at the origin, y up in this list; "
            "convert to Blender's z up) — keep them all and add the real detail:\n" + parts
        )
    model = _checked(ask(images, prompt), ask, images, prompt)
    return _finish(model, save_path, preview_path, sheet)


def from_photo(
    photo: bytes,
    save_path: str,
    note: str = "",
    preview_path: str = "",
    ask: Ask | None = None,
    parts: str = "",
    sheet: bytes | None = None,
    draw: Draw | None = None,
) -> dict[str, Any]:
    """The object in a photo -> a checked script, modelled from the photo
    plus a blueprint sheet of the same object (its unseen sides too)."""
    ask = ask or _ask_gemini
    if sheet is None:
        sheet = reference_sheet(note, photo, draw=draw)
    images = [(photo, image_mime(photo))] + ([(sheet, image_mime(sheet))] if sheet else [])
    request = note.strip() or "el objeto de la foto (el que sostiene en la mano), ultra detallado"
    prompt = TEXT_PROMPT.replace("{request}", request).replace(
        "{images}",
        PHOTO_NOTE.replace("{sheet}", " and a blueprint sheet of it (front, side, top, 3/4)" if sheet else ""),
    )
    prompt += (
        "\nFirst identify the main object (the one held in the hands, else the most "
        "prominent) and estimate its real size from context (an adult hand is ~18 cm long)."
    )
    if parts:
        prompt += "\nIts parts as already measured from the photo (y up; convert to z up):\n" + parts
    model = _checked(ask(images, prompt), ask, images, prompt)
    return _finish(model, save_path, preview_path, sheet)


def refine(
    request: str,
    raw_script: str,
    log: str,
    preview: bytes,
    save_path: str,
    preview_path: str = "",
    reference: bytes = b"",
    ask: Ask | None = None,
    target_cm: list[float] | None = None,
    sheet: bytes = b"",
) -> dict[str, Any]:
    """One review round: look at the four views (and the references), fix the script."""
    ask = ask or _ask_gemini
    refs = []
    if reference:
        refs.append("the photo of the real object")
    if sheet:
        refs.append("the blueprint reference sheet (3/4, front, right, top)")
    target = ""
    if target_cm and len(target_cm) == 3:
        w, d, h = target_cm
        target = f"Target real size: {w} x {d} x {h} cm (width x depth x height).\n"
    prompt = (
        REVIEW_PROMPT.replace("{request}", request)
        .replace("{reference}", f"The first attached images are the references: {'; '.join(refs)}.\n" if refs else "")
        .replace("{target}", target)
        .replace("{log}", (log or "(no errors)")[-3000:])
        .replace("{script}", raw_script[:24000])
    )
    images = [(img, image_mime(img)) for img in (reference, sheet) if img]
    images.append((preview, image_mime(preview)))
    model = _checked(ask(images, prompt), ask, images, prompt)
    return _finish(model, save_path, preview_path, b"")


def step_errors(log: str) -> list[str]:
    """The steps that failed and were skipped (the model was still saved)."""
    return [line.strip() for line in log.splitlines() if line.startswith("SERGIO_STEP_ERROR")]


def blender_failed(log: str) -> bool:
    """Did Blender stop before saving? (failed steps alone do not count)"""
    return "SERGIO_SAVED" not in log


__all__ = ["blender_failed", "from_photo", "from_text", "reference_sheet", "refine"]
