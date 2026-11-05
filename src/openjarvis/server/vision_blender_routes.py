"""3D and video endpoints under ``/v1/vision``: Blender models from a photo or
text, refinement, verification and surgical edits, holograms, CAD drawings,
video plans and learned video styles, Tripo import.

Split out of ``vision_routes.py``, which owns the router; its names are
looked up on that module, so behaviour (and anything patched there) is
unchanged.
"""

from __future__ import annotations

from typing import Any

from fastapi import UploadFile

import openjarvis.server.vision_routes as _vision


@_vision.router.post("/blender")
async def blender_route(
    save_path: str = _vision.Form(...),
    note: str = _vision.Form(""),
    image: UploadFile = _vision.File(...),
    preview_path: str = _vision.Form(""),
    pro: bool = _vision.Form(False),
    blender_version: str = _vision.Form(""),
) -> dict[str, Any]:
    """The object in the user's hands -> a detailed, checked Blender script.

    *pro*: Blender Pro's way — a blueprint sheet of the same object is drawn
    first and the script is written from the photo plus the sheet."""
    from openjarvis.tools.blender_model import model_object

    data = await image.read(_vision.MAX_IMAGE_BYTES + 1)
    if len(data) > _vision.MAX_IMAGE_BYTES:
        raise _vision.HTTPException(status_code=413, detail="Image too large")
    if not save_path.lower().endswith(".blend"):
        raise _vision.HTTPException(
            status_code=400, detail="save_path must end in .blend"
        )
    if pro:
        from openjarvis.tools.blender_pro import from_photo

        try:
            return await _vision.asyncio.to_thread(
                lambda: from_photo(
                    data, save_path, note, preview_path, version=blender_version[:20]
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise _vision.HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    try:
        return await _vision.asyncio.to_thread(
            model_object,
            data,
            save_path,
            note,
            image.content_type or "image/jpeg",
            None,
            2,
            preview_path,
        )
    except RuntimeError as exc:
        raise _vision.HTTPException(status_code=502, detail=str(exc)) from exc


@_vision.router.post("/video_plan")
async def video_plan_route(
    request: str = _vision.Form(...),
    lengths: str = _vision.Form(...),
    sheets: list[UploadFile] = _vision.File(...),
    style: str = _vision.Form(""),
) -> dict[str, Any]:
    """Plan the edit with the configured vision model."""
    import math
    from openjarvis.tools.video_pro import plan
    from openjarvis.tools.video_style import find_style

    try:
        raw = _vision.json.loads(lengths)
        if not isinstance(raw, list):
            raise ValueError
        lens = [float(x) for x in raw]
        if not 1 <= len(sheets) <= 32 or len(lens) != len(sheets):
            raise ValueError
        if any(not math.isfinite(x) or x <= 0 for x in lens):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise _vision.HTTPException(
            status_code=400,
            detail="Envíe de 1 a 32 hojas, con una duración positiva por clip.",
        ) from exc
    images = []
    total = 0
    for sheet in sheets:
        image = await sheet.read(_vision.MAX_IMAGE_BYTES + 1)
        total += len(image)
        if len(image) > _vision.MAX_IMAGE_BYTES or total > 16 * 1024 * 1024:
            raise _vision.HTTPException(
                status_code=413, detail="Las hojas de contacto son demasiado grandes."
            )
        if not image.startswith(b"\xff\xd8"):
            raise _vision.HTTPException(
                status_code=400, detail="Las hojas deben ser JPEG."
            )
        images.append(image)
    chosen = find_style(style) if style.strip() else None
    if style.strip() and chosen is None:
        raise _vision.HTTPException(
            status_code=404,
            detail=f"No conozco el estilo «{style}». Pídame que lo aprenda primero.",
        )
    try:
        result = await _vision.asyncio.to_thread(
            plan, request, images, lens, None, chosen
        )
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    try:
        from openjarvis.evolution.memory import shared

        shared().remember(
            "video",
            f"Edición «{request[:200]}»: {len(result['segments'])} cortes, "
            f"estilo {chosen['name'] if chosen else 'propio'}, título «{result['youtube']['title']}»",
        )
    except Exception:  # noqa: BLE001 — memory is a bonus
        pass
    return result


@_vision.router.post("/blender/learn")
async def blender_learn_route(req: _vision.BlenderLearn) -> dict[str, Any]:
    """A finished Blender Pro build: kept as a worked example if it passes
    the strict check (0 mesh errors, parts in place, nothing floating)."""
    from openjarvis.tools.blender_examples import remember

    kept = await _vision.asyncio.to_thread(
        remember, req.request, req.script[:20000], req.log[-6000:]
    )
    try:  # the outcome joins long-term memory: the next similar model reads it
        from openjarvis.evolution.memory import shared

        v = req.verdict or {}
        note = f"Modelo «{req.request[:160]}»"
        if v:
            note += f": revisión visual {v.get('score')}/10 (parece «{v.get('looks_like', '')}»)"
            if v.get("problems"):
                note += "; problemas: " + "; ".join(str(p) for p in v["problems"][:4])
        await _vision.asyncio.to_thread(shared().remember, "blender", note)
    except Exception:  # noqa: BLE001 — memory is a bonus
        pass
    return kept


@_vision.router.post("/holo_model")
async def holo_model_route(req: _vision.HoloRequest) -> dict[str, Any]:
    """A hologram of anything: its real parts, designed by Gemini."""
    from openjarvis.tools.holo_model import design

    try:
        return await _vision.asyncio.to_thread(design, req.request)
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=502, detail=str(exc)[:400]) from exc


@_vision.router.post("/blender/text")
async def blender_text_route(task: _vision.BlenderTask) -> dict[str, Any]:
    """Any Blender job in words -> a checked script (Blender Pro)."""
    from openjarvis.tools.blender_pro import from_text

    if not task.save_path.lower().endswith(".blend"):
        raise _vision.HTTPException(
            status_code=400, detail="save_path must end in .blend"
        )
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
                    task.request,
                    task.save_path,
                    task.preview_path,
                    parts=parts.result(),
                    sheet=sheet.result(),
                    version=task.blender_version[:20],
                )

        return await _vision.asyncio.to_thread(run)
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=502, detail=str(exc)[:400]) from exc


@_vision.router.post("/blender/refine")
async def blender_refine_route(
    request: str = _vision.Form(...),
    raw_script: str = _vision.Form(...),
    save_path: str = _vision.Form(...),
    log: str = _vision.Form(""),
    preview_path: str = _vision.Form(""),
    preview: UploadFile = _vision.File(...),
    reference: UploadFile | None = _vision.File(None),
    sheet: UploadFile | None = _vision.File(None),
    target_cm: str = _vision.Form(""),
) -> dict[str, Any]:
    """Blender Pro's review round: look at the four views, fix the script."""
    from openjarvis.tools.blender_pro import refine

    shot = await preview.read(_vision.MAX_IMAGE_BYTES + 1)
    ref = (
        await reference.read(_vision.MAX_IMAGE_BYTES + 1)
        if reference is not None
        else b""
    )
    board = await sheet.read(_vision.MAX_IMAGE_BYTES + 1) if sheet is not None else b""
    try:
        target = (
            [float(v) for v in _vision.json.loads(target_cm)] if target_cm else None
        )
    except (ValueError, TypeError):
        target = None
    try:
        return await _vision.asyncio.to_thread(
            refine,
            request,
            raw_script,
            log,
            shot,
            save_path,
            preview_path,
            ref,
            None,
            target,
            board,
        )
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=502, detail=str(exc)[:400]) from exc


@_vision.router.post("/cad/image")
async def cad_image_route(
    image: UploadFile = _vision.File(...),
    width_mm: float = _vision.Form(100.0),
    tolerance_px: float = _vision.Form(1.5),
) -> dict[str, Any]:
    """An image vectorised (OpenCV) into a DXF in millimetres (ezdxf)."""
    import base64

    from openjarvis.tools.cad import image_to_dxf, preview_png

    data = await image.read(_vision.MAX_IMAGE_BYTES + 1)
    if len(data) > _vision.MAX_IMAGE_BYTES:
        raise _vision.HTTPException(status_code=413, detail="Image too large")
    try:
        dxf, info = await _vision.asyncio.to_thread(
            image_to_dxf, data, max(1.0, min(width_mm, 100000.0)), tolerance_px
        )
        png = await _vision.asyncio.to_thread(preview_png, dxf)
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=422, detail=str(exc)[:300]) from exc
    return {
        "dxf_b64": base64.b64encode(dxf).decode(),
        "preview_b64": base64.b64encode(png).decode(),
        **info,
    }


@_vision.router.post("/cad/model")
async def cad_model_route(req: _vision.CadModel) -> dict[str, Any]:
    """A Blender model's feature edges -> a three-view DXF drawing with dimensions."""
    import base64

    from openjarvis.tools.cad import model_to_dxf, parse_edges, preview_png

    try:
        edges = parse_edges(req.log)
        dxf, info = await _vision.asyncio.to_thread(
            model_to_dxf, edges, req.name[:60] or "Modelo"
        )
        png = await _vision.asyncio.to_thread(preview_png, dxf)
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=422, detail=str(exc)[:300]) from exc
    return {
        "dxf_b64": base64.b64encode(dxf).decode(),
        "preview_b64": base64.b64encode(png).decode(),
        **info,
    }


@_vision.router.post("/video_style/learn")
async def video_style_learn_route(req: _vision.StyleLearn) -> dict[str, Any]:
    """Gemini watches real videos (YouTube links, or a channel / ad it
    searches for) and saves their editing style for Video Pro."""
    from openjarvis.tools.video_style import describe, learn

    try:
        style = await _vision.asyncio.to_thread(learn, req.source, req.name)
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    return {"style": style, "summary": describe(style)}


@_vision.router.get("/video_style")
async def video_style_list_route() -> dict[str, Any]:
    """The editing styles Video Pro knows."""
    from openjarvis.tools.video_style import available, describe

    return {
        "styles": [
            {"name": s.get("name"), "slug": s.get("slug"), "summary": describe(s)}
            for s in available()
        ]
    }


@_vision.router.post("/blender/import")
async def blender_import_route(req: _vision.BlenderImport) -> dict[str, Any]:
    """The finished Blender script for a generated GLB (Tripo, SculptMate...)."""
    from openjarvis.tools.blender_pro import import_model

    if not req.save_path.lower().endswith(
        ".blend"
    ) or not req.glb_path.lower().endswith((".glb", ".gltf")):
        raise _vision.HTTPException(
            status_code=400,
            detail="save_path must end in .blend and glb_path in .glb/.gltf",
        )
    return import_model(
        req.glb_path,
        req.save_path,
        req.preview_path,
        req.name[:60],
        min(max(req.size_cm, 0.5), 5000),
    )


@_vision.router.post("/tripo")
async def tripo_route(
    prompt: str = _vision.Form(""),
    quality: str = _vision.Form("standard"),
    image: UploadFile | None = _vision.File(None),
) -> dict[str, Any]:
    """Tripo 3D: text or image -> a textured PBR model (GLB, base64)."""
    import base64

    from openjarvis.tools.tripo import generate

    data = await image.read(_vision.MAX_IMAGE_BYTES + 1) if image is not None else b""
    try:
        out = await _vision.asyncio.to_thread(generate, prompt, data, quality)
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    return {"task_id": out["task_id"], "glb_b64": base64.b64encode(out["glb"]).decode()}


@_vision.router.get("/tripo/status")
async def tripo_status_route() -> dict[str, Any]:
    from openjarvis.tools.tripo import configured

    return {"configured": configured()}


@_vision.router.post("/blender/verify")
async def blender_verify_route(
    request: str = _vision.Form(...),
    preview: UploadFile = _vision.File(...),
    reference: UploadFile | None = _vision.File(None),
    sheet: UploadFile | None = _vision.File(None),
) -> dict[str, Any]:
    """The vision check of a build: what it looks like, 0-10, what to fix."""
    from openjarvis.tools.blender_pro import verify

    shot = await preview.read(_vision.MAX_IMAGE_BYTES + 1)
    ref = (
        await reference.read(_vision.MAX_IMAGE_BYTES + 1)
        if reference is not None
        else b""
    )
    board = await sheet.read(_vision.MAX_IMAGE_BYTES + 1) if sheet is not None else b""
    try:
        return await _vision.asyncio.to_thread(verify, request, shot, ref, board)
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=502, detail=str(exc)[:400]) from exc


@_vision.router.post("/blender/edit")
async def blender_edit_route(
    request: str = _vision.Form(...),
    raw_script: str = _vision.Form(...),
    instruction: str = _vision.Form(...),
    save_path: str = _vision.Form(...),
    preview_path: str = _vision.Form(""),
    collateral: str = _vision.Form(""),
    preview: UploadFile = _vision.File(...),
    reference: UploadFile | None = _vision.File(None),
) -> dict[str, Any]:
    """A surgical edit of a finished model: only what the instruction asks."""
    from openjarvis.tools.blender_pro import edit

    if not save_path.lower().endswith(".blend"):
        raise _vision.HTTPException(
            status_code=400, detail="save_path must end in .blend"
        )
    shot = await preview.read(_vision.MAX_IMAGE_BYTES + 1)
    ref = (
        await reference.read(_vision.MAX_IMAGE_BYTES + 1)
        if reference is not None
        else b""
    )
    try:
        undo = [str(x) for x in _vision.json.loads(collateral)] if collateral else None
    except (ValueError, TypeError):
        undo = None
    try:
        return await _vision.asyncio.to_thread(
            edit,
            request,
            raw_script,
            instruction,
            shot,
            save_path,
            preview_path,
            ref,
            None,
            undo,
        )
    except Exception as exc:  # noqa: BLE001
        raise _vision.HTTPException(status_code=502, detail=str(exc)[:400]) from exc


__all__ = [
    "blender_route",
    "video_plan_route",
    "blender_learn_route",
    "holo_model_route",
    "blender_text_route",
    "blender_refine_route",
    "cad_image_route",
    "cad_model_route",
    "video_style_learn_route",
    "video_style_list_route",
    "blender_import_route",
    "tripo_route",
    "tripo_status_route",
    "blender_verify_route",
    "blender_edit_route",
]
