"""Small JSON endpoints the Windows notch shows natively (no browser).

* ``/v1/world/summary`` — latest earthquakes and the next rocket launches
  (God's Eye View data).
* ``/v1/world/goto`` — point the 3D globe at a place; returns the URL the notch
  opens in its own app window.
* ``/v1/ecc/guides`` — the ECC expert playbooks, optionally filtered.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["notch"])


def _lines(result: Any) -> list[str]:
    text = str(getattr(result, "content", "") or "")
    return [ln.lstrip("- ").strip() for ln in text.splitlines()[1:] if ln.strip()]


def world_summary() -> dict[str, Any]:
    from openjarvis.tools.live_world import (
        LiveEarthquakesTool,
        UpcomingLaunchesTool,
        read_globe_target,
    )

    quakes = LiveEarthquakesTool().execute(days=1, limit=6, min_magnitude=4.5)
    launches = UpcomingLaunchesTool().execute(limit=4)
    return {
        "earthquakes": _lines(quakes) if quakes.success else [],
        "launches": _lines(launches) if launches.success else [],
        "errors": [r.content for r in (quakes, launches) if not r.success],
        "target": read_globe_target(),
    }


@router.get("/v1/world/summary")
async def summary() -> dict[str, Any]:
    return await asyncio.to_thread(world_summary)


class GotoRequest(BaseModel):
    place: str
    style: str = "normal"


@router.post("/v1/world/goto")
async def goto(req: GotoRequest) -> dict[str, Any]:
    from openjarvis.tools.live_world import GlobeViewTool

    result = await asyncio.to_thread(
        GlobeViewTool().execute, place=req.place, style=req.style
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.content)
    meta = result.metadata or {}
    return {"label": meta.get("label", req.place), "url": meta.get("url", "")}


@router.post("/v1/world/open")
async def open_globe() -> dict[str, Any]:
    """Make sure the 3D globe is running (start it if needed)."""
    from openjarvis.tools.live_world import ensure_globe

    running, detail = await asyncio.to_thread(ensure_globe)
    if not running:
        raise HTTPException(status_code=503, detail=detail)
    return {"url": detail}


@router.get("/v1/ecc/guides")
async def guides(q: str = "", limit: int = 40) -> dict[str, Any]:
    from openjarvis.unified.ecc import Library

    lib = Library()
    found = lib.search(q, limit=limit) if q.strip() else lib.guides()[:limit]
    return {
        "installed": lib.installed,
        "guides": [
            {"name": g.name, "kind": g.kind, "description": g.description[:200]}
            for g in found
        ],
    }


__all__ = ["router", "world_summary"]
