"""Watches, rings, scales and apps that Salud can connect to.

Three ways in, from the most automatic to the most manual:

* ``api``    — Salud asks the service itself, with the owner's personal key
  (the ring's cloud today; others as their APIs allow personal keys).
* ``push``   — the phone sends the data to Salud's sync link on its own
  schedule (an automation app on the phone, or the watch's companion app
  through the phone's health store). Works with any watch the phone reads.
* ``file``   — the owner exports from the device's app and drops the file.

The service names are shown as plain text so the owner knows what to pick;
no logos. Keys are kept in ``~/.openjarvis/health/keys.json`` (owner only).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List

import httpx

from openjarvis.health.importers import Row, parse_time

DEVICES: List[Dict[str, Any]] = [
    {
        "id": "phone_ios",
        "name": "iPhone y Apple Watch",
        "ways": ["push", "file"],
        "how": "Automático: una app de automatización del iPhone envía sus datos de Salud al enlace de "
        "sincronización cada hora. Manual: Salud del iPhone → foto de perfil → Exportar todos los datos, "
        "y suba aquí el export.zip.",
    },
    {
        "id": "android",
        "name": "Android y Wear OS (Health Connect)",
        "ways": ["push", "file"],
        "how": "Automático: una app de automatización que lea Health Connect envía los datos al enlace. "
        "Manual: exporte a CSV y súbalo.",
    },
    {
        "id": "oura",
        "name": "Anillo Oura",
        "ways": ["api", "file"],
        "how": "Pegue su token personal (cloud.ouraring.com → Personal Access Tokens). Salud trae sueño, "
        "variabilidad, pulso en reposo, pasos y oxígeno de los últimos días.",
    },
    {
        "id": "garmin",
        "name": "Garmin",
        "ways": ["push", "file"],
        "how": "Garmin Connect → Datos de salud → Exportar a CSV, o deje que Garmin escriba en la app de salud "
        "del teléfono y use la sincronización automática.",
    },
    {
        "id": "fitbit",
        "name": "Fitbit y Pixel Watch",
        "ways": ["push", "file"],
        "how": "Exporte su cuenta (CSV) o sincronice con Health Connect y use el enlace automático.",
    },
    {
        "id": "samsung",
        "name": "Samsung Galaxy Watch",
        "ways": ["push", "file"],
        "how": "Samsung Health → Ajustes → Descargar datos personales (CSV), o Health Connect + enlace automático.",
    },
    {
        "id": "whoop",
        "name": "Whoop",
        "ways": ["push", "file"],
        "how": "Whoop escribe en la app de salud del teléfono: active la sincronización automática.",
    },
    {
        "id": "withings",
        "name": "Básculas y tensiómetros Withings",
        "ways": ["push", "file"],
        "how": "Withings → Descargar mis datos (CSV con peso, grasa y tensión), o a través del teléfono.",
    },
    {
        "id": "polar",
        "name": "Polar, Coros, Suunto",
        "ways": ["push", "file"],
        "how": "Exporte sus entrenamientos y medidas a CSV, o páselos por la app de salud del teléfono.",
    },
    {
        "id": "glucose",
        "name": "Glucómetros continuos",
        "ways": ["push", "file"],
        "how": "La mayoría escribe en la app de salud del teléfono: active la sincronización automática.",
    },
    {
        "id": "other",
        "name": "Cualquier otro (CSV o JSON)",
        "ways": ["file", "push"],
        "how": "Un CSV con una columna de fecha y una por medida (pasos, peso, pulso…) o el formato JSON de "
        "Sergio. También acepta el JSON de las apps de automatización.",
    },
]


def _keys_path(home: Path) -> Path:
    return Path(home) / "health" / "keys.json"


def load_keys(home: Path) -> Dict[str, Dict[str, Any]]:
    path = _keys_path(home)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_key(home: Path, device: str, token: str) -> None:
    path = _keys_path(home)
    keys = load_keys(home)
    if token:
        keys[device] = {"token": token.strip(), "added": time.time()}
    else:
        keys.pop(device, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(keys), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


# -- the ring's cloud (personal access token) -------------------------------------
OURA_BASE = "https://api.ouraring.com/v2/usercollection"


def oura_get(token: str, endpoint: str, params: Dict[str, str]) -> Dict[str, Any]:
    resp = httpx.get(
        f"{OURA_BASE}/{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30.0,
    )
    if resp.status_code == 401:
        raise PermissionError("El token del anillo no es válido o caducó.")
    resp.raise_for_status()
    return resp.json()


def oura_rows(
    token: str, days: int = 30, get: Callable[..., Dict[str, Any]] = oura_get
) -> Iterator[Row]:
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    params = {"start_date": start, "end_date": end}
    for item in get(token, "sleep", params).get("data", []):
        if item.get("type") not in (None, "long_sleep", "sleep"):
            continue  # naps are not the night
        at = parse_time(item.get("bedtime_end")) or parse_time(item.get("day"))
        uid = f"oura|sleep|{item.get('id') or item.get('day')}"
        for key, metric, factor in (
            ("total_sleep_duration", "sleep_h", 1 / 3600),
            ("deep_sleep_duration", "sleep_deep_h", 1 / 3600),
            ("rem_sleep_duration", "sleep_rem_h", 1 / 3600),
            ("average_hrv", "hrv", 1),
            ("lowest_heart_rate", "resting_hr", 1),
            ("average_breath", "resp_rate", 1),
        ):
            if item.get(key) is not None:
                yield (metric, float(item[key]) * factor, at, "oura", f"{uid}|{metric}")
    for item in get(token, "daily_activity", params).get("data", []):
        at = parse_time(item.get("day"))
        for key, metric in (("steps", "steps"), ("active_calories", "active_kcal")):
            if item.get(key) is not None:
                yield (
                    metric,
                    float(item[key]),
                    at,
                    "oura",
                    f"oura|activity|{item.get('day')}|{metric}",
                )
    try:
        spo2 = get(token, "daily_spo2", params).get("data", [])
    except httpx.HTTPStatusError:
        spo2 = []  # older rings do not measure it
    for item in spo2:
        avg = (item.get("spo2_percentage") or {}).get("average")
        if avg:
            yield (
                "spo2",
                float(avg),
                parse_time(item.get("day")),
                "oura",
                f"oura|spo2|{item.get('day')}",
            )


SYNCERS: Dict[str, Callable[[str], Iterator[Row]]] = {"oura": oura_rows}

__all__ = ["DEVICES", "SYNCERS", "load_keys", "oura_rows", "save_key"]
