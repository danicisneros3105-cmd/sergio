"""The person and their Sergio: profile, skills, model and what is running.

* ``GET/PUT /v1/personal/perfil``           — name, how to be addressed, language, country, greetings
* ``GET     /v1/personal/habilidades``      — Sergio's skills and which are on
* ``PUT     /v1/personal/habilidades/{key}`` — switch one on or off
* ``GET     /v1/personal/modelos``          — every chat model to choose from, by company
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
    ("gemini-4-argon", "Gemini 4 Argon", "El más nuevo y capaz de Google (oct. 2026)."),
    ("gemini-3.8-flash", "Gemini 3.8 Flash", "Rápido y capaz: lo de todos los días."),
    ("gemini-3.6-flash", "Gemini 3.6 Flash", "Rápido y estable."),
    (
        "gemini-3.1-pro-preview",
        "Gemini 3.1 Pro",
        "Piensa mucho: trabajos difíciles.",
    ),
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", "El más ligero y barato."),
)
# Other companies (owner, 27 Oct 2026: «que Sergio no solo sea Gemini, sino
# cualquier modelo del mundo»). Each company is one key; OpenRouter is one key
# for hundreds of models from every lab, so «Otro modelo» takes any of its ids.
PROVIDERS = (
    ("google", "Google", "GEMINI_API_KEY", "https://aistudio.google.com/apikey"),
    ("openai", "OpenAI", "OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
    ("anthropic", "Anthropic", "ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"),
    ("deepseek", "DeepSeek", "DEEPSEEK_API_KEY", "https://platform.deepseek.com/api_keys"),
    ("openrouter", "Todos los demás (OpenRouter)", "OPENROUTER_API_KEY", "https://openrouter.ai/keys"),
)  # fmt: skip
OTHER_CHAT = (
    ("openai", "gpt-5.6-sol", "GPT-5.6 Sol", "El más capaz de OpenAI."),
    ("openai", "gpt-5.6-terra", "GPT-5.6 Terra", "Equilibrado, para todos los días."),
    ("openai", "gpt-5.6-luna", "GPT-5.6 Luna", "El más rápido y barato de OpenAI."),
    ("anthropic", "claude-opus-5-5", "Claude Opus 5.5", "El que más piensa de Anthropic."),
    ("anthropic", "claude-sonnet-5-5", "Claude Sonnet 5.5", "Muy bueno para escribir y programar."),
    ("anthropic", "claude-haiku-5-5", "Claude Haiku 5.5", "Rápido y barato."),
    ("deepseek", "deepseek-v4-pro", "DeepSeek V4 Pro", "Razona a fondo, barato."),
    ("deepseek", "deepseek-v4-flash", "DeepSeek V4 Flash", "Rápido y muy barato."),
    ("openrouter", "openrouter/auto", "Automático (el mejor para cada pedido)", "OpenRouter elige el modelo."),
    ("openrouter", "openrouter/x-ai/grok-4", "Grok 4 (xAI)", ""),
    ("openrouter", "openrouter/meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B (Meta)", "Abierto."),
    ("openrouter", "openrouter/mistralai/mistral-large", "Mistral Large", "Europeo."),
    ("openrouter", "openrouter/qwen/qwen3-235b-a22b", "Qwen 3 235B (Alibaba)", "Abierto."),
)  # fmt: skip
# Checked against public reports on 27 Oct 2026; new models still appear by
# themselves: each connected company's own model list is read (:func:`_discover`).
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


@router.get("/semana")
def get_week() -> Dict[str, Any]:
    """The week in real numbers and what is waiting (semana.py)."""
    from openjarvis import semana

    return semana.resumen()


@router.get("/complementos")
def get_addons() -> Dict[str, Any]:
    return {"complementos": personal.addons()}


@router.put("/complementos/{key}")
def put_addon(key: str, body: Switch) -> Dict[str, Any]:
    if key not in personal.ADDONS:
        raise HTTPException(404, "Ese complemento no existe.")
    on = set(personal.load().get("complementos") or [])
    on.add(key) if body.activa else on.discard(key)
    personal.save({"complementos": sorted(on)})
    return {"complementos": personal.addons()}


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
    # Only Gemini models newer than the list (old and «preview» copies made
    # the sheet too long to read, owner 27 Oct 2026: «más fácil de usar»).
    def _version(mid: str) -> float:
        found = re.match(r"gemini-(\d+(?:\.\d+)?)", mid)
        return float(found.group(1)) if found else 0.0

    newest = max(_version(mid) for mid, _n, _w in GEMINI_CHAT)
    for mid in sorted(have):
        if (
            mid.startswith("gemini-")
            and not _NOT_CHAT.search(mid)
            and "preview" not in mid
            and _version(mid) > newest
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
    for m in out:
        m["empresa"] = "google"
    try:
        from openjarvis.server.cloud_router import _load_keys

        keys = _load_keys()
    except Exception:  # noqa: BLE001
        keys = {}
    connected = {p: bool(keys.get(var)) for p, _n, var, _u in PROVIDERS}
    if not connected["google"] and have:
        connected["google"] = True  # a key from the environment
    known = {m["id"] for m in out} | {mid for _p, mid, _n, _w in OTHER_CHAT}
    extra = [
        (provider, mid, mid, "Nuevo")
        for provider, _n, var, _u in PROVIDERS
        if provider in ("openai", "anthropic", "deepseek") and keys.get(var)
        for mid in _discover(provider, keys[var])
        if mid not in known
    ]
    for provider, mid, name, what in (*OTHER_CHAT, *extra[:12]):
        out.append(
            {
                "id": mid,
                "nombre": name,
                "para": what,
                "empresa": provider,
                "disponible": connected.get(provider, False) or _serves(engine, mid),
            }
        )
    from openjarvis.quota import model_weight

    for m in out:
        m["cuenta"] = model_weight(m["id"])  # messages one answer counts
    return {
        "modelos": out,
        "empresas": [
            {
                "id": p,
                "nombre": n,
                "clave": var,
                "donde": url,
                "conectada": connected[p],
            }
            for p, n, var, url in PROVIDERS
        ],
        "esfuerzos": [{"id": e, "nombre": n, "para": w} for e, n, w in EFFORTS],
        "actual": getattr(request.app.state, "model", "") or "",
    }


_FOUND: Dict[str, tuple] = {}
_CHAT_ID = re.compile(r"^(gpt-\d|o\d|claude-|deepseek-)", re.I)
_NOT_NEW = re.compile(
    r"(audio|realtime|tts|transcribe|image|embed|search|moderation|instruct-"
    r"|\d{4}-\d{2}-\d{2}|\d{8})",
    re.I,
)


def _discover(provider: str, key: str) -> List[str]:
    """The chat models a company lists today (cached 6 h; none if offline)."""
    import time

    cached = _FOUND.get(provider)
    if cached and time.time() - cached[0] < 6 * 3600:
        return cached[1]
    urls = {
        "openai": (
            "https://api.openai.com/v1/models",
            {"Authorization": f"Bearer {key}"},
        ),
        "anthropic": (
            "https://api.anthropic.com/v1/models",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
        ),
        "deepseek": (
            "https://api.deepseek.com/models",
            {"Authorization": f"Bearer {key}"},
        ),
    }
    found: List[str] = []
    try:
        import httpx

        url, headers = urls[provider]
        data = httpx.get(url, headers=headers, timeout=4).json().get("data") or []
        found = sorted(
            {
                str(m.get("id"))
                for m in data
                if _CHAT_ID.match(str(m.get("id")))
                and not _NOT_NEW.search(str(m.get("id")))
            },
            reverse=True,
        )
    except Exception:  # noqa: BLE001 — offline or a bad key: the list above
        found = []
    _FOUND[provider] = (time.time(), found)
    return found


def _serves(engine: Any, model: str) -> bool:
    try:
        return bool(engine is not None and engine.can_serve(model))
    except Exception:  # noqa: BLE001
        return False


class VideoSchedule(BaseModel):
    idea: str
    cada_horas: int = 24
    modo: str = "basic"
    formato: str = "9:16"
    segundos: int = 60
    publicar_en: List[str] = []
    auto: bool = False


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
            publish_to=body.publicar_en,
            auto=body.auto,
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


@router.post("/videos/{item_id}/pausar")
def pause_video_schedule(item_id: str) -> Dict[str, Any]:
    """A plain POST so «En marcha» can stop a channel with one tap."""
    from openjarvis.video_essay import schedule

    if schedule.set_active(item_id, False) is None:
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


@router.get("/videos/trabajos/{job_id}")
def video_job(job_id: str) -> Dict[str, Any]:
    """One video job as the chat card shows it: stage, progress, the video
    when it is ready, or why it stopped (plain words)."""
    from openjarvis.video_essay import job as jobs

    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "No encuentro ese video.")
    st = job.state()
    alive = job.id in {j.id for j in jobs.running()}
    status = st.get("status") or "en curso"
    if status == "en curso" and not alive:
        status = "detenido"  # no thread behind it: never «en curso» for nothing
    res = st.get("result") or {}
    pkg = res.get("package") or {}
    return {
        "id": job.id,
        "titulo": st.get("title") or (st.get("params") or {}).get("topic") or "Video",
        "estado": status,
        "etapa": jobs.LABELS.get(st.get("stage", ""), st.get("stage", "")),
        "paso": (jobs.STAGES.index(st["stage"]) + 1)
        if st.get("stage") in jobs.STAGES
        else 0,
        "pasos": len(jobs.STAGES),
        "avance": float(st.get("stage_progress") or 0),
        "error": str(st.get("error") or "")[:300],
        "video": res.get("url", ""),
        "portada": pkg.get("cover_url", ""),
        "referencia_estado": st.get("referencia_estado", ""),
        "resumen": jobs.summary(st),
    }


@router.post("/videos/trabajos/{job_id}/cancel")
def cancel_video(job_id: str) -> Dict[str, Any]:
    from openjarvis.video_essay import job as jobs

    return {"ok": jobs.cancel(job_id)}


@router.get("/segundo-plano")
def background_tasks() -> Dict[str, Any]:
    """Checks left running in the background, newest last."""
    from openjarvis.asistente import tareas

    return {"tareas": [tareas.plain(t) for t in tareas.load()[-30:]]}


@router.post("/segundo-plano/{task_id}/cancel")
def background_cancel(task_id: str) -> Dict[str, Any]:
    from openjarvis.asistente import tareas

    if not tareas.cancel(task_id):
        raise HTTPException(status_code=404, detail="No está en marcha.")
    return {"ok": True}


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
    try:  # checks left running in the background (asistente/tareas.py)
        from openjarvis.asistente import tareas

        for t in tareas.load():
            if t.get("estado") in tareas.ACTIVE:
                verb = "Vigilando " if t.get("tipo") == "vigilar" else "Revisando "
                rows.append({
                    "tipo": "segundo_plano", "id": t["id"], "quien": "Segundo plano",
                    "que": verb + str(t.get("sitio", ""))[:70],
                    "detener": f"/v1/personal/segundo-plano/{t['id']}/cancel",
                })  # fmt: skip
    except Exception:  # noqa: BLE001
        logger.debug("background tasks unavailable", exc_info=True)
    try:  # the video being made (one at a time)
        from openjarvis.video_essay import job as jobs

        for job in jobs.running():
            st = job.state()
            rows.append({
                "tipo": "video", "id": job.id, "quien": "Video",
                "que": ((st.get("params") or {}).get("prompt") or (st.get("params") or {}).get("topic") or "")[:90],
                "etapa": st.get("stage", ""), "avance": st.get("stage_progress", 0),
                "detener": f"/v1/personal/videos/trabajos/{job.id}/cancel",
            })  # fmt: skip
    except Exception:  # noqa: BLE001
        logger.debug("video jobs unavailable", exc_info=True)
    try:  # the school studying the owner's reference videos
        from openjarvis.video_essay import escuela

        now = escuela.status().get("en_curso") or {}
        if now:
            rows.append({"tipo": "escuela", "id": "escuela", "quien": "Escuela de video",
                         "que": str(now.get("que", ""))[:90]})  # fmt: skip
    except Exception:  # noqa: BLE001
        logger.debug("school unavailable", exc_info=True)
    try:  # channels that post by themselves, and the trading robot
        from openjarvis.automatiza import trading
        from openjarvis.video_essay import schedule

        for item in schedule.load():
            if item.get("activo") and item.get("auto"):
                rows.append({
                    "tipo": "canal", "id": item["id"], "quien": "Canal",
                    "que": f"{str(item.get('idea', ''))[:70]} (cada {item.get('cada_horas')} h)",
                    "detener": f"/v1/personal/videos/{item['id']}/pausar",
                })  # fmt: skip
        ts = trading.settings()
        if ts.activo and not trading.stopped():
            rows.append({
                "tipo": "trading", "id": "trading", "quien": "Trading",
                "que": "Dinero real" if trading.real_money(ts) else "En papel (sin dinero real)",
                "detener": "/v1/automatiza/trading/detener",
            })  # fmt: skip
    except Exception:  # noqa: BLE001
        logger.debug("automation unavailable", exc_info=True)
    return {"en_marcha": rows}


__all__ = ["router"]
