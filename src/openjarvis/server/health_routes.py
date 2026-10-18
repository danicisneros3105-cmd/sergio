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
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
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


@router.post("/ask")
async def ask(body: Ask) -> Dict[str, Any]:
    question = body.message.strip()
    if not question:
        raise HTTPException(400, "Escriba su pregunta.")
    facts = insights.known_facts(_store())
    reply = ""
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


__all__ = ["router"]
