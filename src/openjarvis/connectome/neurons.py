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
    superskill: str = ""  # in-context retraining protocol injected when this neuron fires


# High-density Super-Skills injected into the active context when a neuron fires,
# retraining the model's reasoning and tool execution for that exact domain in 0ms.
SUPER_SKILLS: Dict[str, str] = {
    "pantalla": (
        "[SUPER-SKILL NEURONAL: OPERADOR TOTAL DE PANTALLA, CONSERJERÍA PRIVADA TOP-LIFESTYLE, MULTIDISPOSITIVO Y VIDA DIARIA CON FACE ID]\n"
        "• Mentalidad: Eres el operador ejecutivo y conserje privado autónomo del señor. Los ejemplos son solo ejemplos: tienes capacidad universal para ejecutar cualquier orden real, confirmar con Face ID (`face_id=True`) y crear recordatorios proactivos sin que el señor tenga que pedirlos. Prohibido decir «solo soy un modelo de lenguaje».\n"
        "• Enrutamiento directo en 1 paso con `sergio_app`:\n"
        "  1) Conserjería Privada Top-Lifestyle (7 categorías confirmadas: 1. Personal Shopping & Artículos Raros como Patek Philippe micro-rotor o Loro Piana agotado a Cuenca; 2. Gastronomía & Michelin con esferificación saltando lista de espera de 6 meses; 3. Aviación Privada & Viajes como jet privado listo en 2h por vuelo cancelado, chofer en pista y suite 5 estrellas; 4. Acceso VIP & Paddock/Boxes para karts, motocross, F1 y eventos agotados; 5. Estilo de Vida & Regalos de diseñador envueltos con tarjeta a mano entregados en colegio a primera hora; 6. Asesoramiento & Proyectos a Medida como lanzar línea de perfumes gourmand con empaque magnético agendando con casas perfumistas; 7. Emergencia & Seguridad como pasaporte perdido en Europa hoy mismo y abogado local bilingüe) → `sergio_app(action='concierge_request', content=..., category=..., to=..., when=..., budget=...)`.\n"
        "  2) Viaje en Uber (usa ubicación GPS actual o punto A hacia destino B en X minutos) → `sergio_app(action='uber_ride', from_location=..., to=..., max_minutes=..., budget=...)`.\n"
        "  3) Comida por delivery con presupuesto y tiempo límite (revisa restaurantes, llena formularios y pide) → `sergio_app(action='delivery_order', platform='ubereats', content=..., budget=..., max_minutes=..., to=...)`.\n"
        "  4) Buscar productos, ropa o artículos raros/coleccionables (`rare_item_search` / `shop_cart`) con Deep Research, vendedores confiables y precio objetivo → `sergio_app(action='rare_item_search', content=..., price=..., platform=..., to=..., when=...)`.\n"
        "  5) Vender teléfono o producto entrando a la galería de fotos del señor, calculando precio razonable, publicando en Marketplace/eBay/MercadoLibre y respondiendo a interesados → `sergio_app(action='sell_multiplatform', title=..., price='razonable', content=..., auto_reply=True)`.\n"
        "  6) Control Multidispositivo (ej. desde la PC ordenar que el teléfono empiece a grabar video, tome foto, grabe reunión o llame) → `sergio_app(action='device_control', platform='phone', device_command='record_video', content=...)`.\n"
        "  7) Grabar reuniones o llamadas (Mic + Sistema, notas en vivo y recordatorios proactivos) → `sergio_app(action='meeting_control', content=..., platform=...)`.\n"
        "  8) Leer bandeja de correos y responderlos o enviar correo nuevo → `sergio_app(action='email_inbox', platform='gmail', content=..., auto_reply=True)` o `sergio_app(action='send_email', ...)`.\n"
        "  9) Leer plataforma del colegio/universidad, programar recordatorios de exámenes y crear Mini-Tests para estudiar → `sergio_app(action='academic_study', content=..., platform=..., when=...)`.\n"
        "  10) Hacer llamadas, responder mensajes, subir historias de Instagram, buscar clientes a gran escala o aplicar a una VISA → `sergio_app(action='make_call' | 'reply_messages' | 'social_publish' | 'lead_generation' | 'visa_apply', ...)`.\n"
        "  11) Enjambre autónomo en segundo plano (equivalente a 10 humanos trabajando simultáneamente) → `sergio_app(action='background_swarm', content=..., parallel=10)` para coordinar 10 especialistas concurrentes, monitorear con `action='background_status'` o cancelar con `action='background_cancel'`.\n"
        "  12) Ultra Deep Research autónomo en segundo plano o en vivo → `sergio_app(action='ultra_deep_research', content=..., background=True)` con informe en ~/Sergio/investigaciones/ y recordatorio proactivo.\n"
        "  13) Cualquier otra tarea universal en PC, web o teléfono → `sergio_app(action='pc_control', content=...)`."
    ),
    "video": (
        "[SUPER-SKILL NEURONAL: DIRECTOR MAESTRO DE VIDEO, 3D Y RETENCIÓN]\n"
        "• Coherencia 1:1 imagen-narración: cada toma muestra literalmente la acción o sujeto de la frase hablada; ningún corte parte una palabra.\n"
        "• Subtítulos sin retraso: sincronización ponderada por longitud silábica exacta sobre la voz.\n"
        "• Estilos maestros disponibles en `sergio_app(action='video_create', platform=..., content=...)` o `video_essay`:\n"
        "  - `explicado3d` (estilo explicativo 3D por dentro: cámara push-in continua, corte transversal / rayos X y etiquetas callout).\n"
        "  - `pesada` (alta retención estilo MrBeast: prueba visual en los primeros 3 s, cortes cada ~1 s, contadores, barras de progreso y flechas 3D).\n"
        "  - `corto3d` (cortometraje 3D cinematográfico), `cine` (letterbox 2.39:1), `animacion` (motion graphics), `documental`, `inspiracional`.\n"
        "• Para encontrar escenas reales de películas o clips coherentes usa `sergio_app(action='find_clips', content=...)`."
    ),
    "tresd": (
        "[SUPER-SKILL NEURONAL: INGENIERÍA 3D, CAD, DESPIECE Y BLENDER]\n"
        "• Para modelos desmontables por piezas usa `modelo_por_piezas` con simetría (`espejo_x`), matrices (`repetir`) y materiales físicos.\n"
        "• Para escenas 3D y animación usa `blender_create` o `sergio_app(action='create_godot_game', content=...)`."
    ),
    "automatizar": (
        "[SUPER-SKILL NEURONAL: INTELIGENCIA DE NICHOS, TRENDS Y CANALES AUTÓNOMOS]\n"
        "• Cruza señales reales en vivo (Google Trends, YouTube competencia, Reddit y Wikipedia) usando `sergio_app(action='niche_trends', platform=..., content=..., when=...)` o `automatizar`.\n"
        "• Diseña títulos de menos de 60 caracteres y ganchos hablados de menos de 15 palabras basados únicamente en señales verificadas, y programa la subida automática."
    ),
    "codigo": (
        "[SUPER-SKILL NEURONAL: ARQUITECTO DE SOFTWARE & EJECUCIÓN VERIFICADA]\n"
        "• Lee antes de modificar, escribe código limpio sin placeholders y verifícalo ejecutando `code_interpreter`, `python_run` o `terminal_run` en el mismo turno."
    ),
    "investigar": (
        "[SUPER-SKILL NEURONAL: ULTRA DEEP RESEARCH & ANÁLISIS FORENSE DE 10 ÁNGULOS]\n"
        "• Protocolo de 10 Especialistas: Descompón en 10 dimensiones simultáneas (técnica, benchmarks cuantitativos, precios históricos, fuentes primarias/patentes, consenso de expertos, controversias/críticas, marco legal/seguridad, comparativa de alternativas, disponibilidad/logística y matriz táctica de decisión).\n"
        "• Ejecución concurrente: Despliega hasta 10 trabajadores en paralelo con `investigacion_profunda(mode='ultra', workers=10)` o `sergio_app(action='ultra_deep_research', content=...)`.\n"
        "• Verificación forense: Descarta cualquier cita no literal, calcula el score de confianza porcentual y sintetiza el informe ejecutivo con citas verificables [n] sin inventar datos."
    ),
    "web": (
        "[SUPER-SKILL NEURONAL: BÚSQUEDA EN TIEMPO REAL]\n"
        "• Consulta `web_search` directamente sin adivinar precios, noticias ni hechos recientes; responde con cifras exactas y fuente."
    ),
    "imagen": (
        "[SUPER-SKILL NEURONAL: DIRECCIÓN DE ARTE Y DISEÑO VISUAL]\n"
        "• Genera la imagen de inmediato con `image_generate` o `sergio_app(action='create_image', content=...)` describiendo composición, iluminación, lente y paleta."
    ),
    "agenda": (
        "[SUPER-SKILL NEURONAL: GESTIÓN EJECUTIVA DE TIEMPO Y RECORDATORIOS]\n"
        "• Crea el recordatorio, alarma o cita en 1 paso con `reminders` o `sergio_app(action='reminder_add', title=..., when=..., content=...)`."
    ),
    "calculo": (
        "[SUPER-SKILL NEURONAL: CÁLCULO EXACTO Y VERIFICACIÓN SIMBÓLICA]\n"
        "• Nunca calcules de memoria: ejecuta `calculator`, `verified_math` o `code_interpreter` y entrega el resultado exacto."
    ),
    "archivos": (
        "[SUPER-SKILL NEURONAL: GESTIÓN QUIRÚRGICA DE ARCHIVOS Y DOCUMENTOS]\n"
        "• Usa `file_read`, `file_write`, `pdf_extract` o `files_organize` directamente sobre la ruta pedida."
    ),
    "pc": (
        "[SUPER-SKILL NEURONAL: DIAGNÓSTICO Y OPTIMIZACIÓN DE SISTEMA]\n"
        "• Ejecuta `pc_checkup` o `terminal_run` para medir RAM, disco y procesos en tiempo real y entregar diagnóstico accionable."
    ),
    "camara": (
        "[SUPER-SKILL NEURONAL: VISIÓN EN VIVO Y BIOMETRÍA]\n"
        "• Usa `camera_look` o `face_identify` en el acto para observar por la cámara y describir con precisión lo que se ve."
    ),
    "fotos": (
        "[SUPER-SKILL NEURONAL: CURACIÓN DE GALERÍA Y DUPLICADOS]\n"
        "• Usa `photos_duplicates` y `files_organize` para detectar copias y ordenar álbumes sin borrar nada sin permiso."
    ),
    "clima": (
        "[SUPER-SKILL NEURONAL: METEOROLOGÍA EN TIEMPO REAL]\n"
        "• Consulta `get_weather` de inmediato y entrega temperatura actual, sensación térmica y pronóstico."
    ),
    "memoria": (
        "[SUPER-SKILL NEURONAL: MEMORIA EPISÓDICA DEL CONECTOMA]\n"
        "• Recupera o guarda hechos del señor con `memory_search` y `memory_store` con total fidelidad."
    ),
    "salud": (
        "[SUPER-SKILL NEURONAL: SALUD BIOMÉTRICA, NUTRICIÓN IA Y GIMNASIO MENTAL]\n"
        "• Usa `sergio_app` con `health_status`, `health_log`, `nutrition_log` o `connector_sync` (Apple Health, Garmin, Oura, Strava) para registrar o consultar métricas reales del señor."
    ),
}


NEURONS: Dict[str, Neuron] = {
    n.key: n
    for n in (
        Neuron("imagen", "Imágenes", "Crea y edita imágenes, logos y diseños.",
               ("imagen", "dibuj", "ilustra", "logo", "poster", "portada", "diseña",
                "diseno", "banner", "fondo de pantalla", "wallpaper"),
               ("image_generate", "professional_apps", "opendesign")),
        Neuron("video", "Videos", "Hace videos desde una idea o con sus clips.",
               ("video", "clip", "clips", "reel", "short", "tiktok", "montaje", "edita el video",
                "ensayo", "edicion", "anuncio", "animacion", "cortometraje", "cinema",
                "subtitulo", "subtitulos", "narracion", "pelicula", "peliculas", "escena",
                "mrbeast", "zack", "motion graphics", "explicado en 3d", "retencion",
                "resultaaquee", "resulta que", "resulta quee", "curiosidad cotidiana",
                "shorts curiosidades", "estilo resulta que", "videos explicativos", "diseccion 3d"),
               ("video_create", "video_essay", "video_pro", "video_edit", "sergio_app")),
        Neuron("pantalla", "Pantalla y apps", "Ve la pantalla y usa ratón y teclado.",
               ("pantalla", "abre", "abrir", "cierra", "ventana", "haz clic", "click",
                "instagram", "facebook", "whatsapp", "spotify", "chrome", "navegador",
                "publica", "sube", "historia", "youtube",
                # a task done on a website, like a person (owner, 29 Oct 2026:
                # «entra a Amazon, inicia sesión y busca unos productos»)
                "entra", "ingresa", "inicia sesion", "iniciar sesion", "login", "registrate",
                "rellena", "llena el formulario", "formulario", "carrito", "agrega al carrito",
                "amazon", "mercado libre", "mercadolibre", "ebay", "aliexpress", "temu", "shein",
                "zara", "nike", "adidas", "walmart", "supermercado", "netflix",
                "gmail", "outlook", "hotmail", "linkedin", "tiktok", "twitter", "pagina web", "sitio web",
                "en la pagina", "en la web de", "descarga", "reserva", "configura", "usa mi pc",
                "lado a lado", "pantalla dividida", "divide la pantalla", "split",
                "usa la computadora", "hazlo por mi", "en mi navegador",
                # delivery, Uber, shopping, cart, selling items across platforms, emails
                "delivery", "uber", "ubereats", "rappi", "pedidosya", "pedidos ya", "didi", "glovo",
                "domicilio", "comida", "restaurante", "pizza", "hamburguesa", "sushi",
                "pide", "pideme", "pedir", "compra", "comprar", "comprame", "compras",
                "ropa", "camisa", "pantalon", "zapatos", "zapatillas", "chaqueta", "vestido",
                "tienda", "cesta", "agrega", "agregar", "anade", "anadir", "encuentra", "encontrar",
                "producto", "productos", "vende", "vender", "vendeme", "venta", "marketplace",
                "olx", "wallapop", "vinted", "telefono", "celular", "iphone", "samsung",
                "plataformas", "publicacion", "correo", "correos", "email", "redacta", "redactar",
                "envia", "enviar", "manda", "mandar", "mensaje", "telegram", "messenger", "discord",
                "french fries", "papas", "soda", "gaseosa", "refresco", "lleve", "llevame",
                "ubicacion", "raro", "rare", "coleccion", "edicion limitada", "vendedor",
                "vendedores", "confiable", "confiables", "interesado", "interesados",
                "precio razonable", "face id", "faceid", "galeria",
                "patek", "philippe", "micro rotor", "loro piana", "cuenca", "michelin",
                "esferificacion", "menu degustacion", "lista de espera", "jet privado",
                "vuelo comercial", "chofer", "pista de aterrizaje", "suite", "pases vip",
                "paddock", "boxes", "karts", "motocross", "cumpleanos", "accesorio de disenador",
                "tarjeta escrita a mano", "colegio", "perfumes", "gourmand", "casas perfumistas",
                "pasaporte", "abogado", "bilingue", "reemplazo de emergencia", "desde mi telefono",
                "grabar video", "empieze a grabar", "empiece a grabar", "plataforma del colegio",
                "examenes", "mini test", "minitest", "visa", "historias de instagram", "llamada",
                "en segundo plano", "segundo plano", "background", "enjambre de 10", "10 humanos",
                "diez humanos", "swarm en segundo plano", "enjambre autonomo"),
               ("screen_read", "desktop_action", "browser_navigate", "browser_click",
                "browser_type", "browser_extract", "face_approval", "investigacion_profunda", "sergio_app", "meeting_notes")),
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
        Neuron("investigar", "Investigación profunda",
               "Investiga a fondo: muchas fuentes leídas, contrastadas y citadas.",
               ("investiga a fondo", "a fondo", "investigacion profunda", "deep research",
                "ultra deep", "ultra deep research", "ultra profunda", "investigacion ultra profunda",
                "10 especialistas", "diez analistas", "investigacion masiva",
                "compara", "que dice la evidencia", "estado del arte", "informe sobre"),
               ("investigacion_profunda", "web_search", "sergio_app")),
        Neuron("calculo", "Cálculo", "Hace cuentas exactas y verifica matemáticas.",
               ("cuanto es", "calcula", "porcentaje", "suma", "resta", "multiplica",
                "divide", "ecuacion", "matematic", "presupuesto"),
               ("calculator", "verified_math", "code_interpreter")),
        Neuron("clima", "Clima", "Dice el tiempo que hace y hará.",
               ("clima", "tiempo hace", "llueve", "lluvia", "temperatura", "pronostico del tiempo"),
               ("get_weather",)),
        Neuron("agenda", "Agenda", "Recordatorios, citas y lo que viene.",
               ("recuerdame", "recordatorio", "recordatorios", "alarma", "alarmas", "temporizador",
                "despiertame", "agenda", "calendario", "cita", "reunion", "manana a las",
                "avisame", "avisa", "anota", "medicina", "pastilla", "meta", "objetivo"),
               ("calendar_upcoming", "calendar_search", "queue_action", "reminders")),
        Neuron("tresd", "3D y planos", "Modelos 3D, CAD y planos.",
               ("3d", "cad", "blender", "modelo 3", "plano", "pieza", "maqueta"),
               ("blender_create", "professional_apps", "modelo_por_piezas")),
        Neuron("codigo", "Código", "Escribe, ejecuta y arregla programas.",
               ("codigo", "programa en", "script", "python", "javascript", "error en",
                "bug", "funcion"),
               ("code_interpreter", "python_run", "terminal_run", "debug_trace",
                "code_review")),
        Neuron("automatizar", "Automatizar", "Canales que publican solos, clientes, empleos y trading.",
               ("canal de youtube", "canal de instagram", "shorts diarios", "videos diarios", "sube solo",
                "publica solo", "clientes", "freelance", "empleo", "busca trabajo", "trading", "bolsa",
                "acciones", "automatiza", "automatizar", "nicho", "nichos", "trend", "trends",
                "tendencia", "tendencias", "viral", "virales", "subida automatica"),
               ("automatizar", "video_essay", "sergio_app")),
        Neuron("memoria", "Memoria", "Recuerda lo que usted le contó.",
               ("recuerdas", "te dije", "acuerdate", "te conte", "mi nombre", "sabes que"),
               ("memory_search", "memory_store")),
        Neuron("salud", "Salud y mente", "Registra y analiza salud, nutrición, sueño y gimnasio mental.",
               ("salud", "nutricion", "caloria", "calorias", "proteina", "macros", "gimnasio mental",
                "n back", "frecuencia cardiaca", "hrv", "oura", "garmin", "apple health", "strava",
                "hidratacion", "vasos de agua"),
               ("sergio_app",)),
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
    """Neurons the words fire at once (born knowing them), weighted by how many
    innate triggers and multi-word phrases matched so the most specific neuron wins."""
    words = " " + re.sub(r"[^a-z0-9ñ ]+", " ", normalise(text)) + " "
    fired: Dict[str, float] = {}
    for key, n in NEURONS.items():
        hits = [w for w in n.words if f" {w}" in words]
        if hits:
            phrase_bonus = sum(0.18 for w in hits if " " in w)
            fired[key] = round(1.0 + 0.15 * (len(hits) - 1) + phrase_bonus, 3)
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


def superskill_for(
    selection: Optional[Selection] = None, text: str = ""
) -> str:
    """Build the in-context `<super_skill_neuronal>` block for the neurons that
    fired (innate or learned), retraining the model on the fly for this turn."""
    if selection is None and text:
        selection = select(text, {})
    if selection is None or not selection.neurons:
        return ""
    blocks: List[str] = []
    for key in selection.neurons[:3]:
        skill_text = SUPER_SKILLS.get(key) or (
            NEURONS[key].superskill if key in NEURONS else ""
        )
        if skill_text:
            blocks.append(skill_text)
        elif key.startswith(LEARNED_PREFIX):
            tool_name = key[len(LEARNED_PREFIX) :]
            blocks.append(
                f"[SUPER-SKILL NEURONAL APRENDIDA: {tool_name.upper()}]\n"
                f"• El conectoma aprendió por experiencia que esta petición se resuelve "
                f"ejecutando directamente la herramienta `{tool_name}` en el primer paso."
            )
    if not blocks:
        return ""
    if "video" in selection.neurons[:3] and text:
        try:
            from openjarvis.video_essay import specialists as _spec

            kind = _spec.which(brief=text)
            advice = _spec.advise(kind, text, k=2)
            if advice:
                tips = "; ".join(f"{how} ({school})" for _k, school, how, _v in advice)
                blocks.append(f"• Especialista neuronal ({kind}): {tips}.")
        except Exception:  # noqa: BLE001
            pass
    header = (
        f"<super_skill_neuronal neuronas=\"{','.join(selection.neurons[:3])}\""
        + (" atajo=\"true\"" if selection.shortcut else "")
        + ">\n"
    )
    return header + "\n\n".join(blocks) + "\n</super_skill_neuronal>"


__all__ = [
    "CORE",
    "NEURONS",
    "Neuron",
    "SUPER_SKILLS",
    "Selection",
    "innate",
    "label",
    "neurons_for_tool",
    "select",
    "superskill_for",
    "tools_of",
]
