"""Instant voice commands: done on the laptop at once, without the AI.

"Sergio, abre Spotify" should not wait for a model to think. Common, clear
orders are recognised here and run in a fraction of a second; anything else
goes to the agent as before.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any
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
# Sites that are also desktop apps: the app opens when it is installed.
APP_FIRST = {"whatsapp", "spotify", "telegram", "discord", "netflix", "teams", "zoom"}
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
    #           | briefing | call | gym | gym_report | holo | name_face
    #           | analyze | photo | mirror | blender_holo | blender_object
    arg: str = ""
    say: str = ""  # short spoken confirmation
    step: Any = None  # a device.Step for kind "device"


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
_HOLO = re.compile(
    r"^(crea|lanza|tira|suelta|pon|haz|dibuja|genera)( me)? (una?|unos|unas|\d+|dos|tres|cuatro|"
    r"cinco|seis|siete|ocho|nueve|diez)? ?(pelotas?|bolas?|cubos?|cajas?|esferas?|"
    r"cilindros?|conos?|toroides?|donas?|anillos?|piramides?|jarron(es)?|floreros?|"
    r"diamantes?|gemas?|hologramas?|objetos?)\b"
    r"|^(borra|quita|limpia) (los|todos los|todo|los hologramas|todos los hologramas) ?(objetos|hologramas)?$"
    r"|^(activa la |pon la |con |sin )?gravedad"
    r"|^modo (esculpir|dibujar|mover|torno|tubo|extrusion)"
    r"|^(esculpir|dibujar en el aire)$"
    r"|^(hazlo|haz lo) (mas grande|mas pequeno)$"
    r"|^(suavizalo|duplicalo|giralo|borralo)$"
)


_OVERHEAD = re.compile(
    r"\b(que|cual|de donde|a donde|hay algun|hay un)\b.*\b(avion|vuelo|aeronave|avioneta|"
    r"helicoptero|aviones|vuelos)\b.*\b(encima|arriba|sobre (mi|nosotros|la casa)|pasando|"
    r"pasa por aqui|pasa por aca|se escucha|suena|esta pasando|acaba de pasar)"
    r"|\b(que|cual) (avion|vuelo) es (ese|este)\b"
)
_GLOBE_GOTO = re.compile(
    r"(?:muestrame|ensename|llevame a|vamos a|vuela a|ve a|mira|abre)\s+"
    r"(?:la ciudad de |el pais de |la zona de |)?(?P<place>.+?)\s+en\s+"
    r"(?:el globo|gods eye view|god s eye view|god eye view|la vista de dios|el mapa 3d)"
    r"|(?:abre|pon)\s+(?:gods eye view|god s eye view|el globo)\s+en\s+(?P<place2>.+)"
)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s:/.+-]", " ", text).split())


_LEAD = re.compile(
    r"^(?:(?:sergio|oye|hey|ok|bueno|ya|ahora|por favor|porfa|porfavor)[\s,]+)+"
)
_TAIL = re.compile(r"(?:[\s,]+(?:por favor|porfa|porfavor|please|ahora|ya|rapido|sergio))+$")
_POLITE = re.compile(
    r"^(?:(?:me |tu )?(?:puedes|podrias|pudieras|quieres|quisieras)( me)? |"
    r"(?:quiero|necesito|te pido) que (?:me )?|hazme el favor de |"
    r"ayudame a |vamos a |anda y |dale |me haces el favor de )"
)
_VERBS = {
    "abrir": "abre", "abras": "abre", "abres": "abre", "abrirme": "abre",
    "abrime": "abre", "abreme": "abre", "abrimos": "abre",
    "cerrar": "cierra", "cierres": "cierra", "cierras": "cierra",
    "cerrarme": "cierra", "cierrame": "cierra", "cerramos": "cierra",
    "iniciar": "inicia", "inicies": "inicia", "ejecuta": "abre", "ejecutar": "abre",
    "arranca": "abre", "arrancar": "abre", "corre": "abre",
}
_APP_WORDS = re.compile(r"^(?:la |el )?(?:app|aplicacion|programa)(?: de| del)? ")


def polite(t: str) -> str:
    """ "Sergio, ¿me puedes abrir el Word por favor?" -> "abre el word"."""
    for _ in range(2):
        t = _LEAD.sub("", t).strip()
        t = _TAIL.sub("", t).strip()
        t = _POLITE.sub("", t).strip()
    words = t.split()
    if words and words[0] in _VERBS:
        words[0] = _VERBS[words[0]]
    if len(words) > 1 and words[0] in ("abre", "cierra", "inicia"):
        rest = _APP_WORDS.sub("", " ".join(words[1:]))
        return f"{words[0]} {rest}".strip()
    return " ".join(words)


def _nice(name: str) -> str:
    """ "bloc de notas" -> "Bloc de notas", "word" -> "Word"."""
    return name[:1].upper() + name[1:]


def parse_quick(text: str) -> Quick | None:
    """A Quick action for clear one-step orders, else None."""
    t = polite(_plain(text).rstrip(".?!"))
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
    if _GYM.search(t) and re.search(
        r"\b(funciona|sirve|sirviendo|efectiv\w*|resultados?|progreso|informe|mejorando|mejorado)\b", t
    ):
        return Quick("gym_report")
    if _GYM.search(t):
        return Quick("gym", say="Vamos a entrenar la mente.")
    if _HOLO.search(t):
        return Quick("holo", t)
    m = re.fullmatch(r"(?:activa |inicia |pon )?(?:el )?(protocolo|modo) (.+)", t)
    if m and m.group(2) not in ("mouse", "gestos", "3d"):
        from sergio_escritorio.jarvis import find_protocol

        name = find_protocol(f"{m.group(1)} {m.group(2)}")
        if name:
            return Quick("protocol", name)
    # Faces in photos (old ones too) and family resemblance
    source = "pantalla" if "pantalla" in t else "camara"
    if re.search(r"\b(a quien se parece|parecido familiar|son (familia|parientes)|es (pariente|familia|hermano|hermana|hijo|hija|padre|madre|primo|prima|abuelo|abuela) de)\b", t):
        return Quick("kinship", source)
    if re.search(r"\bquien (es|son|sale|aparece)\b.*\b(foto|fotografia|retrato|imagen)\b", t):
        return Quick("photo_who", source)
    # The real object in your hands, modelled in Blender
    if re.search(r"\b(objeto|esto|lo que tengo)\b.*\b(blender)\b", t) and re.search(
        r"\b(analiza|modela|pasa|lleva|haz|crea)", t
    ):
        return Quick("blender_object", text)
    # The plane overhead and the 3D globe (God's Eye View)
    if _OVERHEAD.search(t):
        return Quick("overhead")
    if re.fullmatch(r"(muestramelo|ensenamelo|abrelo|mira?lo)( en (el globo|gods eye view|god s eye view|el mapa))?", t):
        return Quick("globe_last")
    m = _GLOBE_GOTO.fullmatch(t)
    if m:
        place = (m.group("place") or m.group("place2") or "").strip()
        if place and place not in ("el", "la", "eso", "esto"):
            return Quick("globe_goto", place, f"Mostrando {place.title()} en el globo.")
    # Time and date
    if re.fullmatch(r"(que hora es|dime la hora|la hora)( por favor)?", t):
        return Quick("time")
    if re.fullmatch(r"(que dia es hoy|que fecha es hoy|que fecha es)( por favor)?", t):
        return Quick("date")
    # The laptop itself: windows, editing keys, brightness, theme, settings...
    from sergio_escritorio.device import parse_device

    step = parse_device(t, text)
    if step is not None:
        return Quick("device", step.arg, step.say, step)
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
        "activa las manos": ("hands", "holo", "Tus manos ya mueven los hologramas."),
        "modo hologramas": ("hands", "holo", "Tus manos ya mueven los hologramas."),
        "apaga las manos": ("hands", "off", "Listo."),
        "analiza lo que ves": ("analyze", "", ""),
        "analiza la camara": ("analyze", "", ""),
        "que ves en la camara": ("analyze", "", ""),
        "toma una foto": ("photo", "", "Foto tomada."),
        "tomame una foto": ("photo", "", "Foto tomada."),
        "modo espejo": ("mirror", "", "Listo."),
        "pasalo a blender": ("blender_holo", "", ""),
        "pasa los hologramas a blender": ("blender_holo", "", ""),
        "lleva esto a blender": ("blender_holo", "", ""),
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
        if target in APP_FIRST:  # the desktop app if installed, else its web
            return Quick("open_app", target, f"Abriendo {_nice(target)}.")
        if target in SITES:
            return Quick("open_url", SITES[target], f"Abriendo {target.title()}.")
        if re.fullmatch(r"[\w.-]+\.(com|org|net|ec|es|io|ai|dev)(/\S*)?", target):
            return Quick("open_url", f"https://{target}", f"Abriendo {target}.")
        if len(target.split()) <= 3 and m.group(1) != "pon":
            return Quick("open_app", target, f"Abriendo {_nice(target)}.")
    m = re.fullmatch(r"(cierra|cerrar) (el |la )?(.+)", t)
    if m and len(m.group(3).split()) <= 3:
        target = m.group(3).strip()
        return Quick("close_app", target, f"Cerrando {_nice(target)}.")
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


__all__ = ["APP_FIRST", "Quick", "SITES", "polite", "parse_quick", "spoken_date", "spoken_time"]
