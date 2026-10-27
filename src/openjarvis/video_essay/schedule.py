"""Videos made on a schedule («cada 3 horas un video»), never posted alone.

The owner (26 Oct 2026): «podrás pedirle que cree videos cada 3 horas… desde
el script y guion hasta la selección de clips y el video en sí y lo postee».

A schedule is an idea (a theme or a series), a format, an effort (the four
modes: Test, Basic, Post quality, Absolut Cinema) and how often. When one is
due, Sergio starts the whole job (director, script, clips, cuts, captions,
master and the posting package) through the same :func:`job.guard` as any
video: one at a time, the same order not twice in half an hour, and the daily
cap (``SERGIO_VIDEO_JOBS_DIA``). A schedule never makes more than that, and a
failure makes the next turn wait instead of retrying in a loop.

**Posting is automatic only where he turns it on.** Until 27 Oct 2026 a
finished video always waited in «Listos para publicar» for his tap. That is
still the default; a schedule with ``auto`` and ``publicar_en`` (YouTube,
Instagram) now goes up by itself through the official APIs
(:mod:`openjarvis.automatiza.canales`, at most ``SERGIO_PUBLICAR_DIA`` a day
per channel) — the owner asked for it: «que suban 3 diarios de forma
automática».
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

EVERY_HOURS = (1, 3, 6, 12, 24, 48, 168)
_LOCK = threading.Lock()


def _path(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = Path(get_config_dir())
    return Path(home) / "video_programados.json"


def load(home: Optional[Path] = None) -> List[Dict[str, Any]]:
    try:
        data = json.loads(_path(home).read_text("utf-8"))
        return (
            [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []
        )
    except (OSError, ValueError):
        return []


def _save(items: List[Dict[str, Any]], home: Optional[Path] = None) -> None:
    path = _path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def add(
    idea: str,
    *,
    every_hours: int = 24,
    mode: str = "basic",
    aspect: str = "9:16",
    seconds: int = 60,
    publish_to: Optional[List[str]] = None,
    auto: bool = False,
    home: Optional[Path] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    from openjarvis.video_essay import modes

    idea = " ".join(str(idea or "").split())[:600]
    if len(idea) < 3:
        raise ValueError("Diga de qué tratan los videos.")
    if every_hours not in EVERY_HOURS:
        raise ValueError("Cada cuánto: 1, 3, 6, 12 o 24 horas, 2 días o una semana.")
    item = {
        "id": secrets.token_hex(4),
        "idea": idea,
        "cada_horas": every_hours,
        "modo": modes.get(mode).key,
        "formato": aspect if aspect in ("16:9", "9:16", "1:1") else "9:16",
        "segundos": max(15, min(1800, int(seconds))),
        "publicar_en": [c for c in (publish_to or []) if c in ("youtube", "instagram")],
        "auto": bool(auto and publish_to),
        "activo": True,
        "proximo": (time.time() if now is None else now)
        + 60,  # the first one in a minute
        "hechos": [],
        "nota": "",
    }
    with _LOCK:
        items = load(home)
        items.append(item)
        _save(items, home)
    return item


def remove(item_id: str, home: Optional[Path] = None) -> bool:
    with _LOCK:
        items = load(home)
        kept = [s for s in items if s.get("id") != item_id]
        _save(kept, home)
        return len(kept) != len(items)


def set_active(
    item_id: str, on: bool, home: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    with _LOCK:
        items = load(home)
        for s in items:
            if s.get("id") == item_id:
                s["activo"] = bool(on)
                _save(items, home)
                return s
    return None


def order_for(item: Dict[str, Any], n: int) -> Dict[str, Any]:
    """The job order for the *n*-th video of a schedule: a new angle each time."""
    return {
        "mode": item["modo"],
        "prompt": (
            f"Serie de videos: {item['idea']}. Este es el número {n}: busque un ángulo, "
            "una historia o un dato que no se haya contado en los anteriores; gancho en "
            "los primeros 2 segundos."
        ),
        "topic": "",
        "script": "",
        "reference": "",
        "style": "",
        "seconds": float(item["segundos"]),
        "aspect": item["formato"],
        "clips": "",
        "music": "",
        "ai_video": False,
        "web_clips": True,
    }


def tick(
    *,
    home: Optional[Path] = None,
    now: Optional[float] = None,
    start: Optional[Callable[[Dict[str, Any]], Any]] = None,
    guard: Optional[Callable[[Dict[str, Any]], tuple]] = None,
) -> List[str]:
    """Start the videos that are due; the ids of the schedules that started one."""
    from openjarvis.video_essay import job as jobs

    start = start or jobs.start
    guard = guard or jobs.guard
    now = time.time() if now is None else now
    started: List[str] = []
    with _LOCK:
        items = load(home)
        for s in items:
            if not s.get("activo") or float(s.get("proximo") or 0) > now:
                continue
            order = order_for(s, len(s.get("hechos") or []) + 1)
            busy, why = guard(order)
            if busy is not None:
                # One at a time and the daily cap: try again in 15 minutes.
                s["nota"] = {"en curso": "Esperando: hay otro video en camino.",
                             "tope diario": "Hoy ya se hizo el máximo de videos.",
                             "repetido": "Ese video ya está hecho."}.get(why, why)  # fmt: skip
                s["proximo"] = now + 15 * 60
                continue
            try:
                made = start(order)
            except Exception as exc:  # noqa: BLE001 — told, and the next turn waits
                s["nota"] = f"No pude empezar el video: {exc}"[:200]
                s["proximo"] = now + float(s["cada_horas"]) * 3600
                continue
            s["hechos"] = (
                list(s.get("hechos") or []) + [getattr(made, "id", str(made))]
            )[-50:]
            s["nota"] = ""
            s["proximo"] = now + float(s["cada_horas"]) * 3600
            started.append(s["id"])
        _save(items, home)
    return started


def ready_to_post(
    home: Optional[Path] = None, root: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Finished scheduled videos waiting for the owner's OK to be posted."""
    from openjarvis.video_essay import job as jobs

    ids = {j for s in load(home) for j in s.get("hechos") or []}
    out = []
    for job in jobs.all_jobs(root):
        st = job.state()
        if job.id not in ids or st.get("status") != "listo" or st.get("publicado"):
            continue
        res = st.get("result") or {}
        pkg = res.get("package") or {}
        out.append(
            {
                "job": job.id,
                "titulo": pkg.get("title")
                or (st.get("params") or {}).get("prompt", "")[:80],
                "descripcion": pkg.get("description") or "",
                "video": res.get("url") or "",
            }
        )
    return out


_loop_started = False


def start_loop(interval: float = 60.0) -> None:
    """Check the schedules once a minute, in the background (idempotent)."""
    global _loop_started
    if _loop_started:
        return
    _loop_started = True

    def run() -> None:
        import logging

        log = logging.getLogger(__name__)
        while True:
            time.sleep(interval)
            try:
                items = load()
                if items:
                    tick()
                if any(s.get("auto") for s in items):
                    from openjarvis.automatiza import canales

                    canales.post_ready()
                # A video left half done by a restart or a crash picks up again
                # (four tries at most, job.MAX_ATTEMPTS) instead of waiting forever.
                from openjarvis.video_essay import job as jobs

                jobs.resume_unfinished()
            except Exception:  # noqa: BLE001 — the loop never dies
                log.exception("scheduled videos")

    threading.Thread(target=run, name="videos-programados", daemon=True).start()


__all__ = [
    "EVERY_HOURS",
    "add",
    "load",
    "order_for",
    "ready_to_post",
    "remove",
    "set_active",
    "start_loop",
    "tick",
]
