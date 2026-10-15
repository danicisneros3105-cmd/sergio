"""Connectors over HTTP: ``/v1/mcp`` (what the Extensiones page uses).

Same actions as ``sergio mcp``: the directory, adding (from the directory,
a custom URL, or a local command), connecting with the service's own
sign-in page, per-tool permissions, disconnecting and removing.
"""

from __future__ import annotations

import asyncio
import html
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from openjarvis.mcp.hub import ConnectorError, get_hub

router = APIRouter(prefix="/v1/mcp", tags=["mcp"])


class AddRequest(BaseModel):
    directory_id: Optional[str] = None
    name: str = ""
    url: str = ""
    command: List[str] = []
    args: List[str] = []
    env: Dict[str, str] = {}
    client_id: str = ""
    client_secret: str = ""


class PermissionRequest(BaseModel):
    tool: Optional[str] = None  # None: every tool of the connector
    permission: str


class EnabledRequest(BaseModel):
    enabled: bool


class CallRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}


def _fail(exc: ConnectorError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def redirect_uri(request: Request) -> str:
    """Where the service sends the browser back: this same Sergio."""
    base = str(request.base_url).rstrip("/")
    return f"{base}/v1/mcp/oauth/callback"


@router.get("/directory")
async def directory() -> Dict[str, Any]:
    from openjarvis.mcp.directory import CATEGORIES
    from openjarvis.mcp.directory import directory as entries

    added = {s["directory_id"] for s in get_hub().list() if s.get("directory_id")}
    return {
        "categories": CATEGORIES,
        "connectors": [{**e, "added": e["id"] in added} for e in entries()],
    }


@router.get("/servers")
async def servers(request: Request) -> Dict[str, Any]:
    return {"servers": get_hub().list(), "redirect_uri": redirect_uri(request)}


@router.post("/servers")
async def add(req: AddRequest) -> Dict[str, Any]:
    hub = get_hub()
    try:
        if req.directory_id:
            server = hub.add_from_directory(
                req.directory_id,
                args=req.args,
                client_id=req.client_id,
                client_secret=req.client_secret,
            )
        elif req.url:
            server = hub.add_remote(
                req.name,
                req.url,
                client_id=req.client_id,
                client_secret=req.client_secret,
            )
        elif req.command:
            server = hub.add_local(req.name, [*req.command, *req.args], env=req.env)
        else:
            raise ConnectorError(
                "Indique la URL del servidor MCP o la orden que lo arranca."
            )
    except ConnectorError as exc:
        raise _fail(exc) from exc
    return {"server": server}


@router.get("/servers/{server_id}")
async def get_server(server_id: str) -> Dict[str, Any]:
    try:
        return {"server": get_hub().get(server_id)}
    except ConnectorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/servers/{server_id}")
async def remove(server_id: str) -> Dict[str, Any]:
    await asyncio.to_thread(get_hub().remove, server_id)
    return {"ok": True}


@router.post("/servers/{server_id}/connect")
async def connect(server_id: str, request: Request) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(
            get_hub().connect, server_id, redirect_uri(request)
        )
    except ConnectorError as exc:
        raise _fail(exc) from exc


@router.post("/servers/{server_id}/disconnect")
async def disconnect(server_id: str) -> Dict[str, Any]:
    try:
        return {"server": await asyncio.to_thread(get_hub().disconnect, server_id)}
    except ConnectorError as exc:
        raise _fail(exc) from exc


@router.post("/servers/{server_id}/refresh")
async def refresh(server_id: str) -> Dict[str, Any]:
    try:
        return {"server": await asyncio.to_thread(get_hub().refresh_tools, server_id)}
    except ConnectorError as exc:
        raise _fail(exc) from exc


@router.post("/servers/{server_id}/enabled")
async def enabled(server_id: str, req: EnabledRequest) -> Dict[str, Any]:
    try:
        return {"server": get_hub().set_enabled(server_id, req.enabled)}
    except ConnectorError as exc:
        raise _fail(exc) from exc


@router.post("/servers/{server_id}/permissions")
async def permissions(server_id: str, req: PermissionRequest) -> Dict[str, Any]:
    hub = get_hub()
    try:
        if req.tool:
            return {"server": hub.set_permission(server_id, req.tool, req.permission)}
        return {"server": hub.set_all_permissions(server_id, req.permission)}
    except ConnectorError as exc:
        raise _fail(exc) from exc


@router.post("/servers/{server_id}/call")
async def call(server_id: str, req: CallRequest) -> Dict[str, Any]:
    """Try a tool by hand from the connector page (the owner pressed it,
    so it counts as approved — «Nunca» still blocks it)."""
    try:
        return await asyncio.to_thread(
            get_hub().call, server_id, req.tool, req.arguments, approved=True
        )
    except ConnectorError as exc:
        raise _fail(exc) from exc


_PAGE = """<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sergio</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;font:16px system-ui;
background:#fff;color:#0d0d0d}}
@media (prefers-color-scheme:dark){{body{{background:#212121;color:#ececec}}}}main{{text-align:center;padding:24px}}
h1{{font-size:20px;font-weight:600;margin:0 0 8px}}p{{margin:0;color:#8f8f8f}}</style>
<main><h1>{title}</h1><p>{text}</p></main>
<script>try{{window.opener&&window.opener.postMessage({{sergio:'mcp-connected',ok:{ok}}},'*')}}catch(e){{}}
setTimeout(function(){{window.close()}},{delay})</script></html>"""


@router.get("/oauth/callback", response_class=HTMLResponse)
async def callback(
    state: str = "", code: str = "", error: str = "", error_description: str = ""
) -> HTMLResponse:
    if error:
        text = html.escape(error_description or error)
        return HTMLResponse(
            _PAGE.format(title="No se conectó", text=text, ok="false", delay=6000),
            status_code=400,
        )
    try:
        server = await asyncio.to_thread(get_hub().finish, state, code)
    except ConnectorError as exc:
        return HTMLResponse(
            _PAGE.format(
                title="No se conectó",
                text=html.escape(str(exc)),
                ok="false",
                delay=6000,
            ),
            status_code=400,
        )
    name = html.escape(server["name"])
    return HTMLResponse(
        _PAGE.format(
            title=f"{name} conectado",
            text="Ya puede cerrar esta pestaña.",
            ok="true",
            delay=1200,
        )
    )


__all__ = ["router", "redirect_uri"]
