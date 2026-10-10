"""A flight followed live, by number or call sign.

From the open ADS-B networks (adsb.lol, adsb.fi): position, altitude, speed
and heading; the route from adsbdb; and the public live map that follows the
plane. Sergio answers in words (God's Eye View is hidden: it is only a
source of facts about the planet now).
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable

import httpx

HttpGet = Callable[[str, dict[str, str]], Any]


def _get(url: str, headers: dict[str, str]) -> Any:
    resp = httpx.get(
        url, headers={"Accept": "application/json", **headers}, timeout=12.0
    )
    resp.raise_for_status()
    return resp.json()


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


FLIGHT_SOURCES = (
    ("adsb.lol", "https://api.adsb.lol/v2/callsign/{cs}"),
    ("adsb.fi", "https://opendata.adsb.fi/api/v2/callsign/{cs}"),
)
AIRLINES = {  # IATA -> ICAO for the flight numbers people say
    "AV": "AVA",
    "LA": "LAN",
    "CM": "CMP",
    "AA": "AAL",
    "UA": "UAL",
    "DL": "DAL",
    "IB": "IBE",
    "UX": "AEA",
    "KL": "KLM",
    "AF": "AFR",
    "BA": "BAW",
    "LH": "DLH",
    "JJ": "TAM",
    "AM": "AMX",
    "AR": "ARG",
    "H2": "SKU",
    "WS": "WJA",
    "AC": "ACA",
    "EK": "UAE",
    "QR": "QTR",
    "TK": "THY",
    "B6": "JBU",
    "NK": "NKS",
    "WN": "SWA",
    "FR": "RYR",
    "U2": "EZY",
    "VY": "VLG",
    "LX": "SWR",
    "AZ": "ITY",
    "TP": "TAP",
    "4C": "ARE",
    "P5": "RPB",
    "XL": "LNE",
    "EQ": "TAE",
}


def callsigns(flight: str) -> list[str]:
    """«AV 123» -> ['AV123', 'AVA123']: what the transponders broadcast."""
    text = re.sub(r"[^A-Z0-9]", "", flight.upper())
    found = re.fullmatch(r"([A-Z0-9]{2,3}?)(\d{1,4}[A-Z]?)", text)
    if not found:
        return [text] if text else []
    prefix, number = found.groups()
    out = [text]
    if len(prefix) == 2 and prefix in AIRLINES:
        out.append(AIRLINES[prefix] + number)
    return out


def find_flight(flight: str, http_get: HttpGet = _get) -> dict[str, Any]:
    """Where a flight is now: position, altitude, speed, heading."""
    for cs in callsigns(flight):
        for name, url in FLIGHT_SOURCES:
            try:
                data = http_get(url.format(cs=cs), {}) or {}
            except Exception:  # noqa: BLE001 — the next network
                continue
            for ac in data.get("ac") or data.get("aircraft") or []:
                lat, lon = _num(ac.get("lat")), _num(ac.get("lon"))
                if lat is None or lon is None:
                    continue
                hexid = str(ac.get("hex") or "").lower()
                alt = ac.get("alt_baro")
                return {
                    "callsign": str(ac.get("flight") or cs).strip(),
                    "hex": hexid,
                    "lat": lat,
                    "lon": lon,
                    "alt_m": round(float(alt) * 0.3048)
                    if isinstance(alt, (int, float))
                    else None,
                    "on_ground": alt == "ground",
                    "speed_kmh": round(float(ac["gs"]) * 1.852)
                    if _num(ac.get("gs")) is not None
                    else None,
                    "track": _num(ac.get("track")),
                    "type": str(ac.get("t") or ac.get("desc") or ""),
                    "registration": str(ac.get("r") or ""),
                    "source": name,
                    "live_map": f"https://globe.adsb.lol/?icao={hexid}"
                    if hexid
                    else "",
                }
    raise LookupError(f"No encuentro el vuelo {flight} en el aire ahora mismo.")


def flight_route(callsign: str, http_get: HttpGet = _get) -> dict[str, str]:
    try:
        data = http_get(f"https://api.adsbdb.com/v0/callsign/{callsign}", {}) or {}
        route = (data.get("response") or {}).get("flightroute") or {}
    except Exception:  # noqa: BLE001 — the route is a bonus
        return {}

    def where(info: Any) -> str:
        info = info or {}
        return ", ".join(
            x for x in (info.get("municipality"), info.get("country_name")) if x
        )

    return {
        "airline": str((route.get("airline") or {}).get("name") or ""),
        "from": where(route.get("origin")),
        "to": where(route.get("destination")),
    }


def describe_flight(found: dict[str, Any]) -> str:
    """One sentence for Sergio to say."""
    route = found.get("route") or {}
    parts = [f"El vuelo {found['callsign']}"]
    if route.get("airline"):
        parts.append(f"de {route['airline']}")
    if route.get("from") and route.get("to"):
        parts.append(f"({route['from']} → {route['to']})")
    where = "está en tierra" if found.get("on_ground") else "va en el aire"
    text = " ".join(parts) + f" {where}"
    if found.get("alt_m") and not found.get("on_ground"):
        text += f" a {found['alt_m']:,} m".replace(",", ".")
    if found.get("speed_kmh"):
        text += f", a {found['speed_kmh']} km/h"
    return text + "."


__all__ = [
    "AIRLINES",
    "FLIGHT_SOURCES",
    "callsigns",
    "describe_flight",
    "find_flight",
    "flight_route",
]
