"""Reservations, including the restaurants that are «impossible» to book.

Hard tables open at a fixed hour some days ahead and go in seconds; the rest
come back as cancellations. Sergio does what a good assistant does, never a
bot that evades a site's checks:

1. finds **when** the restaurant opens its book (a real source, quoted);
2. sets a reminder a few minutes before (``reminders``) so the owner is in
   front of the page when it opens, with the link ready;
3. joins the **official** waitlist or «notify me» of the platform on the
   owner's screen, with his own account;
4. prepares the phone call (Sergio says it is an AI; the call waits his yes);
5. offers what usually works: the bar, the earliest or latest seating, a
   weekday, the sister restaurant.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from openjarvis.conserje import enlaces

Search = Callable[[str], str]

_WINDOW = re.compile(
    r"(\d{1,3})\s*(days?|d[ií]as|weeks?|semanas?|months?|meses)\s*"
    r"(?:in advance|de anticipaci[oó]n|antes|por adelantado|ahead)",
    re.I,
)
_HOUR = re.compile(
    r"\b(?:at|a las)\s*(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)", re.I
)


@dataclass
class Reserva:
    restaurante: str
    ciudad: str
    fecha: str
    hora: str
    personas: int
    enlaces: Dict[str, str] = field(default_factory=dict)
    apertura: str = ""  # «abre 30 días antes a las 10:00» (from a real page)
    fuente: str = ""
    pasos: List[str] = field(default_factory=list)
    guion_llamada: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _default_search(query: str) -> str:
    from openjarvis.tools.web_search import WebSearchTool

    return WebSearchTool(max_results=6).execute(query=query).content or ""


def booking_window(
    name: str, city: str, search: Optional[Search] = None
) -> Dict[str, str]:
    """When the book opens, only if a search result says it (quoted)."""
    try:
        text = (search or _default_search)(
            f"{name} {city} reservations open days in advance time"
        )
    except Exception:  # noqa: BLE001 — no internet: unknown, never invented
        return {}
    for line in text.splitlines():
        m = _WINDOW.search(line)
        if m:
            hour = _HOUR.search(line)
            unit = m.group(2).lower()
            unit_es = (
                "semanas" if unit.startswith(("week", "seman"))
                else "meses" if unit.startswith(("month", "mes"))
                else "días"
            )  # fmt: skip
            when = f"{m.group(1)} {unit_es} antes" + (
                f", a las {hour.group(1)}" if hour else ""
            )
            url = re.search(r"https?://\S+", line)
            return {
                "apertura": when,
                "fuente": url.group(0) if url else line.strip()[:160],
            }
    return {}


def plan(
    restaurant: str,
    *,
    city: str = "",
    date: str = "",
    time: str = "",
    people: int = 2,
    owner: str = "el señor",
    search: Optional[Search] = None,
) -> Reserva:
    """Everything to get the table; the final «Reservar» is his tap or his yes."""
    if not restaurant.strip():
        raise ValueError("Dígame el restaurante.")
    r = Reserva(restaurant.strip(), city.strip(), date, time, max(1, int(people or 2)))
    r.enlaces = enlaces.restaurant(r.restaurante, r.ciudad, date, time, r.personas)
    found = booking_window(r.restaurante, r.ciudad, search)
    r.apertura, r.fuente = found.get("apertura", ""), found.get("fuente", "")
    when = f"el {date}" if date else "la fecha que usted diga"
    r.pasos = [
        f"Busco mesa para {r.personas} {when}"
        + (f" a las {time}" if time else "")
        + " en las plataformas de reserva (enlaces abajo).",
        (
            f"Si no hay: la agenda abre {r.apertura} (fuente: {r.fuente}); "
            "un recordatorio 5 minutos antes le deja el enlace listo."
            if r.apertura
            else "No encontré cuándo abre su agenda en una fuente fiable; lo pregunto por "
            "teléfono o en su web."
        ),
        "Me apunto en la lista de espera oficial / «avísame» de la plataforma, con su "
        "cuenta, en su pantalla.",
        "Preparo la llamada al restaurante (digo que soy una IA que llama por usted); "
        "llamo solo con su sí.",
        "Alternativas que suelen funcionar: barra o mostrador, primer o último turno, "
        "un día entre semana, o el restaurante hermano.",
        "Reservar, dejar tarjeta de garantía o pagar: lo confirma usted.",
    ]
    of = "del " + owner[3:] if owner.lower().startswith("el ") else f"de {owner}"
    r.guion_llamada = (
        f"Buenas, le habla Sergio, un asistente de inteligencia artificial que llama de "
        f"parte {of}. Quisiera saber si tienen mesa para {r.personas} {when}"
        + (f" alrededor de las {time}" if time else "")
        + ", o si puedo dejarle en la lista de espera por si se libera algo. "
        "¿Cuándo abren las reservas para esa fecha? Muchas gracias."
    )
    return r


_UNIT_DAYS = {"day": 1, "dia": 1, "week": 7, "semana": 7, "month": 30, "mes": 30}


def opening_moment(r: Reserva) -> Optional[tuple]:
    """(``AAAA-MM-DD``, ``HH:MM``) when the book opens for his date, or None
    when the date or the rule is not known (then nothing is promised)."""
    from datetime import date, timedelta

    if not (r.fecha and r.apertura):
        return None
    try:
        day = date.fromisoformat(r.fecha)
    except ValueError:
        return None
    m = re.match(r"(\d{1,3})\s+([a-zíá]+)", r.apertura.lower())
    if not m:
        return None
    unit = m.group(2).replace("í", "i").rstrip("s")
    unit = {"mese": "mes"}.get(unit, unit)
    days = int(m.group(1)) * _UNIT_DAYS.get(unit, 0)
    if not days:
        return None
    opens = day - timedelta(days=days)
    hour = re.search(
        r"a las (\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?", r.apertura.lower()
    )
    hh, mm = 9, 0
    if hour:
        hh, mm = int(hour.group(1)), int(hour.group(2) or 0)
        if (hour.group(3) or "").startswith("p") and hh < 12:
            hh += 12
    total = max(0, hh * 60 + mm - 5)  # five minutes before it opens
    return opens.isoformat(), f"{total // 60:02d}:{total % 60:02d}"


def remind(r: Reserva, add: Optional[Callable[..., Any]] = None) -> str:
    """Save the reminder for the moment the book opens; says what it did."""
    moment = opening_moment(r)
    if moment is None:
        return ""
    day, at = moment
    link = next(iter(r.enlaces.values()), "")
    title = f"Abre la agenda de {r.restaurante} en 5 min: {link}"
    try:
        if add is None:
            from openjarvis.reminders import get_store

            get_store().add("recordatorio", title, times=[at], date=day)
        else:
            add(title, day, at)
    except Exception:  # noqa: BLE001 — say it, never pretend
        return "No pude guardar el recordatorio; anótelo: " + f"{day} {at}."
    return f"Recordatorio guardado: {day} a las {at} (5 min antes de que abra)."


def operator_goal(r: Reserva, platform: str = "OpenTable") -> str:
    """What the screen operator does on the owner's PC (stops before booking)."""
    url = r.enlaces.get(platform) or next(iter(r.enlaces.values()))
    when = f"el {r.fecha}" if r.fecha else "la próxima fecha disponible"
    return (
        f"En {url}, busca «{r.restaurante}» y una mesa para {r.personas} {when}"
        + (f" cerca de las {r.hora}" if r.hora else "")
        + ". Si hay mesa, deja todo listo y DETENTE antes de «Reservar» o «Confirmar». "
        "Si no hay, pulsa la lista de espera o «Notify / Avísame» y detente antes de "
        "confirmar. No escribas contraseñas ni datos de tarjeta."
    )


__all__ = [
    "Reserva",
    "booking_window",
    "opening_moment",
    "operator_goal",
    "plan",
    "remind",
]
