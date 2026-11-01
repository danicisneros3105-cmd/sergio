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
            when = f"{m.group(1)} {m.group(2)} antes" + (
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
            f"Si no hay: la agenda abre {r.apertura} (fuente: {r.fuente}). "
            "Le dejo un recordatorio 5 minutos antes con el enlace listo."
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
    r.guion_llamada = (
        f"Buenas, le habla Sergio, un asistente de inteligencia artificial que llama de "
        f"parte de {owner}. Quisiera saber si tienen mesa para {r.personas} {when}"
        + (f" alrededor de las {time}" if time else "")
        + ", o si puedo dejarle en la lista de espera por si se libera algo. "
        "¿Cuándo abren las reservas para esa fecha? Muchas gracias."
    )
    return r


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


__all__ = ["Reserva", "booking_window", "operator_goal", "plan"]
