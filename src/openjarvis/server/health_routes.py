"""Salud: the owner's health data, insights and device connections.

* ``GET  /v1/healthdata/catalog``            — metrics, categories, devices
* ``GET  /v1/healthdata/summary``            — Resumen: pinned metrics, highlights, readiness
* ``GET  /v1/healthdata/longevity``          — seven areas against public guidance
* ``GET  /v1/healthdata/metric/{key}``       — one metric: daily series and readings
* ``POST /v1/healthdata/samples``            — add a reading by hand; ``DELETE …/samples/{uid}``
* ``PUT  /v1/healthdata/pins`` · ``PUT …/goals/{key}`` — dashboard and goals
* ``GET/PUT /v1/healthdata/notes[/{day}]``   — a note and tags per day
* ``GET  /v1/healthdata/correlations``       — what goes with better sleep, etc.
* ``POST /v1/healthdata/import``             — a file from a watch, ring, scale or phone
* ``GET  /v1/healthdata/sync`` · ``POST …/sync/rotate`` — the live sync link and its key
* ``POST /v1/healthdata/ingest``             — where phones push data (needs the sync key)
* ``POST /v1/healthdata/devices/{id}/key`` · ``…/sync`` · ``DELETE …/devices/{id}``
* ``DELETE /v1/healthdata/sources/{source}`` — remove everything one source brought
* ``GET  /v1/healthdata/export.csv`` · ``GET …/report`` — take the data anywhere
* ``POST /v1/healthdata/ask``                — a question to the coach, with real data only
* ``GET  /v1/healthdata/mind/survey``        — Salud mental: the survey (pictures, scales, open)
* ``POST /v1/healthdata/mind/surveys``       — send answers; scored now, read by the AI ~30 min later
* ``GET  /v1/healthdata/mind/surveys[/{id}]`` · ``DELETE …/{id}`` — past results
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from openjarvis.health import devices, insights
from openjarvis.health.importers import detect_and_parse, from_json
from openjarvis.health.metrics import BY_KEY, CATEGORIES, catalog
from openjarvis.health.store import HealthError, HealthStore, day_of, get_store

router = APIRouter(prefix="/v1/healthdata", tags=["salud"])

MAX_IMPORT_BYTES = 400 * 1024 * 1024  # a decade of phone export fits
MAX_INGEST_BYTES = 20 * 1024 * 1024


def _home():
    from openjarvis.core.paths import get_config_dir

    return get_config_dir()


def _store() -> HealthStore:
    return get_store(_home())


def _metric(key: str) -> None:
    if key not in BY_KEY:
        raise HTTPException(404, "Métrica desconocida.")


@router.get("/catalog")
async def get_catalog() -> Dict[str, Any]:
    return {
        "metrics": catalog(),
        "categories": [{"key": k, "label": v} for k, v in CATEGORIES],
        "devices": devices.DEVICES,
    }


@router.get("/summary")
async def summary() -> Dict[str, Any]:
    store = _store()
    data = await asyncio.to_thread(insights.overview, store)
    today = day_of(time.time())
    connected = sorted(devices.load_keys(_home()))
    return {
        **data,
        "highlights": await asyncio.to_thread(insights.highlights, store),
        "readiness": await asyncio.to_thread(insights.readiness, store),
        "goals": store.goals(),
        "sources": store.sources(),
        "connected": connected,
        "today": today,
        "note": store.notes(2).get(today, {"text": "", "tags": []}),
        "empty": not data["metrics"],
    }


@router.get("/longevity")
async def longevity() -> Dict[str, Any]:
    return {"areas": await asyncio.to_thread(insights.longevity, _store())}


@router.get("/metric/{key}")
async def metric(key: str, days: int = 90) -> Dict[str, Any]:
    _metric(key)
    store = _store()
    days = max(7, min(days, 3650))
    series = store.daily(key, days=days)
    return {
        "metric": BY_KEY[key].public(),
        "summary": insights.metric_summary(store, key),
        "daily": [
            [d, round(v, BY_KEY[key].decimals)] for d, v in sorted(series.items())
        ],
        "readings": store.samples(key, limit=50),
        "goal": store.goals().get(key),
    }


class NewSample(BaseModel):
    metric: str
    value: float
    at: Optional[str] = None  # ISO time; now if missing


@router.post("/samples")
async def add_sample(body: NewSample) -> Dict[str, Any]:
    _metric(body.metric)
    from openjarvis.health.importers import parse_time

    at = parse_time(body.at) if body.at else None
    if body.at and at is None:
        raise HTTPException(400, "Fecha no válida.")
    added = _store().add(body.metric, body.value, at=at, source="manual")
    if not added:
        raise HTTPException(400, "Valor no válido.")
    return {"ok": True}


@router.delete("/samples/{uid}")
async def delete_sample(uid: str) -> Dict[str, Any]:
    if not _store().delete(uid):
        raise HTTPException(404, "No existe ese dato.")
    return {"ok": True}


class Pins(BaseModel):
    pins: List[str]


@router.put("/pins")
async def set_pins(body: Pins) -> Dict[str, Any]:
    return {"pins": _store().set_pins(body.pins)}


class Goal(BaseModel):
    value: Optional[float] = None


@router.put("/goals/{key}")
async def set_goal(key: str, body: Goal) -> Dict[str, Any]:
    _metric(key)
    return {"goals": _store().set_goal(key, body.value)}


class Note(BaseModel):
    text: str = ""
    tags: List[str] = Field(default_factory=list)


@router.get("/notes")
async def notes(days: int = 90) -> Dict[str, Any]:
    store = _store()
    data = store.notes(max(1, min(days, 3650)))
    tags = sorted({t for n in data.values() for t in n["tags"]})
    return {"notes": data, "tags": tags}


@router.put("/notes/{day}")
async def set_note(day: str, body: Note) -> Dict[str, Any]:
    try:
        return _store().set_note(day, body.text, body.tags)
    except HealthError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/correlations")
async def correlations(target: str = "sleep_h", days: int = 90) -> Dict[str, Any]:
    _metric(target)
    return await asyncio.to_thread(
        insights.correlations, _store(), target, max(14, min(days, 730))
    )


@router.post("/import")
async def import_file(file: UploadFile = File(...), source: str = "") -> Dict[str, Any]:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "El archivo es demasiado grande.")
    if not data:
        raise HTTPException(400, "El archivo está vacío.")
    name = file.filename or ""
    label = (source or "").strip()[:40]

    def run() -> Dict[str, Any]:
        store = _store()
        rows = detect_and_parse(name, data, label)
        added = seen = 0
        batch = []
        for row in rows:
            seen += 1
            batch.append(row)
            if len(batch) >= 5000:
                added += store.add_many(batch)
                batch = []
        added += store.add_many(batch)
        return {"read": seen, "added": added}

    try:
        result = await asyncio.to_thread(run)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, str(exc) or "No pude leer ese archivo.") from exc
    except Exception as exc:  # noqa: BLE001 — a broken export must not crash the server
        raise HTTPException(
            400, f"No pude leer ese archivo: {type(exc).__name__}"
        ) from exc
    if not result["read"]:
        raise HTTPException(
            400, "No encontré medidas que Salud conozca en ese archivo."
        )
    return {"ok": True, **result}


@router.get("/sync")
async def sync_info(request: Request) -> Dict[str, Any]:
    store = _store()
    key = store.sync_key()
    return {
        "path": "/v1/healthdata/ingest",
        "key": key,
        "header": f"Authorization: Bearer {key}",
        "example": {
            "samples": [{"metric": "steps", "value": 8421, "at": "2026-10-18T21:00:00"}]
        },
        "metrics": sorted(BY_KEY),
        "sources": store.sources(),
        "last_push": store.get("last_push"),
    }


@router.post("/sync/rotate")
async def rotate_key() -> Dict[str, Any]:
    return {"key": _store().sync_key(rotate=True)}


@router.post("/ingest")
async def ingest(request: Request, key: str = "") -> Dict[str, Any]:
    """Where a phone or watch app pushes data. Needs the sync key (header or ?key=)."""
    store = _store()
    given = (
        key or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )
    if not store.check_sync_key(given):
        raise HTTPException(401, "Clave de sincronización incorrecta.")
    body = await request.body()
    if len(body) > MAX_INGEST_BYTES:
        raise HTTPException(413, "Demasiados datos de una vez.")
    try:
        payload = json.loads(body or b"{}")
        rows = list(
            from_json(
                payload,
                source=str(request.headers.get("x-sergio-source") or "sincronizacion")[
                    :40
                ],
            )
        )
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "JSON no reconocido.") from exc
    added = await asyncio.to_thread(store.add_many, rows)
    store.put("last_push", {"at": time.time(), "read": len(rows), "added": added})
    return {"ok": True, "read": len(rows), "added": added}


class DeviceKey(BaseModel):
    token: str


@router.post("/devices/{device}/key")
async def device_key(device: str, body: DeviceKey) -> Dict[str, Any]:
    if device not in devices.SYNCERS:
        raise HTTPException(
            400, "Ese dispositivo se conecta por archivo o por el enlace automático."
        )
    if len(body.token.strip()) < 8:
        raise HTTPException(400, "Ese token parece incompleto.")
    devices.save_key(_home(), device, body.token)
    return await device_sync(device)


@router.post("/devices/{device}/sync")
async def device_sync(device: str, days: int = 30) -> Dict[str, Any]:
    syncer = devices.SYNCERS.get(device)
    key = devices.load_keys(_home()).get(device, {}).get("token")
    if not syncer or not key:
        raise HTTPException(400, "Primero conecte ese dispositivo.")

    def run() -> Dict[str, Any]:
        rows = list(syncer(key, days=max(1, min(days, 365))))
        return {"read": len(rows), "added": _store().add_many(rows)}

    try:
        result = await asyncio.to_thread(run)
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — network or service down
        raise HTTPException(
            502, f"El servicio no respondió ({type(exc).__name__})."
        ) from exc
    return {"ok": True, **result}


@router.delete("/devices/{device}")
async def device_forget(device: str) -> Dict[str, Any]:
    devices.save_key(_home(), device, "")
    return {"ok": True}


@router.delete("/sources/{source}")
async def delete_source(source: str) -> Dict[str, Any]:
    return {"removed": _store().delete_source(source)}


@router.get("/export.csv")
async def export_csv() -> Response:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["fecha", "metrica", "valor", "unidad", "fuente"])
    for r in _store().all_samples():
        m = BY_KEY.get(r["metric"])
        writer.writerow(
            [
                datetime.fromtimestamp(r["at"]).isoformat(timespec="minutes"),
                r["metric"],
                r["value"],
                m.unit if m else "",
                r["source"],
            ]
        )
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="salud.csv"'},
    )


@router.get("/report")
async def report() -> Dict[str, Any]:
    """What a doctor would want on one page: 30-day averages against guidance."""
    store = _store()
    rows = []
    for key, s in insights.overview(store)["metrics"].items():
        series = store.daily(key, days=30)
        if not series:
            continue
        m = BY_KEY[key]
        values = list(series.values())
        rows.append(
            {
                "label": m.label,
                "unit": m.unit,
                "avg": round(sum(values) / len(values), m.decimals),
                "min": round(min(values), m.decimals),
                "max": round(max(values), m.decimals),
                "days": len(values),
                "status": s["status"],
                "guide": m.guide,
            }
        )
    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "rows": rows,
        "areas": insights.longevity(store),
        "notes": store.notes(30),
    }


class Ask(BaseModel):
    message: str


class Privacy(BaseModel):
    local: bool


@router.get("/privacy")
async def get_privacy() -> Dict[str, Any]:
    from openjarvis.health.privacy import local_only

    return {"local": local_only()}


@router.put("/privacy")
async def put_privacy(body: Privacy) -> Dict[str, Any]:
    """«Solo en este equipo»: the AI never reads health or mental health."""
    from openjarvis.health.privacy import local_only, set_local_only

    set_local_only(body.local)
    return {"local": local_only()}


@router.post("/ask")
async def ask(body: Ask) -> Dict[str, Any]:
    question = body.message.strip()
    if not question:
        raise HTTPException(400, "Escriba su pregunta.")
    facts = insights.known_facts(_store())
    reply = ""
    from openjarvis.health.privacy import local_only, scrub

    if local_only():
        return {
            "reply": "Sus datos de salud se quedan en este equipo, así que no se "
            "los paso a la IA. "
            + (
                f"Lo que sé de usted: {facts}."
                if facts
                else "Aún no tengo datos suyos."
            )
        }
    question = scrub(question)
    try:
        from openjarvis.core.config import load_config
        from openjarvis.engine._discovery import get_engine

        resolved = get_engine(load_config())
        if resolved is not None:
            system = (
                "Eres el coach de salud de Sergio. Habla de usted, cálido y breve (4-5 frases). "
                "No diagnostiques ni inventes cifras: usa solo los datos que siguen y dilo si faltan. "
                "Ante síntomas o valores fuera de rango, recomienda ver a un médico. "
                + (
                    f"Datos reales del señor: {facts}."
                    if facts
                    else "No hay datos del señor todavía."
                )
            )
            res = await asyncio.to_thread(
                resolved[1].generate,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": question},
                ],
                max_tokens=320,
                temperature=0.4,
            )
            reply = (getattr(res, "content", "") or "").strip()
    except Exception:  # noqa: BLE001 — no engine: say so below
        reply = ""
    if not reply:
        reply = "Ahora no puedo pensar la respuesta (el motor no responde). " + (
            f"Lo que sé de usted: {facts}." if facts else "Y aún no tengo datos suyos."
        )
    return {"reply": reply}


# -- Recipes and routines --------------------------------------------------------


class PlanAsk(BaseModel):
    kind: str = Field("receta", pattern="^(receta|rutina)$")
    ask: str = Field("", max_length=600)


PLAN_PROMPT = """Eres el coach de cocina y ejercicio de Sergio. Escribe de usted, claro para \
cualquiera (un niño de 5 o una abuela de 84 deben entenderlo). Pedido: «{ask}».
{facts}
Haz {what}. No diagnostiques ni prometas resultados; si hay una condición médica, \
sugiere consultarlo con su médico. Responde SOLO JSON:
{{"title": "máx. 6 palabras", "minutes": n, "for": "para quién o cuántas porciones / nivel",
"items": ["ingredientes con cantidad" o "material"],
"steps": ["pasos cortos, uno por línea, con tiempos"],
"why": "una frase: por qué le sirve",
"tip": "un consejo corto"}}"""


def _check_plan(text: str) -> Dict[str, Any]:
    data = json.loads(text)
    if not isinstance(data, dict) or not data.get("steps"):
        raise ValueError("sin pasos")
    return data


@router.post("/plan")
async def plan(body: PlanAsk) -> Dict[str, Any]:
    """A recipe or a routine made for the owner (his real data, scrubbed)."""
    from openjarvis.health.privacy import local_only, scrub

    if local_only():
        raise HTTPException(
            409,
            "Sus datos de salud están en «Solo en este equipo»: no los paso a la IA.",
        )
    facts = insights.known_facts(_store())
    what = (
        "una receta sana, rica y sencilla"
        if body.kind == "receta"
        else "una rutina de ejercicio segura, con calentamiento y vuelta a la calma"
    )
    prompt = PLAN_PROMPT.format(
        ask=scrub(body.ask.strip()) or what,
        facts=f"Datos reales del señor: {facts}." if facts else "",
        what=what,
    )
    try:
        from openjarvis.creator.llm import ask as gemini_ask

        raw = await asyncio.to_thread(
            gemini_ask,
            prompt,
            models=("gemini-3.6-flash", "gemini-2.5-flash"),
            json_mode=True,
            check=_check_plan,
            max_tokens=1500,
            timeout=40.0,
        )
        data = _check_plan(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            503, "Ahora no puedo prepararlo; inténtelo en un momento."
        ) from exc
    return {
        "kind": body.kind,
        "title": str(data.get("title") or "")[:80],
        "minutes": data.get("minutes"),
        "for": str(data.get("for") or "")[:120],
        "items": [str(x)[:160] for x in (data.get("items") or [])][:20],
        "steps": [str(x)[:300] for x in (data.get("steps") or [])][:20],
        "why": str(data.get("why") or "")[:300],
        "tip": str(data.get("tip") or "")[:300],
    }


# -- Salud mental ---------------------------------------------------------------

_reading_now: set[str] = set()
_reading_lock = threading.Lock()


def _read_survey(store: HealthStore, sid: str) -> None:
    """Write the AI reading once (from the timer or the first late visit)."""
    from openjarvis.health import mind

    with _reading_lock:
        if sid in _reading_now:
            return
        _reading_now.add(sid)
    try:
        row = store.survey(sid)
        if row is None or row["reading"]:
            return
        variant = mind.variant_of(row["scores"].get("variant", "larga"))
        if mind.VARIANTS[variant].get("widget"):
            # A one-minute card gets the plain reading: no AI call for it.
            text, by = mind.fallback_reading(row["scores"], row["answers"]), "sergio"
        else:
            text, by = mind.write_reading(row["scores"], row["answers"])
        store.set_reading(sid, text, by)
    finally:
        with _reading_lock:
            _reading_now.discard(sid)


def _survey_view(row: Dict[str, Any], *, full: bool) -> Dict[str, Any]:
    from openjarvis.health import mind

    ready = time.time() >= row["ready_at"] and bool(row["reading"])
    variant = mind.variant_of(row["scores"].get("variant", "larga"))
    view: Dict[str, Any] = {
        "id": row["id"],
        "variant": variant,
        "created": row["created"],
        "ready_at": row["ready_at"],
        "status": "ready" if ready else "waiting",
        "crisis": bool(row["scores"].get("crisis")),
        "professional": mind.needs_professional(row["scores"]),
    }
    if view["crisis"]:
        view["crisis_text"] = mind.crisis_text()
    if ready:
        # Scores and reading come together, at the time promised; only the
        # crisis lines above show at once.
        view.update(
            scores=row["scores"], reading=row["reading"], reading_by=row["reading_by"]
        )
        if full:
            view["answers"] = {
                k: v for k, v in row["answers"].items() if k.startswith("open_")
            }
            view["sources"] = mind.sources(variant)
    return view


class SurveyAnswers(BaseModel):
    answers: Dict[str, Any]
    variant: str = "larga"


@router.get("/mind/survey")
def mind_survey(variant: str = "larga") -> Dict[str, Any]:
    from openjarvis.health import mind

    return mind.definition(variant)


@router.post("/mind/surveys")
def mind_submit(body: SurveyAnswers) -> Dict[str, Any]:
    from openjarvis.health import mind

    answers = mind.clean_answers(body.answers)
    scores = mind.score(answers, body.variant)
    if not any(s["score"] is not None for s in scores["scales"]):
        raise HTTPException(400, "Responda al menos una escala completa.")
    store = _store()
    delay = mind.delay_seconds()
    sid = store.add_survey("salud_mental", answers, scores, time.time() + delay)
    timer = threading.Timer(delay, _read_survey, args=(store, sid))
    timer.daemon = True
    timer.start()
    return _survey_view(store.survey(sid) or {}, full=False)


@router.get("/mind/widgets")
def mind_widgets() -> Dict[str, Any]:
    """The short cards (a few validated questions each) and each one's last answer."""
    from openjarvis.health import mind

    rows = _store().surveys("salud_mental", limit=200)
    out = []
    for w in mind.widgets():
        last = next((r for r in rows if r["scores"].get("variant") == w["key"]), None)
        out.append(
            {
                **w,
                "last": _survey_view(last, full=False) if last else None,
            }
        )
    return {"widgets": out, "delay_minutes": round(mind.delay_seconds() / 60)}


@router.get("/mind/surveys")
def mind_list() -> Dict[str, Any]:
    store = _store()
    rows = store.surveys("salud_mental")
    for row in rows:
        if not row["reading"] and time.time() >= row["ready_at"]:
            _read_survey(store, row["id"])
    return {
        "surveys": [_survey_view(store.survey(r["id"]) or r, full=False) for r in rows]
    }


@router.get("/mind/surveys/{sid}")
def mind_result(sid: str) -> Dict[str, Any]:
    store = _store()
    row = store.survey(sid)
    if row is None:
        raise HTTPException(404, "No encuentro esa encuesta.")
    if not row["reading"] and time.time() >= row["ready_at"]:
        _read_survey(store, sid)
        row = store.survey(sid) or row
    return _survey_view(row, full=True)


@router.delete("/mind/surveys/{sid}")
def mind_delete(sid: str) -> Dict[str, Any]:
    if not _store().delete_survey(sid):
        raise HTTPException(404, "No encuentro esa encuesta.")
    return {"ok": True}


# -- Credits: who did the research behind Salud mental and the mental gym ------


@router.get("/credits")
def credits(scope: str = "mente") -> Dict[str, Any]:
    from openjarvis.health import credits as credits_mod

    if scope not in ("mente", "gimnasio"):
        raise HTTPException(400, "Use scope=mente o scope=gimnasio.")
    return credits_mod.credits(scope)


@router.get("/instituciones/{key}/logo")
def institution_logo(key: str) -> Response:
    """A logo the owner added with the institution's permission (never shipped)."""
    from openjarvis.health import credits as credits_mod

    path = credits_mod.logo_path(key)
    if path is None:
        raise HTTPException(404, "No hay logo para esa institución.")
    kind = {".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp"}[
        path.suffix
    ]
    return Response(
        content=path.read_bytes(),
        media_type=kind,
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"
        },
    )


__all__ = ["router"]
