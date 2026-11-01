"""Links that open each service with the request already filled in.

The owner taps the last button himself (the link never buys or books)."""

from __future__ import annotations

from typing import Dict
from urllib.parse import quote, quote_plus, urlencode


def uber(destination: str, pickup: str = "") -> str:
    """Uber's universal link: pickup (or his location) and the destination."""
    q = {"action": "setPickup"}
    if pickup:
        q["pickup[formatted_address]"] = pickup
    else:
        q["pickup"] = "my_location"
    if destination:
        q["dropoff[formatted_address]"] = destination
    return "https://m.uber.com/ul/?" + urlencode(q)


def rides(destination: str, pickup: str = "") -> Dict[str, str]:
    maps = "https://www.google.com/maps/dir/?api=1&" + urlencode(
        {"origin": pickup or "", "destination": destination, "travelmode": "driving"}
    )
    return {
        "Uber": uber(destination, pickup),
        "DiDi": "https://web.didiglobal.com/",
        "Cabify": "https://cabify.com/",
        "Ruta en Maps": maps,
    }


def food(item: str, country: str = "") -> Dict[str, str]:
    q = quote_plus(item)
    c = (country or "").lower()
    out = {"Uber Eats": f"https://www.ubereats.com/search?q={q}"}
    if c in (
        "",
        "ec",
        "ecuador",
        "co",
        "colombia",
        "mx",
        "mexico",
        "pe",
        "cl",
        "ar",
        "br",
    ):
        tld = {"ec": "com.ec", "ecuador": "com.ec", "co": "com.co", "colombia": "com.co",
               "mx": "com.mx", "mexico": "com.mx", "pe": "com.pe", "cl": "cl",
               "ar": "com.ar", "br": "com.br"}.get(c, "com.ec")  # fmt: skip
        out["Rappi"] = f"https://www.rappi.{tld}/search?query={q}"
        out["PedidosYa"] = f"https://www.pedidosya.{tld}/restaurantes?q={q}"
    if c in ("", "us", "usa", "estados unidos", "ca", "canada"):
        out["DoorDash"] = f"https://www.doordash.com/search/store/{quote(item)}/"
    return out


def restaurant(name: str, city: str = "", date: str = "", time: str = "",
               people: int = 2) -> Dict[str, str]:  # fmt: skip
    term = f"{name} {city}".strip()
    q = quote_plus(term)
    dt = f"{date}T{time or '20:00'}" if date else ""
    ot = {"term": term, "covers": people}
    if dt:
        ot["dateTime"] = dt
    resy = {"query": term, "seats": people}
    if date:
        resy["date"] = date
    return {
        "OpenTable": "https://www.opentable.com/s?" + urlencode(ot),
        "Resy": "https://resy.com/cities?" + urlencode(resy),
        "Tock": f"https://www.exploretock.com/search?query={q}",
        "TheFork": f"https://www.thefork.com/search?queryText={q}",
        "Google (Reservar)": f"https://www.google.com/maps/search/{q}",
    }


def flights(
    origin: str, destination: str, date: str = "", back: str = ""
) -> Dict[str, str]:
    words = f"vuelos de {origin} a {destination}" + (f" el {date}" if date else "")
    if back:
        words += f" regreso {back}"
    return {
        "Google Flights": "https://www.google.com/travel/flights?q="
        + quote_plus(words),
        "Kayak": "https://www.kayak.com/flights/"
        + f"{quote(origin)}-{quote(destination)}/{date or ''}"
        + (f"/{back}" if back else ""),
        "Skyscanner": "https://www.skyscanner.com/transport/flights/"
        + f"{quote(origin.lower())}/{quote(destination.lower())}/",
    }


def hotels(
    city: str, checkin: str = "", checkout: str = "", people: int = 2
) -> Dict[str, str]:
    b = {"ss": city, "group_adults": people}
    if checkin:
        b["checkin"] = checkin
    if checkout:
        b["checkout"] = checkout
    return {
        "Booking": "https://www.booking.com/searchresults.html?" + urlencode(b),
        "Airbnb": f"https://www.airbnb.com/s/{quote(city)}/homes"
        + (
            f"?checkin={checkin}&checkout={checkout}&adults={people}" if checkin else ""
        ),
        "Google Hoteles": "https://www.google.com/travel/hotels?q=" + quote_plus(city),
    }


def deals(item: str) -> Dict[str, str]:
    q = quote_plus(item)
    return {
        "Google Shopping": f"https://www.google.com/search?tbm=shop&q={q}",
        "Cupones": f"https://www.google.com/search?q={quote_plus(item + ' cupón descuento código')}",
        "Historial de precio (Amazon)": f"https://camelcamelcamel.com/search?sq={q}",
    }


def lines(links: Dict[str, str]) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in links.items())


__all__ = ["deals", "flights", "food", "hotels", "lines", "restaurant", "rides", "uber"]
