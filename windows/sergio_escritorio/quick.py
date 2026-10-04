"""Instant voice commands: done on the laptop at once, without the AI.

"Sergio, abre Spotify" should not wait for a model to think. Common, clear
orders are recognised here and run in a fraction of a second; anything else
goes to the agent as before.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import quote_plus

SITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "chatgpt": "https://chatgpt.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "amazon": "https://www.amazon.com",
    "github": "https://github.com",
    "maps": "https://www.google.com/maps",
    "google maps": "https://www.google.com/maps",
    "mapas": "https://www.google.com/maps",
    "drive": "https://drive.google.com",
    "calendario": "https://calendar.google.com",
}
SEARCH = {
    "google": "https://www.google.com/search?q={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
    "amazon": "https://www.amazon.com/s?k={}",
    "maps": "https://www.google.com/maps/search/{}",
    "mapas": "https://www.google.com/maps/search/{}",
}
# Words that mean the request needs more than one simple step: let the
# agent handle it ("abre Google, busca Nvidia y entra al primer link").
_COMPLEX = (
    " y entra",
    " y luego",
    " despues",
    " y haz",
    " y escribe",
    " y dime",
    " y lee",
)


@dataclass
class Quick:
    kind: str  # open_url | open_app | close_app | key | volume | camera | hands
    #           | stop | time | date | globe | screenshot | reminder
    #           | reminders_list | reminders_clear | status | protocol
    #           | briefing | call | gym | physics | name_face
    arg: str = ""
    say: str = ""  # short spoken confirmation


_STATUS = re.compile(
    r"(estado del sistema|estado de (la|mi) (computadora|pc|laptop)|"
    r"como esta (la|mi) (bateria|computadora|pc|laptop)|"
    r"cuanta bateria (tengo|queda|hay)|(que|cuanta) bateria|nivel de bateria|"
    r"diagnostico del sistema)"
)
_CALL = re.compile(
    r"(hablemos|conversemos|charlemos|llamada|modo (conversacion|llamada)|"
    r"quiero (hablar|conversar) contigo|hablemos un rato)"
)
_GYM = re.compile(r"(gimnasio mental|ejercicios? mentales?|entrena(r)? (mi|la) mente)")
_PHYSICS = re.compile(
    r"^(crea|lanza|tira|suelta|pon|haz)( me)? (una?|unos|unas|\d+|dos|tres|cuatro|"
    r"cinco|seis|siete|ocho|nueve|diez)? ?(pelotas?|bolas?|cubos?|cajas?|"
    r"triangulos?|estrellas?|objetos?)\b"
    r"|^(borra|quita|limpia) (los|todos los) objetos"
    r"|^gravedad (cero|lunar|normal|invertida|de la luna)"
    r"|^sin gravedad$"
)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s:/.+-]", " ", text).split())


def parse_quick(text: str) -> Quick | None:
    """A Quick action for clear one-step orders, else None."""
    t = _plain(text).rstrip(".")
    if not t or any(c in f" {t}" for c in _COMPLEX):
        return None
    # Stop / silence
    if t in ("para", "parate", "callate", "silencio", "basta", "detente", "stop"):
        return Quick("stop", say="")
    # Timers and reminders: "recuérdame en 10 minutos sacar la ropa"
    if re.search(r"\b(recuerdame|avisame|temporizador(es)?|alarmas?|despiertame|timer)\b", t):
        if re.search(r"\b(cancela|borra|quita|elimina)\b", t):
            return Quick("reminders_clear", say="")
        if re.search(r"\b(que|cuales|mis)\b.*\b(recordatorios|alarmas|temporizadores)\b", t):
            return Quick("reminders_list")
        return Quick("reminder", text)
    if re.search(r"\b(que|cuales|mis) (recordatorios|alarmas|temporizadores)\b", t):
        return Quick("reminders_list")
    if re.search(r"\b(cancela|borra|quita) (los|las|todos los|todas las|mis) (recordatorios|temporizadores|alarmas)\b", t):
        return Quick("reminders_clear")
    if _STATUS.search(t):
        return Quick("status")
    if re.fullmatch(r"(dame |dime )?(el )?(informe|resumen)( del dia| de hoy)?", t):
        return Quick("briefing")
    if _CALL.fullmatch(t) or re.fullmatch(r"(empecemos|iniciemos) (una )?(llamada|conversacion)", t):
        return Quick("call", say="Le escucho, señor.")
    m = re.fullmatch(
        r"(?:el|ella|esta persona|este|esta|mi amigo|mi amiga)\s+(?:se llama|es)\s+(.+)"
        r"|te presento a\s+(.+)",
        t,
    )
    if m:
        name = (m.group(1) or m.group(2) or "").strip()
        count = len(name.split())
        if 0 < count <= 4:
            # Keep the name as said (accents and all): the last words of the text.
            words = [w.strip(".,;:!?¡¿") for w in text.split()][-count:]
            return Quick("name_face", " ".join(w[:1].upper() + w[1:] for w in words if w))
    if _GYM.search(t):
        return Quick("gym", say="Vamos a entrenar la mente.")
    if _PHYSICS.search(t):
        return Quick("physics", t)
    m = re.fullmatch(r"(?:activa |inicia |pon )?(?:el )?(protocolo|modo) (.+)", t)
    if m and m.group(2) not in ("mouse", "gestos", "3d"):
        from sergio_escritorio.jarvis import find_protocol

        name = find_protocol(f"{m.group(1)} {m.group(2)}")
        if name:
            return Quick("protocol", name)
    # Time and date
    if re.fullmatch(r"(que hora es|dime la hora|la hora)( por favor)?", t):
        return Quick("time")
    if re.fullmatch(r"(que dia es hoy|que fecha es hoy|que fecha es)( por favor)?", t):
        return Quick("date")
    # Volume and media keys
    volume = {
        "sube el volumen": ("volume", "up", "Subo el volumen."),
        "subele": ("volume", "up", "Subo el volumen."),
        "baja el volumen": ("volume", "down", "Bajo el volumen."),
        "bajale": ("volume", "down", "Bajo el volumen."),
        "silencia": ("volume", "mute", "Silenciado."),
        "quita el sonido": ("volume", "mute", "Silenciado."),
        "pausa": ("key", "playpause", "Pausado."),
        "pausa la musica": ("key", "playpause", "Pausado."),
        "reproduce": ("key", "playpause", "Reproduciendo."),
        "siguiente cancion": ("key", "nexttrack", "Siguiente."),
        "cancion anterior": ("key", "prevtrack", "Anterior."),
        "captura de pantalla": ("screenshot", "", "Captura guardada."),
        "toma una captura": ("screenshot", "", "Captura guardada."),
        "minimiza todo": ("key", "win+d", "Listo."),
        "muestra el escritorio": ("key", "win+d", "Listo."),
        "bloquea la computadora": ("key", "win+l", ""),
        "abre la camara": ("camera", "on", "Aquí está la cámara."),
        "cierra la camara": ("camera", "off", "Cámara cerrada."),
        "abre el globo": ("globe", "", "Abriendo el globo."),
        "muestrame el globo": ("globe", "", "Abriendo el globo."),
        "abre gods eye view": ("globe", "", "Abriendo el globo."),
        "mouse con la mano": ("hands", "mouse", "Mueve tu índice para mover el mouse."),
        "modo mouse": ("hands", "mouse", "Mueve tu índice para mover el mouse."),
        "modo gestos": ("hands", "gestos", "Te leo los gestos."),
        "apaga las manos": ("hands", "off", "Listo."),
    }
    if t in volume:
        kind, arg, say = volume[t]
        return Quick(kind, arg, say)
    # "busca X en youtube", "busca X" (Google)
    m = re.fullmatch(r"busca (.+?)(?: en (google|youtube|amazon|maps|mapas))?", t)
    if m:
        query, site = m.group(1), m.group(2) or "google"
        url = SEARCH[site].format(quote_plus(query))
        return Quick("open_url", url, f"Buscando {query}.")
    # "abre youtube y busca X"
    m = re.fullmatch(r"abre (google|youtube|amazon|maps|mapas) y busca (.+)", t)
    if m:
        site, query = m.group(1), m.group(2)
        return Quick(
            "open_url", SEARCH[site].format(quote_plus(query)), f"Buscando {query}."
        )
    # "abre X" / "cierra X"
    m = re.fullmatch(
        r"(abre|abrir|abreme|inicia|lanza|pon) (el |la |los |las )?(.+)", t
    )
    if m:
        target = m.group(3).strip()
        if target in SITES:
            return Quick("open_url", SITES[target], f"Abriendo {target.title()}.")
        if re.fullmatch(r"[\w.-]+\.(com|org|net|ec|es|io|ai|dev)(/\S*)?", target):
            return Quick("open_url", f"https://{target}", f"Abriendo {target}.")
        if len(target.split()) <= 3 and m.group(1) != "pon":
            return Quick("open_app", target, f"Abriendo {target.title()}.")
    m = re.fullmatch(r"(cierra|cerrar) (el |la )?(.+)", t)
    if m and len(m.group(3).split()) <= 3:
        target = m.group(3).strip()
        return Quick("close_app", target, f"Cerrando {target.title()}.")
    return None


_DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def spoken_time(now) -> str:  # noqa: ANN001 — a datetime
    """'Son las tres y veinticinco de la tarde' style, with digits."""
    hour = now.hour % 12 or 12
    part = (
        "de la mañana"
        if now.hour < 12
        else ("de la tarde" if now.hour < 19 else "de la noche")
    )
    article = "Es la" if hour == 1 else "Son las"
    if now.minute == 0:
        return f"{article} {hour} en punto {part}."
    return f"{article} {hour} y {now.minute} {part}."


def spoken_date(now) -> str:  # noqa: ANN001 — a datetime
    return f"Hoy es {_DAYS[now.weekday()]} {now.day} de {_MONTHS[now.month - 1]}."


__all__ = ["Quick", "SITES", "parse_quick", "spoken_date", "spoken_time"]
