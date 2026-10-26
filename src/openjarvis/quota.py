"""How much each plan may use, and how much was used today.

Free sets the base; every plan multiplies it (Go x2, Work x5, Dev x10-x23,
Founders x25-x60). Use is counted per day on this computer.

The limits only **block** where Sergio is sold as a service
(``SERGIO_PLANES_ACTIVOS=1``). On the owner's own computer (open source,
Apache-2.0) they are shown and counted but never stop anything: a program
that runs on your machine cannot lock you out of yourself.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any, Dict, Optional

# Free's use per day. Change them here: the pages and the blocking follow.
BASE_DAILY: Dict[str, int] = {
    "mensajes": 30,
    "voz": 15,  # minutes of live conversation
    "nodes": 20,  # things the Nodes do
    "swarm": 2,  # swarm runs
    "cowork": 3,  # Cowork tasks
}
LABELS = {
    "mensajes": "Mensajes",
    "voz": "Conversación en voz (min)",
    "nodes": "Acciones de Nodes",
    "swarm": "Enjambres",
    "cowork": "Tareas de Cowork",
}

_lock = threading.Lock()


class QuotaExceeded(Exception):
    """The plan's limit for today is used up (HTTP 402 in the routes)."""

    def __init__(self, kind: str, limit: int, plan: str) -> None:
        self.kind, self.limit, self.plan = kind, limit, plan
        super().__init__(
            f"Se acabó su límite de hoy ({LABELS.get(kind, kind).lower()}: {limit}) "
            f"en el plan {plan}. Mañana vuelve a empezar; o compre créditos o suba de plan en Planes."
        )


def enforcing() -> bool:
    return os.environ.get("SERGIO_PLANES_ACTIVOS", "").strip().lower() in {
        "1",
        "true",
        "si",
        "sí",
    }


def _db() -> sqlite3.Connection:
    from openjarvis.core.paths import get_config_dir

    path = get_config_dir() / "uso_planes.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute(
        "CREATE TABLE IF NOT EXISTS use (day TEXT, kind TEXT, n REAL, PRIMARY KEY (day, kind))"
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return db


def today(now: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now or time.time()))


def multiplier() -> int:
    """How many times Free's use the current plan allows."""
    from openjarvis import tiers

    mine = tiers.current()
    info = tiers.PLAN_INFO[mine["plan"]]
    chosen = int(mine.get("mult") or info.mult)
    return max(info.mult, min(info.mult_max or info.mult, chosen))


def limits(mult: Optional[int] = None) -> Dict[str, int]:
    mult = mult or multiplier()
    return {kind: base * mult for kind, base in BASE_DAILY.items()}


def used(now: Optional[float] = None) -> Dict[str, float]:
    with _lock, _db() as db:
        rows = db.execute(
            "SELECT kind, n FROM use WHERE day = ?", (today(now),)
        ).fetchall()
    return {kind: float(n) for kind, n in rows}


def count(kind: str, n: float = 1, now: Optional[float] = None) -> None:
    """Add *n* to today's use of *kind* (unknown kinds are not counted)."""
    if kind not in BASE_DAILY or n <= 0:
        return
    with _lock, _db() as db:
        db.execute(
            "INSERT INTO use (day, kind, n) VALUES (?, ?, ?) "
            "ON CONFLICT(day, kind) DO UPDATE SET n = n + excluded.n",
            (today(now), kind, n),
        )
        db.execute(
            "DELETE FROM use WHERE day < ?", (today((now or time.time()) - 40 * 86400),)
        )


def check(kind: str) -> None:
    """Raise :class:`QuotaExceeded` if blocking is on and today's limit is used."""
    if not enforcing() or kind not in BASE_DAILY:
        return
    from openjarvis import tiers

    limit = limits()[kind]
    if used().get(kind, 0) >= limit:
        raise QuotaExceeded(kind, limit, tiers.PLAN_INFO[tiers.current()["plan"]].name)


def take(kind: str, n: float = 1) -> None:
    """Check, then count: the one call the routes make before doing the work.

    Past today's limit, bought credits pay for the use (creditos.py)."""
    try:
        check(kind)
    except QuotaExceeded:
        from openjarvis import creditos

        if not creditos.spend(kind):
            raise
    count(kind, n)


def guard(kind: str, n: float = 1) -> None:
    """:func:`take` for HTTP routes: a used-up limit answers 402 (payment needed)."""
    try:
        take(kind, n)
    except QuotaExceeded as exc:
        from fastapi import HTTPException

        raise HTTPException(402, str(exc)) from exc


def status() -> Dict[str, Any]:
    mult = multiplier()
    lim, now = limits(mult), used()
    return {
        "multiplier": mult,
        "blocking": enforcing(),
        "items": [
            {
                "kind": kind,
                "label": LABELS[kind],
                "used": round(now.get(kind, 0), 1),
                "limit": lim[kind],
            }
            for kind in BASE_DAILY
        ],
    }


__all__ = [
    "QuotaExceeded",
    "check",
    "count",
    "guard",
    "limits",
    "status",
    "take",
    "used",
]
