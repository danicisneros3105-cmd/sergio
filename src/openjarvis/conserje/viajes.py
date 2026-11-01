"""Flights, hotels and a whole trip to a budget.

* ``search_flights`` — real offers with real prices from Duffel
  (``DUFFEL_ACCESS_TOKEN`` in sergio.env, duffel.com); without the key, links
  to Google Flights, Kayak and Skyscanner with the search filled in.
* ``plan_trip`` — «hazme un viaje a China con 3 000 dólares»: the budget split,
  the real cheapest fare when there is a key, a day-by-day itinerary for his
  interests, hotels, local transport, documents and a checklist. Every booking
  is a step he confirms.

Booking itself happens on the airline's or the agency's page on his own
screen (Sergio fills it and stops before paying): an order needs his name,
passport, e-mail and payment, and his e-mail and card never go to a service
through Sergio.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openjarvis.conserje import enlaces

DUFFEL = "https://api.duffel.com"
SPLIT = {  # an orientative split of a trip budget (said as such)
    "vuelos": 0.35,
    "alojamiento": 0.30,
    "comida": 0.15,
    "transporte local": 0.10,
    "actividades": 0.10,
}


def _token() -> str:
    return str(os.environ.get("DUFFEL_ACCESS_TOKEN", "")).strip()


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Duffel-Version": "v2",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _http() -> Any:
    import httpx

    return httpx.Client(timeout=40)


def iata(place: str, http: Any = None) -> str:
    """An airport or city code for *place* («Quito» → «UIO»)."""
    p = (place or "").strip()
    if re.fullmatch(r"[A-Za-z]{3}", p):
        return p.upper()
    if not _token():
        return ""
    http = http or _http()
    r = http.get(
        f"{DUFFEL}/places/suggestions", params={"query": p}, headers=_headers()
    )
    r.raise_for_status()
    for item in (r.json() or {}).get("data") or []:
        code = item.get("iata_code") or item.get("iata_city_code")
        if code:
            return str(code)
    return ""


@dataclass
class Offer:
    precio: float
    moneda: str
    aerolinea: str
    salida: str
    llegada: str
    escalas: int
    duracion: str
    id: str = ""

    def line(self) -> str:
        stops = "directo" if self.escalas == 0 else f"{self.escalas} escala(s)"
        return (
            f"{self.precio:,.2f} {self.moneda} · {self.aerolinea} · sale {self.salida} · "
            f"llega {self.llegada} · {stops} · {self.duracion}"
        )


def search_flights(
    origin: str,
    destination: str,
    date: str,
    *,
    back: str = "",
    adults: int = 1,
    cabin: str = "economy",
    limit: int = 5,
    http: Any = None,
) -> Dict[str, Any]:
    """``{"ofertas": [Offer…], "enlaces": {...}, "fuente": "Duffel"|""}``."""
    links = enlaces.flights(origin, destination, date, back)
    if not _token():
        return {"ofertas": [], "enlaces": links, "fuente": ""}
    http = http or _http()
    o, d = iata(origin, http), iata(destination, http)
    if not o or not d:
        return {
            "ofertas": [],
            "enlaces": links,
            "fuente": "",
            "nota": "No encontré el aeropuerto.",
        }
    slices = [{"origin": o, "destination": d, "departure_date": date}]
    if back:
        slices.append({"origin": d, "destination": o, "departure_date": back})
    body = {"data": {
        "slices": slices,
        "passengers": [{"type": "adult"} for _ in range(max(1, adults))],
        "cabin_class": cabin,
    }}  # fmt: skip
    r = http.post(
        f"{DUFFEL}/air/offer_requests",
        params={"return_offers": "true", "supplier_timeout": 20000},
        headers=_headers(),
        json=body,
    )
    r.raise_for_status()
    offers = []
    for raw in ((r.json() or {}).get("data") or {}).get("offers") or []:
        try:
            first = raw["slices"][0]
            segs = first["segments"]
            offers.append(Offer(
                precio=float(raw["total_amount"]),
                moneda=str(raw["total_currency"]),
                aerolinea=str((raw.get("owner") or {}).get("name") or ""),
                salida=str(segs[0]["departing_at"]).replace("T", " ")[:16],
                llegada=str(segs[-1]["arriving_at"]).replace("T", " ")[:16],
                escalas=len(segs) - 1,
                duracion=_duration(first.get("duration") or ""),
                id=str(raw.get("id") or ""),
            ))  # fmt: skip
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    offers.sort(key=lambda x: (x.precio, x.escalas))
    return {"ofertas": offers[:limit], "enlaces": links, "fuente": "Duffel"}


def _duration(iso: str) -> str:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", iso or "")
    if not m or not any(m.groups()):
        return ""
    days, hours, mins = (int(x or 0) for x in m.groups())
    return f"{days * 24 + hours} h {mins:02d} min"


# -- a whole trip ----------------------------------------------------------------------


@dataclass
class Trip:
    id: str
    destino: str
    origen: str
    dias: int
    presupuesto: float
    moneda: str
    personas: int
    fecha: str = ""
    reparto: Dict[str, float] = field(default_factory=dict)
    vuelo_mas_barato: str = ""
    itinerario: List[Dict[str, str]] = field(default_factory=list)
    enlaces: Dict[str, Dict[str, str]] = field(default_factory=dict)
    documentos: List[str] = field(default_factory=list)
    pasos: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _home() -> Path:
    base = os.environ.get("OPENJARVIS_HOME") or str(Path.home() / ".openjarvis")
    return Path(base) / "viajes"


def plan_trip(
    destination: str,
    *,
    days: int = 7,
    budget: float = 0.0,
    currency: str = "USD",
    origin: str = "",
    start: str = "",
    people: int = 1,
    interests: str = "",
    ask: Optional[Callable[[str], str]] = None,
    flights: Optional[Callable[..., Dict[str, Any]]] = None,
    root: Optional[Path] = None,
) -> Trip:
    """The plan; every booking in it waits for the owner's yes."""
    if not destination.strip():
        raise ValueError("Dígame a dónde quiere ir.")
    days = max(1, min(60, int(days or 7)))
    trip = Trip(uuid.uuid4().hex[:10], destination.strip(), origin.strip(), days,
                float(budget or 0), currency, max(1, int(people or 1)), start)  # fmt: skip
    if trip.presupuesto:
        trip.reparto = {k: round(trip.presupuesto * v, 2) for k, v in SPLIT.items()}
    back = ""
    if start and re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
        from datetime import date, timedelta

        back = (date.fromisoformat(start) + timedelta(days=days)).isoformat()
    if origin and start:
        try:
            found = (flights or search_flights)(origin, destination, start, back=back,
                                                 adults=trip.personas)  # fmt: skip
        except Exception:  # noqa: BLE001 — the links still work
            found = {
                "ofertas": [],
                "enlaces": enlaces.flights(origin, destination, start, back),
            }
        offers = found.get("ofertas") or []
        if offers:
            best = offers[0]
            trip.vuelo_mas_barato = best.line() + " (precio real, Duffel)"
            if trip.presupuesto and best.moneda == currency:
                rest = max(0.0, trip.presupuesto - best.precio)
                share = sum(v for k, v in SPLIT.items() if k != "vuelos")
                trip.reparto = {"vuelos": round(best.precio, 2)} | {
                    k: round(rest * v / share, 2)
                    for k, v in SPLIT.items()
                    if k != "vuelos"
                }
        trip.enlaces["vuelos"] = found.get("enlaces") or {}
    elif origin:
        trip.enlaces["vuelos"] = enlaces.flights(origin, destination)
    trip.enlaces["hoteles"] = enlaces.hotels(destination, start, back, trip.personas)
    trip.itinerario = _itinerary(trip, interests, ask)
    trip.documentos = [
        "Pasaporte con al menos 6 meses de vigencia y hojas libres.",
        f"Visa o exención para {destination}: verifíquelo en el sitio oficial del "
        "consulado o la embajada (cambia según su nacionalidad y la fecha).",
        "Seguro de viaje con gastos médicos.",
        "Datos móviles (eSIM) y la forma de pago que se usa allá.",
    ]
    trip.pasos = [
        "1. Usted aprueba el plan y el reparto del presupuesto.",
        "2. Vuelos: abro la mejor opción en su pantalla y la dejo lista; usted paga.",
        "3. Hotel: igual, con cancelación gratis cuando la haya.",
        "4. Transporte local y entradas que se agotan: los reservo en el mismo orden.",
        "5. Le dejo recordatorios: check-in del vuelo, salida al aeropuerto y cada reserva.",
    ]
    folder = root or _home()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{trip.id}.json").write_text(
        json.dumps(trip.to_dict(), ensure_ascii=False, indent=2), "utf-8"
    )
    return trip


def _itinerary(
    trip: Trip, interests: str, ask: Optional[Callable[[str], str]]
) -> List[Dict[str, str]]:
    prompt = (
        f"Plan a {trip.dias}-day trip to {trip.destino} for {trip.personas} person(s)"
        + (
            f", budget {trip.presupuesto:g} {trip.moneda} total"
            if trip.presupuesto
            else ""
        )
        + (f", interests: {interests}" if interests else "")
        + ". Real places only, grouped by area so travel is short, with the local "
        "transport between them. Answer only JSON in Spanish: "
        '{"dias": [{"dia": "1", "zona": "...", "manana": "...", "tarde": "...", '
        '"noche": "...", "transporte": "..."}]}'
    )
    raw = ""
    try:
        if ask is None:
            from openjarvis.creator.llm import ask as ask_model

            raw = ask_model(prompt)
        else:
            raw = ask(prompt)
    except Exception:  # noqa: BLE001 — an outline instead
        raw = ""
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    days = [
        {k: str(v)[:300] for k, v in d.items()}
        for d in (data.get("dias") or [])
        if isinstance(d, dict)
    ]
    if days:
        return days[: trip.dias]
    return [
        {
            "dia": str(i),
            "zona": "por definir",
            "manana": "",
            "tarde": "",
            "noche": "",
            "transporte": "",
        }  # fmt: skip
        for i in range(1, trip.dias + 1)
    ]


__all__ = ["Offer", "Trip", "iata", "plan_trip", "search_flights"]
