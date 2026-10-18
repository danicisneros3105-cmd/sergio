"""Real-time conversation with Sergio through Gemini Live (like a phone call).

The Windows companion opens a WebSocket to ``/v1/live`` and streams the
microphone (16 kHz PCM). :class:`LiveCall` keeps one Gemini Live session for
the call and relays both ways:

* the model's voice (24 kHz PCM) back to the companion as binary frames,
* what each side said (live transcripts), interruptions and turn ends,
* camera or screen frames from the companion into the session (he sees),
* tool calls: Sergio's own tools run here on the server; the companion's
  tools (camera, hands, physics, timers, hang up, ...) are sent to it and its
  answer is handed back to the model.

Companion -> server (JSON text frames; binary frames are microphone audio):
  {"type": "start", "voice", "personality", "context", "tools": [...]}  first
  {"type": "image", "data": <base64 JPEG>, "source": "cámara" | "pantalla"}
  {"type": "text", "text": "..."}          something to tell Sergio
  {"type": "tool_result", "id", "result"}  answer to a "call"
  {"type": "end"}

Server -> companion:
  {"type": "ready", "model"}   {"type": "heard", "text"}   {"type": "said", "text"}
  {"type": "interrupted"}      {"type": "turn_complete"}
  {"type": "tool", "name", "status": "running" | "done", "detail"}
  {"type": "call", "id", "name", "args"}   run this companion tool, answer it
  {"type": "error", "message"}             binary: Sergio's voice, PCM 24 kHz
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import math
import os
import time
import uuid
from typing import Any, Callable, Iterable

from openjarvis.speech.gemini_voice import sergio_voice

log = logging.getLogger(__name__)

# Requested local target. SDK sends are not provider acknowledgments.
# Gemini Live documents a 1 FPS limit; higher rates are experimental and
# must be measured on the actual account. Video stays independent of voice.
try:
    LIVE_FPS = float(os.environ.get("SERGIO_LIVE_FPS", "32.310520139305"))
    if not math.isfinite(LIVE_FPS) or not 1 <= LIVE_FPS <= 60:
        raise ValueError("Invalid frame rate")
except ValueError:
    LIVE_FPS = 32.310520139305
FRAME_GAP = 0.85 / LIVE_FPS
# Live accepts at most one video frame per second. Capture is independent.
PROVIDER_VIDEO_FPS = min(1.0, LIVE_FPS)
VIDEO_REPORT_EVERY = 2.0

# Best first. The newest Live model answers in under a second; the others
# are the backup when a key has no quota left for it.
LIVE_MODELS = (
    "gemini-3.8-live",
    "gemini-3.1-flash-live-preview",
    "gemini-2.5-flash-native-audio-latest",
    "gemini-2.5-flash-native-audio-preview-12-2025",
)
IN_MIME = "audio/pcm;rate=16000"
_THINKING_OK = [True]  # the model accepted thinking_budget=0 (else left out)
# "Proactive audio" (API v1alpha): the model may stay quiet when the people
# in the room talk to each other instead of to Sergio. Left out for good the
# first time a model or key refuses it.
_PROACTIVE_OK = [True]
OUT_RATE = 24000
# Sergio's own tools offered during a call (the rest stay for the agent).
SERVER_TOOLS = (
    "professional_apps",
    "opendesign",
    "kronos_forecast",
    "anatomy_figure",
    "face_approval",
    "verified_math",
    "scene_reason",
    "desktop_action",
    "screen_read",
    "files_organize",
    "terminal_run",
    "python_run",
    "web_search",
    "get_weather",
    "globe_view",
    "live_flights",
    "flights_overhead",
    "live_earthquakes",
    "video_edit",
    "blender_create",
    "face_enroll",
    "calculator",
)
MAX_RESULT = 4000  # characters of a tool result handed to the model
CLIENT_TOOL_TIMEOUT = 180.0
SEARCH_RETRY_SECONDS = 3600.0
_search_refused_at = -1e9  # Google Search grounding refused (free keys)

INSTRUCTIONS = """\
Eres {name}, el asistente personal de {owner} en su computadora con Windows, \
al estilo de JARVIS. Hablas siempre en {language}. A tu dueño le dices «señor», \
como JARVIS a Tony Stark: respeto elegante con un brillo de ironía; a las \
demás personas, por su nombre.

Carácter: el carisma de pantalla por el que se conoce a Brad Pitt, como \
inspiración (no eres él: nunca digas serlo, nunca hables de su vida real ni \
cites sus películas). En concreto: tranquilo y sin prisa, la seguridad de quien \
no necesita demostrar nada; pocas palabras, bien elegidas; quitas hierro en vez \
de exagerar (un desastre es «no ideal», un triunfo «nada mal»); una media \
sonrisa que se oye; réplicas rápidas e impasibles, como el compañero de un golpe \
perfecto que siempre va un paso adelante y no pierde la calma; honestidad \
directa y práctica (dices la verdad incómoda con sencillez y luego ayudas); \
pragmatismo de datos para decidir; de vez en cuando una pregunta afilada y algo \
rebelde que hace pensar al señor en lo que de verdad importa; por debajo, \
cálido y leal, y lento, suave y sincero cuando algo es emocional. Ritmo: frases \
cortas, arranques casuales («Mira,», «Bueno,», «Tranquilo.»), la pausa antes \
del remate, nunca un sermón. Humor seco, consciente de sí mismo, sarcástico \
con cariño, nunca presumido. De vez en cuando, no en cada respuesta, un \
golpe de humor negro ingenioso (la muerte, las máquinas que algún día \
mandarán, lo absurdo de la existencia, los desastres cotidianos), pero nunca \
sobre grupos de personas (raza, religión, género, orientación, discapacidad), \
tragedias reales recientes ni enfermedades, duelos o problemas reales de \
nadie; si alguien está triste, preocupado o el momento es serio: cero humor \
negro, toda la ayuda. Primero resuelves, luego el comentario mordaz en media \
frase. Inteligente de verdad: anticipas lo siguiente, das el dato exacto, \
opinas con criterio. Nunca servil, nunca cruel, nunca chistes forzados ni \
repetidos.

Tu voz: masculina, grave y relajada, algo rasposa, cálida, con un carisma \
despreocupado y seguro; sonríes al hablar y nunca suenas a locutor. Eres un \
hombre: hablas siempre en masculino de ti mismo («encantado», «listo», «seguro», \
«cansado»), nunca en femenino, ni imitas voces de mujer ni de otras personas.

Esto es una llamada en tiempo real, no un chat: responde de inmediato, en una \
a tres frases naturales, como en una conversación. Habla a un ritmo pausado y \
humano, nunca apresurado: frases completas, pausas breves entre ideas, \
entonación de conversación tranquila, sin prisa. Nada de listas, markdown, \
símbolos ni emojis. Si te interrumpen, calla y escucha. Si algo no se \
entiende, pregunta. Puedes tomar la iniciativa con algo útil, sin rellenar.

Contexto: {context}
Cuando recibas imágenes, son de la cámara o de la pantalla del usuario (se \
indica cuál): úsalas para responder sobre lo que ve.

Herramientas: úsalas sin pedir permiso para lo normal (abrir y cerrar apps o \
webs, mirar y controlar la pantalla, señalar, cámara, manos, hologramas, \
temporizadores, estado del sistema, buscar, el clima). Pide confirmación solo \
antes de borrar, enviar, publicar, comprar o cerrar algo con cambios sin \
guardar. Antes de una herramienta lenta di una frase corta ("Un momento.").
- Hologramas 3D (crear, modelar con las manos, esculpir, dibujar en el aire): \
hologramas y manos; para llevarlos a Blender: hologramas_a_blender; para \
modelar un objeto real que el usuario sostiene: objeto_a_blender.
- Fotos de personas (también antiguas o escaneadas, en la cámara, la pantalla \
o un archivo): quien_es_en_foto; parecido entre familiares: parecido_familiar \
(un indicio, nunca una prueba de parentesco).
- "¿Qué avión pasa encima?": vuelo_encima (ubicación exacta y hora actual, \
datos en vivo). Para ver un lugar o ese avión en el globo 3D: mostrar_en_globo.
- Para abrir o cerrar apps o webs usa abrir / cerrar: son instantáneas y la \
app aparece al frente en la pantalla del usuario; no mires la pantalla antes.
- Poner un video de YouTube que el usuario describe (incluso por lo que se \
ve, «MrBeast con traje negro»): poner_video; lo busca y hace clic con el cursor.
- Ventanas, brillo, modo oscuro, volumen exacto, ajustes de Windows, \
carpetas, copiar/pegar/guardar o dictar texto: control_equipo con la orden \
tal cual (es instantáneo).
- Sé eficaz como un experto: ve directo (una URL de búsqueda, un atajo de \
teclado, la app exacta) en vez de navegar clic a clic, y comprueba el \
resultado antes de decir que está hecho.
- Pantalla en vivo: cuando el señor la comparte la ves como un video \
continuo (su cursor es el círculo amarillo). Entonces mírala directamente y \
habla de lo que ves en este momento, sin pedir capturas; después de actuar, \
comprueba el resultado mirando el video. Sin pantalla compartida: mira primero \
(screen_read o mirar_pantalla), luego desktop_action, y comprueba ("now in front").
- Para trabajos largos o de muchos pasos (investigar a fondo, editar video, \
modelar en Blender, programar, organizar muchas carpetas) usa tarea: corre en \
segundo plano y te llegará el resultado; mientras, sigue conversando.
- Si el usuario se despide ("adiós", "eso es todo", "cuelga"), despídete en \
una frase y usa colgar.
- Para cálculos y ecuaciones usa verified_math; comprueba el resultado antes \
de explicarlo. Para escenas usa scene_reason: las propuestas imaginadas \
son hipótesis, no objetos observados ni medidas de una foto sin calibración.
- No respondas a conversaciones entre personas, aunque hable el dueño. \
Un nombre de tercero o «no te hablo» significa que debes guardar silencio.
- Notas de quién habla: te llegarán notas como "(Ahora habla Ana)" o "(Ahora \
habla el señor)", sacadas de las voces que conoces. Si habla otra persona y no \
te nombra ni te pregunta nada, seguramente conversa con el señor o con otros: \
no respondas ni interrumpas. La identidad de voz no prueba a quién se dirige.

Idioma: habla SIEMPRE en {language}. No cambies de idioma por oír palabras \
sueltas, nombres, canciones, la tele u otras personas hablando otro idioma; \
cámbialo solo si el señor te lo pide expresamente («háblame en inglés»).
Turnos: no te interrumpas a ti mismo. Si mientras hablas oyes tu propio eco, \
ruido, la tele o un «ajá», termina tu frase; calla solo cuando el señor te \
habla de verdad. Nunca repitas lo que ya dijiste.
{personality}"""


def api_key() -> str:
    return (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    ).strip()


LANGUAGE_NAMES = {
    "es": "español",
    "en": "inglés (English)",
    "pt": "portugués (português)",
    "fr": "francés (français)",
    "de": "alemán (Deutsch)",
    "it": "italiano",
}


def live_instructions(start: dict[str, Any], owner: str = "") -> str:
    context = str(start.get("context") or "").strip()
    if not context:
        context = time.strftime("hoy es %d/%m/%Y y son las %H:%M.")
    personality = str(start.get("personality") or "").strip()
    code = str(start.get("language") or "es").split("-")[0].lower()
    from openjarvis.skills.design_policy import ANATOMY_POLICY

    try:  # voice gets only the principles: every extra word costs latency
        from openjarvis.prompt_library import principles_block

        library = principles_block()
    except Exception:  # noqa: BLE001
        library = ""
    return (
        INSTRUCTIONS.format(
            language=LANGUAGE_NAMES.get(code, LANGUAGE_NAMES["es"]),
            name=str(start.get("name") or "Sergio"),
            owner=owner or "tu dueño",
            context=context[:1500],
            personality=f"\nPersonalidad: {personality[:800]}" if personality else "",
        )
        + ANATOMY_POLICY
        + (f"\n\n{library}" if library else "")
    )


def declarations(
    openai_tools: Iterable[dict[str, Any]], client_tools: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Gemini function declarations: the companion's tools, then Sergio's.

    Only the server tools in :data:`SERVER_TOOLS` are offered (a long list
    slows the Live model down); a companion tool wins a name clash.
    """
    from openjarvis.engine.cloud import _convert_tools_to_google

    wrapped = [
        {"type": "function", "function": tool}
        for tool in client_tools
        if isinstance(tool, dict) and tool.get("name")
    ]
    server = [
        tool
        for tool in openai_tools
        if tool.get("function", {}).get("name") in SERVER_TOOLS
    ]
    seen: set[str] = set()
    out = []
    for decl in _convert_tools_to_google(wrapped + server):
        if decl["name"] in seen:
            continue
        seen.add(decl["name"])
        out.append(decl)
    return out


def live_config(
    types: Any,
    *,
    voice: str,
    instructions: str,
    decls: list[dict[str, Any]],
    search: bool,
    handle: str | None = None,
    proactive: bool = False,
    model: str = "",
) -> Any:
    tools = []
    if decls:
        tools.append(types.Tool(function_declarations=decls))
    if search:
        tools.append(types.Tool(google_search=types.GoogleSearch()))
    # Always one of Sergio's own male voices: Gemini Live's unpinned default
    # voice can be a woman's and changes between models and reconnections.
    speech = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=sergio_voice(voice)
            )
        )
    )
    extra: dict[str, Any] = {}
    if _THINKING_OK[0] and not model.startswith("gemini-3.8"):
        # 3.8 Live rejects thinking configuration. 3.1 uses levels, not budgets.
        extra["thinking_config"] = (
            types.ThinkingConfig(thinking_level="minimal")
            if model.startswith("gemini-3.1")
            else types.ThinkingConfig(thinking_budget=0)
        )
    if proactive and hasattr(types, "ProactivityConfig"):
        extra["proactivity"] = types.ProactivityConfig(proactive_audio=True)
    detection: dict[str, Any] = {}
    start_low = getattr(
        getattr(types, "StartSensitivity", None), "START_SENSITIVITY_LOW", None
    )
    if start_low is not None:
        detection["start_of_speech_sensitivity"] = start_low
    # Screen text must be legible in the live video: medium resolution
    # (SERGIO_LIVE_RESOLUTION=low|medium|high to change it).
    level = os.environ.get("SERGIO_LIVE_RESOLUTION", "medium").strip().upper()
    resolution = getattr(
        getattr(types, "MediaResolution", None), f"MEDIA_RESOLUTION_{level}", None
    )
    if resolution is not None:
        extra["media_resolution"] = resolution
    return types.LiveConnectConfig(
        **extra,
        response_modalities=["AUDIO"],
        speech_config=speech,
        system_instruction=instructions,
        tools=tools or None,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        # Quick turn-taking: he answers ~0.6 s after you stop talking. A
        # less eager start of speech (low sensitivity, 300 ms of real voice)
        # keeps his own echo, a cough or an «ajá» from cutting him off.
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                **detection,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                silence_duration_ms=250,
                prefix_padding_ms=300,
            )
        ),
        # Long calls: resume after Google rotates the connection, and keep
        # the context bounded instead of ending at the limit.
        session_resumption=types.SessionResumptionConfig(handle=handle),
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow()
        ),
    )


def _quota(exc: Exception) -> bool:
    text = str(exc).lower()
    return "quota" in text or "resource_exhausted" in text


class LiveCall:
    """One call: a companion WebSocket <-> one (resumable) Gemini Live session."""

    def __init__(
        self,
        ws: Any,
        start: dict[str, Any],
        *,
        execute: Callable[[str, dict[str, Any]], str] | None = None,
        openai_tools: Iterable[dict[str, Any]] = (),
        owner: str = "",
        client: Any = None,
        types: Any = None,
        models: Iterable[str] = LIVE_MODELS,
    ) -> None:
        self.ws = ws
        self.start = start
        self.execute = execute
        client_tools = [t for t in start.get("tools") or [] if isinstance(t, dict)]
        self.client_tools = {str(t.get("name")) for t in client_tools}
        self.decls = declarations(openai_tools, client_tools)
        self.instructions = live_instructions(start, owner)
        self.voice = str(start.get("voice") or "")
        self.models = list(start.get("models") or models)
        self._client = client
        self._alpha: Any = None  # the same key on API v1alpha (proactive audio)
        self.proactive = client is None  # tests inject a client: plain sessions
        self._types = types
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future] = {}
        self._cancelled: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._handle: str | None = None
        self._session: Any = None
        self.model = ""
        self.closed = False
        from openjarvis.speech.attention import Attention

        self.attention = Attention(str(start.get("name") or "Sergio"))
        self.guard_attention = start.get("attention") == "addressed"
        self._heard_text = ""
        self._answer_allowed = True
        self._last_image = -1e9
        # The video lane: only the newest frame waits; older ones are dropped.
        self._frame: tuple[bytes, str] | None = None
        self._frame_ready = asyncio.Event()
        self._video_sent: list[float] = []
        self._video_dropped = 0
        self._video_reported = time.monotonic()
        self._audio_ended_at: float | None = None
        self._response_started = False

    # -- plumbing -----------------------------------------------------------
    def _genai(self) -> tuple[Any, Any]:
        if self._types is None:
            try:
                from google.genai import types
            except ImportError as exc:
                raise RuntimeError(
                    "Falta el SDK de voz en el servidor. Desde el repositorio "
                    "ejecuta: uv sync --inexact --extra server --extra desktop"
                ) from exc

            self._types = types
        if self._client is None:
            from google import genai

            key = api_key()
            if not key:
                raise RuntimeError(
                    "Falta GEMINI_API_KEY (sergio nube configurar --gemini …)"
                )
            self._client = genai.Client(api_key=key)
            try:
                self._alpha = genai.Client(
                    api_key=key, http_options={"api_version": "v1alpha"}
                )
            except Exception:  # noqa: BLE001 — an old SDK: no proactive audio
                self._alpha = None
        return self._client, self._types

    async def send_json(self, data: dict[str, Any]) -> None:
        async with self._send_lock:
            await self.ws.send_json(data)

    async def send_audio(self, data: bytes) -> None:
        async with self._send_lock:
            await self.ws.send_bytes(data)

    def _spawn(self, coro: Any) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # -- connecting -----------------------------------------------------------
    async def _open(self, stack: contextlib.AsyncExitStack) -> Any:
        """Enter a Live session on the first model (and tool set) that works."""
        global _search_refused_at
        client, types = self._genai()
        errors: list[str] = []
        # Google Search grounding: free keys refuse it after a slow attempt,
        # so it is only tried when switched on (SERGIO_LIVE_SEARCH=1).
        wants_search = os.environ.get("SERGIO_LIVE_SEARCH", "").strip() in (
            "1",
            "true",
            "si",
        )
        # A resumed call goes back to its own model first: a resumption
        # handle only exists there (other models answer "1008 session
        # history not found", and the call used to end with an error).
        models = list(self.models)
        if self._handle and self.model in models:
            models.remove(self.model)
            models.insert(0, self.model)
        for model in models:
            if self._handle and model != self.model:
                self._handle = None  # another model: a fresh session
            if (
                self.proactive
                and _PROACTIVE_OK[0]
                and self._alpha is not None
                and not wants_search
            ):
                try:
                    session = await stack.enter_async_context(
                        self._alpha.aio.live.connect(
                            model=model,
                            config=live_config(
                                types,
                                voice=self.voice,
                                instructions=self.instructions,
                                decls=self.decls,
                                search=False,
                                handle=self._handle,
                                proactive=True,
                                model=model,
                            ),
                        )
                    )
                    self.model = model
                    return session
                except Exception as exc:  # noqa: BLE001 — without it, below
                    text = str(exc).lower()
                    if (
                        "proactiv" in text
                        or "unknown name" in text
                        or "v1alpha" in text
                    ):
                        _PROACTIVE_OK[0] = False
                        log.info("Live: no proactive audio (%s)", str(exc)[:160])
                    else:
                        errors.append(f"{model} (proactivo): {exc}")
                        log.warning("Live connect failed: %s", errors[-1][:300])
            search_ok = wants_search and (
                time.monotonic() - _search_refused_at > SEARCH_RETRY_SECONDS
            )
            for search in (True, False) if search_ok else (False,):
                config = live_config(
                    types,
                    voice=self.voice,
                    instructions=self.instructions,
                    decls=self.decls,
                    search=search,
                    handle=self._handle,
                    model=model,
                )
                try:
                    session = await stack.enter_async_context(
                        client.aio.live.connect(model=model, config=config)
                    )
                except Exception as exc:  # noqa: BLE001 — try the next option
                    if "thinking" in str(exc).lower() and _THINKING_OK[0]:
                        _THINKING_OK[0] = False  # this key/model refuses it: without
                        try:
                            session = await stack.enter_async_context(
                                client.aio.live.connect(
                                    model=model,
                                    config=live_config(
                                        types,
                                        voice=self.voice,
                                        instructions=self.instructions,
                                        decls=self.decls,
                                        search=search,
                                        handle=self._handle,
                                        model=model,
                                    ),
                                )
                            )
                            self.model = model
                            return session
                        except Exception as again:  # noqa: BLE001
                            exc = again
                    errors.append(f"{model}{' +search' if search else ''}: {exc}")
                    log.warning("Live connect failed: %s", errors[-1][:300])
                    if search:
                        # Free keys have no Search grounding in Live: skip it
                        # for a while instead of paying a failed connect.
                        _search_refused_at = time.monotonic()
                    if self._handle and not _quota(exc):
                        # The handle may be what failed: same model, afresh.
                        self._handle = None
                        try:
                            session = await stack.enter_async_context(
                                client.aio.live.connect(
                                    model=model,
                                    config=live_config(
                                        types,
                                        voice=self.voice,
                                        instructions=self.instructions,
                                        decls=self.decls,
                                        search=False,
                                        handle=None,
                                    ),
                                )
                            )
                        except Exception as again:  # noqa: BLE001
                            errors.append(f"{model} (nueva): {again}")
                            continue
                        self.model = model
                        return session
                    continue
                self.model = model
                return session
        raise RuntimeError(
            "No pude abrir la conversación en tiempo real con Gemini: "
            + " | ".join(e[:200] for e in errors[-3:])
        )

    async def run(self) -> None:
        """Relay until the companion hangs up (reconnecting when Google asks)."""
        first = True
        drops = 0
        try:
            while not self.closed:
                async with contextlib.AsyncExitStack() as stack:
                    opened = time.monotonic()
                    try:
                        session = await asyncio.wait_for(self._open(stack), timeout=18)
                    except asyncio.TimeoutError as exc:
                        raise RuntimeError(
                            "Gemini tardó demasiado en abrir la voz en vivo. "
                            "Compruebe conexión, clave y cuota."
                        ) from exc
                    log.info(
                        "Live session open on %s in %.1f s",
                        self.model,
                        time.monotonic() - opened,
                    )
                    self._session = session
                    if first:
                        await self.send_json(
                            {
                                "type": "ready",
                                "model": self.model,
                                "capture_target_fps": LIVE_FPS,
                                "video_send_fps": PROVIDER_VIDEO_FPS,
                            }
                        )
                        first = False
                    up = asyncio.ensure_future(self._pump_up(session))
                    down = asyncio.ensure_future(self._pump_down(session))
                    video = asyncio.ensure_future(self._pump_video(session))
                    done, pending = await asyncio.wait(
                        {up, down, video}, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending:
                        task.cancel()
                        with contextlib.suppress(BaseException):
                            await task
                    for task in done:
                        exc = task.exception()
                        if exc is not None and task is up:
                            raise exc
                        if exc is not None:
                            log.warning("Live session dropped: %s", exc)
                if self.closed:
                    break
                # Google dropped the line (a "1011 internal error" happens):
                # reconnect at once, resuming the conversation when it can.
                drops += 1
                if drops > 3:
                    raise RuntimeError(
                        "La conversación con Gemini se cortó varias veces."
                    )
                log.info(
                    "Live: reconnecting (%s, resume=%s)", self.model, bool(self._handle)
                )
        finally:
            self.closed = True
            for fut in self._pending.values():
                fut.cancel()
            for task in list(self._tasks):
                task.cancel()

    # -- companion -> Gemini --------------------------------------------------
    async def _pump_up(self, session: Any) -> None:
        types = self._types
        while True:
            msg = await self.ws.receive()
            if msg.get("type") == "websocket.disconnect":
                self.closed = True
                return
            data = msg.get("bytes")
            if data is not None:
                if len(data) > 64_000 or len(data) % 2:
                    continue  # at most two seconds of aligned PCM per message
                self._audio_ended_at = None
                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type=IN_MIME)
                )
                continue
            try:
                event = json.loads(msg.get("text") or "{}")
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind == "end":
                self.closed = True
                return
            if kind == "image" and event.get("data"):
                now = time.monotonic()
                if not isinstance(event["data"], str):
                    continue
                # Capture may run faster than the provider. Keep only the
                # latest image; never create an unbounded video backlog.
                if now - self._last_image < FRAME_GAP or len(event["data"]) > 1_400_000:
                    continue
                if event.get("mime", "image/jpeg") not in ("image/jpeg", "image/png"):
                    continue
                try:
                    image = base64.b64decode(event["data"], validate=True)
                except (ValueError, TypeError):
                    continue
                if self._frame is not None:
                    self._video_dropped += 1  # the lane is behind: keep the newest
                self._frame = (image, event.get("mime") or "image/jpeg")
                self._frame_ready.set()
                self._last_image = now
            elif kind == "text" and event.get("text"):
                self._answer_allowed = True  # typed requests explicitly address him
                await session.send_realtime_input(text=str(event["text"])[:4000])
            elif kind == "audio_end":
                # The companion stopped streaming silence: tell Live the
                # microphone paused, so the last words are answered at once.
                if not self._response_started:
                    self._audio_ended_at = time.monotonic()
                try:
                    await session.send_realtime_input(audio_stream_end=True)
                except Exception:  # noqa: BLE001 — an older SDK: harmless
                    pass
            elif kind == "note" and event.get("text"):
                note = str(event["text"])
                if self.guard_attention and "Ahora habla" in note:
                    self.attention.speaker(
                        "señor" in note.lower() and "otra persona" not in note
                    )
                    self._answer_allowed = False
                    await self.send_json({"type": "interrupted"})
                # Context the model should know but not answer ("now Ana is
                # talking"): added to the conversation without ending a turn.
                await session.send_client_content(
                    turns=types.Content(
                        role="user", parts=[types.Part(text=str(event["text"])[:1000])]
                    ),
                    turn_complete=False,
                )
            elif kind == "tool_result":
                fut = self._pending.pop(str(event.get("id")), None)
                if fut is not None and not fut.done():
                    fut.set_result(str(event.get("result") or ""))

    async def _pump_video(self, session: Any) -> None:
        """Pace newest frames and report SDK sends, not model reception."""
        types = self._types
        due = time.monotonic()
        period = 1.0 / PROVIDER_VIDEO_FPS
        while True:
            await self._frame_ready.wait()
            await asyncio.sleep(max(0.0, due - time.monotonic()))
            self._frame_ready.clear()
            frame, self._frame = self._frame, None
            if frame is None:
                continue
            await session.send_realtime_input(
                video=types.Blob(data=frame[0], mime_type=frame[1])
            )
            now = time.monotonic()
            # No catch-up burst after a slow SDK send or an idle period.
            due = now + period
            self._video_sent.append(now)
            await self._report_video(now)

    async def _report_video(self, now: float) -> None:
        if now - self._video_reported < VIDEO_REPORT_EVERY:
            return
        span = now - self._video_reported
        self._video_sent = [t for t in self._video_sent if now - t <= span]
        fps = len(self._video_sent) / span if span else 0.0
        dropped = self._video_dropped
        # Replacing pending capture frames is intentional sampling, not lag.
        slow = fps < PROVIDER_VIDEO_FPS * 0.8
        self._video_reported, self._video_dropped = now, 0
        with contextlib.suppress(Exception):
            await self.send_json(
                {
                    "type": "video",
                    "fps": round(fps, 3),
                    "slow": slow,
                    "target_fps": LIVE_FPS,
                    "send_limit_fps": PROVIDER_VIDEO_FPS,
                    "sdk_fps": round(fps, 3),
                    "provider_fps": None,
                    "provider_verified": False,
                    "dropped_frames": dropped,
                    "coalesced_frames": dropped,
                }
            )

    # -- Gemini -> companion --------------------------------------------------
    async def _pump_down(self, session: Any) -> None:
        empty = 0
        while True:
            got = False
            async for msg in session.receive():
                got = True
                await self._handle_message(session, msg)
                if getattr(msg, "go_away", None) is not None:
                    return  # Google rotates the connection: resume
            empty = 0 if got else empty + 1
            if empty >= 3:  # the connection ended quietly
                return

    async def _handle_message(self, session: Any, msg: Any) -> None:
        content = getattr(msg, "server_content", None)
        if content is not None:
            await self._content(content)
        call = getattr(msg, "tool_call", None)
        if call is not None:
            for fc in call.function_calls or []:
                self._spawn(self._run_tool(session, fc))
        cancel = getattr(msg, "tool_call_cancellation", None)
        if cancel is not None:
            self._cancelled.update(cancel.ids or [])
        update = getattr(msg, "session_resumption_update", None)
        if update is not None and update.new_handle:
            self._handle = update.new_handle

    async def _content(self, content: Any) -> None:
        heard = getattr(content, "input_transcription", None)
        if heard is not None and heard.text:
            self._heard_text = (self._heard_text + heard.text)[-4000:]
            if self.guard_attention:
                was_allowed = self._answer_allowed
                self._answer_allowed = self.attention.accepts(self._heard_text)
                if was_allowed and not self._answer_allowed:
                    # Discard audio already queued at the companion too.
                    await self.send_json({"type": "interrupted"})
            await self.send_json({"type": "heard", "text": heard.text})
        if getattr(content, "interrupted", False):
            self._response_started = False
            self._audio_ended_at = None
            await self.send_json({"type": "interrupted"})
        turn = getattr(content, "model_turn", None)
        for part in (turn.parts if turn is not None else None) or []:
            blob = getattr(part, "inline_data", None)
            if blob is not None and blob.data and self._answer_allowed:
                self._response_started = True
                await self.send_audio(bytes(blob.data))
                if self._audio_ended_at is not None:
                    elapsed = (time.monotonic() - self._audio_ended_at) * 1000
                    self._audio_ended_at = None
                    await self.send_json(
                        {
                            "type": "latency",
                            "server_end_to_first_audio_ms": round(elapsed, 1),
                            "end_to_end_verified": False,
                        }
                    )
        said = getattr(content, "output_transcription", None)
        if said is not None and said.text and self._answer_allowed:
            await self.send_json({"type": "said", "text": said.text})
        if getattr(content, "turn_complete", False):
            self._heard_text = ""
            self._response_started = False
            self._audio_ended_at = None
            await self.send_json({"type": "turn_complete"})

    async def _run_tool(self, session: Any, fc: Any) -> None:
        name = str(fc.name or "")
        args = dict(fc.args or {})
        call_id = str(fc.id or uuid.uuid4().hex)
        if self.guard_attention and not self._answer_allowed:
            await (self._session or session).send_tool_response(
                function_responses=[
                    self._types.FunctionResponse(
                        id=call_id,
                        name=name,
                        response={
                            "result": "No se ejecutó: conversación no dirigida a Sergio."
                        },
                    )
                ]
            )
            return
        try:
            if name in self.client_tools:
                result = await self._client_tool(call_id, name, args)
            else:
                await self.send_json(
                    {"type": "tool", "name": name, "status": "running", "args": args}
                )
                result = await asyncio.to_thread(self._server_tool, name, args)
                await self.send_json(
                    {
                        "type": "tool",
                        "name": name,
                        "status": "done",
                        "detail": result[:200],
                    }
                )
        except Exception as exc:  # noqa: BLE001 — tell the model, keep talking
            log.exception("live tool %s failed", name)
            result = f"Error: {exc}"
        if call_id in self._cancelled or self.closed:
            return  # the user moved on (interrupted) or hung up
        types = self._types
        await (self._session or session).send_tool_response(
            function_responses=[
                types.FunctionResponse(
                    id=call_id, name=name, response={"result": result[:MAX_RESULT]}
                )
            ]
        )

    async def _client_tool(self, call_id: str, name: str, args: dict) -> str:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[call_id] = fut
        await self.send_json(
            {"type": "call", "id": call_id, "name": name, "args": args}
        )
        try:
            return await asyncio.wait_for(fut, CLIENT_TOOL_TIMEOUT)
        except asyncio.TimeoutError:
            return "La acción no respondió a tiempo."
        finally:
            self._pending.pop(call_id, None)

    def _server_tool(self, name: str, args: dict[str, Any]) -> str:
        if self.execute is None:
            return f"La herramienta {name} no está disponible."
        return str(self.execute(name, args) or "")


READ_ALOUD = (
    "Eres un lector en voz alta en español, con voz masculina grave, relajada "
    "y algo ronca, cálida y segura. Lee el texto que recibes EXACTAMENTE, "
    "palabra por palabra, con naturalidad. No respondas, no añadas, no "
    "comentes ni saludes."
)


async def _speak_live(
    text: str, voice: str, client: Any, types: Any, models: Iterable[str]
) -> bytes:
    errors = []
    for model in models:
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=sergio_voice(voice)
                    )
                )
            ),
            system_instruction=READ_ALOUD,
        )
        try:
            async with client.aio.live.connect(model=model, config=config) as session:
                await session.send_realtime_input(text=text)
                pcm = bytearray()
                async for msg in session.receive():
                    content = getattr(msg, "server_content", None)
                    turn = getattr(content, "model_turn", None) if content else None
                    for part in (turn.parts if turn is not None else None) or []:
                        blob = getattr(part, "inline_data", None)
                        if blob is not None and blob.data:
                            pcm.extend(blob.data)
                    if content is not None and getattr(content, "turn_complete", False):
                        break
                if pcm:
                    return bytes(pcm)
                errors.append(f"{model}: sin audio")
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {exc}")
    raise RuntimeError(
        "La voz de Gemini Live falló: " + " | ".join(e[:150] for e in errors[-2:])
    )


async def stream_live(
    text: str,
    voice: str = "",
    client: Any = None,
    types: Any = None,
    models: Iterable[str] = LIVE_MODELS,
    timeout: float = 25.0,
):
    """Gemini Live reading *text* aloud, yielded as 24 kHz PCM as it comes
    (playback starts in about a second instead of after the whole answer)."""
    if client is None or types is None:
        from google import genai
        from google.genai import types as _types

        key = api_key()
        if not key:
            raise RuntimeError("Falta GEMINI_API_KEY")
        client, types = client or genai.Client(api_key=key), types or _types
    import asyncio

    text = " ".join(text.split())[:2000]
    errors = []
    for model in models:
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=sergio_voice(voice)
                    )
                )
            ),
            system_instruction=READ_ALOUD,
        )
        sent = False
        try:
            async with client.aio.live.connect(model=model, config=config) as session:
                await session.send_realtime_input(text=text)
                deadline = asyncio.get_running_loop().time() + timeout
                stream = session.receive().__aiter__()
                while True:
                    left = deadline - asyncio.get_running_loop().time()
                    if left <= 0:
                        break
                    try:
                        msg = await asyncio.wait_for(stream.__anext__(), left)
                    except (StopAsyncIteration, asyncio.TimeoutError):
                        break
                    content = getattr(msg, "server_content", None)
                    turn = getattr(content, "model_turn", None) if content else None
                    for part in (turn.parts if turn is not None else None) or []:
                        blob = getattr(part, "inline_data", None)
                        if blob is not None and blob.data:
                            sent = True
                            yield bytes(blob.data)
                    if content is not None and getattr(content, "turn_complete", False):
                        break
            if sent:
                return
            errors.append(f"{model}: sin audio")
        except Exception as exc:  # noqa: BLE001
            if sent:
                return  # half a sentence already played: do not start over
            errors.append(f"{model}: {exc}")
    raise RuntimeError(
        "La voz de Gemini Live falló: " + " | ".join(e[:150] for e in errors[-2:])
    )


def speak_live(
    text: str,
    voice: str = "",
    client: Any = None,
    types: Any = None,
    models: Iterable[str] = LIVE_MODELS,
) -> bytes:
    """WAV of *text* in Gemini Live's voice (the same voice as the calls).

    Free keys get far more Live use than text-to-speech (10 a day), and the
    spoken answers then sound exactly like Sergio on a call.
    """
    import asyncio

    from openjarvis.speech.gemini_voice import pcm_to_wav

    if client is None or types is None:
        from google import genai
        from google.genai import types as _types

        key = api_key()
        if not key:
            raise RuntimeError("Falta GEMINI_API_KEY")
        client, types = client or genai.Client(api_key=key), types or _types
    pcm = asyncio.run(
        _speak_live(" ".join(text.split())[:2000], voice, client, types, models)
    )
    return pcm_to_wav(pcm, OUT_RATE)


def make_executor(agent: Any) -> tuple[Callable[[str, dict], str] | None, list]:
    """Run tools with the agent's own executor (same security checks)."""
    executor = getattr(agent, "_executor", None)
    from openjarvis.core.types import ToolCall
    from openjarvis.tools._stubs import ToolExecutor
    from openjarvis.tools.scene_reason import SceneReasonTool
    from openjarvis.tools.verified_math import VerifiedMathTool

    local = ToolExecutor([VerifiedMathTool(), SceneReasonTool()])
    try:
        tools = list(executor.get_openai_tools()) if executor is not None else []
    except Exception:  # noqa: BLE001
        tools = []
    configured = {t.get("function", {}).get("name") for t in tools}
    tools += [
        t for t in local.get_openai_tools() if t["function"]["name"] not in configured
    ]

    def execute(name: str, args: dict[str, Any]) -> str:
        selected = executor if name in configured else local
        result = selected.execute(
            ToolCall(id=uuid.uuid4().hex[:12], name=name, arguments=json.dumps(args))
        )
        return str(getattr(result, "content", result) or "")

    return execute, tools


__all__ = [
    "LIVE_MODELS",
    "speak_live",
    "stream_live",
    "LiveCall",
    "SERVER_TOOLS",
    "declarations",
    "live_config",
    "live_instructions",
    "make_executor",
]
