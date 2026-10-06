"""Live public cameras near a place, and a flight followed live.

Cameras: only official, public open-data feeds (traffic and weather
cameras that the road authorities publish for everyone), the same ones the
3D globe uses — Transport for London JamCams, Fintraffic (Finland), DriveBC
(British Columbia), Live Traffic NSW (Sydney) and Ontario 511 — plus, if
the user adds a free Windy key (``WINDY_API_KEY``), Windy's public webcams
all over the world. Never private or hacked cameras: only what the owners
publish for the public. Each camera is a still that refreshes every few
seconds.

Flights: by flight number or call sign ("AV123", "IBE6463") from the open
ADS-B networks (adsb.lol, adsb.fi), with the route from adsbdb, and the
public live map that follows the plane.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable

import httpx

HttpGet = Callable[[str, dict[str, str]], Any]
NEAR_KM = 30.0
FAR_KM = 150.0
MAX_CAMS = 12


def _get(url: str, headers: dict[str, str]) -> Any:
    resp = httpx.get(url, headers={"Accept": "application/json", **headers}, timeout=12.0)
    resp.raise_for_status()
    return resp.json()


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _cam(name: str, provider: str, lat: Any, lon: Any, url: str, license_: str) -> dict[str, Any] | None:
    la, lo = _num(lat), _num(lon)
    if la is None or lo is None or not url.startswith("https://"):
        return None
    if not (-90 <= la <= 90 and -180 <= lo <= 180) or (la == 0 and lo == 0):
        return None
    return {"name": " ".join(str(name).split())[:80] or provider, "provider": provider,
            "lat": la, "lon": lo, "url": url, "license": license_}


# -- the feeds (formats as in extensions/globe/server/providers/cctv) --------
def tfl(data: Any) -> list[dict[str, Any]]:
    out = []
    for place in data if isinstance(data, list) else []:
        props = {p.get("key"): p.get("value") for p in place.get("additionalProperties") or [] if isinstance(p, dict)}
        url = str(props.get("imageUrl") or "")
        if str(props.get("available")).lower() != "true" or not url.startswith("https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/"):
            continue
        cam = _cam(place.get("commonName") or "JamCam", "Transport for London", place.get("lat"), place.get("lon"), url, "TfL Open Data")
        if cam:
            out.append(cam)
    return out


def fintraffic(data: Any) -> list[dict[str, Any]]:
    out = []
    for feature in (data or {}).get("features") or []:
        props = feature.get("properties") or {}
        if str(props.get("collectionStatus") or "").upper() != "GATHERING":
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        for preset in props.get("presets") or []:
            pid = str(preset.get("id") or "")
            if preset.get("inCollection") is True and re.fullmatch(r"C\d{7}", pid):
                cam = _cam(props.get("name") or pid, "Fintraffic", coords[1], coords[0],
                           f"https://weathercam.digitraffic.fi/{pid}.jpg", "Fintraffic CC BY 4.0")
                if cam:
                    out.append(cam)
    return out


def drivebc(data: Any) -> list[dict[str, Any]]:
    out = []
    for row in data if isinstance(data, list) else []:
        if row.get("is_on") is not True or row.get("should_appear") is not True:
            continue
        if not isinstance(row.get("id"), int) or row["id"] <= 0:
            continue
        coords = (row.get("location") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        cam = _cam(row.get("name") or row.get("caption") or f"DriveBC {row['id']}", "DriveBC", coords[1], coords[0],
                   f"https://www.drivebc.ca/images/{row['id']}.jpg", "DriveBC (BC Ministry of Transportation)")
        if cam:
            out.append(cam)
    return out


def nsw(data: Any) -> list[dict[str, Any]]:
    out = []
    for feature in (data or {}).get("features") or []:
        props = feature.get("properties") or {}
        url = str(props.get("href") or "")
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if not url.startswith("https://webcams.transport.nsw.gov.au/") or len(coords) < 2:
            continue
        cam = _cam(props.get("view") or props.get("title") or "NSW", "Live Traffic NSW", coords[1], coords[0], url,
                   "Transport for NSW CC BY 4.0")
        if cam:
            out.append(cam)
    return out


def ontario(data: Any) -> list[dict[str, Any]]:
    out = []
    for row in data if isinstance(data, list) else []:
        views = row.get("Views") or row.get("views") or []
        url = ""
        for view in views:
            candidate = str(view.get("Url") or view.get("url") or "")
            status = str(view.get("Status") or "").lower()
            if candidate.startswith("https://511on.ca/map/Cctv/") and status != "disabled":
                url = candidate
                break
        cam = _cam(row.get("Location") or row.get("Roadway") or "Ontario 511", "Ontario 511",
                   row.get("Latitude"), row.get("Longitude"), url, "Open Government Licence - Ontario")
        if cam:
            out.append(cam)
    return out


def windy(data: Any) -> list[dict[str, Any]]:
    out = []
    for cam in (data or {}).get("webcams") or []:
        if str(cam.get("status") or "active") != "active":
            continue
        loc = cam.get("location") or {}
        images = (cam.get("images") or {}).get("current") or {}
        url = str(images.get("preview") or images.get("thumbnail") or "")
        item = _cam(cam.get("title") or loc.get("city") or "Webcam", "Windy Webcams", loc.get("latitude"),
                    loc.get("longitude"), url, "Windy.com webcams (public)")
        if item:
            item["page"] = f"https://www.windy.com/webcams/{cam.get('webcamId')}"
            out.append(item)
    return out


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    parse: Callable[[Any], list[dict[str, Any]]]
    box: tuple[float, float, float, float]  # south, west, north, east
    headers: tuple[tuple[str, str], ...] = ()

    def covers(self, lat: float, lon: float, margin: float = 1.5) -> bool:
        s, w, n, e = self.box
        return s - margin <= lat <= n + margin and w - margin <= lon <= e + margin


FEEDS = (
    Feed("Londres", "https://api.tfl.gov.uk/Place/Type/JamCam", tfl, (51.25, -0.6, 51.75, 0.35)),
    Feed("Finlandia", "https://tie.digitraffic.fi/api/weathercam/v1/stations", fintraffic, (59.5, 19.0, 70.2, 31.7),
         (("Digitraffic-User", "Sergio/1.0"),)),
    Feed("Columbia Británica", "https://www.drivebc.ca/api/webcams/", drivebc, (48.2, -139.1, 60.0, -114.0)),
    Feed("Nueva Gales del Sur", "https://data.livetraffic.com/cameras/traffic-cam.json", nsw, (-37.6, 140.9, -28.1, 153.7)),
    Feed("Ontario", "https://511on.ca/api/v2/get/cameras?format=json&lang=en", ontario, (41.6, -95.2, 56.9, -74.3)),
)
COVERAGE = ", ".join(f.name for f in FEEDS)


def windy_url(lat: float, lon: float, km: float) -> str:
    return (
        "https://api.windy.com/webcams/api/v3/webcams?"
        f"nearby={lat:.4f},{lon:.4f},{int(km)}&include=images,location&limit=30"
    )


def cams_near(
    lat: float, lon: float, *, http_get: HttpGet = _get, windy_key: str = "", limit: int = MAX_CAMS
) -> dict[str, Any]:
    """The closest public cameras to a point (nearest first)."""
    found: list[dict[str, Any]] = []
    used, failed = [], []
    for feed in FEEDS:
        if not feed.covers(lat, lon):
            continue
        try:
            found += feed.parse(http_get(feed.url, dict(feed.headers)))
            used.append(feed.name)
        except Exception:  # noqa: BLE001 — that authority is down: the others count
            failed.append(feed.name)
    if windy_key:
        try:
            found += windy(http_get(windy_url(lat, lon, FAR_KM), {"x-windy-api-key": windy_key}))
            used.append("Windy")
        except Exception:  # noqa: BLE001
            failed.append("Windy")
    for cam in found:
        cam["km"] = round(distance_km(lat, lon, cam["lat"], cam["lon"]), 1)
    found.sort(key=lambda c: c["km"])
    near = [c for c in found if c["km"] <= NEAR_KM] or [c for c in found if c["km"] <= FAR_KM]
    seen, unique = set(), []
    for cam in near:
        if cam["url"] not in seen:
            seen.add(cam["url"])
            unique.append(cam)
    return {"cams": unique[:limit], "sources": used, "failed": failed}


# -- a flight, live -----------------------------------------------------------
FLIGHT_SOURCES = (
    ("adsb.lol", "https://api.adsb.lol/v2/callsign/{cs}"),
    ("adsb.fi", "https://opendata.adsb.fi/api/v2/callsign/{cs}"),
)
AIRLINES = {  # IATA -> ICAO for the flight numbers people say
    "AV": "AVA", "LA": "LAN", "CM": "CMP", "AA": "AAL", "UA": "UAL", "DL": "DAL", "IB": "IBE",
    "UX": "AEA", "KL": "KLM", "AF": "AFR", "BA": "BAW", "LH": "DLH", "JJ": "TAM", "AM": "AMX",
    "AR": "ARG", "H2": "SKU", "WS": "WJA", "AC": "ACA", "EK": "UAE", "QR": "QTR", "TK": "THY",
    "B6": "JBU", "NK": "NKS", "WN": "SWA", "FR": "RYR", "U2": "EZY", "VY": "VLG", "LX": "SWR",
    "AZ": "ITY", "TP": "TAP", "4C": "ARE", "P5": "RPB", "XL": "LNE", "EQ": "TAE",
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
                    "alt_m": round(float(alt) * 0.3048) if isinstance(alt, (int, float)) else None,
                    "on_ground": alt == "ground",
                    "speed_kmh": round(float(ac["gs"]) * 1.852) if _num(ac.get("gs")) is not None else None,
                    "track": _num(ac.get("track")),
                    "type": str(ac.get("t") or ac.get("desc") or ""),
                    "registration": str(ac.get("r") or ""),
                    "source": name,
                    "live_map": f"https://globe.adsb.lol/?icao={hexid}" if hexid else "",
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
        return ", ".join(x for x in (info.get("municipality"), info.get("country_name")) if x)

    return {
        "airline": str((route.get("airline") or {}).get("name") or ""),
        "from": where(route.get("origin")),
        "to": where(route.get("destination")),
    }


__all__ = ["COVERAGE", "FEEDS", "callsigns", "cams_near", "find_flight", "flight_route"]
