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
    if isinstance(exc, HTTPException):  # already readable (e.g. the desktop is closed)
        return exc
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
    png, method = await _run(studio.cutout_detail, data)
    # The UI tells the owner when the cruder fallback was used.
    return Response(png, media_type="image/png", headers={"X-Sergio-Recorte": method})


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


@router.get("/media/{filename}")
async def creator_media(filename: str) -> Response:
    """Serve generated Creator images/assets so chat messages can render them inline."""
    import re as _re

    safe = _re.sub(r"[^\w.\-]+", "", filename)
    if not safe or safe != filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido.")
    candidates = [
        studio.projects_root() / "imagenes" / safe,
        studio.projects_root() / safe,
    ]
    for path in candidates:
        if path.is_file():
            ext = path.suffix.lower()
            mime = (
                "image/jpeg"
                if ext in (".jpg", ".jpeg")
                else "image/webp"
                if ext == ".webp"
                else "image/svg+xml"
                if ext == ".svg"
                else "image/png"
            )
            return FileResponse(path, media_type=mime)
    raise HTTPException(status_code=404, detail="Imagen no encontrada.")


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


@router.post("/plan/ifc")
async def plan_ifc(req: PlanRequest) -> Response:
    """The plan as an IFC building (BIM) for FreeCAD or Blender with Bonsai."""
    from openjarvis.creator import bim

    data = await _run(bim.plan_ifc, req.walls, req.openings)
    return Response(
        data,
        media_type="application/x-step",
        headers={"Content-Disposition": 'attachment; filename="plano-sergio.ifc"'},
    )


class PlanOpenRequest(PlanRequest):
    program: str  # librecad / freecad (DXF) or freecad / bonsai (IFC)
    kind: str = "ifc"


@router.post("/plan/open")
async def plan_open(request: Request, req: PlanOpenRequest) -> dict[str, Any]:
    """Make the file and open it in the program on the owner's PC."""
    from openjarvis.creator import bim, programs

    _local_only(request)
    if req.kind not in programs.OPENS or req.program not in programs.OPENS[req.kind]:
        raise HTTPException(status_code=400, detail="Ese programa no abre ese archivo.")
    make = bim.plan_ifc if req.kind == "ifc" else studio.plan_dxf
    data = await _run(make, req.walls, req.openings)
    message = await _run(
        programs.open_in_windows, req.program, f"plano-sergio.{req.kind}", data
    )
    return {"message": message}


# -- the real programs (OpenDesign, VSCodium, ArtCraft, FreeCAD…) ----------------------


@router.get("/programs")
async def programs_list(request: Request) -> dict[str, Any]:
    from openjarvis.creator import programs
    from openjarvis.server.vision_routes import from_this_computer

    local = from_this_computer(request) or (
        request.client and request.client.host == "testclient"
    )
    return {"programs": await _run(programs.status, bool(local))}


@router.post("/programs/{pid}/start")
async def programs_start(request: Request, pid: str) -> dict[str, Any]:
    from openjarvis.creator import programs

    _local_only(request)
    return await _run(programs.start, pid)


class InstallRequest(BaseModel):
    where: str = ""  # "windows" for VSCodium's desktop app


@router.post("/programs/{pid}/install")
async def programs_install(
    request: Request, pid: str, req: InstallRequest | None = None
) -> dict[str, Any]:
    from openjarvis.creator import programs

    _local_only(request)
    return await _run(programs.install, pid, (req.where if req else ""))


@router.post("/programs/{pid}/open")
async def programs_open(request: Request, pid: str) -> dict[str, Any]:
    from openjarvis.creator import programs

    _local_only(request)
    return {"message": await _run(programs.open_in_windows, pid)}


class OpenFileRequest(BaseModel):
    name: str
    data: str  # base64


@router.post("/programs/{pid}/open-file")
async def programs_open_file(
    request: Request, pid: str, req: OpenFileRequest
) -> dict[str, Any]:
    """Open a file made in the web (an image, a model) in a Windows program."""
    import base64
    import binascii

    from openjarvis.creator import programs

    _local_only(request)
    try:
        data = base64.b64decode(req.data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Archivo no válido.") from exc
    if len(data) > 60 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo pasa de 60 MB.")
    message = await _run(programs.open_in_windows, pid, req.name, data)
    return {"message": message}


class OpenDesignRequest(BaseModel):
    request: str
    width: int = 1080
    height: int = 1080


@router.post("/opendesign/create")
async def opendesign_create(req: OpenDesignRequest) -> dict[str, Any]:
    """Sergio lays the design out and creates it inside OpenDesign."""
    from openjarvis.creator import opendesign

    layout = await _run(studio.design_layout, req.request, req.width, req.height)
    row = await _run(
        opendesign.create_design, req.request[:60], layout, req.width, req.height
    )
    return {"id": row["id"], "name": row.get("name", "")}


# -- Bolsa (Kronos) ----------------------------------------------------------------------


class ForecastRequest(BaseModel):
    symbol: str
    horizon: int = 20
    size: str = "small"


@router.post("/bolsa/forecast")
async def bolsa_forecast(req: ForecastRequest) -> dict[str, Any]:
    from openjarvis.creator import kronos

    return await _run(kronos.forecast, req.symbol, req.horizon, req.size)


@router.get("/bolsa/history")
async def bolsa_history(symbol: str) -> dict[str, Any]:
    from openjarvis.creator import kronos

    rows = await _run(kronos.history, symbol)
    return {"symbol": symbol.upper(), "history": rows[-120:]}


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
