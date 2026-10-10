"""The web app's Health and Profile pages, read from Sergio Escritorio.

Health data and the personal profile live on the Windows desktop app (kept
there, encrypted). The server asks the desktop's local API for a summary and
can ask it to open one of its sections (the health window, the gym…).

* ``GET  /v1/desktop/health``  — what Sergio knows about your health.
* ``GET  /v1/desktop/profile`` — the profile summary.
* ``POST /v1/desktop/open``    — ``{"section": "health"}`` opens it on the PC.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/desktop", tags=["desktop"])

SECTIONS = frozenset(
    {
        "health",
        "night",
        "gym",
        "results",
        "consult",
        "profile",
        "goals",
        "faces",
        "agents",
    }
)
NOT_REACHABLE = (
    "Sergio Escritorio no responde. Ábralo en Windows (sergio escritorio iniciar)."
)


def _skill(name: str, args: Dict[str, Any] | None = None) -> Any:
    import httpx

    from openjarvis.tools.desktop_tools import _endpoint

    url, headers = _endpoint()
    if not headers["Authorization"].removeprefix("Bearer "):
        raise HTTPException(status_code=503, detail=NOT_REACHABLE)
    try:
        resp = httpx.post(
            f"{url}/skill",
            headers=headers,
            json={"name": name, "args": args or {}},
            timeout=httpx.Timeout(20, connect=3),
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=NOT_REACHABLE) from exc
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code == 404:
        raise HTTPException(
            status_code=501,
            detail="Actualice Sergio Escritorio para ver esto aquí.",
        )
    if resp.status_code != 200 or not data.get("ok", True):
        raise HTTPException(
            status_code=502, detail=str(data.get("error") or resp.status_code)
        )
    return data.get("result")


@router.get("/health")
async def health() -> Dict[str, Any]:
    return await asyncio.to_thread(_skill, "health_summary")


@router.get("/profile")
async def profile() -> Dict[str, Any]:
    return await asyncio.to_thread(_skill, "profile_summary")


class OpenRequest(BaseModel):
    section: str


@router.post("/open")
async def open_section(req: OpenRequest) -> Dict[str, Any]:
    if req.section not in SECTIONS:
        raise HTTPException(status_code=400, detail="Sección desconocida.")
    await asyncio.to_thread(_skill, "open_section", {"section": req.section})
    return {"ok": True}


__all__ = ["SECTIONS", "router"]
