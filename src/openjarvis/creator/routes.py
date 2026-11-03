"""HTTP API for Creator (/v1/creator/*)."""

from __future__ import annotations

import asyncio
from pathlib import Path
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


# -- models to take apart in the chat (despiece.py) ------------------------------


@router.get("/despiece")
async def despiece_list() -> dict[str, Any]:
    from openjarvis.creator import despiece

    return {"modelos": await asyncio.to_thread(despiece.models)}


@router.get("/despiece/view/{name}")
async def despiece_view(name: str) -> dict[str, Any]:
    from openjarvis.creator import despiece

    try:
        meta = despiece.meta(name)
    except CreatorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {**meta, "url": f"/v1/creator/despiece/file/{name}/{meta['archivo']}"}


@router.get("/despiece/file/{name}/{rel:path}")
async def despiece_file(name: str, rel: str) -> FileResponse:
    from openjarvis.creator import despiece

    try:
        path = despiece.file_path(name, rel)
    except CreatorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    kinds = {
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
        ".json": "application/json",
    }
    return FileResponse(path, media_type=kinds.get(path.suffix.lower()))


class DespieceRequest(BaseModel):
    request: str


@router.post("/despiece/create")
async def despiece_create(body: DespieceRequest) -> dict[str, Any]:
    from openjarvis.creator import despiece

    try:
        return await asyncio.to_thread(despiece.create, body.request)
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from exc


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


@router.get("/galeria")
async def gallery(limit: int = 300) -> dict[str, Any]:
    """Everything the owner made with Sergio that the chat can show: images,
    videos and the 3D models to take apart; newest first."""
    from openjarvis.server.auth_middleware import _OPEN_MEDIA

    def collect() -> list[dict[str, Any]]:
        root = studio.projects_root()
        rows: list[dict[str, Any]] = []
        for folder in (root / "imagenes", root / "videos", root):
            if not folder.is_dir():
                continue
            for p in folder.iterdir():
                url = f"/v1/creator/media/{p.name}"
                if not p.is_file() or not _OPEN_MEDIA.fullmatch(url):
                    continue
                kind = "video" if p.suffix.lower() == ".mp4" else "imagen"
                rows.append({"url": url, "mini": f"/v1/creator/miniatura/{p.name}", "tipo": kind,
                             "nombre": p.stem.rsplit("-", 1)[0],
                             "fecha": p.stat().st_mtime, "bytes": p.stat().st_size})  # fmt: skip
        try:
            from openjarvis.creator import despiece

            base = despiece.root()
            for m in despiece.models():
                name = str(m.get("name", ""))
                when = (
                    (base / name / "meta.json").stat().st_mtime
                    if (base / name).is_dir()
                    else 0.0
                )
                rows.append(
                    {
                        "url": "",
                        "modelo": name,
                        "tipo": "3d",
                        "nombre": m.get("titulo") or name,
                        "fecha": when,
                        "piezas": m.get("piezas"),
                    }
                )
        except Exception:  # noqa: BLE001 — no 3D models yet
            pass
        rows.sort(key=lambda r: -r["fecha"])
        return rows[: max(1, min(limit, 1000))]

    items = await asyncio.to_thread(collect)
    return {"elementos": items, "total": len(items)}


def make_thumbnail(src: Path, dest: Path, size: int = 480) -> bool:
    """A small JPEG of a picture, or of the first moments of a video, kept
    next to the others (the gallery shows 9 cards at once: nine 5 MB pictures
    were why it felt like nothing loaded)."""
    import subprocess

    from PIL import Image

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.jpg")
    try:
        if src.suffix.lower() == ".mp4":
            from openjarvis.tools.video_create import ffmpeg_exe

            ffmpeg = ffmpeg_exe()
            if not ffmpeg:
                return False
            subprocess.run(
                [ffmpeg, "-v", "error", "-y", "-ss", "0.5", "-i", str(src), "-frames:v", "1",
                 "-vf", f"scale='min({size},iw)':-2", str(tmp)],
                check=True, timeout=60,
            )  # fmt: skip
            if not tmp.is_file():  # a clip shorter than half a second
                subprocess.run(
                    [ffmpeg, "-v", "error", "-y", "-i", str(src), "-frames:v", "1",
                     "-vf", f"scale='min({size},iw)':-2", str(tmp)],
                    check=True, timeout=60,
                )  # fmt: skip
        else:
            with Image.open(src) as im:
                im = im.convert("RGB")
                im.thumbnail((size, size * 2))
                im.save(tmp, "JPEG", quality=80)
        tmp.replace(dest)
        return True
    except Exception:  # noqa: BLE001 — the card then shows the original
        tmp.unlink(missing_ok=True)
        return False


@router.get("/miniatura/{filename}")
async def creator_thumbnail(filename: str) -> Response:
    """The small version of a media file (made once, then served from disk)."""
    import re as _re

    safe = _re.sub(r"[^\w.\-]+", "", filename)
    if not safe or safe != filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido.")
    root = studio.projects_root()
    src = next(
        (
            p
            for p in (root / "imagenes" / safe, root / "videos" / safe, root / safe)
            if p.is_file()
        ),
        None,
    )
    if src is None:
        raise HTTPException(status_code=404, detail="No encuentro ese archivo.")
    thumb = root / ".miniaturas" / (src.stem + ".jpg")
    if not thumb.is_file() or thumb.stat().st_mtime < src.stat().st_mtime:
        if not await asyncio.to_thread(make_thumbnail, src, thumb):
            raise HTTPException(status_code=404, detail="Sin miniatura.")
    return FileResponse(
        thumb,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


_WEB_JOBS: dict[str, str] = {}  # name -> "preparando" | "error: why"


def web_playable(src: Path) -> bool | None:
    """Can a browser play this file as it is? H.264 8-bit (yuv420p) with AAC or
    MP3 sound. ``None`` when it cannot be told (no ffmpeg): the page then just
    tries the original. The «máster» of the highest mode is HEVC 10-bit, which
    most browsers refuse: that was a video that did nothing when clicked."""
    import re as _re
    import subprocess

    from openjarvis.tools.video_create import ffmpeg_exe

    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        return None
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(src)],
            capture_output=True, text=True, timeout=30,
        ).stderr  # fmt: skip
    except Exception:  # noqa: BLE001
        return None
    video = _re.search(r"Video: (\w+)[^\n]*?,\s*(yuv\w+|[a-z0-9_]+)[,( ]", out)
    if not video:
        return None
    codec, pix = video.group(1), video.group(2)
    if codec != "h264" or pix != "yuv420p":
        return False
    audio = _re.search(r"Audio: (\w+)", out)
    return not audio or audio.group(1) in ("aac", "mp3")


def _make_web_copy(src: Path, dest: Path, name: str) -> None:
    """A copy every browser plays (H.264 8-bit, AAC, at most 1080p wide)."""
    import subprocess

    from openjarvis.tools.video_create import ffmpeg_exe

    tmp = dest.with_suffix(".tmp.mp4")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [ffmpeg_exe(), "-v", "error", "-y", "-i", str(src),
             "-vf", "scale='min(1920,iw)':-2,format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(tmp)],
            check=True, timeout=3600, capture_output=True,
        )  # fmt: skip
        tmp.replace(dest)
        _WEB_JOBS.pop(name, None)
    except Exception as exc:  # noqa: BLE001 — told to the person, never hidden
        tmp.unlink(missing_ok=True)
        _WEB_JOBS[name] = f"error: {str(exc)[:160]}"


@router.get("/video-listo/{filename}")
async def creator_video_ready(filename: str, forzar: bool = False) -> dict[str, Any]:
    """Is this video ready to play in a browser? ``listo`` with the address to
    use, ``preparando`` (a browser-friendly copy is being made: ask again in a
    few seconds) or ``error`` with the reason."""
    import re as _re
    import threading

    safe = _re.sub(r"[^\w.\-]+", "", filename)
    if not safe or safe != filename or not safe.endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido.")
    root = studio.projects_root()
    src = next((p for p in (root / "videos" / safe, root / safe) if p.is_file()), None)
    if src is None:
        raise HTTPException(status_code=404, detail="No encuentro ese video.")
    original = {"estado": "listo", "url": f"/v1/creator/media/{safe}"}
    copy = root / ".web" / safe
    if copy.is_file() and copy.stat().st_mtime >= src.stat().st_mtime:
        return {"estado": "listo", "url": f"/v1/creator/reproducir/{safe}"}
    state = _WEB_JOBS.get(safe)
    if state:
        if state.startswith("error"):
            return {"estado": "error", "motivo": state[7:]}
        return {"estado": "preparando"}
    # ``forzar``: the page tried the original and the browser refused it
    ok = False if forzar else await asyncio.to_thread(web_playable, src)
    if ok is not False:
        return original
    from openjarvis.tools.video_create import ffmpeg_exe

    if not ffmpeg_exe():
        return {
            "estado": "error",
            "motivo": "Este video usa un formato que el navegador no reproduce y no hay ffmpeg para convertirlo.",
        }
    _WEB_JOBS[safe] = "preparando"
    threading.Thread(target=_make_web_copy, args=(src, copy, safe), daemon=True).start()
    return {"estado": "preparando"}


@router.get("/reproducir/{filename}")
async def creator_video_web(filename: str) -> Response:
    """The browser-friendly copy made by ``/video-listo`` (supports Range)."""
    import re as _re

    safe = _re.sub(r"[^\w.\-]+", "", filename)
    path = studio.projects_root() / ".web" / safe
    if not safe or safe != filename or not path.is_file():
        raise HTTPException(status_code=404, detail="Todavía no está listo.")
    return FileResponse(path, media_type="video/mp4")


@router.get("/archivo/{filename}")
async def creator_document(filename: str) -> Response:
    """A document Sergio made (an .xlsx from ``hoja_calculo``), to download."""
    import re as _re

    safe = _re.sub(r"[^\w.\-]+", "", filename)
    path = studio.projects_root() / "documentos" / safe
    if not safe or safe != filename or not safe.endswith(".xlsx") or not path.is_file():
        raise HTTPException(status_code=404, detail="No encuentro ese archivo.")
    nice = safe.rsplit("-", 1)[0] + ".xlsx"
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nice}"'},
    )


@router.get("/inspiracion/{rid}")
async def inspiration(rid: str) -> dict[str, Any]:
    """The three videos found for a brief (the chat draws them as a card)."""
    from openjarvis.video_essay import inspiracion

    try:
        return inspiracion.load(rid)
    except (KeyError, OSError, ValueError):
        raise HTTPException(status_code=404, detail="No encuentro esa búsqueda.")


class InspirationChoice(BaseModel):
    opcion: int


@router.post("/inspiracion/{rid}/elegir")
async def inspiration_choose(rid: str, body: InspirationChoice) -> dict[str, Any]:
    from openjarvis.video_essay import inspiracion

    try:
        return inspiracion.choose(rid, body.opcion)
    except (KeyError, OSError, ValueError, IndexError):
        raise HTTPException(status_code=404, detail="No encuentro esa opción.")


@router.get("/inspiracion/{rid}/miniatura/{name}")
async def inspiration_thumb(rid: str, name: str) -> Response:
    import re as _re

    from openjarvis.video_essay import inspiracion

    if not _re.fullmatch(r"[0-9a-f]{24}", rid) or not _re.fullmatch(
        r"[0-9]\.jpg", name
    ):
        raise HTTPException(status_code=404, detail="No.")
    path = inspiracion.home() / rid / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Sin miniatura.")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# -- video plans (planear.py) and the edit with the creator's takes (montaje.py) -----

_EDITS: dict[str, Any] = {}


def _plan_folder(pid: str) -> Path:
    from openjarvis.video_essay import planear

    try:
        path = planear.folder(pid)
    except KeyError:
        raise HTTPException(status_code=404, detail="No encuentro ese plan.")
    if not (path / "plan.json").is_file():
        raise HTTPException(status_code=404, detail="No encuentro ese plan.")
    return path


@router.get("/plan/{pid}")
async def plan_get(pid: str) -> dict[str, Any]:
    from openjarvis.video_essay import planear

    _plan_folder(pid)
    data = planear.load(pid)
    data["montando"] = bool(_EDITS.get(pid) and _EDITS[pid].is_alive())
    return data


@router.get("/plan/{pid}/animatic.mp4")
async def plan_animatic(pid: str) -> Response:
    path = _plan_folder(pid) / "animatic.mp4"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Sin animación.")
    return FileResponse(path, media_type="video/mp4")


@router.get("/plan/{pid}/cuadro/{name}")
async def plan_frame(pid: str, name: str) -> Response:
    import re as _re

    if not _re.fullmatch(r"toma-\d{2}\.png", name):
        raise HTTPException(status_code=404, detail="No.")
    path = _plan_folder(pid) / "cuadros" / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Sin cuadro.")
    return FileResponse(path, media_type="image/png")


@router.post("/plan/{pid}/toma/{n}")
async def plan_take(pid: str, n: int, file: UploadFile = File(...)) -> dict[str, Any]:
    """One of the creator's takes for shot *n* (any video format)."""
    from openjarvis.video_essay import planear

    folder = _plan_folder(pid)
    data = planear.load(pid)
    shot = next((s for s in data["tomas"] if s["n"] == n), None)
    if shot is None:
        raise HTTPException(status_code=404, detail="Esa toma no está en el plan.")
    ext = Path(file.filename or "toma.mp4").suffix.lower()
    if ext not in (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"):
        raise HTTPException(status_code=400, detail="Suba un video (mp4, mov, webm…).")
    dest = folder / "tomas"
    dest.mkdir(parents=True, exist_ok=True)
    name = f"toma-{n:02d}{ext}"
    with (dest / name).open("wb") as fh:
        while chunk := await file.read(1 << 20):
            fh.write(chunk)
    shot["archivo"] = name
    planear.save(pid, data)
    return {
        "ok": True,
        "toma": n,
        "subidas": sum(1 for s in data["tomas"] if s.get("archivo")),
    }


@router.post("/plan/{pid}/montar")
async def plan_edit(pid: str) -> dict[str, Any]:
    """Starts the edit with the takes uploaded so far (in the background)."""
    import threading

    from openjarvis.video_essay import montaje, planear

    _plan_folder(pid)
    running = _EDITS.get(pid)
    if running and running.is_alive():
        return {"estado": "montando"}

    def work() -> None:
        try:
            montaje.edit(pid)
        except Exception as exc:  # noqa: BLE001 — said in the plan, never silent
            data = planear.load(pid)
            data["montaje_error"] = str(exc)[:300]
            planear.save(pid, data)

    t = threading.Thread(target=work, daemon=True, name=f"montaje-{pid[:6]}")
    _EDITS[pid] = t
    t.start()
    return {"estado": "montando"}


@router.get("/artefacto/{filename}")
async def creator_artifact(filename: str) -> Response:
    """An artifact (a self-contained page Sergio made) for the chat's frame. The
    content policy is put on top again here, and the frame is a sandbox with no
    access to Sergio's page: see ``tools/artefacto.py``."""
    import re as _re

    from openjarvis.tools import artefacto

    safe = _re.sub(r"[^\w.\-]+", "", filename)
    if not safe or safe != filename or not safe.endswith(".html"):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido.")
    path = studio.projects_root() / "artefactos" / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No encuentro ese artefacto.")
    html = artefacto.inject_policy(path.read_text("utf-8"))
    return Response(
        html,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'inline; filename="{safe}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/media/{filename}")
async def creator_media(filename: str) -> Response:
    """Serve generated Creator images/assets so chat messages can render them inline."""
    import re as _re

    safe = _re.sub(r"[^\w.\-]+", "", filename)
    if not safe or safe != filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido.")
    candidates = [
        studio.projects_root() / "imagenes" / safe,
        studio.projects_root() / "videos" / safe,
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
                else "video/mp4"
                if ext == ".mp4"
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
