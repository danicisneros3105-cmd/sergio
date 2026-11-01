"""«Sergio, prende la calefacción del Tesla»: the car by Tesla's official Fleet API.

Needs the owner's own Fleet API access (``TESLA_ACCESS_TOKEN`` from his
developer app at developer.tesla.com, ``TESLA_REGION`` na/eu/cn, optional
``TESLA_VIN``). Cars on recent software only obey **signed** commands: the
owner runs Tesla's own ``tesla-http-proxy`` (vehicle-command) with his app's
key installed on the car and sets ``TESLA_PROXY_URL``; commands then go
through it. Reading the car's state works without it.

What it does: climate on/off and the temperature, defrost, seat heat, lock,
honk, flash the lights, where it is and its battery. Unlocking and opening
the trunk wait for his yes. **Moving the car** («tráelo a la puerta») is not
in Tesla's public API: Summon and Smart Summon only work from the Tesla app,
with him watching the car, and Sergio says so instead of pretending.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Callable, Dict, Optional

REGIONS = {
    "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.cn",
}
NO_SUMMON = (
    "Mover el auto (Summon / Smart Summon, «tráelo a la puerta») no está en la API "
    "oficial de Tesla: solo se hace desde la app de Tesla en su teléfono y con usted "
    "mirando el auto. Puedo dejarle el auto encendido y climatizado para cuando salga."
)


class TeslaError(RuntimeError):
    """Plain words for the owner."""


def configured() -> bool:
    return bool(os.environ.get("TESLA_ACCESS_TOKEN", "").strip())


def _base(signed: bool) -> str:
    proxy = os.environ.get("TESLA_PROXY_URL", "").strip().rstrip("/")
    if signed and proxy:
        return proxy
    return REGIONS.get(
        os.environ.get("TESLA_REGION", "na").strip().lower(), REGIONS["na"]
    )


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('TESLA_ACCESS_TOKEN', '').strip()}"
    }


def _http() -> Any:
    import httpx

    # tesla-http-proxy uses its own local certificate.
    verify = os.environ.get("TESLA_PROXY_CA", "").strip() or True
    return httpx.Client(timeout=30, verify=verify)


def vin(http: Any = None) -> str:
    chosen = os.environ.get("TESLA_VIN", "").strip()
    if chosen:
        return chosen
    http = http or _http()
    r = http.get(f"{_base(False)}/api/1/vehicles", headers=_headers())
    r.raise_for_status()
    cars = (r.json() or {}).get("response") or []
    if not cars:
        raise TeslaError("Su cuenta de Tesla no tiene autos.")
    return str(cars[0].get("vin") or cars[0].get("id"))


def wake(
    car: str, http: Any = None, sleep: Callable[[float], None] = time.sleep
) -> None:
    http = http or _http()
    for _ in range(10):
        r = http.post(
            f"{_base(False)}/api/1/vehicles/{car}/wake_up", headers=_headers()
        )
        r.raise_for_status()
        if ((r.json() or {}).get("response") or {}).get("state") == "online":
            return
        sleep(3.0)
    raise TeslaError("El auto no despertó (sin señal o dormido profundo).")


def command(
    car: str, name: str, body: Optional[Dict[str, Any]] = None, http: Any = None
) -> Dict[str, Any]:
    http = http or _http()
    r = http.post(
        f"{_base(True)}/api/1/vehicles/{car}/command/{name}",
        headers=_headers(),
        json=body or {},
    )
    if r.status_code in (401, 403):
        raise TeslaError(
            "Tesla rechazó la orden: falta la llave virtual de su app en el auto o "
            "el proxy firmado (TESLA_PROXY_URL)."
        )
    r.raise_for_status()
    res = (r.json() or {}).get("response") or {}
    if res.get("result") is False:
        raise TeslaError(f"El auto no lo hizo: {res.get('reason') or 'sin motivo'}")
    return res


def state(car: str, http: Any = None) -> Dict[str, Any]:
    http = http or _http()
    r = http.get(
        f"{_base(False)}/api/1/vehicles/{car}/vehicle_data",
        params={"endpoints": "charge_state;climate_state;drive_state;vehicle_state"},
        headers=_headers(),
    )
    r.raise_for_status()
    data = (r.json() or {}).get("response") or {}
    ch, cl = data.get("charge_state") or {}, data.get("climate_state") or {}
    dr, vs = data.get("drive_state") or {}, data.get("vehicle_state") or {}
    return {
        "bateria": ch.get("battery_level"),
        "autonomia_km": round(float(ch.get("battery_range") or 0) * 1.609) or None,
        "dentro_c": cl.get("inside_temp"),
        "clima": bool(cl.get("is_climate_on")),
        "cerrado": vs.get("locked"),
        "lat": dr.get("latitude"),
        "lon": dr.get("longitude"),
    }


def do(
    text: str,
    *,
    http: Any = None,
    approver: Any = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """One order in words → the car (or the honest «no se puede»)."""
    from openjarvis.conserje.aprobar import owner_yes

    t = (text or "").lower()
    move = bool(
        re.search(
            r"\b(trae|traer|maneja|manejar|conduce|llevalo|llévalo|mueve|summon|"
            r"puerta de entrada|ven a)\b",
            t,
        )
    )
    note = NO_SUMMON + " " if move else ""
    if move and not re.search(
        r"\b(calefacci[oó]n|calienta|clima|aire|climatiza|temperatura|desempa|"
        r"asiento|bloquea|desbloquea|maletero|cajuela|bocina|pita|luces|bateria|batería)",
        t,
    ):
        return NO_SUMMON
    if not configured():
        return note + (
            "Para su Tesla falta su acceso a la API oficial: TESLA_ACCESS_TOKEN (y "
            "TESLA_PROXY_URL para órdenes firmadas) en sergio.env."
        )
    http = http or _http()
    car = vin(http)
    if re.search(
        r"\b(bateria|batería|carga|donde esta|dónde está|estado|temperatura dentro)\b",
        t,
    ):
        s = state(car, http)
        return (
            f"Batería {s['bateria']} % (unos {s['autonomia_km']} km), dentro "
            f"{s['dentro_c']} °C, clima {'encendido' if s['clima'] else 'apagado'}, "
            f"{'cerrado' if s['cerrado'] else 'abierto'}."
        )
    wake(car, http, sleep)
    done = []
    if re.search(r"\b(calefacci[oó]n|calienta|clima|aire|climatiza|temperatura)\b", t):
        if re.search(r"\b(apaga|quita|para)\b", t):
            command(car, "auto_conditioning_stop", http=http)
            done.append("clima apagado")
        else:
            m = re.search(r"(\d{2})(?:[.,](\d))?\s*(?:°|grados)?", t)
            temp = float(f"{m.group(1)}.{m.group(2) or 0}") if m else (
                24.0 if "calef" in t or "calienta" in t else 21.0)  # fmt: skip
            temp = max(15.0, min(28.0, temp))
            command(car, "auto_conditioning_start", http=http)
            command(
                car, "set_temps", {"driver_temp": temp, "passenger_temp": temp}, http
            )
            done.append(f"clima encendido a {temp:g} °C")
    if re.search(r"\b(desempa[nñ]a|descongela|defrost)\b", t):
        command(car, "set_preconditioning_max", {"on": True}, http)
        done.append("desempañado al máximo")
    if re.search(r"\b(asiento|asientos)\b", t):
        command(car, "remote_seat_heater_request", {"heater": 0, "level": 3}, http)
        done.append("asiento del conductor caliente")
    if re.search(r"\b(desbloquea|abre el auto|abre el carro|unlock)\b", t):
        if owner_yes("Desbloquear su Tesla", {"vin": car[-6:]}, approver=approver):
            command(car, "door_unlock", http=http)
            done.append("desbloqueado")
        else:
            done.append("no lo desbloqueé (sin su sí)")
    elif re.search(r"\b(bloquea|cierra el auto|cierra el carro|lock)\b", t):
        command(car, "door_lock", http=http)
        done.append("cerrado")
    if re.search(r"\b(maletero|cajuela|baul|baúl|trunk)\b", t):
        if owner_yes(
            "Abrir el maletero de su Tesla", {"vin": car[-6:]}, approver=approver
        ):
            command(car, "actuate_trunk", {"which_trunk": "rear"}, http)
            done.append("maletero abierto")
    if re.search(r"\b(pita|bocina|claxon|honk)\b", t):
        command(car, "honk_horn", http=http)
        done.append("bocina")
    if re.search(r"\b(luces|parpadea|flash)\b", t):
        command(car, "flash_lights", http=http)
        done.append("luces")
    if not done:
        return (
            note
            + "No entendí qué hacer con el auto: clima, desempañar, cerrar, bocina o luces."
        )
    return note + "Su Tesla: " + ", ".join(done) + "."


__all__ = [
    "NO_SUMMON",
    "TeslaError",
    "command",
    "configured",
    "do",
    "state",
    "vin",
    "wake",
]
