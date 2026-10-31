"""``GET /v1/actividad``: what Sergio is doing on the computer, in pictures.

The owner (1 Nov 2026): «debe darte imágenes de lo que está haciendo, como
Claude Code app». The desktop's operator keeps a small picture of the screen
and one line per step (``windows/sergio_escritorio/pelicula.py``); this route
asks the desktop for it so the chat can show the strip while the task runs.
No desktop running: an empty strip, never an error page.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Query

router = APIRouter(prefix="/v1/actividad", tags=["actividad"])

EMPTY: Dict[str, Any] = {
    "ok": True,
    "task": 0,
    "state": "idle",
    "goal": "",
    "result": "",
    "frames": [],
}

_fetch: Optional[Callable[[int], Dict[str, Any]]] = None


def _desktop(since: int) -> Dict[str, Any]:
    from openjarvis.tools.desktop_tools import DesktopActionTool

    return DesktopActionTool()._call("GET", f"/film?since={int(since)}", timeout=5)


@router.get("")
def actividad(since: int = Query(0, ge=0)) -> Dict[str, Any]:
    try:
        data = (_fetch or _desktop)(since)
    except Exception:  # noqa: BLE001 — no desktop here: nothing to show
        return dict(EMPTY)
    return {
        **EMPTY,
        **{
            k: data.get(k, EMPTY.get(k))
            for k in ("task", "state", "goal", "result", "frames")
        },
    }


__all__ = ["router"]
