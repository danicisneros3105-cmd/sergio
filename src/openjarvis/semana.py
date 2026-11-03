"""What Sergio really did for the person this week, and what is waiting.

The owner (2 Nov 2026) asked for «efectos psicológicos de dependencia a la
app». Sergio does not use dark patterns: no streaks that guilt, no random
rewards, no «you are missing out», nothing that makes leaving hard (see
``docs/ENGANCHE-SANO.md``). What brings people back is value they can see:

* **the week in real numbers** — answers, minutes of voice, things the Nodes
  and Cowork did, videos finished (from ``quota`` and the video jobs; a
  number that is not counted is not shown);
* **pick up where you left** — the unfinished video or task, one tap away;
* **constancia** (:func:`racha`) — days in a row and the best run, as a thing to
  be proud of. The owner asked on 2 Nov 2026 for a streak «que dé culpa»: the
  streak is here, the guilt is not (a mental-health app must not punish a
  rest day); it is shown only in the profile and can be hidden.

Nothing here is sent anywhere; it is read on this PC.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

LABELS = {
    "mensajes": ("respuesta", "respuestas"),
    "voz": ("minuto de voz", "minutos de voz"),
    "nodes": ("cosa de los Nodes", "cosas de los Nodes"),
    "cowork": ("tarea de Cowork", "tareas de Cowork"),
    "swarm": ("enjambre", "enjambres"),
}


def _days(today: Optional[date] = None) -> List[str]:
    today = today or date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(7)]


def counted(today: Optional[date] = None) -> Dict[str, float]:
    """The owner's own use over the last 7 days (customers count apart)."""
    from openjarvis import quota

    days = _days(today)
    marks = ",".join("?" for _ in days)
    try:
        with quota._lock, quota._db() as db:
            rows = db.execute(
                f"SELECT kind, SUM(n) FROM use WHERE day IN ({marks}) GROUP BY kind",
                days,
            ).fetchall()
    except Exception:  # noqa: BLE001 — no data yet
        return {}
    return {k: float(n or 0) for k, n in rows if n}


def videos(since: float) -> Dict[str, Any]:
    """Videos finished this week and the one still being made."""
    try:
        from openjarvis.video_essay import job as jobs

        states = [j.state() for j in jobs.all_jobs()]
    except Exception:  # noqa: BLE001
        return {"hechos": 0, "en_curso": None}
    done = sum(
        1
        for s in states
        if s.get("status") == "listo" and float(s.get("finished") or 0) >= since
    )
    live = next(
        (s for s in states if s.get("status") not in ("listo", "error", "cancelado")),
        None,
    )
    return {
        "hechos": done,
        "en_curso": {"titulo": live.get("title") or "Video", "etapa": live.get("stage", ""),
                     "avance": float(live.get("stage_progress") or 0)} if live else None,
    }  # fmt: skip


def active_days(back: int = 400) -> List[date]:
    """The days the owner used Sergio (any use counted by ``quota``)."""
    from openjarvis import quota

    since = (date.today() - timedelta(days=back)).isoformat()
    try:
        with quota._lock, quota._db() as db:
            rows = db.execute(
                "SELECT DISTINCT day FROM use WHERE day >= ? AND n > 0", (since,)
            ).fetchall()
    except Exception:  # noqa: BLE001 — no data yet
        return []
    out = []
    for (d,) in rows:
        try:
            out.append(date.fromisoformat(str(d)))
        except ValueError:
            continue
    return sorted(set(out))


def racha(
    days: Optional[List[date]] = None, today: Optional[date] = None
) -> Dict[str, Any]:
    """Days in a row, the best run and the days this month: **a number to be
    proud of, never a debt**. Today does not have to be over for the run to
    count (yesterday's run stays alive until the day ends), a break is simply
    not shown (no «you lost…»), and the person can hide all of it. Nothing
    here warns, nags or sends a notification."""
    today = today or date.today()
    days = sorted(set(days if days is not None else active_days()))
    have = set(days)
    cursor = today if today in have else today - timedelta(days=1)
    now = 0
    while cursor in have:
        now += 1
        cursor -= timedelta(days=1)
    best = run = 0
    prev: Optional[date] = None
    for d in days:
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    month = sum(1 for d in days if d.year == today.year and d.month == today.month)
    return {"seguidos": now, "mejor": best, "este_mes": month, "total": len(days)}


def resumen(
    today: Optional[date] = None, now: Optional[float] = None
) -> Dict[str, Any]:
    now = now or time.time()
    use = counted(today)
    vids = videos(now - 7 * 86400)
    lines = []
    for kind, (one, many) in LABELS.items():
        n = int(round(use.get(kind, 0)))
        if n:
            lines.append(f"{n} {one if n == 1 else many}")
    if vids["hechos"]:
        lines.append(
            f"{vids['hechos']} video{'s' if vids['hechos'] != 1 else ''} terminado{'s' if vids['hechos'] != 1 else ''}"
        )
    return {
        "semana": lines,
        "seguir": vids["en_curso"],
        "numeros": {**use, "videos": vids["hechos"]},
        "racha": racha(),
    }


__all__ = ["active_days", "counted", "racha", "resumen", "videos"]
