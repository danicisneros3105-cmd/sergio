"""The neurons that decide what Sergio does: the core, like the fly brain.

Each neuron has one job (pictures, videos, the screen, files, the web…) and
the tools that do it. A request lights up neurons two ways:

* **innate** (lateral horn): words it is born knowing («imagen», «cámara»,
  «recuérdame») fire the neuron at once;
* **learned** (mushroom body): every time a tool works for a request, the
  synapses from the request's Kenyon cells to that tool's neuron get
  stronger. Next time similar words fire it even without the innate words.
  A tool that works and belongs to no neuron (a new connector, a new skill)
  becomes a **new neuron** of its own: the brain grows connections.

A synapse that strong (``SHORTCUT``) is an internal **shortcut**: that
request goes straight to its neuron's tools.

The brain then hands the agent only the tools of the neurons that fired,
plus a few that always help (``CORE``). Fewer, fitting tools: faster turns
and fewer wrong calls than offering all sixty every time. When nothing fires
with confidence, nothing is narrowed: the agent sees every tool, as before.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Neuron:
    key: str
    label: str  # what the owner reads on the brain page
    job: str
    words: Tuple[str, ...]  # innate triggers, without accents, as word starts
    tools: Tuple[str, ...]


NEURONS: Dict[str, Neuron] = {
    n.key: n
    for n in (
        Neuron("imagen", "Imágenes", "Crea y edita imágenes, logos y diseños.",
               ("imagen", "dibuj", "ilustra", "logo", "poster", "portada", "diseña",
                "diseno", "banner", "fondo de pantalla", "wallpaper"),
               ("image_generate", "professional_apps", "opendesign")),
        Neuron("video", "Videos", "Hace videos desde una idea o con sus clips.",
               ("video", "clip", "reel", "short", "tiktok", "montaje", "edita el video",
                "ensayo", "edicion", "anuncio", "animacion", "cortometraje", "cinema"),
               ("video_create", "video_essay", "video_pro", "video_edit")),
        Neuron("pantalla", "Pantalla y apps", "Ve la pantalla y usa ratón y teclado.",
               ("pantalla", "abre", "abrir", "cierra", "ventana", "haz clic", "click",
                "instagram", "facebook", "whatsapp", "spotify", "chrome", "navegador",
                "publica", "sube", "historia", "youtube"),
               ("screen_read", "desktop_action", "browser_navigate", "browser_click",
                "browser_type", "browser_extract")),
        Neuron("pc", "Su PC", "Revisa por qué va lenta y la deja ligera.",
               ("lenta", "lento", "rapida", "rapido", "ram", "disco", "memoria del pc",
                "inicio de windows", "temporales", "ventilador", "se traba"),
               ("pc_checkup", "terminal_run")),
        Neuron("archivos", "Archivos", "Ordena carpetas y lee o escribe documentos.",
               ("archivo", "carpeta", "documento", "descargas", "escritorio", "ordena",
                "organiza", "pdf", "excel", "word"),
               ("files_organize", "file_read", "file_write", "pdf_extract")),
        Neuron("fotos", "Fotos", "Ordena la galería y encuentra duplicadas.",
               ("galeria", "fotos", "duplicad", "album"),
               ("photos_duplicates", "files_organize", "face_identify")),
        Neuron("camara", "Cámara y caras", "Mira por la cámara y reconoce caras.",
               ("camara", "como me veo", "mirame", "quien es", "cara de"),
               ("camera_look", "face_identify", "face_list")),
        Neuron("web", "Internet", "Busca y lee lo último en internet.",
               ("busca", "investiga", "noticia", "internet", "precio", "ultimo", "ultima",
                "que paso", "google", "web"),
               ("web_search", "http_request", "browser_extract")),
        Neuron("calculo", "Cálculo", "Hace cuentas exactas y verifica matemáticas.",
               ("cuanto es", "calcula", "porcentaje", "suma", "resta", "multiplica",
                "divide", "ecuacion", "matematic", "presupuesto"),
               ("calculator", "verified_math", "code_interpreter")),
        Neuron("clima", "Clima", "Dice el tiempo que hace y hará.",
               ("clima", "tiempo hace", "llueve", "lluvia", "temperatura", "pronostico del tiempo"),
               ("get_weather",)),
        Neuron("agenda", "Agenda", "Recordatorios, citas y lo que viene.",
               ("recuerdame", "recordatorio", "alarma", "agenda", "calendario", "cita",
                "reunion", "manana a las", "avisame", "medicina", "pastilla", "meta", "objetivo"),
               ("calendar_upcoming", "calendar_search", "queue_action", "reminders")),
        Neuron("tresd", "3D y planos", "Modelos 3D, CAD y planos.",
               ("3d", "cad", "blender", "modelo 3", "plano", "pieza", "maqueta"),
               ("blender_create", "professional_apps")),
        Neuron("codigo", "Código", "Escribe, ejecuta y arregla programas.",
               ("codigo", "programa en", "script", "python", "javascript", "error en",
                "bug", "funcion"),
               ("code_interpreter", "python_run", "terminal_run", "debug_trace",
                "code_review")),
        Neuron("memoria", "Memoria", "Recuerda lo que usted le contó.",
               ("recuerdas", "te dije", "acuerdate", "te conte", "mi nombre", "sabes que"),
               ("memory_search", "memory_store")),
    )
}  # fmt: skip

# Always offered when the brain narrows: thinking, a quick search, memory
# and plain arithmetic help with almost anything.
CORE = ("think", "web_search", "memory_search", "calculator", "sergio_app")
FIRE = 0.5  # activation that lights a neuron
SHORTCUT = 0.6  # a learned synapse this strong is a shortcut
LEARNED_PREFIX = "aprendida:"  # a neuron the brain grew for one tool


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def innate(text: str) -> Dict[str, float]:
    """Neurons the words fire at once (born knowing them)."""
    words = " " + re.sub(r"[^a-z0-9ñ ]+", " ", normalise(text)) + " "
    fired: Dict[str, float] = {}
    for key, n in NEURONS.items():
        if any(f" {w}" in words for w in n.words):
            fired[key] = 1.0
    return fired


def tools_of(key: str) -> Tuple[str, ...]:
    if key.startswith(LEARNED_PREFIX):
        return (key[len(LEARNED_PREFIX) :],)
    n = NEURONS.get(key)
    return n.tools if n else ()


def neurons_for_tool(tool: str) -> List[str]:
    """The neurons a tool belongs to (a new one if it belongs to none)."""
    mine = [k for k, n in NEURONS.items() if tool in n.tools]
    if mine or tool in CORE:
        return mine
    return [LEARNED_PREFIX + tool]


def label(key: str) -> str:
    if key.startswith(LEARNED_PREFIX):
        return "Aprendida: " + key[len(LEARNED_PREFIX) :]
    n = NEURONS.get(key)
    return n.label if n else key


@dataclass(frozen=True)
class Selection:
    neurons: Tuple[str, ...]
    tools: FrozenSet[str]
    shortcut: bool  # a learned synapse alone decided it


def select(
    text: str, learned: Dict[str, float], routes: Iterable[str] = ()
) -> Optional[Selection]:
    """The neurons this request fires and the tools they bring, or None
    (nothing fired with confidence: the agent keeps every tool).

    *learned* is the activation of each ``neurona:`` item from the request's
    Kenyon cells; *routes* the single tools the brain learned for these words.
    """
    act = innate(text)
    for key, w in learned.items():
        act[key] = act.get(key, 0.0) + w
    fired = sorted((k for k, a in act.items() if a >= FIRE), key=lambda k: -act[k])
    routes = [r for r in routes if r]
    if not fired and not routes:
        return None
    tools = set(CORE) | set(routes)
    for key in fired[:4]:  # the strongest four, as a fly picks a few
        tools.update(tools_of(key))
    shortcut = any(learned.get(k, 0.0) >= SHORTCUT for k in fired)
    return Selection(tuple(fired[:4]), frozenset(tools), shortcut)


__all__ = [
    "CORE",
    "NEURONS",
    "Neuron",
    "Selection",
    "innate",
    "label",
    "neurons_for_tool",
    "select",
    "tools_of",
]
