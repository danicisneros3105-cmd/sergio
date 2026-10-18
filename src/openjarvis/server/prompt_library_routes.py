"""The prompt library from the app.

* ``GET  /v1/prompt-library``         — what is installed, from where, how much
* ``POST /v1/prompt-library/sync``    — download every source whole and re-index (background)
* ``GET  /v1/prompt-library/search``  — the passages a request would bring in
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict

from fastapi import APIRouter, Query

router = APIRouter(prefix="/v1/prompt-library", tags=["prompts"])

_job: Dict[str, Any] = {"running": False, "step": "", "error": "", "finished": 0}
_lock = threading.Lock()


def _run() -> None:
    from openjarvis.prompt_library import sync

    try:
        sync(on_step=lambda line: _job.update(step=line))
        _job.update(error="")
    except Exception as exc:  # noqa: BLE001 - reported to the app
        _job.update(error=str(exc)[:300])
    finally:
        _job.update(running=False, step="", finished=int(time.time()))


@router.get("")
def library_status() -> Dict[str, Any]:
    from openjarvis.prompt_library import status

    return {**status(), "job": dict(_job)}


@router.post("/sync")
def library_sync() -> Dict[str, Any]:
    with _lock:
        if not _job["running"]:
            _job.update(running=True, step="Empezando…", error="")
            threading.Thread(
                target=_run, name="prompt-library-sync", daemon=True
            ).start()
    return {"job": dict(_job)}


@router.get("/search")
def library_search(
    q: str = Query(..., min_length=1, max_length=2000), k: int = Query(3, ge=1, le=10)
) -> Dict[str, Any]:
    from openjarvis.prompt_library import search

    return {"found": search(q, k)}


__all__ = ["library_search", "library_status", "library_sync", "router"]
