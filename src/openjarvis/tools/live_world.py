"""Live world data from the God's Eye View sources, plus globe control.

The globe extension (``extensions/globe``) shows aircraft, earthquakes and
launches on a 3D map. These tools let the assistant answer questions with the
same public, keyless sources and point the embedded globe at a place:

* ``live_flights`` — aircraft near a point (adsb.lol, ADS-B).
* ``live_earthquakes`` — recent earthquakes (USGS FDSN).
* ``upcoming_launches`` — next rocket launches (The Space Devs).
* ``globe_view`` — fly the embedded globe to a place with a visual style.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_USER_AGENT = "OpenJarvis/1.0 (+https://github.com/open-jarvis/OpenJarvis)"
_TIMEOUT = 15.0

HttpGet = Callable[[str, dict[str, Any]], Any]


def _default_get(url: str, params: dict[str, Any]) -> Any:
    import httpx

    resp = httpx.get(
        url, params=params, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def _num(value: Any, name: str, lo: float, hi: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be a number") from None
    if not math.isfinite(out) or not lo <= out <= hi:
        raise ValueError(f"'{name}' must be between {lo} and {hi}")
    return out


def home_country() -> str:
    """Two-letter country to prefer for bare place names ("Cuenca")."""
    import os

    return (os.environ.get("SERGIO_COUNTRY") or "ec").strip().lower()


def geocode(place: str, http_get: HttpGet = _default_get) -> tuple[float, float, str]:
    """Resolve a place name with OpenStreetMap Nominatim (same as the globe).

    A bare name is looked up in the user's country first: "Cuenca" is
    Cuenca, Ecuador for a user in Ecuador (not Cuenca, Spain).
    """
    rows = []
    country = home_country()
    if country and "," not in place:
        try:
            rows = http_get(
                "https://nominatim.openstreetmap.org/search",
                {"q": place, "format": "json", "limit": 1, "countrycodes": country},
            )
        except Exception:  # noqa: BLE001 — try worldwide
            rows = []
    if not rows:
        rows = http_get(
            "https://nominatim.openstreetmap.org/search",
            {"q": place, "format": "json", "limit": 1},
        )
    if not rows:
        raise ValueError(f"Place not found: {place}")
    row = rows[0]
    return float(row["lat"]), float(row["lon"]), str(row.get("display_name", place))


def _location(params: dict[str, Any], http_get: HttpGet) -> tuple[float, float, str]:
    place = str(params.get("place") or "").strip()
    if params.get("lat") is not None and params.get("lon") is not None:
        lat = _num(params["lat"], "lat", -90, 90)
        lon = _num(params["lon"], "lon", -180, 180)
        return lat, lon, place or f"{lat:.4f}, {lon:.4f}"
    if place:
        return geocode(place, http_get)
    raise ValueError("Give either 'place' or both 'lat' and 'lon'.")


_LOCATION_PROPS = {
    "place": {"type": "string", "description": "Place name, e.g. 'Madrid'."},
    "lat": {"type": "number", "description": "Latitude (instead of place)."},
    "lon": {"type": "number", "description": "Longitude (instead of place)."},
}


class _WorldTool(BaseTool):
    def __init__(self, *, http_get: HttpGet = _default_get) -> None:
        self._get = http_get

    def _ok(self, content: str, **meta: Any) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=content, metadata=meta)

    def _fail(self, message: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=message, success=False)

    def execute(self, **params: Any) -> ToolResult:
        try:
            return self._run(params)
        except ValueError as exc:
            return self._fail(str(exc))
        except Exception as exc:  # network / provider errors
            return self._fail(f"{self.tool_id} failed: {exc}")

    def _run(self, params: dict[str, Any]) -> ToolResult:  # pragma: no cover
        raise NotImplementedError


@ToolRegistry.register("live_flights")
class LiveFlightsTool(_WorldTool):
    tool_id = "live_flights"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "List aircraft flying right now near a place (live ADS-B data): "
                "callsign, registration, type, altitude, speed and position."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_LOCATION_PROPS,
                    "radius_km": {
                        "type": "number",
                        "description": "Search radius in km (1-460, default 50).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max rows (default 15).",
                    },
                },
            },
            category="world",
            timeout_seconds=30.0,
        )

    def _run(self, params: dict[str, Any]) -> ToolResult:
        lat, lon, label = _location(params, self._get)
        radius_km = _num(params.get("radius_km", 50), "radius_km", 1, 460)
        limit = int(_num(params.get("limit", 15), "limit", 1, 100))
        radius_nm = max(1, round(radius_km / 1.852))
        data = self._get(f"https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}", {})
        aircraft = [a for a in (data or {}).get("ac", []) if isinstance(a, dict)]
        aircraft.sort(key=lambda a: _distance_km(lat, lon, a.get("lat"), a.get("lon")))
        if not aircraft:
            return self._ok(f"No aircraft within {radius_km:.0f} km of {label}.")
        lines = [f"{len(aircraft)} aircraft within {radius_km:.0f} km of {label}:"]
        for a in aircraft[:limit]:
            dist = _distance_km(lat, lon, a.get("lat"), a.get("lon"))
            lines.append(
                "- {cs} ({reg}, {typ}) alt {alt} ft, {gs} kt, {d}".format(
                    cs=(a.get("flight") or a.get("hex") or "?").strip(),
                    reg=a.get("r") or "?",
                    typ=a.get("t") or "?",
                    alt=a.get("alt_baro", "?"),
                    gs=round(a["gs"]) if isinstance(a.get("gs"), (int, float)) else "?",
                    d=f"{dist:.0f} km away"
                    if math.isfinite(dist)
                    else "position unknown",
                )
            )
        return self._ok("\n".join(lines), count=len(aircraft), lat=lat, lon=lon)


def _distance_km(lat1: float, lon1: float, lat2: Any, lon2: Any) -> float:
    if not isinstance(lat2, (int, float)) or not isinstance(lon2, (int, float)):
        return math.inf
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# -- the plane right above you ----------------------------------------------------------
# Public ADS-B networks (no key). They are asked at the same time; the
# answer is whatever arrives within the time budget.
ADSB_SOURCES = (
    ("adsb.lol", "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}"),
    ("airplanes.live", "https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}"),
    ("adsb.fi", "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}"),
    # God's Eye View's main source; positional rows, converted below.
    (
        "opensky",
        "https://opensky-network.org/api/states/all?lamin={s}&lomin={w}&lamax={n}&lomax={e}",
    ),
)
M = 1 / 0.3048  # feet per metre


def opensky_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """OpenSky's state vectors -> the readsb fields the others use."""
    now = float(data.get("time") or 0)
    rows = []
    for st in data.get("states") or []:
        if not isinstance(st, list) or len(st) < 14 or st[8]:  # on the ground
            continue
        alt = st[13] if st[13] is not None else st[7]
        if st[5] is None or st[6] is None or alt is None:
            continue
        rows.append(
            {
                "hex": st[0],
                "flight": (st[1] or "").strip(),
                "lat": st[6],
                "lon": st[5],
                "alt_geom": alt * M,
                "gs": (st[9] or 0) * 3.6 / KT,
                "track": st[10],
                "baro_rate": (st[11] or 0) * M * 60,
                "seen_pos": max(0.0, now - float(st[3] or now)),
                "squawk": st[14] if len(st) > 14 else None,
            }
        )
    return rows
OVERHEAD_NM = 25  # look this far around (46 km)
FT = 0.3048
KT = 1.852
_COMPASS = ("norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste")


def _quick_get(url: str, params: dict[str, Any], timeout: float = 3.5) -> Any:
    import httpx

    resp = httpx.get(url, params=params, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(degrees: float) -> str:
    return _COMPASS[round(degrees / 45) % 8]


def _move(lat: float, lon: float, track: float, km: float) -> tuple[float, float]:
    """Dead reckoning: where a plane is after flying *km* along *track*."""
    r = km / 6371.0
    p1, t = math.radians(lat), math.radians(track)
    p2 = math.asin(math.sin(p1) * math.cos(r) + math.cos(p1) * math.sin(r) * math.cos(t))
    l2 = math.radians(lon) + math.atan2(
        math.sin(t) * math.sin(r) * math.cos(p1), math.cos(r) - math.sin(p1) * math.sin(p2)
    )
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def plane_geometry(
    lat: float, lon: float, ground_m: float, ac: dict[str, Any], now_lag: float = 0.0
) -> dict[str, Any] | None:
    """Where the plane is seen from you: distance, elevation angle, direction."""
    plat, plon = ac.get("lat"), ac.get("lon")
    alt_ft = ac.get("alt_geom", ac.get("alt_baro"))
    if not isinstance(plat, (int, float)) or not isinstance(plon, (int, float)):
        return None
    if not isinstance(alt_ft, (int, float)):  # "ground" or unknown
        return None
    lag = float(ac.get("seen_pos") or 0.0) + now_lag
    gs, track = ac.get("gs"), ac.get("track")
    if isinstance(gs, (int, float)) and isinstance(track, (int, float)) and 0 < lag < 60:
        plat, plon = _move(plat, plon, track, gs * KT * lag / 3600.0)  # to "now"
    ground_km = _distance_km(lat, lon, plat, plon)
    height_m = alt_ft * FT - ground_m
    elevation = math.degrees(math.atan2(height_m, max(ground_km * 1000.0, 1.0)))
    return {
        "lat": plat,
        "lon": plon,
        "ground_km": ground_km,
        "height_m": height_m,
        "slant_km": math.hypot(ground_km, height_m / 1000.0),
        "elevation": elevation,
        "bearing": bearing_deg(lat, lon, plat, plon),
        "alt_m": alt_ft * FT,
        "alt_ft": alt_ft,
    }


def fetch_aircraft(
    lat: float, lon: float, nm: int, http_get: HttpGet, budget: float = 3.5
) -> tuple[list[dict[str, Any]], list[str]]:
    """All networks at once; merged by aircraft, freshest position wins."""
    from concurrent.futures import ThreadPoolExecutor, wait

    pool = ThreadPoolExecutor(max_workers=len(ADSB_SOURCES))
    dlat = nm * KT / 111.0
    dlon = dlat / max(0.2, math.cos(math.radians(lat)))
    box = {
        "s": f"{lat - dlat:.4f}", "n": f"{lat + dlat:.4f}",
        "w": f"{lon - dlon:.4f}", "e": f"{lon + dlon:.4f}",
    }
    jobs = {
        pool.submit(
            http_get, url.format(lat=f"{lat:.4f}", lon=f"{lon:.4f}", nm=nm, **box), {}
        ): name
        for name, url in ADSB_SOURCES
    }
    done, _late = wait(jobs, timeout=budget)
    pool.shutdown(wait=False, cancel_futures=True)
    merged: dict[str, dict[str, Any]] = {}
    used = []
    for future in done:
        try:
            data = future.result() or {}
        except Exception:  # noqa: BLE001 — that network failed: the others count
            continue
        name = jobs[future]
        rows = opensky_rows(data) if name == "opensky" else (data.get("ac") or data.get("aircraft") or [])
        used.append(name)
        for ac in rows:
            if not isinstance(ac, dict) or not ac.get("hex"):
                continue
            key = str(ac["hex"]).lower()
            old = merged.get(key)
            if old is None or float(ac.get("seen_pos") or 99) < float(old.get("seen_pos") or 99):
                merged[key] = {**(old or {}), **ac, "_source": jobs[future]}
    return list(merged.values()), sorted(used)


def ground_elevation(lat: float, lon: float, http_get: HttpGet) -> float:
    """Height of the ground where you are (Cuenca is ~2 500 m up)."""
    try:
        data = http_get(
            "https://api.open-meteo.com/v1/elevation", {"latitude": lat, "longitude": lon}
        )
        return float((data or {}).get("elevation", [0.0])[0])
    except Exception:  # noqa: BLE001
        return 0.0


def flight_details(ac: dict[str, Any], http_get: HttpGet) -> dict[str, Any]:
    """Airline, route and aircraft from adsbdb (free, no key)."""
    from concurrent.futures import ThreadPoolExecutor

    callsign = str(ac.get("flight") or "").strip()
    hexid = str(ac.get("hex") or "").strip()
    out: dict[str, Any] = {}

    def route() -> Any:
        return http_get(f"https://api.adsbdb.com/v0/callsign/{callsign}", {}) if callsign else None

    def plane() -> Any:
        return http_get(f"https://api.adsbdb.com/v0/aircraft/{hexid}", {}) if hexid else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        r_job, p_job = pool.submit(route), pool.submit(plane)
        for key, job in (("route", r_job), ("aircraft", p_job)):
            try:
                data = (job.result(timeout=3.0) or {}).get("response")
            except Exception:  # noqa: BLE001
                continue
            if isinstance(data, dict):
                out[key] = data.get("flightroute") if key == "route" else data.get("aircraft")
    return out


def _airport(info: dict[str, Any] | None) -> str:
    if not info:
        return ""
    city = info.get("municipality") or info.get("name") or ""
    code = info.get("iata_code") or info.get("icao_code") or ""
    return f"{city} ({code})" if code else city


def describe_plane(ac: dict[str, Any], geo: dict[str, Any], extra: dict[str, Any]) -> str:
    route = extra.get("route") or {}
    plane = extra.get("aircraft") or {}
    callsign = str(ac.get("flight") or "").strip() or "sin indicativo"
    airline = (route.get("airline") or {}).get("name") or ac.get("ownOp") or plane.get("registered_owner") or ""
    number = callsign
    iata = (route.get("airline") or {}).get("iata")
    if iata and callsign[:3].isalpha() and callsign[3:].isdigit():
        number = f"{iata}{callsign[3:]} ({callsign})"
    model = " ".join(
        x for x in (plane.get("manufacturer"), plane.get("type")) if x
    ) or ac.get("desc") or ac.get("t") or "modelo desconocido"
    reg = plane.get("registration") or ac.get("r") or ""
    parts = [f"vuelo {number}" + (f" de {airline}" if airline else "")]
    parts.append(f"{model}" + (f", matrícula {reg}" if reg else ""))
    origin, dest = _airport(route.get("origin")), _airport(route.get("destination"))
    if origin or dest:
        parts.append(f"de {origin or '?'} a {dest or '?'}")
    alt = f"a {geo['alt_m']:,.0f} m ({geo['alt_ft']:,.0f} pies)".replace(",", ".")
    parts.append(alt)
    if isinstance(ac.get("gs"), (int, float)):
        parts.append(f"{ac['gs'] * KT:.0f} km/h")
    if isinstance(ac.get("track"), (int, float)):
        parts.append(f"rumbo {ac['track']:.0f}° (hacia el {compass(ac['track'])})")
    rate = ac.get("baro_rate", ac.get("geom_rate"))
    if isinstance(rate, (int, float)) and abs(rate) >= 300:
        parts.append(("subiendo" if rate > 0 else "bajando") + f" {abs(rate) * FT:.0f} m/min")
    if ac.get("squawk") in ("7500", "7600", "7700"):
        parts.append(f"¡código de emergencia {ac['squawk']}!")
    return ", ".join(parts)


def overhead_report(
    lat: float,
    lon: float,
    *,
    ground_m: float | None = None,
    http_get: HttpGet = _quick_get,
    nm: int = OVERHEAD_NM,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """The aircraft closest to straight above (lat, lon) right now."""
    from concurrent.futures import ThreadPoolExecutor

    started = clock()
    with ThreadPoolExecutor(max_workers=1) as pool:
        ground_job = pool.submit(ground_elevation, lat, lon, http_get) if ground_m is None else None
        aircraft, used = fetch_aircraft(lat, lon, nm, http_get)
        ground = ground_m or 0.0
        if ground_job is not None:
            try:
                ground = ground_job.result(timeout=2.0)
            except Exception:  # noqa: BLE001 — sea level then
                ground = 0.0
    if not used:
        raise RuntimeError("Ninguna red ADS-B respondió a tiempo (sin internet o caídas).")
    seen = []
    for ac in aircraft:
        geo = plane_geometry(lat, lon, ground, ac, now_lag=clock() - started)
        if geo is not None and geo["height_m"] > -100:
            seen.append((geo["elevation"], ac, geo))
    seen.sort(key=lambda row: -row[0])
    out: dict[str, Any] = {
        "lat": lat, "lon": lon, "ground_m": ground, "sources": used,
        "count": len(seen), "utc": datetime.now(timezone.utc).strftime("%H:%M:%S"),
    }
    if not seen:
        out["text"] = (
            f"Ahora mismo no hay aviones con ADS-B a menos de {nm * KT:.0f} km "
            f"(redes: {', '.join(used)}; en Ecuador la cobertura de las redes "
            "abiertas es limitada)."
        )
        return out
    elevation, ac, geo = seen[0]
    extra = flight_details(ac, http_get)
    where = (
        "justo encima de usted"
        if elevation >= 70
        else ("casi encima" if elevation >= 45 else "el más alto en su cielo")
    )
    text = (
        f"{where.capitalize()} (elevación {elevation:.0f}°, a {geo['ground_km']:.1f} km "
        f"en horizontal hacia el {compass(geo['bearing'])}): {describe_plane(ac, geo, extra)}."
    )
    others = [
        f"{str(a.get('flight') or a.get('r') or a.get('hex')).strip()} a {g['ground_km']:.0f} km "
        f"al {compass(g['bearing'])}"
        for _e, a, g in seen[1:4]
    ]
    if others:
        text += " También cerca: " + "; ".join(others) + "."
    text += f" Datos ADS-B en vivo ({', '.join(used)}, {out['utc']} UTC)."
    out.update(
        text=text,
        elevation=round(elevation, 1),
        hex=ac.get("hex"),
        callsign=str(ac.get("flight") or "").strip(),
        plane_lat=geo["lat"],
        plane_lon=geo["lon"],
        plane_alt_m=geo["alt_m"],
        seconds=round(clock() - started, 2),
    )
    return out


@ToolRegistry.register("flights_overhead")
class FlightsOverheadTool(_WorldTool):
    tool_id = "flights_overhead"

    def __init__(self, *, http_get: HttpGet = _quick_get) -> None:
        super().__init__(http_get=http_get)

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Which plane is flying right above a spot RIGHT NOW (live ADS-B): "
                "flight number, airline, aircraft, route, altitude, speed, "
                "direction and how high in the sky it is seen. Use the user's "
                "exact location (lat/lon) when known."
            ),
            parameters={"type": "object", "properties": dict(_LOCATION_PROPS)},
            category="world",
            timeout_seconds=12.0,
        )

    def _run(self, params: dict[str, Any]) -> ToolResult:
        lat, lon, _label = _location(params, self._get)
        report = overhead_report(lat, lon, http_get=self._get)
        return self._ok(report["text"], **{k: v for k, v in report.items() if k != "text"})


@ToolRegistry.register("live_earthquakes")
class LiveEarthquakesTool(_WorldTool):
    tool_id = "live_earthquakes"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Recent earthquakes from USGS, worldwide or near a place: "
                "magnitude, location, depth and time."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_LOCATION_PROPS,
                    "radius_km": {
                        "type": "number",
                        "description": "Radius around the place (default 500).",
                    },
                    "min_magnitude": {
                        "type": "number",
                        "description": "Minimum magnitude (default 4.0).",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Look-back days (default 1).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max rows (default 10).",
                    },
                },
            },
            category="world",
            timeout_seconds=30.0,
        )

    def _run(self, params: dict[str, Any]) -> ToolResult:
        days = int(_num(params.get("days", 1), "days", 1, 30))
        limit = int(_num(params.get("limit", 10), "limit", 1, 100))
        query: dict[str, Any] = {
            "format": "geojson",
            "orderby": "time",
            "limit": limit,
            "minmagnitude": _num(
                params.get("min_magnitude", 4.0), "min_magnitude", 0, 10
            ),
            "starttime": (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
        }
        label = "worldwide"
        if params.get("place") or params.get("lat") is not None:
            lat, lon, label = _location(params, self._get)
            query.update(
                latitude=lat,
                longitude=lon,
                maxradiuskm=_num(params.get("radius_km", 500), "radius_km", 1, 20000),
            )
            label = f"near {label}"
        data = self._get("https://earthquake.usgs.gov/fdsnws/event/1/query", query)
        quakes = (data or {}).get("features", [])
        if not quakes:
            return self._ok(
                f"No earthquakes M{query['minmagnitude']}+ {label} in {days} day(s)."
            )
        lines = [f"Earthquakes M{query['minmagnitude']}+ {label}, last {days} day(s):"]
        for q in quakes:
            p = q.get("properties", {})
            coords = (q.get("geometry") or {}).get("coordinates") or [None, None, None]
            when = datetime.fromtimestamp(p.get("time", 0) / 1000, tz=timezone.utc)
            depth = coords[2] if len(coords) > 2 else None
            lines.append(
                f"- M{p.get('mag')} {p.get('place', '?')} — {when:%Y-%m-%d %H:%M} UTC"
                + (f", depth {depth:.0f} km" if isinstance(depth, (int, float)) else "")
            )
        return self._ok("\n".join(lines), count=len(quakes))


@ToolRegistry.register("upcoming_launches")
class UpcomingLaunchesTool(_WorldTool):
    tool_id = "upcoming_launches"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description="Next scheduled rocket launches worldwide (The Space Devs).",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "How many (default 5)."}
                },
            },
            category="world",
            timeout_seconds=30.0,
        )

    def _run(self, params: dict[str, Any]) -> ToolResult:
        limit = int(_num(params.get("limit", 5), "limit", 1, 20))
        data = self._get(
            "https://ll.thespacedevs.com/2.3.0/launches/upcoming/",
            {"limit": limit, "mode": "list"},
        )
        rows = (data or {}).get("results", [])
        if not rows:
            return self._ok("No upcoming launches found.")
        lines = ["Upcoming launches:"]
        for r in rows:
            status = r.get("status")
            status = status.get("name") if isinstance(status, dict) else status
            pad = r.get("pad")
            where = r.get("location") or (
                ((pad or {}).get("location") or {}).get("name")
                if isinstance(pad, dict)
                else ""
            )
            lines.append(
                f"- {r.get('name', '?')} — {r.get('net', '?')}"
                + (f" — {where}" if where else "")
                + (f" ({status})" if status else "")
            )
        return self._ok("\n".join(lines), count=len(rows))


# Visual styles of the globe (URL names used by its share links).
GLOBE_STYLES = {
    "normal": "normal",
    "night_vision": "nvg",
    "thermal": "flir",
    "retro": "crt",
    "noir": "noir",
    "snow": "snow",
    "anime": "anime",
}


def globe_target_file():
    from openjarvis.unified.paths import state_dir

    return state_dir() / "globe_target.json"


def ensure_globe(wait: float = 90.0) -> tuple[bool, str]:
    """Start the 3D globe service if it is not answering yet.

    Returns (running, url-or-reason). The background service normally keeps
    it up; this covers a stopped service so "open the globe" never lands on
    "localhost refused to connect".
    """
    from openjarvis.core.config import load_config
    from openjarvis.unified.supervisor import Supervisor, port_open

    config = load_config()
    port = config.extensions.globe.port
    url = f"http://127.0.0.1:{port}/"
    if port_open(port):
        return True, url
    sup = Supervisor(config)
    try:
        svc = sup.get("globe")
    except KeyError:
        return False, "El globo 3D está desactivado ([extensions.globe] enabled)."
    outcome = sup.start(svc, wait=wait)
    if port_open(port):
        return True, url
    tail = ""
    try:
        lines = sup.log_file("globe").read_text(errors="replace").splitlines()
        tail = " | ".join(line.strip() for line in lines[-4:] if line.strip())
    except OSError:
        pass
    return False, f"El globo no arrancó: {outcome}" + (f" — {tail}" if tail else "")


def point_globe(
    lat: float,
    lon: float,
    *,
    alt: float = 1500.0,
    style: str = "normal",
    label: str = "",
    pitch: float | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    """Aim the globe (its share-link URL and the embedded globe's target)."""
    if port is None:
        from openjarvis.core.config import load_config

        port = load_config().extensions.globe.port
    if pitch is None:
        pitch = -90 if alt > 200_000 else -35
    fragment = urlencode(
        {
            "lat": f"{lat:.5f}",
            "lon": f"{lon:.5f}",
            "alt": f"{alt:.0f}",
            "heading": 0,
            "pitch": pitch,
            "style": GLOBE_STYLES.get(style, "normal"),
        }
    )
    target = {
        "label": label or f"{lat:.4f}, {lon:.4f}",
        "lat": lat,
        "lon": lon,
        "style": style,
        "hash": fragment,
        "url": f"http://127.0.0.1:{port}/#{fragment}",
        "updated_at": time.time(),
    }
    try:
        globe_target_file().write_text(json.dumps(target))
    except OSError:
        pass
    return target


def read_globe_target() -> dict[str, Any] | None:
    try:
        return json.loads(globe_target_file().read_text())
    except (OSError, ValueError):
        return None


@ToolRegistry.register("globe_view")
class GlobeViewTool(_WorldTool):
    tool_id = "globe_view"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Show a place on the live 3D globe (Globe tab of the app), "
                "optionally with a visual style such as night vision or thermal."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_LOCATION_PROPS,
                    "altitude_m": {
                        "type": "number",
                        "description": "Camera height in meters (default 1500).",
                    },
                    "style": {"type": "string", "enum": sorted(GLOBE_STYLES)},
                },
            },
            category="world",
            timeout_seconds=150.0,  # first start may install the globe
        )

    def _run(self, params: dict[str, Any]) -> ToolResult:
        from openjarvis.core.config import load_config

        lat, lon, label = _location(params, self._get)
        alt = _num(params.get("altitude_m", 1500), "altitude_m", 50, 40_000_000)
        style_key = str(params.get("style") or "normal")
        if style_key not in GLOBE_STYLES:
            choices = ", ".join(sorted(GLOBE_STYLES))
            raise ValueError(f"Unknown style '{style_key}'. Use one of: {choices}")
        target = point_globe(lat, lon, alt=alt, style=style_key, label=label)
        running, detail = ensure_globe()
        if not running:
            return self._fail(detail)
        return self._ok(
            f"Globe pointed at {label} ({style_key}). Show it to the user with "
            f"desktop_action open target={target['url']} (opens in its own window).",
            **target,
        )


__all__ = [
    "FlightsOverheadTool",
    "GLOBE_STYLES",
    "GlobeViewTool",
    "LiveEarthquakesTool",
    "LiveFlightsTool",
    "UpcomingLaunchesTool",
    "ensure_globe",
    "geocode",
    "overhead_report",
    "plane_geometry",
    "point_globe",
    "read_globe_target",
]
