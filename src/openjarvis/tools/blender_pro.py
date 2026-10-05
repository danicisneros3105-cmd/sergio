"""Blender Pro: a senior 3D artist that checks its own work.

One shot is not professional work. Here Gemini (3.1 Pro first) writes the
scene, Blender renders a quick preview on the laptop, and Gemini *looks at
the render* (next to the reference photo, if there is one) and at Blender's
error log, lists what is wrong and rewrites the script. Two or three rounds
make models with the right proportions, parts and materials, and scripts
that actually run.

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
- Do NOT add cameras, lights, render settings or save the file (Sergio does).
- Blender 4.x API (common mistakes): Principled BSDF inputs are "Base Color",
  "Metallic", "Roughness", "IOR", "Alpha", "Transmission Weight", "Emission Color",
  "Emission Strength", "Subsurface Weight", "Coat Weight", "Specular IOR Level"
  (there is NO "Transmission", "Emission" or "Specular" input); the colour ramp
  node is "ShaderNodeValToRGB"; set material.use_nodes = True before using nodes;
  link materials with obj.data.materials.append(mat); prefer bmesh or
  bpy.ops.mesh.primitive_* then edit; apply rotation/scale where it matters.
Answer ONLY with JSON:
{"name": "short Spanish name", "description": "one Spanish sentence", \
"dimensions_cm": [width, depth, height], "parts": number of parts, \
"script": "the complete Python script"}"""

TEXT_PROMPT = (
    "You are a senior 3D artist and Blender technical director. Build exactly "
    "what the user asks, in Blender 4.x with Python (bpy), with production "
    "detail.\nThe user asks (Spanish): «{request}»\n" + RULES
)

REVIEW_PROMPT = (
    "You are a senior Blender technical director reviewing your own work.\n"
    "Request: «{request}»\n{reference}"
    "Attached: the quick render of your current scene.\n"
    "Blender's log (errors matter most):\n{log}\n"
    "First list to yourself what is wrong or missing versus the request "
    "(errors, proportions, missing parts, materials, scale, placement). Then "
    "rewrite the COMPLETE script fixing all of it. Keep what was right.\n"
    "Your current script:\n```python\n{script}\n```\n" + RULES
)


def _ask_gemini(images: list[tuple[bytes, str]], prompt: str) -> str:
    """Gemini Pro first (thinking high), the Flash models as backup."""
    import os

    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs
    from openjarvis.engine.google_client import SwitchingClient

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY (sergio nube configurar --gemini …)")
    client = SwitchingClient(key)
    parts = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images if data]
    errors: list[str] = []
    for model in MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[*parts, prompt],
                config=types.GenerateContentConfig(
                    **google_config_kwargs(model, 0.4, 32000, "high"),
                    response_mime_type="application/json",
                ),
            )
            text = str(resp.text or "").strip()
            parse_model(text)
            return text
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {str(exc)[:120]}")
    raise RuntimeError("Gemini no pudo hacer el trabajo de Blender: " + " | ".join(errors))


Ask = Callable[[list[tuple[bytes, str]], str], str]


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


def from_text(request: str, save_path: str, preview_path: str = "", ask: Ask | None = None) -> dict[str, Any]:
    """Any Blender job said in words -> a checked script (with preview render)."""
    ask = ask or _ask_gemini
    prompt = TEXT_PROMPT.replace("{request}", request)
    model = _checked(ask([], prompt), ask, [], prompt)
    model["raw_script"] = model["script"]
    model["script"] = finish_script(model["script"], save_path, model["name"], preview_path)
    return model


def refine(
    request: str,
    raw_script: str,
    log: str,
    preview: bytes,
    save_path: str,
    preview_path: str = "",
    reference: bytes = b"",
    ask: Ask | None = None,
) -> dict[str, Any]:
    """One review round: look at the render (and the reference), fix the script."""
    ask = ask or _ask_gemini
    prompt = (
        REVIEW_PROMPT.replace("{request}", request)
        .replace("{reference}", "The FIRST attached image is the reference photo of the real object.\n" if reference else "")
        .replace("{log}", (log or "(no errors)")[-3000:])
        .replace("{script}", raw_script[:24000])
    )
    images = [(reference, "image/jpeg"), (preview, "image/png")] if reference else [(preview, "image/png")]
    model = _checked(ask(images, prompt), ask, images, prompt)
    model["raw_script"] = model["script"]
    model["script"] = finish_script(model["script"], save_path, model["name"], preview_path)
    return model


def blender_failed(log: str) -> bool:
    """Did Blender stop on an error before saving?"""
    return "SERGIO_SAVED" not in log or "Traceback" in log.split("SERGIO_SAVED")[0]


__all__ = ["blender_failed", "from_text", "refine"]
