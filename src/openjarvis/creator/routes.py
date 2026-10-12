"""HTTP API for Creator (/v1/creator/*)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from openjarvis.creator import anatomy_build, studio
from openjarvis.creator.llm import CreatorError

router = APIRouter(prefix="/v1/creator", tags=["creator"])


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, CreatorError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ImportError):
        return HTTPException(
            status_code=503,
            detail="Falta un componente de Creator (uv sync --extra faces --extra cad).",
        )
    return HTTPException(status_code=500, detail=f"Creator falló: {str(exc)[:300]}")


def _local_only(request: Request) -> None:
    """Running or saving code, and building figures (which runs Node), only
    from this computer: never through a tunnel or proxy."""
    from openjarvis.server.vision_routes import from_this_computer

    host = request.client.host if request.client else ""
    if host != "testclient" and not from_this_computer(request):
        raise HTTPException(status_code=403, detail="Solo desde este equipo.")


async def _run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — one readable answer for the UI
        raise _fail(exc) from exc


# -- anatomy -----------------------------------------------------------------------


@router.get("/anatomy")
async def anatomy_list() -> dict[str, Any]:
    return {"figures": await _run(anatomy_build.examples)}


class BuildRequest(BaseModel):
    name: str
    light: bool = False


@router.post("/anatomy/build")
async def anatomy_build_route(request: Request, req: BuildRequest) -> dict[str, Any]:
    _local_only(request)
    await _run(anatomy_build.build_example, req.name, req.light)
    suffix = "?light=1" if req.light else ""
    return {"name": req.name, "url": f"/v1/creator/anatomy/view/{req.name}{suffix}"}


class CreateRequest(BaseModel):
    request: str


@router.post("/anatomy/create")
async def anatomy_create(request: Request, req: CreateRequest) -> dict[str, Any]:
    _local_only(request)
    out = await _run(anatomy_build.create, req.request)
    return {**out, "url": f"/v1/creator/anatomy/view/{out['name']}"}


@router.get("/anatomy/view/{name}")
async def anatomy_view(name: str, light: bool = False) -> FileResponse:
    page = await asyncio.to_thread(anatomy_build.page_path, name, light)
    if page is None:
        raise HTTPException(
            status_code=404, detail="Esa lámina aún no está construida."
        )
    # Shown in a sandboxed iframe (no access to Sergio's pages or storage).
    return FileResponse(
        page, media_type="text/html", headers={"Cache-Control": "no-store"}
    )


# -- design and images -------------------------------------------------------------


class DesignRequest(BaseModel):
    request: str
    width: int = 1080
    height: int = 1080


@router.post("/design")
async def design(req: DesignRequest) -> dict[str, Any]:
    return await _run(studio.design_layout, req.request, req.width, req.height)


@router.post("/image/cutout")
async def image_cutout(image: UploadFile = File(...)) -> Response:
    data = await image.read(studio.MAX_IMAGE + 1)
    png = await _run(studio.cutout, data)
    return Response(png, media_type="image/png")


class ImagePrompt(BaseModel):
    prompt: str


@router.post("/image/generate")
async def image_generate(req: ImagePrompt) -> Response:
    data = await _run(studio.generate_image, req.prompt)
    return Response(data, media_type="image/png")


@router.post("/image/edit")
async def image_edit(
    image: UploadFile = File(...), instruction: str = Form(...)
) -> Response:
    data = await image.read(studio.MAX_IMAGE + 1)
    out = await _run(studio.edit_image, data, instruction)
    return Response(out, media_type="image/png")


# -- plans ---------------------------------------------------------------------------


class PlanRequest(BaseModel):
    walls: list[dict[str, Any]]
    openings: list[dict[str, Any]] = []


@router.post("/plan/dxf")
async def plan_dxf(req: PlanRequest) -> Response:
    data = await _run(studio.plan_dxf, req.walls, req.openings)
    return Response(
        data,
        media_type="application/dxf",
        headers={"Content-Disposition": 'attachment; filename="plano-sergio.dxf"'},
    )


# -- code ----------------------------------------------------------------------------


@router.get("/code/files")
async def code_files() -> dict[str, Any]:
    return {"files": await _run(studio.list_files)}


@router.get("/code/file")
async def code_read(path: str) -> dict[str, Any]:
    return {"path": path, "content": await _run(studio.read_file, path)}


class SaveRequest(BaseModel):
    path: str
    content: str


@router.put("/code/file")
async def code_save(request: Request, req: SaveRequest) -> dict[str, Any]:
    _local_only(request)
    return await _run(studio.save_file, req.path, req.content)


class EditRequest(BaseModel):
    path: str
    content: str
    instruction: str


@router.post("/code/ai")
async def code_ai(req: EditRequest) -> dict[str, Any]:
    return {
        "content": await _run(studio.ai_edit, req.path, req.content, req.instruction)
    }


class RunRequest(BaseModel):
    path: str


@router.post("/code/run")
async def code_run(request: Request, req: RunRequest) -> dict[str, Any]:
    _local_only(request)
    return await _run(studio.run_file, req.path)


__all__ = ["router"]
