"""Small JSON endpoints the Windows notch shows natively (no browser).

* ``/v1/world/summary`` — latest earthquakes and the next rocket launches
  (God's Eye View data).
* ``/v1/world/place`` — where a place is, its local time and weather now.
  God's Eye View is hidden: its data answers questions, nothing is shown.
* ``/v1/ecc/guides`` — the ECC expert playbooks, optionally filtered.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

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


@router.get("/v1/world/place")
async def place(q: str) -> dict[str, Any]:
    """Where a place is, its local time and weather now (no globe shown)."""
    from openjarvis.tools.live_world import place_report

    try:
        return await asyncio.to_thread(place_report, {"place": q})
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"No encuentro «{q}».") from exc
    except Exception as exc:  # noqa: BLE001 — a network problem, said plainly
        raise HTTPException(status_code=503, detail=str(exc)[:300]) from exc


@router.get("/v1/world/overhead")
async def overhead(lat: float, lon: float, alt: float | None = None) -> dict[str, Any]:
    """The plane right above the user now (their GPS spot), in seconds.

    The globe is aimed at that plane in the background, so "muéstramelo"
    opens God's Eye View already looking at it.
    """
    from openjarvis.tools.live_world import overhead_report, point_globe

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Coordenadas fuera de rango.")
    try:
        # A hard limit: the answer is due in under 8 seconds, whatever the
        # networks do.
        report = await asyncio.wait_for(
            asyncio.to_thread(overhead_report, lat, lon, ground_m=alt), timeout=7.5
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Las redes de aviones no respondieron en 7 segundos.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if report.get("plane_lat") is not None:
        target = await asyncio.to_thread(
            lambda: point_globe(
                report["plane_lat"],
                report["plane_lon"],
                alt=report["plane_alt_m"] + 9000,
                label=report.get("callsign") or "avión",
                pitch=-90,
            )
        )
        report["globe_url"] = target["url"]
    return report


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


@router.get("/v1/world/flight")
async def flight(q: str) -> dict[str, Any]:
    """A flight right now (by number or call sign), with its route and a
    sentence to say. Nothing is shown: God's Eye View is hidden."""
    from openjarvis.tools.flights_live import describe_flight, find_flight, flight_route

    try:
        found = await asyncio.to_thread(find_flight, q)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    found["route"] = await asyncio.to_thread(flight_route, found["callsign"])
    found["text"] = describe_flight(found)
    return found


__all__ = ["router", "world_summary"]
