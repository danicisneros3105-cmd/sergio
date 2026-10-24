"""Shortcuts wired like the fly brain (see :mod:`openjarvis.connectome`).

* ``GET    /v1/connectome/map``      — the regions and the part of Sergio doing each job
* ``GET    /v1/connectome/learned``  — mushroom body: destinations learned for these words
* ``POST   /v1/connectome/learn``    — dopamine: the owner chose (or dismissed) a destination
* ``DELETE /v1/connectome/memory``   — forget every learned shortcut
* ``POST   /v1/connectome/escape``   — giant fiber: stop what Sergio is doing right now
* ``GET    /v1/connectome/proof``    — the core's measured proof (connectome/proof.py)
* ``POST   /v1/connectome/sleep``    — a night now: every brain consolidates
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from openjarvis.connectome import brain_map, get_memory

router = APIRouter(prefix="/v1/connectome", tags=["atajos"])
logger = logging.getLogger(__name__)


@router.get("/map")
def connectome_map() -> Dict[str, Any]:
    from openjarvis.connectome.brain import get_brain

    return brain_map(get_memory().stats(), get_brain().stats())


@router.get("/proof")
def proof(fresh: bool = False) -> Dict[str, Any]:
    from openjarvis.connectome.proof import proof as measure

    return measure(fresh=fresh)


@router.post("/sleep")
def sleep() -> Dict[str, Any]:
    from openjarvis.connectome.core import get_core
    from openjarvis.connectome.proof import clear_cache

    report = get_core().sleep()
    clear_cache()
    return {"ok": True, "brains": report}


@router.get("/learned")
def learned(q: str = Query("", max_length=300)) -> Dict[str, Any]:
    return {"learned": [{"action": a, "score": s} for a, s in get_memory().predict(q)]}


class Learn(BaseModel):
    query: str = Field("", max_length=300)
    action: str = Field(..., max_length=120)
    reward: float = 1.0


@router.post("/learn")
def learn(body: Learn) -> Dict[str, Any]:
    if not get_memory().reinforce(body.query, body.action, body.reward):
        raise HTTPException(400, "Nada que aprender de eso.")
    return {"ok": True}


@router.delete("/memory")
def forget() -> Dict[str, Any]:
    get_memory().forget()
    return {"ok": True}


@router.post("/escape")
def escape(request: Request) -> Dict[str, Any]:
    """Cancel every Node action, Agent Swarm and Cowork run in progress.

    Only engines that already exist are touched; nothing new is started."""
    state = request.app.state
    stopped = {"nodes": 0, "swarm": 0, "cowork": 0}
    worker = getattr(state, "node_worker", None)
    if worker is not None:
        for node in worker.store.all():
            if getattr(node, "status", "") == "working":
                try:
                    stopped["nodes"] += bool(worker.cancel(node.id))
                except Exception:  # noqa: BLE001 - stop the rest anyway
                    logger.debug("escape: node %s", node.id, exc_info=True)
    for key, attr in (("swarm", "swarm_engine"), ("cowork", "cowork_engine")):
        engine = getattr(state, attr, None)
        if engine is None:
            continue
        for run in engine.list():
            try:
                stopped[key] += bool(engine.cancel(run.id))
            except Exception:  # noqa: BLE001
                logger.debug("escape: %s %s", key, run.id, exc_info=True)
    return {"ok": True, "stopped": stopped}


__all__ = ["Learn", "connectome_map", "escape", "forget", "learn", "learned", "router"]
