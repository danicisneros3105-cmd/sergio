"""The person and their Sergio: profile, skills, model and what is running.

* ``GET/PUT /v1/personal/perfil``           — name, how to be addressed, language, country, greetings
* ``GET     /v1/personal/habilidades``      — Sergio's skills and which are on
* ``PUT     /v1/personal/habilidades/{key}`` — switch one on or off
* ``GET     /v1/personal/modelos``          — the Gemini models to choose from
* ``GET     /v1/personal/en-marcha``        — everything running right now (Nodes, swarms, Cowork)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from openjarvis import personal

router = APIRouter(prefix="/v1/personal", tags=["personal"])
logger = logging.getLogger(__name__)

# Chat models people choose between (newest first); the engine's own list
# decides which of them this key can really use.
GEMINI_CHAT = (
    ("gemini-3.8-flash", "Gemini 3.8 Flash", "Rápido y capaz: lo de todos los días."),
    ("gemini-3.7-flash", "Gemini 3.7 Flash", "Rápido."),
    ("gemini-3.6-flash", "Gemini 3.6 Flash", "Rápido y estable."),
    ("gemini-3.5-flash", "Gemini 3.5 Flash", "Rápido."),
    (
        "gemini-3.1-pro-preview",
        "Gemini 3.1 Pro",
        "El que más piensa: trabajos difíciles.",
    ),
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", "El más ligero y barato."),
    ("gemini-2.5-pro", "Gemini 2.5 Pro", "Pro de la generación anterior."),
    ("gemini-2.5-flash", "Gemini 2.5 Flash", "Flash de la generación anterior."),
)
EFFORTS = (
    ("auto", "Automático", "Sergio decide cuánto pensar."),
    ("low", "Rápido", "Responde enseguida."),
    ("medium", "Normal", "Piensa un poco."),
    ("high", "A fondo", "Piensa mucho; tarda más."),
)
_NOT_CHAT = re.compile(r"(tts|image|live|embed|aqa|audio|veo|imagen)", re.I)


class Profile(BaseModel):
    nombre: Optional[str] = None
    trato: Optional[str] = None
    idioma: Optional[str] = None
    pais: Optional[str] = None
    tono_saludo: Optional[str] = None
    saludos_propios: Optional[List[str]] = None


class Switch(BaseModel):
    activa: bool


@router.get("/perfil")
def get_profile() -> Dict[str, Any]:
    p = personal.load()
    return {**p, "tratos": list(personal.ADDRESS), "tonos": list(personal.TONES)}


@router.put("/perfil")
def put_profile(body: Profile) -> Dict[str, Any]:
    try:
        p = personal.save({k: v for k, v in body.model_dump().items() if v is not None})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {**p, "tratos": list(personal.ADDRESS), "tonos": list(personal.TONES)}


@router.get("/habilidades")
def get_skills() -> Dict[str, Any]:
    return {"habilidades": personal.skills()}


@router.put("/habilidades/{key}")
def put_skill(key: str, body: Switch) -> Dict[str, Any]:
    known = {s["clave"] for s in personal.skills()}
    if key not in known:
        raise HTTPException(404, "Esa habilidad no existe.")
    off = set(personal.load().get("habilidades_apagadas") or [])
    off.discard(key) if body.activa else off.add(key)
    personal.save({"habilidades_apagadas": sorted(off)})
    return {"habilidades": personal.skills()}


@router.get("/modelos")
def models(request: Request) -> Dict[str, Any]:
    available: List[str] = []
    engine = getattr(request.app.state, "engine", None)
    try:
        available = [str(m) for m in (engine.list_models() if engine else [])]
    except Exception:  # noqa: BLE001 — offline: the known list, unmarked
        available = []
    have = {m.split("@")[0] for m in available}
    out = [
        {
            "id": mid,
            "nombre": name,
            "para": what,
            "disponible": (not have) or mid in have,
        }
        for mid, name, what in GEMINI_CHAT
    ]
    # Gemini chat models the key offers that are not in the list yet (newer ones).
    for mid in sorted(have):
        if (
            mid.startswith("gemini-")
            and not _NOT_CHAT.search(mid)
            and mid not in {m["id"] for m in out}
        ):
            out.append(
                {
                    "id": mid,
                    "nombre": mid.replace("gemini-", "Gemini ").replace("-", " "),
                    "para": "",
                    "disponible": True,
                }
            )
    return {
        "modelos": out,
        "esfuerzos": [{"id": e, "nombre": n, "para": w} for e, n, w in EFFORTS],
        "actual": getattr(request.app.state, "model", "") or "",
    }


class VideoSchedule(BaseModel):
    idea: str
    cada_horas: int = 24
    modo: str = "basic"
    formato: str = "9:16"
    segundos: int = 60


class Active(BaseModel):
    activo: bool


def _videos() -> Dict[str, Any]:
    from openjarvis.video_essay import modes, schedule

    return {
        "programados": schedule.load(),
        "listos": schedule.ready_to_post(),
        "cada": list(schedule.EVERY_HOURS),
        "modos": [{"id": k, "nombre": modes.NAMES[k]} for k in modes.ORDER],
    }


@router.get("/videos")
def videos() -> Dict[str, Any]:
    """Scheduled videos and the finished ones waiting for the owner's OK."""
    return _videos()


@router.post("/videos")
def add_video_schedule(body: VideoSchedule) -> Dict[str, Any]:
    from openjarvis.video_essay import schedule

    try:
        schedule.add(
            body.idea,
            every_hours=body.cada_horas,
            mode=body.modo,
            aspect=body.formato,
            seconds=body.segundos,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _videos()


@router.put("/videos/{item_id}")
def switch_video_schedule(item_id: str, body: Active) -> Dict[str, Any]:
    from openjarvis.video_essay import schedule

    if schedule.set_active(item_id, body.activo) is None:
        raise HTTPException(404, "Esa programación no existe.")
    return _videos()


@router.delete("/videos/{item_id}")
def remove_video_schedule(item_id: str) -> Dict[str, Any]:
    from openjarvis.video_essay import schedule

    if not schedule.remove(item_id):
        raise HTTPException(404, "Esa programación no existe.")
    return _videos()


@router.post("/videos/listos/{job_id}/publicar")
def approve_post(job_id: str) -> Dict[str, Any]:
    """The owner's OK for one video: Sergio hands over everything to post it
    (the file, title and description) and marks it as posted. Nothing is
    uploaded by itself."""
    from openjarvis.video_essay import job as jobs

    job = jobs.get(job_id)
    if job is None or job.state().get("status") != "listo":
        raise HTTPException(404, "Ese video no está listo.")
    job.update(publicado=True)
    res = job.state().get("result") or {}
    pkg = res.get("package") or {}
    return {
        "video": res.get("url", ""),
        "titulo": pkg.get("title", ""),
        "descripcion": pkg.get("description", ""),
    }


@router.post("/videos/trabajos/{job_id}/cancel")
def cancel_video(job_id: str) -> Dict[str, Any]:
    from openjarvis.video_essay import job as jobs

    return {"ok": jobs.cancel(job_id)}


@router.get("/en-marcha")
def running(request: Request) -> Dict[str, Any]:
    """What Sergio, the Nodes, the swarms and Cowork are doing now."""
    rows: List[Dict[str, Any]] = []
    state = request.app.state
    worker = getattr(state, "node_worker", None)
    try:
        for n in worker.store.all() if worker else []:
            if getattr(n, "busy", False) or getattr(n, "status", "") in (
                "working",
                "waiting_approval",
            ):
                rows.append({
                    "tipo": "node", "id": n.id, "quien": n.name,
                    "que": getattr(n, "doing", "") or "Trabajando…",
                    "detener": f"/v1/nodes/{n.id}/cancel",
                })  # fmt: skip
    except Exception:  # noqa: BLE001
        logger.debug("nodes unavailable", exc_info=True)
    for name, kind, label in (
        ("swarm_engine", "enjambre", "Agent Swarm"),
        ("cowork_engine", "cowork", "Cowork"),
    ):
        engine = getattr(state, name, None)
        try:
            for run in engine.list() if engine else []:
                status = getattr(run, "status", "")
                if status not in (
                    "done",
                    "failed",
                    "cancelled",
                    "error",
                    "finished",
                    "stopped",
                ):
                    rows.append({
                        "tipo": kind, "id": run.id, "quien": label,
                        "que": (getattr(run, "task", "") or getattr(run, "goal", ""))[:90],
                        "detener": f"/v1/{'swarm' if kind == 'enjambre' else 'cowork'}/{run.id}/cancel",
                    })  # fmt: skip
        except Exception:  # noqa: BLE001
            logger.debug("%s unavailable", name, exc_info=True)
    try:  # the video being made (one at a time)
        from openjarvis.video_essay import job as jobs

        for job in jobs.running():
            st = job.state()
            rows.append({
                "tipo": "video", "id": job.id, "quien": "Video",
                "que": ((st.get("params") or {}).get("prompt") or (st.get("params") or {}).get("topic") or "")[:90],
                "detener": f"/v1/personal/videos/trabajos/{job.id}/cancel",
            })  # fmt: skip
    except Exception:  # noqa: BLE001
        logger.debug("video jobs unavailable", exc_info=True)
    return {"en_marcha": rows}


__all__ = ["router"]
