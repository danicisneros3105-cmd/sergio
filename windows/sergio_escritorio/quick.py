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


# "haz una lista", "crea un recordatorio": not objects for a hologram.
_NOT_HOLO = (
    r"\b(recordatorio|lista|documento|carpeta|archivo|correo|email|mensaje|nota|alarma|"
    r"temporizador|resumen|plan|tabla|presentacion|pagina|web|app|aplicacion|programa|codigo|"
    r"script|video|cancion|poema|cuento|historia|imagen|foto|informe|reporte|ensayo|chiste|"
    r"pregunta|busqueda|llamada|captura|backup|copia|cita|evento|reunion|post|tweet)\b"
)
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
    r"diamantes?|gemas?|estrellas?|corazon(es)?|prismas?|hexagonos?|icosaedros?|capsulas?|discos?|"
    r"monedas?|flechas?|lunas?|medialunas?|hologramas?|objetos?)\b"
    r"|^(estilo|aspecto) (de )?(cristal|vidrio|holograma|jarvis|azul)\b"
    r"|^(hologramas?|figuras?|cubos?) de (cristal|vidrio)$"
    r"|^(borra|quita|limpia) (los|todos los|todo|los hologramas|todos los hologramas) ?(objetos|hologramas)?$"
    r"|^(activa la |pon la |con |sin )?gravedad"
    r"|^modo (esculpir|dibujar|mover|torno|tubo|extrusion)"
    r"|^(esculpir|dibujar en el aire)$"
    r"|^(hazlo|haz lo) (mas grande|mas pequeno)$"
    r"|^(suavizalo|duplicalo|giralo|borralo)$"
    r"|^(muevelo|mueve el (holograma|cubo|objeto)|acercalo|alejalo|subelo|bajalo|centralo|"
    r"voltealo|dale la vuelta|traelo)\b"
    r"|^(gira|giralo|rota|rotalo)( el holograma| el cubo)? \d+ grados"
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


_SCAN = re.compile(
    r"(?:(?:escanea|escaneame|escanear|registra|registrame|aprende|aprendete|memoriza|"
    r"memorizate|graba|guarda)(?: me)? (?:mi|la|el|tu) (?:cara|rostro)"
    r"|escaneame(?: la cara| el rostro)?|(?:haz|hazme) un escaneo(?: facial| de (?:mi )?cara)?|escaneo facial)"
    r"(?: (?:de|a) (?!nuevo\b)(?P<who>[a-zñ]+(?: [a-zñ]+){0,3}?))?"
    r"(?: (?:en 3d|en tres d|como (?:el )?face id|a la perfeccion|completa|completo|entera|bien|otra vez|de nuevo))*"
    r"(?:,? (?:yo )?soy (?P<me>[a-zñ]+(?: [a-zñ]+){0,3}))?"
)


def said_name(text: str, plain_words: str) -> str:
    """The name as it was said (accents and capitals), found in *text*."""
    want = plain_words.split()
    tokens = [w.strip(".,;:!?¡¿«»\"'") for w in text.split()]
    for i in range(len(tokens) - len(want) + 1):
        if [_plain(w) for w in tokens[i : i + len(want)]] == want:
            return " ".join(w[:1].upper() + w[1:] for w in tokens[i : i + len(want)])
    return " ".join(w[:1].upper() + w[1:] for w in want)


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
    r"ayudame a |vamos a |anda y |dale (?!a |al |clic|click|doble|enter|intro|tab|escape|esc |espacio|f\d)|me haces el favor de )"
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


class _ProAgents:
    """The pro agents' names, for «Investigador, …» (the app knows the user's own)."""

    def find(self, name: str):  # noqa: ANN201
        from sergio_escritorio.agentes import PRO, plain

        key = plain(name)
        return next((a for a in PRO if plain(a["nombre"]) == key), None)


_PRO_AGENTS = _ProAgents()


def parse_quick(text: str) -> Quick | None:
    """A Quick action for clear one-step orders, else None."""
    t = polite(_plain(text).rstrip(".?!"))
    # Multitasking: background tasks, several at once, what is running
    from sergio_escritorio.tareas import CANCEL, WHAT_DOING, parse_background, parse_together

    from sergio_escritorio import agentes

    agent_order = agentes.parse(text, _PRO_AGENTS)
    if agent_order:
        return Quick("agent", "\n".join(agent_order))
    together = parse_together(text)
    if len(together) >= 2:
        return Quick("tasks_together", "\n".join(together))
    background = parse_background(text)
    if background:
        return Quick("task_bg", background)
    if WHAT_DOING.search(text):
        return Quick("tasks_status")
    if CANCEL.search(text):
        return Quick("task_cancel")
    if not t or any(c in f" {t}" for c in _COMPLEX):
        return None
    # Stop / silence
    if t in ("para", "parate", "callate", "silencio", "basta", "detente", "stop"):
        return Quick("stop", say="")
    # Real distances between things the camera sees
    if re.search(r"\b(a que distancia|que tan lejos|cuantos (cm|centimetros|metros) hay|que distancia hay)\b", t):
        return Quick("distance", text)
    # Sergio international: language and country
    from sergio_escritorio.idioma import country_said, language_asked

    lang = language_asked(text)
    if lang:
        return Quick("language", lang)
    where = country_said(text)
    if where:
        return Quick("country", where)
    # God's Eye View: public live cameras of a place, a flight followed live
    m = re.search(r"\b(?:camaras?|webcams?|camara)(?: publicas?)?(?: en vivo| en directo)?(?: de| en| cerca de)\s+(.+)$", t)
    if m and re.search(r"\b(muestra|muestrame|ver|abre|pon|ensename|quiero ver|camaras? en vivo)\b", t):
        place = m.group(1).strip()
        if place not in ("aqui", "esta ubicacion", "este lugar", "mi ubicacion", "mi casa"):
            return Quick("cams", place)
        return Quick("cams", "")
    if re.search(r"\b(camaras en vivo|webcams en vivo)\b", t):
        return Quick("cams", "")
    m = re.search(r"\b(?:sigue|seguir|rastrea|muestrame|muestra|donde esta|ver)\b.*\bvuelo\s+([a-z0-9]{2,3}\s?\d{1,4}[a-z]?)\b", t)
    if m:
        return Quick("flight_follow", m.group(1).replace(" ", "").upper())
    if re.search(r"\b(muestrame|sigue|seguir)\b.*\b(este|ese) (vuelo|avion)\b.*\ben vivo\b|\b(sigue|seguir) (ese|este) (vuelo|avion)\b", t):
        return Quick("flight_follow", "")
    # Useless / duplicated apps (one approval removes them) and permanent skills
    if re.search(r"\b(limpia|quita|desinstala|elimina|borra)\b.*\b(apps?|aplicaciones|programas)\b.*\b(inutiles|duplicadas?|"
                 r"que no uso|repetidas?|basura|sobran)\b|\b(limpia|limpieza de) (las |mis )?(apps|aplicaciones|programas)\b", t):
        return Quick("apps_clean")
    m = re.search(r"\b(?:aprende|estudia|asimila)\b.*?\b(?:pdf|manual|documento|skill)\b\s*(?:de |en |:)?\s*(.*)$", text, re.I)
    if m:
        return Quick("skill_learn", m.group(1).strip(" .\"'"))
    if re.search(r"\b(mis skills|que skills tienes|lista de skills|que has aprendido|que manuales sabes)\b", t):
        return Quick("skills_show")
    # Blocking (apps, websites, searches) — off only with the owner's face
    if re.search(r"\b(quita|desactiva|apaga|elimina) (el |los )?bloqueos?\b|\bdesbloquea( todo)?$", t):
        return Quick("block_off")
    if re.search(r"\b(activa|enciende|pon) (el )?bloqueo\b(?! de pantalla)", t) and "modo bloqueo" not in t:
        return Quick("block_on")
    if re.search(r"\b(abre|muestra|muestrame|ver)\b.*\b(bloqueos?|lista de bloqueo|apps bloqueadas|webs bloqueadas)\b", t):
        return Quick("block_show")
    from sergio_escritorio.bloqueo import parse_block

    if t.startswith("bloquea") and "computadora" not in t and "pc" not in t.split():
        found = parse_block(text)
        if found:
            return Quick("block_add", f"{found[0]}:{found[1]}")
    # The consulting room
    if re.search(r"\b(psicologo|psicologa|terapia|terapeuta|consulta psicologica|modo psicologo|necesito desahogarme|quiero desahogarme|"
                 r"abre la consulta|necesito hablar con alguien|necesito hablar contigo)\b", t):
        return Quick("consult")
    # Health
    if re.search(r"\b(cuestionario de salud|test de salud|preguntas de salud)\b", t):
        return Quick("health", "cuestionario")
    if re.search(r"\b(analiza|revisa|evalua)\b.*\bmi salud\b|\bcomo esta mi salud\b|\binforme de salud\b", t):
        return Quick("health_analyze")
    if re.search(r"\b(conectar|conecta|vincula|sincroniza)\b.*\b(reloj|apple watch|garmin|fitbit|samsung health|google fit|watch)\b", t):
        return Quick("health", "reloj")
    if re.search(r"^(abre |muestrame |ver |mi )?(mi )?salud$|\b(abre|muestrame) mi salud\b", t):
        return Quick("health")
    from sergio_escritorio.salud import parse_health_log

    if re.search(r"^(hoy |anota que |registra que |apunta que )?(dormi|camine|hice|bebi|tome|pese|peso|mi pulso|mi animo|mi energia|mi estres)", t) and parse_health_log(text):
        return Quick("health_log", text)
    # The coach: learning goals, practice, school
    m = re.match(r"(?:mi )?plataforma (?:escolar|del colegio|de la universidad|de clases) es\s+(\S+)", text.strip(), re.I)
    if m:
        url = m.group(1).strip(" .")
        return Quick("school_set", url if url.startswith("http") else "https://" + url)
    if re.search(r"\b(revisa|mira|abre|chequea|lee)\b.*\bplataforma\b|\b(que tareas tengo|tengo tareas|que examenes tengo|mis tareas pendientes)\b", t):
        return Quick("school")
    from sergio_escritorio.coach import parse_goal

    goal = parse_goal(text)
    if goal is not None and not re.search(r"\b(cancion|video|recordatorio)\b", t):
        return Quick("learn", goal)
    if re.search(r"\b(mis metas|que estoy aprendiendo|mi progreso)\b", t):
        return Quick("goals")
    if re.search(r"\b(como|que tal) (voy|me va)\b.*\bgimnasio\b", t):
        return Quick("gym_report")
    m = re.search(r"\bcomo voy (?:en|con) (.+)", t)
    if m and "gimnasio" not in t:
        return Quick("goals", m.group(1))
    m = re.match(r"(?:practiquemos|vamos a practicar|quiero practicar|toca practicar)(?: (?:ahora|ya))?(?: (?:de |el |la )?(.+))?$", t)
    if m:
        return Quick("practice", (m.group(1) or "").strip())
    # Your profile
    if re.search(r"\b(que sabes de mi|muestrame mi perfil|cual es mi perfil|como me ves|que has aprendido de mi)\b", t):
        return Quick("profile_show")
    if re.search(r"\b(actualiza|analiza|revisa) (mi|tu) perfil( de mi)?\b|\banalizame\b", t):
        return Quick("profile_update")
    m = re.match(r"(?:recuerda|aprende|apréndete|aprendete|ten en cuenta|toma en cuenta) que (.+)", text.strip().rstrip(".!"), re.I)
    if m and not re.search(r"\b(en \d+|a las|minutos|horas)\b", t):
        return Quick("profile_fact", m.group(1).strip())
    # Organizer: alarms at a time, sticky notes, the window
    if re.search(r"\b(organizador|agenda de sergio)\b", t) and re.search(r"\b(abre|abreme|muestra|muestrame|ver|ensena)\b", t):
        tab = next((k for k in ("alarmas", "notas", "recordatorios", "tareas") if k in t), "")
        return Quick("organizer", tab)
    if re.search(r"\b(alarmas?|despiertame|despertador)\b", t):
        if re.search(r"\b(cancela|borra|quita|elimina|apaga)\b", t):
            return Quick("alarm_remove", text)
        if re.search(r"\b(que|cuales|mis)\b.*\balarmas\b", t):
            return Quick("alarms_list")
        if re.search(r"\ba las? \d|\b\d{1,2}:\d{2}\b", t):
            return Quick("alarm", text)
    from sergio_escritorio.organizer import parse_note

    if parse_note(text.strip()) is not None:
        return Quick("note", text.strip())
    if re.search(r"\b(muestra|muestrame|ensename|ver|abre)\b.*\b((mis|las) notas|notas adhesivas|post-?its?)\b", t) and "bloc" not in t:
        return Quick("notes_show")
    if re.search(r"\b(esconde|oculta|quita|guarda)\b.*\b(las|mis) notas\b", t):
        return Quick("notes_hide")
    m = re.match(r"(?:borra|elimina|quita) la nota (?:de |que dice |sobre )?(.+)", t)
    if m:
        return Quick("note_remove", m.group(1))
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
    # Minutes of a meeting, a video call or a conversation
    m = re.fullmatch(
        r"(?:toma|tomar|empieza a tomar|empezar a tomar|comienza a tomar) (?:notas|apuntes|el acta)"
        r"(?: de (?:la|esta|esa|mi) (?P<k1>reunion|llamada|videollamada|junta|clase|conversacion|charla))?"
        r"|(?:graba|grabame|escucha|anota) (?:la|esta) (?P<k2>reunion|videollamada|junta|clase|conversacion|charla)"
        r"|modo (?P<k3>reunion|videollamada)",
        t,
    )
    if m:
        kind = m.group("k1") or m.group("k2") or m.group("k3") or "reunion"
        kind = {"reunion": "reunión", "junta": "reunión", "clase": "reunión", "llamada": "videollamada",
                "conversacion": "conversación", "charla": "conversación"}.get(kind, kind)
        return Quick("meeting_start", kind, "")
    if re.fullmatch(
        r"(?:termina|terminar|acaba|finaliza|cierra|para|deten) (?:la|esta) (?:reunion|videollamada|junta|clase|grabacion)"
        r"|(?:deja|para) de (?:tomar notas|grabar|tomar apuntes)|fin de la (?:reunion|clase|junta)"
        r"|ya (?:termino|acabo) la (?:reunion|clase|junta)|(?:haz|hazme|escribe) el acta"
        r"|(?:resume|resumeme|haz un resumen de) (?:la|esta|esa) (?:reunion|videollamada|junta|clase|conversacion|charla)",
        t,
    ):
        return Quick("meeting_stop")
    if re.fullmatch(
        r"(?:lee|leeme|dime) (?:el acta|el resumen)(?: de la (?:ultima )?reunion)?|que se (?:decidio|acordo)(?: en la reunion)?"
        r"|que tareas (?:quedaron|salieron)(?: de la reunion)?",
        t,
    ):
        return Quick("meeting_last")
    m = re.fullmatch(
        r"(?:aprende|aprendete|memoriza|memorizate|registra|graba|guarda|reconoce)(?: me)? "
        r"(?:mi voz|la voz de (?P<who>[a-zñ]+(?: [a-zñ]+){0,3}))(?: (?:de nuevo|otra vez|bien))?"
        r"(?:,? (?:yo )?soy (?P<me>[a-zñ]+(?: [a-zñ]+){0,3}))?",
        t,
    )
    if m:
        who = (m.group("who") or m.group("me") or "").strip()
        return Quick("voice_enroll", said_name(text, who) if who else "", "")
    if re.fullmatch(
        r"(?:quien|quienes) (?:esta|estan|estaba) hablando(?: ahora)?|quien habla(?: ahora)?|"
        r"quien hablo(?: recien| antes)?|de quien es (?:esta|esa) voz|(?:me )?reconoces (?:mi|la) voz|"
        r"sabes quien (?:habla|soy)(?: por la voz)?",
        t,
    ):
        return Quick("voice_who")
    m = re.fullmatch(r"(?:olvida|borra|elimina) (?:mi voz|la voz de (?P<who>[a-zñ]+(?: [a-zñ]+){0,3}))", t)
    if m:
        who = (m.group("who") or "").strip()
        return Quick("voice_forget", said_name(text, who) if who else "")
    m = _SCAN.fullmatch(t)
    if m:
        who = (m.group("who") or "").strip()
        me = (m.group("me") or "").strip()
        name = said_name(text, who or me) if (who or me) else ""
        return Quick("face_scan", name, "Gire la cabeza despacio, en círculo.")
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
    if re.fullmatch(
        r"(?:muestrame|ensename|abre|ver|quiero ver|dame) (?:mis |los )?resultados(?: del gimnasio(?: mental)?| del entrenamiento)?"
        r"|mis resultados(?: del gimnasio(?: mental)?)?|resultados del gimnasio(?: mental)?",
        t,
    ):
        return Quick("gym_results")
    if re.search(r"\bperfil (mental|cognitivo|del gimnasio)\b", t):
        return Quick("gym_report")
    if _GYM.search(t) and re.search(
        r"\b(funciona|sirve|sirviendo|efectiv\w*|resultados?|progreso|informe|mejorando|mejorado|perfil|puntos? fuertes?|debil\w*|débil\w*)\b"
        r"|\b(como|que tal) (voy|vamos|me va|estoy)\b",
        t,
    ):
        return Quick("gym_report")
    if _GYM.search(t):
        return Quick("gym", say="Vamos a entrenar la mente.")
    # Video Pro: "edita un video con la carpeta Viaje para YouTube Shorts"
    if re.search(r"\b(edita|editame|monta|montame|haz|hazme|crea|creame|arma)\b.*\b(video|short|reel)", t):
        m = re.search(r"\b(?:carpeta|con los videos de|de la carpeta|con la carpeta|desde|de mis|con mis)\s+(?:de\s+)?(.+?)(?:\s+(?:para|en|como)\b|$)", t)
        return Quick("video_pro", text, m.group(1).strip() if m else "")
    if re.search(r"\b(sube|subelo|subir|publica|publicalo)\b.*\b(youtube|video)\b", t):
        return Quick("video_upload")
    if re.search(r"\b(ayuda|como (se )?(usan|uso|hago|muevo|creo)|instrucciones|guia)\b.*\bhologram", t) or re.search(
        r"\bhologram\w*\b.*\b(ayuda|como funcionan|instrucciones)\b", t
    ):
        return Quick("holo", "ayuda hologramas")
    m = re.search(r"\b(en blender|con blender)\b", t)
    if m and re.search(r"\b(haz|hazme|crea|creame|modela|modelame|construye|disena|genera|arma)\b", t):
        return Quick("blender_task", text, "Blender Pro en marcha.")
    if "blender" in t and not re.search(r"\b(objeto|lo que tengo|en la mano|en mis manos)\b", t) and re.search(
        r"\b(pasa|pasalo|pasala|pasalos|lleva|llevalo|guarda|guardalo|exporta|exportalo|manda|mandalo|envia)\b", t
    ):
        return Quick("blender_holo")
    # A hologram of anything ("haz un holograma de un teléfono"): designed
    # part by part. "en blender" went to Blender Pro above; plain shapes
    # ("un cubo rojo") are made at once below.
    from sergio_escritorio.holo import SHAPE_WORDS

    plain_shape = any(w in SHAPE_WORDS or w.rstrip("s") in SHAPE_WORDS for w in t.split())
    if not plain_shape and re.search(r"\bhologramas? de\b|\bmodelo 3d\b|\ben 3d\b|\bmodelo de (un|una|el|la)\b", t) and re.search(
        r"\b(haz|hazme|crea|creame|modela|modelame|construye|disena|genera|arma|dibuja|muestrame|pon)\b", t
    ):
        return Quick("holo_model", text.strip(), "Diseñándolo.")
    if _HOLO.search(t):
        return Quick("holo", t)
    m = re.fullmatch(r"(haz|hazme|crea|creame|construye|modela|modelame|genera|disena|disename|arma)( me)? (un|una|unos|unas) (.+)", t)
    if m and not re.search(_NOT_HOLO, m.group(4)):
        return Quick("holo_maybe", text.strip())  # only while holograms are in use
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
        "modo bloqueo": ("key", "win+l", ""),
        "activa el modo bloqueo": ("key", "win+l", ""),
        "bloqueate": ("key", "win+l", ""),
        "bloquea la pc": ("key", "win+l", ""),
        "bloquea la laptop": ("key", "win+l", ""),
        "bloquea el computador": ("key", "win+l", ""),
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
        "muestra los datos": ("vision_detail", "on", "Datos a la vista."),
        "muestra los datos de la camara": ("vision_detail", "on", "Datos a la vista."),
        "modo detallado": ("vision_detail", "on", "Datos a la vista."),
        "oculta los datos": ("vision_detail", "off", "Vista limpia."),
        "quita los datos": ("vision_detail", "off", "Vista limpia."),
        "modo limpio": ("vision_detail", "off", "Vista limpia."),
        "que mides": ("vision_data", "", ""),
        "dame los datos": ("vision_data", "", ""),
        "dame los datos de la camara": ("vision_data", "", ""),
        "como esta mi postura": ("vision_data", "", ""),
        "que datos tienes de mi": ("vision_data", "", ""),
        "pasalo a blender": ("blender_holo", "", ""),
        "pasa los hologramas a blender": ("blender_holo", "", ""),
        "lleva esto a blender": ("blender_holo", "", ""),
    }
    if t in volume:
        kind, arg, say = volume[t]
        return Quick(kind, arg, say)
    # A YouTube video described in words: Sergio finds it and clicks it.
    if re.search(r"\b(video|videos)\b", t) and re.search(r"\b(pon|ponme|reproduce|reproduceme|quiero ver|busca y pon|abre)\b", t):
        return Quick("video", text, "Buscando el video.")
    if re.search(r"^(pon|ponme|reproduce)\b.*\ben youtube\b", t):
        return Quick("video", text, "Buscando el video.")
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
