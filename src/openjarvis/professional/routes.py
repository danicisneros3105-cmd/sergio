"""Tools shelf: real host detection, optional installs and companion handoff."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from openjarvis.professional.catalog import BY_ID, catalog, installer

router = APIRouter(prefix="/v1/programs", tags=["professional"])


@router.get("/opendesign/status")
async def design_status() -> dict:
    import httpx

    from openjarvis.professional.opendesign import request

    def probe():
        with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
            return request("templates", client=client)

    try:
        templates = await asyncio.to_thread(probe)
        if not isinstance(templates, list):
            raise ValueError("El servicio no devuelve el catálogo de OpenDesign.")
        return {
            "ready": True,
            "templates": len(templates),
            "editor": "http://127.0.0.1:5178/?agent=true",
        }
    except Exception:
        return {
            "ready": False,
            "message": "OpenDesign aún no está iniciado en este servidor.",
        }


class Canvas(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    width: int = Field(default=1080, ge=64, le=8192)
    height: int = Field(default=1080, ge=64, le=8192)


@router.post("/opendesign/canvas")
async def create_canvas(body: Canvas) -> dict:
    from openjarvis.professional.opendesign import request

    try:
        return await asyncio.to_thread(request, "create", body.model_dump())
    except Exception as exc:
        raise HTTPException(503, "OpenDesign no pudo crear el lienzo local.") from exc


@router.get("")
async def programs() -> dict:
    return await asyncio.to_thread(catalog)


class Selection(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=40)


@router.post("/installer")
async def prepare_installer(body: Selection) -> Response:
    try:
        script = installer(body.ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # UTF-8 BOM: Windows PowerShell 5.1 also reads accented text correctly.
    return Response(
        b"\xef\xbb\xbf" + script.encode("utf-8"),
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="Sergio-Programas.ps1"'},
    )


@router.post("/{program_id}/open")
async def open_program(program_id: str) -> dict:
    p = BY_ID.get(program_id)
    if not p or not p.opens_window:
        raise HTTPException(
            400, "Esta integración requiere su configuración específica."
        )
    from openjarvis.tools.desktop_tools import DesktopActionTool

    result = await asyncio.to_thread(
        DesktopActionTool().execute, action="open_app", target=p.name
    )
    if not result.success:
        raise HTTPException(503, result.content)
    return {"result": result.content}


__all__ = [
    "Canvas",
    "Selection",
    "create_canvas",
    "design_status",
    "open_program",
    "prepare_installer",
    "programs",
    "router",
]
