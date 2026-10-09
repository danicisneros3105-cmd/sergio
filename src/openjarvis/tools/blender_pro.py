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

from openjarvis.tools.blender_kit import KIT_DOC
from openjarvis.tools.blender_model import (
    MODELS,
    UnsafeScript,
    check_script,
    finish_script,
    parse_model,
)

RULES_BODY = """Rules for the script:
- Only bpy, bmesh, math, mathutils. No os, sys, subprocess, files, network or exec.
- Start from an empty scene: bpy.ops.wm.read_factory_settings(use_empty=True).
- SPATIAL PLAN FIRST (think like a draughtsman before you model): right after
  the imports write SERGIO_LAYOUT = [{"part": "Asiento", "center_cm": [x, y, z],
  "size_cm": [width, depth, height]}, ...] using LITERAL numbers only (no
  variables: it runs before anything else) with every main part, in cm, Blender
  axes (x width left-right, y depth front-back with the front at -y, z up),
  origin at the centre of the model's base on the ground. Check the plan
  before modelling: each part rests on or attaches to another (bottom of one =
  top of the one below), symmetric parts mirror in x, nothing floats, nothing
  sinks under z = 0, sizes add up to the whole. Then build FROM these numbers
  and name each object starting with its "part" name (Pata_1, Pata_2 for
  "Pata"). Plan coordinates are WORLD positions of the assembled model, even
  for parented parts. For articulated or angled things (lamp arms, hinges,
  limbs) chain the joints like forward kinematics: keep each angle in a
  variable, compute the next joint = previous joint + length x (0, cos a,
  sin a) in metres, place every arm between its two joints, and keep every
  joint above the base (z > 0). Sergio measures what you built against this plan
  (SERGIO_LAYOUT_OFF, SERGIO_FLOATING, SERGIO_BELOW_GROUND in the log).
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
- Structure: ONE FUNCTION PER PART or group of parts, called at the end,
  built with the kit above. A function that fails is skipped and reported,
  so the rest of the model still gets built.
- Use the right technique for each shape, like a pro: kit_lathe for round
  objects (bottles, lipstick, cups, lenses, lampshades, wheels); kit_tube for
  cables, handles, bent arms and frames; kit_extrude for any flat part with a
  real outline (rounded phone bodies, brackets, logos); kit_cut for holes,
  ports and cut-outs; kit_copy / kit_array_circle / kit_mirror_x for repeated
  and symmetric features; kit_box only for truly boxy parts and always
  bevelled. A model that is a pile of plain cubes is WRONG: the silhouette
  must be recognisable.
- Repeated identical parts (legs, wheels, screws, keys): build one, then
  linked duplicates (dup = obj.copy(); keep dup.data shared; link dup to the
  collection), so they cost no extra memory; arrays or Geometry Nodes for
  hundreds of copies.
- Closed, clean meshes: no stray vertices, no faces inside faces, normals
  pointing out (Sergio checks it: SERGIO_TOPOLOGY in the log).
- Materials never block geometry: make them in a helper that always returns
  a usable material (texture extras inside their own try), and parts work
  even if a material is missing.
- Check your numbers: every part's size and position in metres must match
  the real object and touch its neighbours (nothing floating or buried).
- Do NOT add cameras, lights, render settings or save the file (Sergio does).
- Blender 4.x / 5.x API (common mistakes): Principled BSDF inputs are "Base Color",
  "Metallic", "Roughness", "IOR", "Alpha", "Transmission Weight", "Emission Color",
  "Emission Strength", "Subsurface Weight", "Coat Weight", "Specular IOR Level"
  (there is NO "Transmission", "Emission", "Specular" or "Clearcoat" input); the colour ramp
  node is "ShaderNodeValToRGB"; set material.use_nodes = True before using nodes;
  node_tree belongs to the MATERIAL (mat.node_tree.nodes / .links), never to
  a node; link materials with obj.data.materials.append(mat); the Principled BSDF
  output socket is "BSDF" (not "Shader"); the wave texture has wave_type and
  bands_direction (no "direction"); primitive_*_add operators take size /
  radius / depth / location / rotation / scale only (no "enter_editmode" in
  calls you are unsure of); prefer bmesh or
  bpy.ops.mesh.primitive_* then edit; apply rotation/scale where it matters,
  and note bpy.ops.object.transform_apply() applies LOCATION too by default:
  call transform_apply(location=False, rotation=False, scale=True) or the
  object's origin jumps to the world origin (copies then land twice as far);
  after moving or copying objects, bpy.context.view_layer.update() before
  reading matrix_world.
Answer ONLY with JSON:
{"name": "short Spanish name", "description": "one Spanish sentence", \
"dimensions_cm": [width, depth, height], "parts": number of parts, \
"script": "the complete Python script"}"""

RULES = KIT_DOC + "\n" + RULES_BODY

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
    "SERGIO_DIMS is the model's real size, SERGIO_PARTS its pieces, SERGIO_TOPOLOGY the mesh check: non-manifold edges and loose vertices are modelling errors to fix; "
    "SERGIO_LAYOUT_OFF / SERGIO_LAYOUT_MISSING compare your SERGIO_LAYOUT plan with the measured result, "
    "SERGIO_FLOATING / SERGIO_BELOW_GROUND are parts touching nothing or under the floor: fix each one by "
    "moving or resizing exactly by the numbers given, and update SERGIO_LAYOUT if the plan itself was "
    "wrong):\n{log}\n"
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
    parts = [
        types.Part.from_bytes(data=data, mime_type=mime)
        for data, mime in images
        if data
    ]
    extra: dict[str, Any] = {}
    if parts:
        extra["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_HIGH
    errors: list[str] = []
    for attempt in range(2):  # a second pass after a short quota pause
        errors = []
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
        if attempt == 0 and not _pause(errors):
            break
    raise RuntimeError(
        "Gemini no pudo hacer el trabajo de Blender: " + " | ".join(errors)
    )


def _pause(errors: list[str]) -> bool:
    """Wait out a short quota pause (all models "back in ~1 min"); True if waited."""
    import time

    from openjarvis.engine.google_client import short_wait

    wait = short_wait(errors)
    if wait:
        time.sleep(wait)
    return bool(wait)


def _draw_gemini(prompt: str, photo: bytes = b"") -> bytes:
    """One image from Gemini's image models (the first that answers)."""
    from google.genai import types

    client = _client()
    contents: list[Any] = [prompt]
    if photo:
        contents.insert(
            0, types.Part.from_bytes(data=photo, mime_type=image_mime(photo))
        )
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
                    data = (
                        getattr(part.inline_data, "data", None)
                        if part.inline_data
                        else None
                    )
                    if data:
                        return bytes(data)
            errors.append(f"{model}: sin imagen")
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {str(exc)[:100]}")
    raise RuntimeError("No pude dibujar la lámina de referencia: " + " | ".join(errors))


Ask = Callable[[list[tuple[bytes, str]], str], str]
Draw = Callable[[str, bytes], bytes]


def reference_sheet(
    request: str, photo: bytes = b"", draw: Draw | None = None
) -> bytes:
    """The blueprint sheet (front, side, top, 3/4) the modeller works from.

    Empty bytes if no image model could draw it: modelling goes on without."""
    if photo:
        prompt = PHOTO_SHEET_PROMPT.replace(
            "{note}", f" ({request})" if request.strip() else ""
        )
    else:
        prompt = SHEET_PROMPT.replace("{request}", request)
    try:
        return (draw or _draw_gemini)(prompt, photo)
    except Exception:  # noqa: BLE001 — a bonus, not a requirement
        return b""


def static_report(script: str) -> str:
    """Problems found without running Blender ("" = fine): safety, the
    spatial plan, and a model that is only a pile of plain cubes."""
    try:
        check_script(script)
    except UnsafeScript as exc:
        return f"refused by the safety check: {exc}"
    issues = []
    if "SERGIO_LAYOUT" not in script:
        issues.append("there is no SERGIO_LAYOUT spatial plan")
    cubes = script.count("primitive_cube_add")
    shaped = sum(
        script.count(f)
        for f in (
            "kit_lathe(",
            "kit_extrude(",
            "kit_tube(",
            "kit_cylinder(",
            "kit_sphere(",
            "kit_box(",
            "kit_text(",
            "bmesh.",
            "primitive_cylinder_add",
            "primitive_uv_sphere_add",
            "curves.new",
        )
    )
    if cubes >= 3 and shaped == 0:
        issues.append(
            f"the model is {cubes} plain cubes and nothing else: build each part with the kit "
            "(kit_lathe / kit_extrude / kit_tube, bevelled kit_box)"
        )
    return "; ".join(issues)


def _checked(
    text: str, ask: Ask, images: list[tuple[bytes, str]], prompt: str, topic: str = ""
) -> dict[str, Any]:
    """A model whose script passed the checks: self-correction loop
    (LangGraph) — a refused or careless script goes back with the reason,
    and what fixed it is remembered as a lesson."""
    from openjarvis.evolution.reflect import self_correct

    first = [text]

    def generate(_task: str, notes: list[str]) -> dict[str, Any]:
        raw = first.pop() if first else ask(images, prompt + "\n" + "\n".join(notes))
        try:
            return parse_model(raw)
        except Exception as exc:  # noqa: BLE001 — an unreadable answer is a failed attempt
            return {"error": f"the answer was not valid JSON with a script: {exc}"}

    def check(model: dict[str, Any]) -> tuple[bool, str]:
        if "error" in model:
            return False, model["error"]
        report = static_report(model["script"])
        return not report, report

    def remember(lesson: str) -> None:
        from openjarvis.evolution.memory import shared

        shared().remember("lesson", lesson)

    out = self_correct(
        topic or "Blender script",
        generate,
        check,
        reflect=lambda _t, _c, report: (
            f"Your previous script was refused: {report}. Fix it."
        ),
        max_rounds=3,
        remember=remember,
        topic=f"Blender «{topic[:60]}»",
    )
    model = out["result"] or {}
    if not out["ok"]:
        if "error" in model:
            raise RuntimeError(model["error"])
        check_script(
            model["script"]
        )  # unsafe is never returned; only softer issues are tolerated
    return model


def _lessons(request: str) -> str:
    from openjarvis.evolution.memory import lessons

    return lessons(request, ("lesson", "feedback", "blender"))


def _examples(request: str) -> str:
    """Worked examples (verified scripts) first: in-context training."""
    try:
        from openjarvis.tools.blender_examples import prompt_block

        return prompt_block(request)
    except Exception:  # noqa: BLE001 — a bonus, never a blocker
        return ""


def _finish(
    model: dict[str, Any], save_path: str, preview_path: str, sheet: bytes
) -> dict[str, Any]:
    model["raw_script"] = model["script"]
    model["script"] = finish_script(
        model["script"], save_path, model["name"], preview_path
    )
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
    version: str = "",
) -> dict[str, Any]:
    """Any Blender job said in words -> a checked script (with preview render).

    *parts*: the object's parts already designed (holo_model), so the model
    starts from the real structure instead of a box. *sheet*: a blueprint
    sheet to model from (None: draw one; b"": go without)."""
    ask = ask or _ask_gemini
    if sheet is None:
        sheet = reference_sheet(request, draw=draw)
    images = [(sheet, image_mime(sheet))] if sheet else []
    prompt = TEXT_PROMPT.replace("{request}", request).replace(
        "{images}", SHEET_NOTE if sheet else ""
    )
    prompt = _examples(request) + prompt
    if parts:
        prompt += (
            "\nThe object's parts (real sizes, centred at the origin, y up in this list; "
            "convert to Blender's z up) — keep them all and add the real detail:\n"
            + parts
        )
    prompt += version_note(version) + _lessons(request)
    model = _checked(ask(images, prompt), ask, images, prompt, request)
    return _finish(model, save_path, preview_path, sheet)


def version_note(version: str) -> str:
    """The user's Blender version, so only its API is used."""
    return (
        f"\nThe user's Blender is {version}: use only API that exists in Blender {version} "
        "(the kit functions work in all versions)."
        if version
        else ""
    )


def from_photo(
    photo: bytes,
    save_path: str,
    note: str = "",
    preview_path: str = "",
    ask: Ask | None = None,
    parts: str = "",
    sheet: bytes | None = None,
    draw: Draw | None = None,
    version: str = "",
) -> dict[str, Any]:
    """The object in a photo -> a checked script, modelled from the photo
    plus a blueprint sheet of the same object (its unseen sides too)."""
    ask = ask or _ask_gemini
    if sheet is None:
        sheet = reference_sheet(note, photo, draw=draw)
    images = [(photo, image_mime(photo))] + (
        [(sheet, image_mime(sheet))] if sheet else []
    )
    request = (
        note.strip()
        or "el objeto de la foto (el que sostiene en la mano), ultra detallado"
    )
    prompt = TEXT_PROMPT.replace("{request}", request).replace(
        "{images}",
        PHOTO_NOTE.replace(
            "{sheet}",
            " and a blueprint sheet of it (front, side, top, 3/4)" if sheet else "",
        ),
    )
    prompt = _examples(request) + prompt
    prompt += (
        "\nFirst identify the main object (the one held in the hands, else the most "
        "prominent) and estimate its real size from context (an adult hand is ~18 cm long)."
    )
    if parts:
        prompt += (
            "\nIts parts as already measured from the photo (y up; convert to z up):\n"
            + parts
        )
    prompt += version_note(version) + _lessons(request)
    model = _checked(ask(images, prompt), ask, images, prompt, request)
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
        .replace(
            "{reference}",
            f"The first attached images are the references: {'; '.join(refs)}.\n"
            if refs
            else "",
        )
        .replace("{target}", target)
        .replace(
            "{log}",
            (
                "\n".join(
                    ln
                    for ln in (log or "").splitlines()
                    if not ln.startswith("SERGIO_BBOX ")
                )
                or "(no errors)"
            )[-3500:],
        )
        .replace("{script}", raw_script[:24000])
    )
    images = [(img, image_mime(img)) for img in (reference, sheet) if img]
    images.append((preview, image_mime(preview)))
    model = _checked(ask(images, prompt), ask, images, prompt)
    return _finish(model, save_path, preview_path, b"")


VERIFY_PROMPT = (
    "You are a strict art director checking a 3D model before it reaches the "
    "client.\n{reference}"
    "Last image: the review sheet of the model, 2 x 2 — top left the finished "
    "look (3/4 view), then FRONT, RIGHT side and TOP, orthographic, same scale.\n"
    "STEP 1, blind: judging ONLY the shapes in the sheet (forget any request), "
    "what object would a stranger say this is? Write it in Spanish in looks_like.\n"
    "STEP 2: the request was «{request}». Is it clearly that object, at "
    "professional quality? Score 0-10: 10 = indistinguishable from a "
    "professional model of the request; 7 = clearly it, good detail; 5 = "
    "recognisable but crude; 3 or less = boxes or blobs, not recognisable, or "
    "a different object. Be harsh: plain cubes standing in for curved parts "
    "score 3 or less.\n"
    "List the concrete problems a modeller must fix (Spanish; name the part, "
    "what is wrong and by roughly how many cm), most important first, and what "
    "is already good.\n"
    'Answer ONLY JSON: {{"looks_like": "...", "is_it": true, "score": 0, '
    '"problems": ["..."], "good": ["..."]}}'
)
VISION_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
)


def parse_verdict(text: str) -> dict[str, Any]:
    """The art director's verdict, checked (score 0..10, short lists)."""
    import json
    import re

    found = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(found.group(0)) if found else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict) or "score" not in data:
        raise RuntimeError("La revisión visual no devolvió una nota.")
    try:
        score = max(0.0, min(10.0, float(data.get("score"))))
    except (TypeError, ValueError):
        score = 0.0

    def items(key: str) -> list[str]:
        raw = data.get(key) or []
        return (
            [" ".join(str(x).split())[:160] for x in raw if str(x).strip()][:8]
            if isinstance(raw, list)
            else []
        )

    return {
        "looks_like": " ".join(str(data.get("looks_like") or "").split())[:80],
        "is_it": bool(data.get("is_it")) and score >= 5,
        "score": round(score, 1),
        "problems": items("problems"),
        "good": items("good"),
    }


def _ask_vision(images: list[tuple[bytes, str]], prompt: str) -> str:
    """A quick look (Flash first): the vision check runs every round."""
    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs

    client = _client()
    parts = [
        types.Part.from_bytes(data=data, mime_type=mime)
        for data, mime in images
        if data
    ]
    errors: list[str] = []
    for attempt in range(2):  # a second pass after a short quota pause
        errors = []
        for model in VISION_MODELS:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[*parts, prompt],
                    config=types.GenerateContentConfig(
                        **google_config_kwargs(model, 0.2, 6000, "low"),
                        response_mime_type="application/json",
                        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
                    ),
                )
                text = str(resp.text or "")
                parse_verdict(text)
                return text
            except Exception as exc:  # noqa: BLE001 — next model
                errors.append(f"{model}: {str(exc)[:100]}")
        if attempt == 0 and not _pause(errors):
            break
    raise RuntimeError("La revisión visual no respondió: " + " | ".join(errors))


def verify(
    request: str,
    preview: bytes,
    reference: bytes = b"",
    sheet: bytes = b"",
    ask: Ask | None = None,
) -> dict[str, Any]:
    """The vision model checks the build: what it looks like (blind), whether
    it is what was asked, a 0-10 score and the problems to fix."""
    refs = []
    if reference:
        refs.append("the photo or image the model must reproduce")
    if sheet:
        refs.append("the blueprint reference sheet")
    note = f"First attached images: {'; '.join(refs)}.\n" if refs else ""
    prompt = (
        VERIFY_PROMPT.replace("{reference}", note)
        .replace("{request}", request)
        .replace("{{", "{")
        .replace("}}", "}")
    )
    images = [(img, image_mime(img)) for img in (reference, sheet) if img]
    images.append((preview, image_mime(preview)))
    return parse_verdict((ask or _ask_vision)(images, prompt))


def vision_note(verdict: dict[str, Any]) -> str:
    """The verdict as log lines the next review round reads."""
    lines = [
        f"SERGIO_VISION score {verdict['score']}/10; a stranger would say it is: «{verdict['looks_like']}»"
        + ("" if verdict["is_it"] else " — NOT recognisable as the request yet")
    ]
    lines += [f"SERGIO_VISION_FIX {p}" for p in verdict.get("problems", [])]
    return "\n".join(lines)


EDIT_PROMPT = (
    "You are a senior Blender technical director making a SURGICAL edit to a "
    "finished model.\nThe model: «{request}».\nThe edit (Spanish): «{instruction}»\n"
    "{reference}"
    "Attached (last image): the review sheet of the model as it is now.\n"
    "Change ONLY what the edit asks. Every other part keeps exactly the same "
    "code, numbers, names, position, size and material — Sergio measures every "
    "part before and after (SERGIO_BBOX) and any part you were not asked to "
    "touch that moves or changes is an error. If the edit needs a neighbour to "
    "adapt (a longer leg moves the foot), change that neighbour too and list it.\n"
    'Return the COMPLETE script with the edit applied, and in "changed" the '
    "object names (or name prefixes) you added, removed or modified.\n"
    "The current script:\n```python\n{script}\n```\n"
    "Same rules as before:\n"
    + RULES.replace(
        '"script": "the complete Python script"}',
        '"changed": ["object names"], "script": "the complete Python script"}',
    )
)


def edit(
    request: str,
    raw_script: str,
    instruction: str,
    preview: bytes,
    save_path: str,
    preview_path: str = "",
    reference: bytes = b"",
    ask: Ask | None = None,
    collateral: list[str] | None = None,
) -> dict[str, Any]:
    """A surgical edit: only what *instruction* asks changes. *collateral*:
    parts a previous attempt changed by mistake (they must go back)."""
    ask = ask or _ask_gemini
    prompt = (
        EDIT_PROMPT.replace("{request}", request)
        .replace("{instruction}", instruction)
        .replace(
            "{reference}",
            "First attached image: the reference image of the model.\n"
            if reference
            else "",
        )
        .replace("{script}", raw_script[:24000])
    )
    if collateral:
        prompt += (
            "\nYour previous attempt ALSO changed parts the edit did not ask for: "
            + ", ".join(collateral[:20])
            + ". Put them back exactly as in the script above."
        )
    images = [(img, image_mime(img)) for img in (reference,) if img]
    images.append((preview, image_mime(preview)))
    text = ask(images, prompt)
    model = _checked(text, ask, images, prompt)
    import json
    import re

    found = re.search(r"\{.*\}", text, re.S)
    try:
        changed = json.loads(found.group(0)).get("changed") if found else []
    except (ValueError, AttributeError):
        changed = []
    model["changed"] = [str(c)[:60] for c in (changed or []) if str(c).strip()][:40]
    model["instruction"] = instruction
    return _finish(model, save_path, preview_path, b"")


def bboxes(log: str) -> dict[str, tuple[float, ...]]:
    """Each part's measured box from the log: name -> (cx, cy, cz, sx, sy, sz) cm."""
    out: dict[str, tuple[float, ...]] = {}
    for line in log.splitlines():
        if not line.startswith("SERGIO_BBOX "):
            continue
        try:
            name, centre, size = line[len("SERGIO_BBOX ") :].split(" | ")
            out[name.strip()] = tuple(
                float(v) for v in (*centre.split(), *size.split())
            )
        except ValueError:
            continue
    return out


def surgical_report(
    before: str, after: str, changed: list[str], tol_cm: float = 0.3
) -> dict[str, Any]:
    """What an edit really touched: the parts it was allowed to change
    (*changed*, by name or prefix) and the collateral ones it should not have."""
    a, b = bboxes(before), bboxes(after)
    allowed = [c.lower() for c in changed]

    def ok(name: str) -> bool:
        low = name.lower()
        return any(
            low == c or low.startswith(c) or c.startswith(low.split("_")[0])
            for c in allowed
        )

    moved = [
        n for n in a if n in b and max(abs(x - y) for x, y in zip(a[n], b[n])) > tol_cm
    ]
    removed = [n for n in a if n not in b]
    added = [n for n in b if n not in a]
    collateral = [n for n in moved + removed if not ok(n)]
    return {
        "kept": sum(1 for n in a if n in b and n not in moved),
        "edited": [n for n in moved + removed + added if ok(n) or n in added],
        "moved": moved,
        "removed": removed,
        "added": added,
        "collateral": collateral,
    }


IMPORT_SCRIPT = """import bpy
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=__PATH__)
SERGIO_LAYOUT = []


def normalise():
    # Generated models come in any unit (pixels, metres, arbitrary): scaled
    # so the longest side is the size asked, centred, resting on the floor.
    bpy.context.view_layer.update()
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    k = __SIZE__ / max(max(hi - lo), 1e-6)
    roots = [o for o in bpy.context.scene.objects if o.parent is None]
    pivot = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for o in roots:
        o.location = (o.location - pivot) * k
        o.scale = o.scale * k
    print("SERGIO_IMPORTED %d meshes, scaled x%.4f to %.1f cm" % (len(meshes), k, __SIZE__ * 100))


normalise()
"""


def import_model(
    glb_path: str,
    save_path: str,
    preview_path: str = "",
    name: str = "Modelo",
    size_cm: float = 30.0,
) -> dict[str, Any]:
    """A generated model file (Tripo, SculptMate, Image-to-Mesh) through
    Sergio's ending: real size (*size_cm* on its longest side), grounded,
    lit, framed, checked, saved and rendered. Sergio's own import script, so
    it is not put through the model check."""
    import json

    raw = IMPORT_SCRIPT.replace("__PATH__", json.dumps(glb_path)).replace(
        "__SIZE__", f"{max(size_cm, 0.5) / 100:.4f}"
    )
    return {
        "name": name,
        "description": "",
        "dimensions_cm": [],
        "raw_script": raw,
        "script": finish_script(raw, save_path, name, preview_path),
    }


def step_errors(log: str) -> list[str]:
    """The steps that failed and were skipped (the model was still saved)."""
    return [
        line.strip()
        for line in log.splitlines()
        if line.startswith("SERGIO_STEP_ERROR")
    ]


def blender_failed(log: str) -> bool:
    """Did Blender stop before saving? (failed steps alone do not count)"""
    return "SERGIO_SAVED" not in log


__all__ = [
    "blender_failed",
    "bboxes",
    "edit",
    "from_photo",
    "from_text",
    "parse_verdict",
    "reference_sheet",
    "refine",
    "surgical_report",
    "verify",
    "vision_note",
]
