"""The Workspace over HTTP: pages, files, search, export and share links.

* ``GET    /v1/workspace/pages``            — every page, as summaries.
* ``GET    /v1/workspace/pages/{id}``       — one page.
* ``PUT    /v1/workspace/pages/{id}``       — ``{"page": …, "base_rev": n}``;
  409 with the stored page when it changed meanwhile (the sent copy is kept
  as «(copia en conflicto)»).
* ``DELETE /v1/workspace/pages/{id}``       — to the trash (30 days).
* ``POST   /v1/workspace/files``            — upload a voice note or a photo.
* ``GET    /v1/workspace/files/{file}``     — get it back.
* ``GET    /v1/workspace/search?q=``        — pages with every word.
* ``GET    /v1/workspace/export``           — a .zip with JSON + Markdown.
* ``POST   /v1/workspace/shares``           — share a page, block, rows or view.
* ``GET    /v1/workspace/shares``           — the links (optionally of a page).
* ``DELETE /v1/workspace/shares/{token}``   — revoke one.
* ``GET    /s/{token}``                     — the public, read-only copy
  (outside ``/v1``: no key needed, only the token; nothing else reachable).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from openjarvis.workspace.shares import Shares, render_html, scoped_blocks, shared_files
from openjarvis.workspace.store import FILE_TYPES, Conflict, WorkspaceError, default_store

router = APIRouter(tags=["workspace"])
PUBLIC_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; media-src 'self'",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


class PutPage(BaseModel):
    page: Dict[str, Any]
    base_rev: Optional[int] = None


class NewShare(BaseModel):
    page: str
    scope: str = "page"
    block: str = ""
    rows: List[str] = []
    view: str = ""
    days: Optional[int] = None


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/v1/workspace/pages")
async def list_pages() -> Dict[str, Any]:
    store = default_store()
    return {"pages": await asyncio.to_thread(store.list)}


@router.get("/v1/workspace/pages/{page_id}")
async def get_page(page_id: str) -> Dict[str, Any]:
    try:
        page = await asyncio.to_thread(default_store().get, page_id)
    except WorkspaceError as exc:
        raise _bad(exc) from exc
    if page is None:
        raise HTTPException(status_code=404, detail="No encuentro esa página.")
    return {"page": page}


@router.put("/v1/workspace/pages/{page_id}")
async def put_page(page_id: str, body: PutPage) -> Any:
    if body.page.get("id") != page_id:
        raise HTTPException(status_code=400, detail="El identificador no coincide.")
    try:
        saved = await asyncio.to_thread(default_store().put, body.page, body.base_rev)
    except Conflict as exc:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=409,
            content={"detail": "La página cambió en otro sitio.", "page": exc.current, "copy": exc.copy_id},
        )
    except WorkspaceError as exc:
        raise _bad(exc) from exc
    return {"page": saved}


@router.delete("/v1/workspace/pages/{page_id}")
async def delete_page(page_id: str) -> Dict[str, Any]:
    try:
        gone = await asyncio.to_thread(default_store().delete, page_id)
    except WorkspaceError as exc:
        raise _bad(exc) from exc
    return {"deleted": gone}


@router.post("/v1/workspace/files")
async def upload_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    name = file.filename or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if not ext:
        guess = {v: k for k, v in FILE_TYPES.items()}
        ext = guess.get((file.content_type or "").split(";")[0], "")
    data = await file.read(26_000_000)
    try:
        file_id = await asyncio.to_thread(default_store().save_file, data, ext)
    except WorkspaceError as exc:
        raise _bad(exc) from exc
    return {"file": file_id, "name": name or file_id, "mime": FILE_TYPES.get(file_id.rsplit(".", 1)[-1], "")}


@router.get("/v1/workspace/files/{file_id}")
async def get_file(file_id: str) -> FileResponse:
    path = default_store().file_path(file_id)
    if path is None:
        raise HTTPException(status_code=404, detail="No encuentro ese archivo.")
    return FileResponse(path, media_type=FILE_TYPES.get(path.suffix.lstrip("."), "application/octet-stream"))


@router.get("/v1/workspace/search")
async def search(q: str, limit: int = 20) -> Dict[str, Any]:
    hits = await asyncio.to_thread(default_store().search, q, max(1, min(limit, 100)))
    return {"results": hits}


@router.get("/v1/workspace/export")
async def export() -> Response:
    data = await asyncio.to_thread(default_store().export_zip)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="sergio-workspace.zip"'},
    )


@router.post("/v1/workspace/shares")
async def create_share(body: NewShare, request: Request) -> Dict[str, Any]:
    shares = Shares(default_store())
    try:
        record = await asyncio.to_thread(
            lambda: shares.create(
                body.page, body.scope, block_id=body.block, row_ids=body.rows, view_id=body.view, days=body.days
            )
        )
    except WorkspaceError as exc:
        raise _bad(exc) from exc
    base = str(request.base_url).rstrip("/")
    return {**record, "path": f"/s/{record['token']}", "url": f"{base}/s/{record['token']}"}


@router.get("/v1/workspace/shares")
async def list_shares(page: str = "") -> Dict[str, Any]:
    return {"shares": Shares(default_store()).list(page)}


@router.delete("/v1/workspace/shares/{token}")
async def revoke_share(token: str) -> Dict[str, Any]:
    return {"revoked": Shares(default_store()).revoke(token)}


def _shared(token: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    store = default_store()
    record = Shares(store).resolve(token)
    page = store.get(record["page"]) if record else None
    if not record or not page or page.get("sealed"):
        raise HTTPException(status_code=404, detail="Este enlace no existe o ya no está activo.")
    return page, scoped_blocks(page, record)


@router.get("/s/{token}", response_class=HTMLResponse, include_in_schema=False)
async def public_share(token: str) -> HTMLResponse:
    page, blocks = await asyncio.to_thread(_shared, token)
    return HTMLResponse(render_html(page, blocks, token), headers=PUBLIC_HEADERS)


@router.get("/s/{token}/files/{file_id}", include_in_schema=False)
async def public_file(token: str, file_id: str) -> FileResponse:
    _page, blocks = await asyncio.to_thread(_shared, token)
    if file_id not in shared_files(blocks):
        raise HTTPException(status_code=404, detail="No encuentro ese archivo.")
    path = default_store().file_path(file_id)
    if path is None:
        raise HTTPException(status_code=404, detail="No encuentro ese archivo.")
    return FileResponse(path, media_type=FILE_TYPES.get(path.suffix.lstrip("."), "application/octet-stream"),
                        headers=PUBLIC_HEADERS)


__all__ = ["router"]
