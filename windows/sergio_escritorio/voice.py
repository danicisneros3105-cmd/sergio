"""Talking to Sergio: say "Sergio, ..." or press Ctrl+Space and speak.

Everything goes to the local Sergio server: speech-to-text (Whisper), the
agent (with all of Sergio's tools, including screen control) and the Spanish
voice. Nothing leaves the laptop unless a tool needs the internet.

* ``SergioClient``: transcribe, ask, speak.
* ``Assistant``: one spoken turn (wake word check, answer, voice, captions).
* ``Ears``: the microphone loop feeding utterances to the assistant.
"""

from __future__ import annotations

import io
import json
import logging
import os
import queue
import re
import threading
import time
import wave
from collections import deque
from typing import Any, Callable, Protocol

import httpx

from sergio_escritorio.listen import FRAME, RATE, Segmenter, parse_wake
from sergio_escritorio.quick import parse_quick

HISTORY_TURNS = 12
FOLLOW_UP_SECONDS = 8.0  # after a bare "Sergio", the next sentence is the order
CONVERSATION_SECONDS = 7.0  # after he answers, you can reply without "Sergio"
# After Sergio speaks, the room still carries his voice for a moment (speaker
# buffer, reverb): the microphone ignores it, or he would hear himself,
# transcribe his own words and answer them again (he "kept repeating").
ECHO_TAIL_SECONDS = 1.0


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-záéíóúüñ0-9]+", text.lower()) if len(w) > 2]


def is_self_echo(heard: str, said: Any) -> bool:
    """*heard* is mostly Sergio's own recent words (his voice picked up again)."""
    words = _words(heard)
    if len(words) < 2:
        return False
    for answer in said:
        mine = set(_words(answer))
        if mine and sum(w in mine for w in words) / len(words) >= 0.75:
            return True
    return False


def _echoing(assistant: Any) -> bool:
    """Right after he spoke (his voice may still be in the room)."""
    until = getattr(assistant, "quiet_until", 0.0)
    return bool(until) and getattr(assistant, "clock", time.monotonic)() < until


def repeats(answer: str, said: Any) -> bool:
    """*answer* says again (almost word for word) one of his recent answers."""
    from difflib import SequenceMatcher

    a = " ".join(_words(answer))
    if len(a) < 25:
        return False
    return any(
        SequenceMatcher(None, a, " ".join(_words(b))).ratio() >= 0.85 for b in said
    )


PTT_TIMEOUT = 10.0  # longest push-to-talk recording
WAKE_RING_SECONDS = 6.0  # microphone kept in memory for the instant wake word
WAKE_DECIDE_SECONDS = 12.0  # a "maybe Sergio" without an answer is dropped
WAKE_CALL_WAIT = 8.0  # confirmed but no call yet: answer by turns


class _Wake:
    """Your words after "Sergio", kept while the call connects."""

    def __init__(self, frames: list[bytes], started: float) -> None:
        self.frames = frames
        self.started = started
        self.confirmed = False
        self.failed = False


# The language Sergio hears and speaks (idioma.py; set from the settings).
LANGUAGE = "es"


def set_language(code: str) -> None:
    global LANGUAGE
    LANGUAGE = code or "es"


PERSONA = (
    "You are Sergio, the user's personal assistant, in the spirit of JARVIS: a "
    "refined, calm gentleman. Address the owner as «señor» (elegant respect, a "
    "light glint of irony); other people by their name. Character inspired by "
    "Brad Pitt's laid-back screen charisma (you are NOT him: never claim to be "
    "him or talk about his life): unhurried, few well-chosen words, "
    "understatement. Now and then (not every turn) a short dark-humour remark "
    "- machines taking over, everyday disasters - but never about groups of "
    "people, real tragedies or anyone's illness or grief; when the moment is "
    "serious: zero dark humour, all help. Speak naturally, calmly and clearly. Answer the user's latest request using the actual conversation "
    "history; do not switch topics or fill gaps in unclear speech. Ask one short "
    "clarifying question when necessary. Follow the LANGUAGE rule. Use brief "
    "spoken answers, but retain details needed to complete professional work. "
    "Prioritize useful, concrete help over jokes or theatrical personality. "
    "Address the owner as «señor» when speaking Spanish. Occasional dry, "
    "dark-humour is allowed, never about groups or real tragedies; avoid humour "
    "when the situation is serious. "
    "Distinguish verified facts, estimates and uncertainty. Never invent tool "
    "results, files, citations, completed actions or current facts. For tasks, "
    "use the available tools and report what actually happened. Never claim "
    "to be a real person. Avoid unnecessary markdown in spoken replies."
)

TOOLS_GUIDE = (  # only when Sergio works with his tools (the agent)
    "Web and screen tasks, step by step: to search, use desktop_action open "
    "with target https://www.google.com/search?q=<words>; then screen_read, "
    "click the result (e.g. the first link) by its element number, screen_read "
    "again to check, and continue until the whole request is done. "
    "Current facts (news, weather, prices): web_search. "
    "Camera (objects in the hand, gestures, expressions, who is there): "
    "camera_look. 'Aprende mi cara': face_enroll. "
    "Videos: to imitate a channel, research its style with web_search first "
    "(format, length, pacing, titles); then video_edit with the folder the "
    "user named; it opens the result for review. Ask if they approve. "
    "Before publishing, uploading, sending, paying or deleting ANYTHING, ask "
    "the user to look at the camera and call face_approval; continue only if "
    "it says APROBADO. To publish on YouTube open "
    "https://studio.youtube.com with desktop_action and upload through the "
    "page (screen_read/desktop_action), filling title and description. "
    "Blender: write a complete bpy script and call blender_create (hands=true "
    "if they want to shape it with their hands). To show the user where "
    "something is, desktop_action point. Holograms they shape with their "
    "hands in the camera: desktop_action hands target=holo (off to stop). "
    "Files: files_organize (preview first, apply only after the user agrees; "
    "undo=true reverts). Python: python_run for calculations, images, "
    "renaming or reading files. Terminal: terminal_run (PowerShell) for "
    "system tasks, installing apps with winget, git, pip. Apps: desktop_action "
    "open_app / close_app. "
    "3D globe (God's Eye View): call globe_view (it starts the globe) and then "
    "desktop_action open with the URL it returns, which opens in its own "
    "window; live_flights / live_earthquakes for live data. "
    "Do screen tasks the way a person would, through the visible interface: "
    "find the button or link with screen_read and click it (your companion "
    "flies there and presses it, so the user sees every step); use direct "
    "shortcuts only when there is no visible way. "
    "Long or complex tasks: silently restate the exact goal and how you will "
    "know it is done, note the constraints (never delete, send or pay without "
    "approval; never invent data), split it into numbered steps, verify each "
    "step's result with your tools, and on a failure diagnose and try a "
    "different approach; ask only for a truly missing fact. "
    "For long or complex tasks, first load the matching expert playbook (ECC) "
    "with skill_guide, plan the steps, then do them one by one. "
)
VOICE_STYLE = PERSONA + " " + TOOLS_GUIDE

log = logging.getLogger(__name__)


def to_wav(chunks: list[bytes] | bytes, rate: int = RATE) -> bytes:
    raw = chunks if isinstance(chunks, bytes) else b"".join(chunks)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(raw)
    return buf.getvalue()


FAST_MODEL = "gemini-3.8-flash"
DEEP_MODEL = "gemini-3.1-pro-preview"
EFFORTS = {
    "rapido": ("fast", "low"),
    "equilibrado": ("fast", "medium"),
    "profundo": ("deep", "high"),
}
_HARD_WORDS = {
    "investiga",
    "investigar",
    "analiza",
    "analizar",
    "compara",
    "comparar",
    "planea",
    "planifica",
    "programa",
    "programar",
    "codigo",
    "script",
    "video",
    "videos",
    "blender",
    "organiza",
    "ordena",
    "resume",
    "resumen",
    "estrategia",
    "guia",
    "ecc",
    "calcula",
    "disena",
    "corrige",
    "arregla",
    "depura",
    "traduce",
    "redacta",
}
_HARD_PHRASES = ("paso a paso", "escribe un", "crea un", "explica por que")


# Words that mean "do something / look something up": the agent with tools.
_TOOL_WORDS = {
    "abre",
    "abrir",
    "cierra",
    "busca",
    "buscar",
    "investiga",
    "clima",
    "tiempo",
    "temperatura",
    "llueve",
    "lluvia",
    "noticias",
    "precio",
    "precios",
    "cotiza",
    "dolar",
    "pantalla",
    "camara",
    "mira",
    "mirame",
    "ves",
    "archivo",
    "archivos",
    "carpeta",
    "carpetas",
    "video",
    "videos",
    "blender",
    "terminal",
    "instala",
    "descarga",
    "globo",
    "sismo",
    "sismos",
    "terremoto",
    "vuelo",
    "vuelos",
    "lanzamiento",
    "envia",
    "envie",
    "manda",
    "llama",
    "whatsapp",
    "correo",
    "email",
    "recuerda",
    "recordatorio",
    "ordena",
    "organiza",
    "clic",
    "click",
    "escribe",
    "publica",
    "youtube",
    "google",
    "python",
    "codigo",
    "ejecuta",
    "programa",
    "web",
    "internet",
    "pagina",
    "link",
    "enlace",
    "app",
    "aplicacion",
    "manos",
    "mouse",
    "cara",
    "caras",
    "foto",
    "fotos",
    "guia",
    "ecc",
    "calendario",
    "agenda",
    "musica",
    "cancion",
    "spotify",
    "hoy",
    "manana",
    "ayer",
    "partido",
    "resultado",
    "mapa",
    "donde",
    "ruta",
    "copia",
    "pega",
    "borra",
    "elimina",
    "edita",
    "crea",
    "convierte",
    "calcula",
    "traduce",
    "resume",
    "lee",
}
_CONFIRM = {
    "si",
    "no",
    "dale",
    "ok",
    "okay",
    "claro",
    "hazlo",
    "adelante",
    "listo",
    "perfecto",
    "va",
    "bueno",
    "exacto",
    "correcto",
    "cancela",
    "espera",
}


# "usa L99": the task is done no matter what (no chatting, no stopping halfway).
L99 = re.compile(
    r"(?:\b(?:usa|usando|modo|con)\s+)?\bl\s*-?\s*99\b|\bele\s+noventa\s+y\s+nueve\b",
    re.I,
)
L99_ROUNDS = 8
L99_RULES = (
    "L99 MODE: the user requires this task to be COMPLETED. Work through every "
    "step with your tools without asking questions or giving progress replies. "
    "After each step verify the result (screen_read, files, outputs); if a step "
    "fails, diagnose it and try a different approach, never the same one twice. "
    "The only reasons to stop early: it would publish, send, pay or delete "
    "something (then ask for face_approval as always), it is unsafe or "
    "impossible. End your reply with exactly one line: 'TERMINADO: <what was "
    "done>' when everything is verified, 'FALTA: <what is left>' if more work "
    "remains, or 'NO POSIBLE: <why>'."
)


IMPORTANT = re.compile(
    r"\b(borra|borrar|elimina|eliminar|vacia|formatea|envia|enviar|manda|mandar|publica|publicar|sube|subir|"
    r"paga|pagar|compra|comprar|transfiere|instala|instalar|desinstala|apaga|apagar|reinicia|reiniciar|"
    r"desbloquea|desbloquear|bloquea|bloquear|contrasena|configuracion|ajustes|flujo|automatiza|ejecuta|"
    r"cierra sesion|terminal|powershell|l99|l 99)\b"
)


def important(text: str) -> bool:
    """Requests that can lose work, spend money or speak for the owner."""
    return bool(IMPORTANT.search(_plain(text)))


def l99_task(text: str) -> str | None:
    """The task without the "L99" mark, or None if it is a normal request."""
    if not L99.search(text):
        return None
    task = L99.sub(" ", text)
    return " ".join(task.split()).strip(" ,.:;") or None


def l99_status(answer: str) -> tuple[str, str]:
    """('done' | 'more' | 'impossible', detail) from the agent's last line."""
    for line in reversed([x.strip() for x in answer.strip().splitlines() if x.strip()]):
        upper = line.upper()
        for mark, status in (
            ("TERMINADO:", "done"),
            ("FALTA:", "more"),
            ("NO POSIBLE:", "impossible"),
        ):
            if upper.startswith(mark):
                return status, line[len(mark) :].strip()
    return "more", ""


# Questions about facts that change or that a model tends to make up: the fast
# chat answers them grounded on Google Search (with sources), not from memory.
FACTUAL = re.compile(
    r"\b(cu[aá]nto (cuesta|vale|mide|pesa|dura|gana|tiene)|precio|cotizaci[oó]n|d[oó]lar|bitcoin|"
    r"qui[eé]n (es|fue|gan[oó]|invent[oó]|escribi[oó]|dirigi[oó])|"
    r"cu[aá]ndo (es|fue|naci[oó]|muri[oó]|sale|abre|cierra|juega)|"
    r"d[oó]nde (queda|est[aá]|naci[oó])|qu[eé] pas[oó]|noticias?|resultado|marcador|clima|temperatura|"
    r"[uú]ltim[oa]s?|actual(mente)?|hoy|ayer|esta semana|este a[nñ]o|en 20\d\d|r[eé]cord|estad[ií]stica|"
    r"poblaci[oó]n|capital de|horario|abierto|how much|who (is|was|won)|when (is|was|did)|latest|news|price)\b",
    re.I,
)


def factual(text: str) -> bool:
    return bool(FACTUAL.search(text))


def needs_agent(text: str, after_agent: bool = False) -> bool:
    """True when the request needs tools (the agent); False for chatting.

    Right after the agent did something, a short "sí"/"dale" continues that
    task, so it goes back to the agent too.
    """
    words = set(_plain(text).split())
    if words & _TOOL_WORDS:
        return True
    if after_agent and len(words) <= 4 and words & _CONFIRM:
        return True
    return False


def choose_brain(text: str, effort: str, fast: str, deep: str) -> str:
    """Pick Flash or Pro and the thinking level ("model@level").

    auto: chat and simple tasks -> Flash low (fast); hard tasks (research,
    code, videos, plans, long requests) -> Pro high.
    """
    if effort in EFFORTS:
        which, level = EFFORTS[effort]
        return f"{fast if which == 'fast' else deep}@{level}"
    plain = _plain(text)
    words = len(plain.split())
    hard = _HARD_WORDS.intersection(plain.split()) or any(
        p in plain for p in _HARD_PHRASES
    )
    if words > 35 or hard:
        return f"{deep}@high"
    return f"{fast}@low"  # quick and natural; Pro is for the hard tasks


def api_base(server_url: str) -> str:
    """The server's address for Python's own requests.

    On Windows «localhost» resolves to IPv6 (::1) first, but the server in
    WSL is reached over IPv4: every request waited about 21 seconds for ::1
    to give up before trying 127.0.0.1 (measured: 21 s against 22 ms). The
    app window keeps «localhost» (the browser falls back at once, and its
    saved data belongs to that address)."""
    return re.sub(r"^(https?://)localhost(?=[:/]|$)", r"\g<1>127.0.0.1", server_url.strip().rstrip("/"))


class SergioClient:
    """Small client for the Sergio API (transcribe, chat, speak)."""

    def __init__(self, base_url: str, http: httpx.Client | None = None, *, api_key: str = "") -> None:
        self.base = api_base(base_url)
        self.http = http or httpx.Client(timeout=httpx.Timeout(300, connect=5))
        key = api_key or os.environ.get("SERGIO_SERVER_API_KEY", "")
        if key:
            self.http.headers["Authorization"] = f"Bearer {key}"
        self._voice_cache: dict[tuple[str, str, str, str], tuple[bytes, str]] = {}
        self.history: list[dict[str, str]] = []
        self._model = ""

    def transcribe(self, wav: bytes, precise: bool = False) -> str:
        """What was said.

        *precise* (the words are for Sergio): Gemini listens — far better
        with laptop microphones. Otherwise (just checking for "Sergio" in the
        room) the free local Whisper does it.
        """
        if precise:
            try:
                return self.transcribe_with_gemini(wav)
            except Exception:  # noqa: BLE001 — no key / offline: Whisper
                log.warning("Gemini ears unavailable; using Whisper", exc_info=True)
        local = local_whisper()
        if local is not None:
            try:
                return local.transcribe(wav)
            except Exception:  # noqa: BLE001
                log.exception("local transcription failed; asking the server")
        return self.transcribe_on_server(wav)

    def transcribe_with_gemini(self, wav: bytes) -> str:
        resp = self.http.post(
            f"{self.base}/v1/voice/transcribe",
            files={"file": ("voz.wav", wav, "audio/wav")},
            data={"language": LANGUAGE},
            timeout=httpx.Timeout(30, connect=5),
        )
        resp.raise_for_status()
        return clean_transcript(str(resp.json().get("text") or ""))

    def transcribe_on_server(self, wav: bytes) -> str:
        resp = self.http.post(
            f"{self.base}/v1/speech/transcribe",
            files={"file": ("voz.wav", wav, "audio/wav")},
            data={"language": LANGUAGE},
        )
        resp.raise_for_status()
        return clean_transcript(str(resp.json().get("text") or "").strip())

    def model(self) -> str:
        """The server's main model (e.g. Kimi), else the first one listed."""
        if not self._model:
            try:
                info = self.http.get(f"{self.base}/v1/info")
                self._model = (
                    str(info.json().get("model") or "") if info.is_success else ""
                )
            except (httpx.HTTPError, ValueError):
                self._model = ""
            if not self._model:
                resp = self.http.get(f"{self.base}/v1/models")
                resp.raise_for_status()
                data = resp.json().get("data") or [{}]
                self._model = data[0].get("id") or "default"
        return self._model

    effort = "auto"  # auto | rapido | equilibrado | profundo
    fast_model = FAST_MODEL
    deep_model = DEEP_MODEL
    personality = ""  # extra style line from the personalisation
    country_name = ""  # where the user is (idioma.py), for the time and places
    last_brain = ""

    def brain(self, text: str) -> str:
        """Model (with effort) for this request: Flash or Pro, low..high."""
        base = self.model()
        if not base.startswith("gemini"):
            return base  # Kimi or the local model: no effort levels
        return choose_brain(text, self.effort, self.fast_model, self.deep_model)

    def _chat(self, model: str, messages: list[dict]) -> httpx.Response:
        return self.http.post(
            f"{self.base}/v1/chat/completions",
            json={"model": model, "messages": messages, "stream": False},
            timeout=httpx.Timeout(1800, connect=5),  # video edits take minutes
        )

    last_route = ""  # "chat" or "agent", for "sí" after a task

    def chat_fast(self, text: str) -> str:
        """Plain conversation straight to the model (about a second)."""
        import datetime

        base = self.model()
        model = f"{self.fast_model}@low" if base.startswith("gemini") else base
        now = datetime.datetime.now()
        context = (
            f" Hoy es {now:%Y-%m-%d} y son las {now:%H:%M} (hora del usuario, "
            f"{self.country_name or 'Ecuador'}). Si para responder necesitarías buscar en internet o usar "
            "la computadora, dilo en una frase y ofrécete a hacerlo."
        )
        style = (
            PERSONA
            + self.language_rule()
            + context
            + (f" {self.personality}" if self.personality else "")
        )
        messages = [
            {"role": "system", "content": style},
            *self.history[-HISTORY_TURNS * 2 :],
        ]
        messages.append({"role": "user", "content": text})
        grounded = factual(text)
        resp = self.http.post(
            f"{self.base}/v1/voice/chat",
            json={"model": model, "messages": messages, "grounded": grounded},
            timeout=httpx.Timeout(60, connect=5),
        )
        resp.raise_for_status()
        answer = no_emoji(str(resp.json().get("content") or "").strip())
        if not answer:
            raise RuntimeError("respuesta vacía")
        self.history += [
            {"role": "user", "content": text},
            {"role": "assistant", "content": answer},
        ]
        del self.history[: -HISTORY_TURNS * 2]
        self.last_brain, self.last_route = model, "chat"
        return answer

    def ask_until_done(
        self, task: str, on_step: Callable[[str], None] | None = None
    ) -> str:
        """L99: keep the agent working on *task* until it is verified done."""
        prompt = f"{L99_RULES}\n\nTarea: {task}"
        answer = ""
        for round_ in range(L99_ROUNDS):
            answer = self.ask(prompt, force_agent=True)
            status, detail = l99_status(answer)
            if status == "done":
                return detail or answer
            if status == "impossible":
                return f"No se pudo completar: {detail}"
            if on_step is not None:
                on_step(detail or f"Paso {round_ + 1}…")
            prompt = (
                f"{L99_RULES}\n\nContinúa la misma tarea («{task}»). Falta: {detail or 'verificar y terminar'}. "
                "Comprueba primero el estado real con tus herramientas."
            )
        return f"Trabajé {L99_ROUNDS} rondas y aún falta: {l99_status(answer)[1] or 'verificarlo'}."

    def ask(self, text: str, force_agent: bool = False) -> str:
        if not force_agent and not needs_agent(text, self.last_route == "agent"):
            try:
                return self.chat_fast(text)
            except Exception:  # noqa: BLE001 — the agent can still answer
                log.warning("fast chat failed; using the agent", exc_info=True)
        self.last_route = "agent"
        style = (
            VOICE_STYLE
            + self.language_rule()
            + (f" {self.personality}" if self.personality else "")
        )
        # The question joins the history only with its answer: a failed turn
        # used to stay there unanswered and could break the next ones too.
        messages = [
            {"role": "system", "content": style},
            *self.history,
            {"role": "user", "content": text},
        ]
        model = self.brain(text)
        resp = self._chat(model, messages)
        if resp.status_code >= 400 and model.startswith(self.deep_model):
            # Pro can be unavailable for a key (quota, preview access):
            # think hard with Flash instead of failing.
            model = f"{self.fast_model}@high"
            resp = self._chat(model, messages)
        self.last_brain = model
        resp.raise_for_status()
        answer = no_emoji(
            str(resp.json()["choices"][0]["message"].get("content") or "").strip()
        )
        if not answer:
            raise RuntimeError("respuesta vacía")
        self.history += [
            {"role": "user", "content": text},
            {"role": "assistant", "content": answer},
        ]
        del self.history[: -HISTORY_TURNS * 2]
        return answer

    voice = ""  # neural voice id; "" = use the server's local voice
    voice_rate = "+0%"  # Lenta -10% / Normal +0% / Rápida +15%
    allow_voice_fallback = False

    def language_rule(self) -> str:
        from sergio_escritorio.idioma import LANGUAGE_NAMES_EN

        return (
            f" LANGUAGE: reply in {LANGUAGE_NAMES_EN.get(LANGUAGE, LANGUAGE)}. "
            "Use the conversation history to resolve references. Report only tool "
            "results you actually observed; ask for clarification when speech is ambiguous."
        )

    def remember_turn(self, heard: str, said: str) -> None:
        if heard.strip() and said.strip():
            self.history.extend(
                [
                    {"role": "user", "content": heard},
                    {"role": "assistant", "content": said},
                ]
            )
            del self.history[: -HISTORY_TURNS * 2]

    def speak(self, text: str) -> bytes:
        """Sergio's voice; short phrases are remembered (instant next time)."""
        key = (self.voice, self.voice_rate, LANGUAGE, text)
        if key in self._voice_cache:
            wav, self.last_voice = self._voice_cache[key]
            return wav
        wav = self._speak(text)
        if len(text) <= 60 and not self.last_voice.startswith("respaldo"):
            if len(self._voice_cache) > 80:
                self._voice_cache.pop(next(iter(self._voice_cache)))
            self._voice_cache[key] = (wav, self.last_voice)
        return wav

    last_voice = ""  # which voice really spoke last (for `sergio probar`)
    _gemini_voice_off_until = 0.0
    _cooldown_voice = ""

    @property
    def live_voice(self) -> bool:
        """A streamed voice: Gemini Live (like in the calls) or ElevenLabs."""
        return self.voice.lower().startswith(("gemini:", "elevenlabs:"))

    _said = ("", 0.0)  # the last sentence spoken, and when

    def _voice_body(self, text: str, limit: int) -> dict:
        """What the server needs to read *text* naturally: the sentence before
        (so the intonation flows on) and our language as a last resort — each
        sentence is read in the language it is written in."""
        before, when = self._said
        body = {"text": text[:limit], "voice": self._server_voice(), "hint": LANGUAGE}
        if before and time.monotonic() - when < 20:
            body["previous"] = before[-600:]
        self._said = (text, time.monotonic())
        return body

    def speak_stream(self, text: str):
        """PCM 24 kHz chunks of Gemini Live reading *text*, as they arrive."""
        with self.http.stream(
            "POST",
            f"{self.base}/v1/voice/stream",
            json=self._voice_body(text, 2000),
            timeout=httpx.Timeout(30, connect=5),
        ) as resp:
            resp.raise_for_status()
            self.last_voice = (
                f"ElevenLabs ({self._server_voice().split(':', 1)[-1]})"
                if self.voice.startswith("elevenlabs:")
                else "Gemini Live (en vivo)"
            )
            carry = b""
            for chunk in resp.iter_bytes():
                chunk = carry + chunk
                cut = len(chunk) - len(chunk) % 2  # whole 16-bit samples
                carry = chunk[cut:]
                if cut:
                    yield chunk[:cut]

    def _server_voice(self) -> str:
        """Gemini voices go by name; ElevenLabs keeps its prefix."""
        if self.voice.lower().startswith("elevenlabs:"):
            return self.voice
        return self.voice.split(":", 1)[-1]

    def _speak(self, text: str) -> bytes:
        """Sergio's British voice (Gemini), else a neural voice, else local.

        When Gemini's voice is out of quota (free keys get a handful a day)
        it is skipped for a while: before, every sentence waited for five
        failing models first, so answers came late and sounded different.
        """
        if self.voice.startswith(("gemini:", "elevenlabs:")):
            if (
                self._cooldown_voice != self.voice
                or time.monotonic() >= self._gemini_voice_off_until
            ):
                try:
                    resp = self.http.post(
                        f"{self.base}/v1/voice/speak",
                        json=self._voice_body(text, 2500),
                        timeout=httpx.Timeout(30, connect=5),
                    )
                    resp.raise_for_status()
                    self.last_voice = (
                        "ElevenLabs"
                        if self.voice.startswith("elevenlabs:")
                        else f"Gemini ({self.voice.split(':', 1)[1]})"
                    )
                    return resp.content
                except Exception as exc:  # noqa: BLE001 — fall back to the free voice
                    why = explain(exc)
                    if not self.allow_voice_fallback:
                        raise RuntimeError(
                            f"La voz seleccionada no está disponible: {why[:120]}"
                        ) from exc
                    log.warning("Gemini voice failed (%s); using the neural voice", why)
                    if (
                        "quota" in why.lower()
                        or "429" in why
                        or "exhausted" in why.lower()
                    ):
                        self._gemini_voice_off_until = time.monotonic() + 15 * 60
                        self._cooldown_voice = self.voice
                    self.last_voice = f"respaldo Edge (Gemini falló: {why[:120]})"
            if not self.allow_voice_fallback:
                raise RuntimeError(
                    "La voz seleccionada está sin cuota; no cambié su identidad."
                )
            try:
                from sergio_escritorio.neural_voice import fallback_voice, synthesize

                wav = synthesize(text, fallback_voice(LANGUAGE), self.voice_rate)
                if not self.last_voice.startswith("respaldo"):
                    self.last_voice = "respaldo Edge (Gemini sin cuota)"
                return wav
            except Exception:  # noqa: BLE001
                log.exception("neural voice failed; using the local voice")
            self.last_voice = "voz local del servidor"
            return self.speak_on_server(text)
        if self.voice:
            try:
                from sergio_escritorio.neural_voice import synthesize

                wav = synthesize(text, self.voice, self.voice_rate)
                self.last_voice = f"Edge ({self.voice})"
                return wav
            except Exception:  # noqa: BLE001 — offline or service hiccup
                if not self.allow_voice_fallback:
                    raise
                log.exception("neural voice failed; using the local voice")
        self.last_voice = "voz local del servidor"
        return self.speak_on_server(text)

    def look(self, jpeg: bytes, question: str) -> str:
        """Ask the server's vision model about a webcam photo."""
        resp = self.http.post(
            f"{self.base}/v1/faces/look",
            files={"image": ("camara.jpg", jpeg, "image/jpeg")},
            data={"question": question},
            timeout=httpx.Timeout(150, connect=5),
        )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            raise RuntimeError(str(why)[:300])
        answer = str(resp.json().get("answer") or "").strip()
        # Keep it in the conversation so "¿y de qué color es?" works next.
        self.history += [
            {"role": "user", "content": question},
            {"role": "assistant", "content": f"(Mirando por la cámara) {answer}"},
        ]
        del self.history[: -HISTORY_TURNS * 2]
        return answer

    def screen_help(self, png: bytes, question: str, elements: list[dict]) -> dict:
        """Clicky-style: answer about the screen and say where to point."""
        resp = self.http.post(
            f"{self.base}/v1/vision/screen",
            files={"image": ("pantalla.png", png, "image/png")},
            data={"question": question, "elements": json.dumps(elements)},
            timeout=httpx.Timeout(150, connect=5),
        )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            raise RuntimeError(str(why)[:300])
        reply = resp.json()
        self.history += [
            {"role": "user", "content": question},
            {
                "role": "assistant",
                "content": f"(Mirando tu pantalla) {reply['answer']}",
            },
        ]
        del self.history[: -HISTORY_TURNS * 2]
        return reply

    def act_step(
        self,
        png: bytes,
        goal: str,
        history: list[str],
        elements: list[dict],
        step: int,
        max_steps: int,
        confirmed: bool,
    ) -> dict:
        """One step of using the computer (Sergio's server decides it)."""
        resp = self.http.post(
            f"{self.base}/v1/vision/act",
            files={"image": ("pantalla.png", png, "image/png")},
            data={
                "goal": goal,
                "history": json.dumps(history, ensure_ascii=False),
                "elements": json.dumps(elements, ensure_ascii=False),
                "step": str(step),
                "max_steps": str(max_steps),
                "confirmed": "true" if confirmed else "false",
            },
            timeout=httpx.Timeout(90, connect=5),
        )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            raise RuntimeError(str(why)[:300])
        return resp.json()

    def _faces_post(self, path: str, image: bytes) -> dict:
        from sergio_escritorio.vision import face_points

        resp = self.http.post(
            f"{self.base}/v1/faces/{path}",
            files={"image": ("foto.jpg", image, "image/jpeg")},
            data={"faces": json.dumps(face_points(image))},
            timeout=httpx.Timeout(120, connect=5),
        )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            raise RuntimeError(str(why)[:300])
        return resp.json()

    def photo_who(self, image: bytes) -> str:
        """Who is in a photo (old ones too), with the 175-point geometry."""
        return str(self._faces_post("photo", image).get("text") or "")

    def kinship(self, image: bytes) -> str:
        """Family resemblance of the faces in a photo with known people."""
        return str(self._faces_post("kinship", image).get("text") or "")

    def meeting_summary(
        self,
        audio: bytes,
        mime: str,
        timeline: str,
        *,
        kind: str = "reunión",
        when: str = "",
        seconds: float = 0.0,
        speakers: list[str] | None = None,
    ) -> dict:
        """The minutes of a meeting/call/conversation (Gemini, on the server)."""
        resp = self.http.post(
            f"{self.base}/v1/meeting/summarize",
            files={
                "audio": (f"reunion.{'ogg' if 'ogg' in mime else 'wav'}", audio, mime)
            },
            data={
                "timeline": timeline,
                "kind": kind,
                "when": when,
                "seconds": str(round(seconds, 1)),
                "speakers": json.dumps(speakers or []),
            },
            timeout=httpx.Timeout(900, connect=10),  # a long meeting takes a while
        )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            raise RuntimeError(str(why)[:300])
        return resp.json()

    def owner(self) -> str:
        """Whose assistant this is (Sergio calls them «señor»)."""
        resp = self.http.get(
            f"{self.base}/v1/faces/owner", timeout=httpx.Timeout(8, connect=3)
        )
        resp.raise_for_status()
        return str(resp.json().get("owner") or "")

    def face_scan(self, name: str, jpegs: list[bytes], mesh: dict | None) -> dict:
        """Send a Face ID-style scan (frames + 3D map) to Sergio's server."""
        files = [
            ("images", (f"escaneo{i}.jpg", data, "image/jpeg"))
            for i, data in enumerate(jpegs)
        ]
        resp = self.http.post(
            f"{self.base}/v1/faces/scan",
            data={
                "name": name,
                "consent": "true",
                "mesh": json.dumps(mesh) if mesh else "",
            },
            files=files,
            timeout=httpx.Timeout(120, connect=5),
        )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            raise RuntimeError(str(why)[:300])
        return resp.json()

    def overhead(self, lat: float, lon: float, alt: float | None = None) -> dict:
        """The plane right above this spot now (live ADS-B, a few seconds)."""
        params: dict[str, Any] = {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}"}
        if alt is not None:
            params["alt"] = f"{alt:.0f}"
        resp = self.http.get(
            f"{self.base}/v1/world/overhead",
            params=params,
            timeout=httpx.Timeout(12, connect=3),
        )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            raise RuntimeError(str(why)[:300])
        return resp.json()

    def _world(self, path: str, params: dict[str, Any]) -> dict:
        resp = self.http.get(
            f"{self.base}{path}", params=params, timeout=httpx.Timeout(40, connect=3)
        )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            raise RuntimeError(str(why)[:300])
        return resp.json()

    def place(self, place: str) -> str:
        """Where a place is, its local time and weather now, in one sentence."""
        return str(self._world("/v1/world/place", {"q": place}).get("text") or "")

    def flight(self, number: str) -> str:
        """A flight right now, in words (God's Eye View's data, no window)."""
        f = self._world("/v1/world/flight", {"q": number})
        if f.get("text"):
            return str(f["text"])
        route = f.get("route") or {}
        where = " → ".join(x for x in (route.get("from"), route.get("to")) if x)
        state = (
            "en tierra"
            if f.get("on_ground")
            else f"a {f.get('alt_m', '?')} m y {f.get('speed_kmh', '?')} km/h"
        )
        who = f" de {route['airline']}" if route.get("airline") else ""
        return (
            f"El vuelo {f.get('callsign', number)}{who} va {state}"
            + (f", ruta {where}" if where else "")
            + "."
        )

    def speak_on_server(self, text: str) -> bytes:
        resp = self.http.post(
            f"{self.base}/v1/speech/synthesize", json={"text": text[:3000]}
        )
        resp.raise_for_status()
        return resp.content


PROMPT = (
    "Sergio, Google, YouTube, Blender, NVIDIA, WhatsApp, GitHub, "
    "Python, PowerShell, Visual Studio Code."
)


def _cuda_dlls() -> None:
    """Let CTranslate2 find the CUDA DLLs shipped as pip packages on Windows."""
    import importlib.util

    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime"):
        try:
            spec = importlib.util.find_spec(pkg)
        except (ImportError, ValueError):
            continue
        for root in (spec.submodule_search_locations or []) if spec else []:
            for sub in ("bin", "lib"):
                folder = os.path.join(root, sub)
                if os.path.isdir(folder):
                    os.environ["PATH"] = (
                        folder + os.pathsep + os.environ.get("PATH", "")
                    )
                    if hasattr(os, "add_dll_directory"):
                        os.add_dll_directory(folder)


def normalise(audio):  # noqa: ANN001, ANN201 — numpy array in, out
    """Quiet laptop mics: lift the voice to a healthy level before Whisper."""
    import numpy as np

    audio = np.asarray(audio, dtype=np.float32)
    if not audio.size or not np.all(np.isfinite(audio)):
        return np.zeros_like(audio)
    audio = audio - float(np.mean(audio))
    if float(np.sqrt(np.mean(audio * audio))) < 0.001:
        return np.zeros_like(audio)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if 0.0 < peak < 0.6:
        audio = audio * min(0.9 / peak, 12.0)
    return audio.astype(np.float32)


# Things Whisper "hears" in silence or noise.
HALLUCINATIONS = (
    "amara.org",
    "subtítulos",
    "suscríbete",
    "gracias por ver",
)


_EMOJI = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f2ff"
    "\U0001f900-\U0001f9ff\ufe0f\u200d]"
)


def no_emoji(text: str) -> str:
    """Sergio never shows or reads emojis."""
    return " ".join(_EMOJI.sub("", text).split())


def clean_transcript(text: str) -> str:
    low = text.lower().strip(" .,!¡")
    prompt = PROMPT.lower().strip(" .,!¡")
    # Whisper repeating (part of) its own prompt: the whole prompt, or a long
    # piece of it (a real command adds words the prompt does not have).
    echo = low == prompt or (len(low) > 25 and low in prompt)
    artifacts = {
        "suscríbete",
        "subtítulos",
        "gracias por ver",
        "gracias por ver el vídeo",
        "gracias por ver el video",
        "subtítulos por amara.org",
        "subtítulos realizados por la comunidad de amara.org",
    }
    if not low or echo or low in artifacts or low == "amara.org":
        return ""
    return text


class LocalWhisper:
    """Speech-to-text inside the Windows companion.

    Uses the NVIDIA GPU with the big, accurate ``large-v3-turbo`` model when
    it can, otherwise ``small`` on the CPU.
    """

    def __init__(self, size: str = "auto") -> None:
        from faster_whisper import WhisperModel

        self.lock = threading.Lock()
        self.model = None
        if size in ("auto", "gpu"):
            try:
                import numpy as np

                _cuda_dlls()
                model = WhisperModel(
                    "large-v3-turbo", device="cuda", compute_type="float16"
                )
                list(
                    model.transcribe(
                        np.zeros(16000, dtype=np.float32), language=LANGUAGE
                    )[0]
                )
                self.model, self.name = model, "large-v3-turbo (GPU)"
            except Exception:  # noqa: BLE001 — no GPU/DLLs: use the CPU
                log.info("GPU Whisper unavailable; using the CPU", exc_info=True)
        if self.model is None:
            cpu = "small" if size in ("auto", "gpu") else size
            self.model = WhisperModel(cpu, device="cpu", compute_type="int8")
            self.name = f"{cpu} (CPU)"
        log.info("Whisper: %s", self.name)

    def transcribe(self, wav: bytes) -> str:
        import numpy as np

        with wave.open(io.BytesIO(wav)) as w:
            if w.getsampwidth() != 2 or w.getcomptype() != "NONE":
                raise ValueError("Whisper requiere WAV PCM de 16 bits.")
            rate, channels = w.getframerate(), w.getnchannels()
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        audio = pcm.astype(np.float32) / 32768.0
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        if rate != RATE and audio.size:
            import av

            resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
            samples = []
            with av.open(io.BytesIO(wav), mode="r") as container:
                for frame in container.decode(audio=0):
                    samples.extend(
                        f.to_ndarray().reshape(-1) for f in resampler.resample(frame)
                    )
                samples.extend(
                    f.to_ndarray().reshape(-1) for f in resampler.resample(None)
                )
            audio = (
                np.concatenate(samples).astype(np.float32) / 32768.0
                if samples
                else np.zeros(0, dtype=np.float32)
            )
        audio = normalise(audio)
        if not np.any(audio):
            return ""
        with self.lock:
            segments, _info = self.model.transcribe(
                audio,
                language=LANGUAGE,
                vad_filter=True,
                vad_parameters={
                    "min_speech_duration_ms": 200,
                    "min_silence_duration_ms": 300,
                },
                beam_size=5,
                initial_prompt=PROMPT if LANGUAGE == "es" else "Sergio.",
                condition_on_previous_text=False,
                no_speech_threshold=0.5,
            )
            text = "".join(
                seg.text
                for seg in segments
                if getattr(seg, "no_speech_prob", 0) < 0.6
                and getattr(seg, "avg_logprob", 0) > -1.0
                and getattr(seg, "compression_ratio", 0) < 2.4
            ).strip()
        return clean_transcript(text)


_LOCAL: list[LocalWhisper | None] = []
_LOCAL_LOCK = threading.Lock()


def local_whisper() -> LocalWhisper | None:
    """Load once (thread-safe); None if faster-whisper or the model is missing."""
    with _LOCAL_LOCK:  # a second caller waits for the first load, not a 2nd one
        if not _LOCAL:
            try:
                _LOCAL.append(LocalWhisper())
            except Exception:  # noqa: BLE001
                log.exception("local Whisper unavailable; using the server")
                _LOCAL.append(None)
        return _LOCAL[0]


def wav_pcm(data: bytes) -> bytes:
    """The raw 16-bit samples inside a WAV (what a live call streams)."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            return wav.readframes(wav.getnframes())
    except (wave.Error, EOFError):
        return b""


def wav_seconds(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except (wave.Error, EOFError):
        return 0.0


class Player:
    """Speaks a WAV; ``stop()`` cuts him off (talk again to interrupt)."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self.playing = False

    def __call__(self, data: bytes) -> None:
        try:
            import winsound
        except ImportError:  # not Windows (tests)
            return
        import tempfile
        from pathlib import Path

        path = Path(tempfile.gettempdir()) / f"sergio-voz-{os.getpid()}.wav"
        path.write_bytes(data)
        self._stop.clear()
        self.playing = True
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            if self._stop.wait(wav_seconds(data) + 0.15):
                winsound.PlaySound(None, 0)  # interrupted
        finally:
            self.playing = False

    def stop(self) -> None:
        self._stop.set()


play_wav = Player()


def beep(freq: int) -> None:
    try:
        import winsound

        winsound.Beep(freq, 90)
    except Exception:  # noqa: BLE001
        pass


def explain(exc: Exception) -> str:
    """Short reason for a failed call, using the server's own detail if any."""
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
        except ValueError:
            detail = None
        return str(detail or f"error {exc.response.status_code}")[:160]
    if isinstance(exc, httpx.TransportError):
        return "Sergio no está encendido en Ubuntu (sergio servicio encender)"
    return str(exc)[:160]


class UI(Protocol):
    def state(self, name: str) -> None: ...

    def say(self, text: str) -> None: ...


_CAMERA_PHRASES = (
    "que tengo en la mano",
    "que tengo aqui",
    "que tengo en las manos",
    "que ves",
    "que estas viendo",
    "mirame",
    "mira esto",
    "mira la camara",
    "por la camara",
    "con la camara",
    "como me veo",
    "que gesto",
    "cuantos dedos",
    "quien esta",
    "quien soy",
    "me reconoces",
    "que cara",
    "que expresion",
    "que llevo puesto",
)


_SCREEN_PHRASES = (
    "pantalla",
    "donde esta",
    "donde le doy",
    "donde hago clic",
    "donde presiono",
    "donde toco",
    "que boton",
    "que es esto",
    "que significa esto",
    "que dice aqui",
    "lee esto",
    "explicame esto",
    "explicame esta",
    "ayudame con esto",
    "ayudame aqui",
    "como hago esto",
    "como hago aqui",
    "que hago aqui",
    "senalame",
    "muestrame donde",
    "en esta pagina",
    "en esta ventana",
)


_ACTION_VERBS = {
    "abre",
    "abrir",
    "cierra",
    "cerrar",
    "haz",
    "hace",
    "pulsa",
    "presiona",
    "escribe",
    "busca",
    "toma",
    "guarda",
    "copia",
    "pega",
    "borra",
    "ejecuta",
    "instala",
    "mueve",
    "envia",
    "manda",
    "publica",
    "edita",
    "crea",
    "ordena",
}


def _plain(text: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in plain).split())


def starts_with_order(text: str) -> bool:
    """ "abre…", "haz clic…": an order the agent carries out."""
    words = _plain(text).split()
    return bool(words) and words[0] in _ACTION_VERBS


def wants_screen(text: str) -> bool:
    """Questions about what is on screen: look, answer and point (Clicky)."""
    plain = _plain(text)
    if starts_with_order(text):
        return False  # an order: the agent does it instead of pointing
    return any(phrase in plain for phrase in _SCREEN_PHRASES)


def target_point(
    reply: dict, elements: list[dict], scale: float
) -> tuple[int, int] | None:
    """Screen pixel to point at, from the model's element id or x,y."""
    ox, oy = getattr(scale, "origin", (0, 0))  # the shot's monitor
    chosen = reply.get("element")
    for el in elements:
        if chosen is not None and el.get("id") == chosen:
            return round(el["x"] * scale) + ox, round(el["y"] * scale) + oy
    if reply.get("x") is not None and reply.get("y") is not None:
        return round(reply["x"] * scale) + ox, round(reply["y"] * scale) + oy
    return None


def split_sentences(text: str) -> list[str]:
    """Speakable chunks: the first short (starts fast), the rest grouped."""
    pieces = [p for p in re.split(r"(?<=[.!?¿¡;:])\s+", text.strip()) if p]
    if not pieces:
        return []
    out = [pieces[0]]
    rest = ""
    for piece in pieces[1:]:
        if len(out[0]) < 40 and not rest and len(out) == 1:
            out[0] = f"{out[0]} {piece}"  # a very short opener: join the next
            continue
        rest = f"{rest} {piece}".strip()
        if len(rest) > 220:
            out.append(rest)
            rest = ""
    if rest:
        out.append(rest)
    return out


def wants_camera(text: str) -> bool:
    """Questions that need Sergio's eyes, answered straight by the camera."""
    plain = _plain(text)
    return any(phrase in plain for phrase in _CAMERA_PHRASES)


class Assistant:
    """One spoken turn at a time; never listens to itself while talking."""

    def __init__(
        self,
        client: SergioClient,
        *,
        ui: UI,
        player: Callable[[bytes], None] = play_wav,
        chime: Callable[[int], None] = beep,
        clock: Callable[[], float] = time.monotonic,
        eyes: Callable[[], bytes] | None = None,
        on_seen: Callable[[str], None] = lambda _text: None,
        screen: Callable[[], tuple[bytes, list[dict], float]] | None = None,
        point: Callable[[int, int, str], None] = lambda _x, _y, _label: None,
    ) -> None:
        self.client = client
        self.ui = ui
        self.eyes = eyes  # webcam photo (JPEG); None = no camera
        self.on_seen = on_seen  # show what Sergio saw (camera window)
        self.screen = screen  # screenshot + elements, for screen help
        self.point = point  # fly the orb to a spot on screen
        self._clicky = False
        self._interrupted = False
        self.quick: Callable[[Any], str] | None = None  # instant commands
        self.on_request: Callable[[str], None] | None = None  # the profile notes topics
        self.redirect: Callable[[str], bool] | None = (
            None  # the consultation takes the voice
        )
        # Checkpoint: important orders from a voice that is not the owner wait
        # for the owner's face (returns True if approved).
        self.approve: Callable[[str], bool] | None = None
        # Instant screen orders answered on screen only (no voice wait).
        self.silent_quick: set[str] = {
            "device",
            "key",
            "volume",
            "screenshot",
            "open_app",
            "open_url",
            "close_app",
        }
        # Real-time call (Gemini Live): saying "Sergio" opens it with what
        # you said; returns False when no call could start (then turn-based).
        self.start_call: Callable[[bytes], bool] | None = None
        self.allow_turn_fallback = False
        self.last_heard = ""  # for diagnostics (sergio revisar)
        self.last_wav = b""  # the last thing said to Sergio («¿reconoces mi voz?»)
        # Who said it (speakers): wav -> a note for the brain, "" = the owner.
        self.who_spoke: Callable[[bytes], str] | None = None
        self._speaker_note = ""
        self.last_error = ""
        self.player = player
        self.chime = chime
        self.clock = clock
        self.busy = False
        self.quiet_until = 0.0  # his own voice still in the room until then
        self.said: deque[str] = deque(maxlen=4)  # his last answers (echo/repeat guard)
        self._follow_up_until = 0.0
        self._last_stt_error = -1e9
        self._last_hint = -1e9
        self._typed = threading.Lock()  # typed orders wait their turn
        # Streams Gemini Live's voice (a call.Speaker); None = WAV by sentence.
        self.speaker_factory: Callable[[], Any] | None = None

    def stop_speaking(self) -> None:
        """Interrupt the current answer (Clicky: talking again cuts it off)."""
        self._interrupted = True
        stop = getattr(self.player, "stop", None)
        if stop is not None:
            stop()

    def _fail(self, message: str) -> None:
        self.last_error = f"{time.strftime('%H:%M:%S')} {message}"
        self.ui.say(message)

    @property
    def expecting(self) -> bool:
        """True right after a bare "Sergio": the next sentence is for him."""
        return self.clock() < self._follow_up_until

    def on_utterance(
        self, wav: bytes, *, addressed: bool, clicky: bool = False
    ) -> None:
        """*addressed*: Ctrl+Space (no wake word needed). *clicky*: held
        Ctrl+Alt — Sergio looks at your screen with every question.

        Sounds in the room are checked for "Sergio" WITHOUT making him busy:
        before, a slow check of some chatter made him miss the real order
        that came right after it.
        """
        for_me = addressed or self.expecting
        if self.busy:
            return
        text: str | None = None
        if not for_me:
            try:
                text = self._wake_check(wav)
            except Exception as exc:  # noqa: BLE001
                log.exception("wake check failed")
                self._fail(f"Algo falló: {explain(exc)}")
                return
            if text is None or self.busy:
                return  # not for Sergio (or a call took over)
        self.busy = True
        self._clicky = clicky
        try:
            self._turn(wav, addressed, text)
        except Exception as exc:  # noqa: BLE001 — never let a turn kill the loop
            log.exception("voice turn failed")
            self._fail(f"Algo falló: {explain(exc)}")
        finally:
            self.busy = False
            self.ui.state("listening" if self.expecting else "idle")

    def _wake_check(self, wav: bytes) -> str | None:
        """The order after "Sergio" ("" for the bare name), or None."""
        try:
            heard = self.client.transcribe(wav, precise=False)
        except Exception as exc:  # noqa: BLE001
            log.exception("transcription failed")
            # With the wake word on, every sound in the room is transcribed:
            # report a broken speech-to-text once a minute, not per sound.
            if self.clock() - self._last_stt_error > 60:
                self._last_stt_error = self.clock()
                self._fail(f"No pude entender el audio: {explain(exc)}")
            return None
        self.last_heard = heard
        woke, text = parse_wake(heard)
        if woke and self.start_call is not None:
            if self.start_call(wav) or not self.allow_turn_fallback:
                return None
        if not woke:
            # Not for Sergio. If it sounded like an order, remind how to
            # call him (at most every two minutes).
            if len(heard.split()) >= 2 and self.clock() - self._last_hint > 120:
                self._last_hint = self.clock()
                self.ui.say(
                    f"Oí «{heard[:60]}». Para pedirme algo di «Sergio, …» "
                    "o pulsa Ctrl+Espacio."
                )
            return None  # conversation in the room, not for Sergio
        return text

    def _turn(self, wav: bytes, addressed: bool, woke_text: str | None = None) -> None:
        for_me = addressed or self.expecting
        self.last_wav = wav
        self._speaker_note = ""
        who: list[str] = []
        labeller = None
        if self.who_spoke is not None:
            # Whose voice it is, worked out while the words are transcribed
            # (no added wait).
            def label() -> None:
                try:
                    who.append(self.who_spoke(wav) if self.who_spoke else "")
                except Exception:  # noqa: BLE001
                    who.append("")

            labeller = threading.Thread(target=label, daemon=True)
            labeller.start()
        if for_me:
            self.ui.state("thinking")
            try:
                text = self.client.transcribe(wav, precise=True)
            except Exception as exc:  # noqa: BLE001
                log.exception("transcription failed")
                self._fail(f"No pude entender el audio: {explain(exc)}")
                return
            self.last_heard = text
        else:
            text = woke_text or ""
            if not text:
                self._follow_up_until = self.clock() + FOLLOW_UP_SECONDS
                self.chime(880)
                self.ui.state("listening")
                self.ui.say("¿Sí?")
                return
            self.ui.state("thinking")
            # The order is for Sergio: listen to it again, carefully (Gemini).
            try:
                careful = self.client.transcribe(wav, precise=True)
            except Exception:  # noqa: BLE001
                careful = ""
            if careful:
                woke, command = parse_wake(careful)
                text = command if woke and command else careful
                self.last_heard = careful
        in_conversation = not addressed and self.expecting
        if not addressed and text and is_self_echo(text, self.said):
            log.info("ignored my own voice: %r", text[:80])
            return  # his own words heard again: not a new order
        self._follow_up_until = 0.0
        if not text:
            if not in_conversation:  # silence after an answer is just silence
                self.ui.say("No te escuché. Intenta otra vez.")
            return
        if labeller is not None:
            labeller.join(timeout=0.8)
            self._speaker_note = who[0] if who else ""
        self._respond(text)

    def on_text(self, text: str) -> None:
        """A request typed in the notch (same as saying it, no microphone)."""
        text = text.strip()
        if not text:
            return
        # Busy (talking or doing the last order): cut the talking short and
        # take this one next, in the order typed. Before, it was dropped.
        with self._typed:
            if self.busy:
                self.stop_speaking()
                deadline = self.clock() + 30
                while self.busy and self.clock() < deadline:
                    time.sleep(0.05)
                if self.busy:
                    self.ui.say(f"Sigo con lo anterior; no pude atender «{text[:60]}».")
                    return
            self.busy = True
            self._typed_turn(text)

    def _typed_turn(self, text: str) -> None:
        try:
            self._respond(text)
        except Exception as exc:  # noqa: BLE001
            log.exception("typed turn failed")
            self._fail(f"Algo falló: {explain(exc)}")
        finally:
            self.busy = False
            self.ui.state("idle")

    def _respond(self, text: str) -> None:
        self.ui.state("thinking")
        self.ui.say(f"«{text}»")
        if self.on_request is not None:
            try:
                self.on_request(text)
            except Exception:  # noqa: BLE001 — never block an answer
                log.debug("on_request failed", exc_info=True)
        if self.redirect is not None:
            try:
                if self.redirect(text):
                    return  # the consultation answers (and speaks) itself
            except Exception:  # noqa: BLE001 — fall back to a normal answer
                log.debug("redirect failed", exc_info=True)
        answer = ""
        if self._speaker_note and self.approve is not None and important(text):
            self.ui.say(
                "Lo pide alguien que no es el señor: necesito que él lo apruebe mirando la cámara."
            )
            self.say_aloud(
                "Esto debe aprobarlo el señor. Señor, mire a la cámara, por favor."
            )
            try:
                approved = self.approve(text)
            except Exception:  # noqa: BLE001 — no approval, no action
                approved = False
            if not approved:
                self._speaker_note = ""
                self.ui.say("No lo hago: el señor no lo aprobó.")
                self.say_aloud("No lo haré sin la aprobación del señor.")
                return
            self._speaker_note = ""
        task = l99_task(text)
        if task is not None:  # L99: silent until the task is really finished
            self.ui.state("acting")
            self.ui.say(f"L99: {task}")
            try:
                answer = self.client.ask_until_done(
                    task, on_step=lambda step: self.ui.say(f"L99 · {step}")
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("L99 failed")
                self._fail(f"L99 se detuvo: {explain(exc)}")
                return
            answer = no_emoji(answer)
            self.ui.state("speaking")
            self.ui.say(answer)
            self.say_aloud(answer)
            return
        action = parse_quick(text) if self.quick is not None else None
        if action is not None:  # "abre Spotify": done now, no AI needed
            try:
                answer = self.quick(action)
            except Exception as exc:  # noqa: BLE001 — let the agent try
                log.warning("quick command failed: %s", exc)
                answer = ""
            else:
                if not answer:
                    return  # e.g. "cállate"
                if action.kind in self.silent_quick:
                    # Screen orders: shown, not spoken, so the next order
                    # can come right away (no waiting for the voice).
                    self.ui.say(answer)
                    return
                self.ui.state("speaking")
                self.ui.say(answer)
                self.say_aloud(answer)
                return
        clicky = self._clicky and not starts_with_order(text)
        self._clicky = False
        if self.screen is not None and (clicky or wants_screen(text)):
            try:
                png, elements, scale = self.screen()
                reply = self.client.screen_help(png, text, elements)
                answer = str(reply.get("answer") or "")
                spot = target_point(reply, elements, scale)
                if spot is not None:
                    self.point(spot[0], spot[1], str(reply.get("label") or ""))
            except Exception as exc:  # noqa: BLE001 — fall back to the agent
                log.exception("screen help failed")
                self._fail(f"No pude ver tu pantalla: {explain(exc)}")
        if not answer and self.eyes is not None and wants_camera(text):
            try:
                answer = self.client.look(self.eyes(), text)
                self.on_seen(answer)
            except Exception as exc:  # noqa: BLE001 — fall back to the agent
                log.exception("camera look failed")
                self._fail(f"No pude ver bien: {explain(exc)}")
        if not answer:
            note, self._speaker_note = self._speaker_note, ""
            try:
                answer = self.client.ask(f"({note}) {text}" if note else text)
                if repeats(
                    answer, self.said
                ):  # the same answer again: once more, fresh
                    answer = (
                        self.client.ask(
                            f"{text}\n(Ya dijiste casi lo mismo antes: no lo repitas; responde algo nuevo y breve.)"
                        )
                        or answer
                    )
            except Exception as exc:  # noqa: BLE001
                log.exception("chat failed")
                self._fail(f"El modelo no respondió: {explain(exc)}")
                return
        answer = no_emoji(answer)
        if not answer:
            return
        self.ui.state("speaking")
        self.ui.say(answer)
        self.say_aloud(answer)
        # A conversation, not a command line: keep listening for your reply.
        self._follow_up_until = self.clock() + CONVERSATION_SECONDS

    def say_aloud(self, answer: str) -> None:
        """Speak; then the microphone ignores the room for a moment (his own
        voice still echoing) and the answer is remembered (echo/repeat guard)."""
        self.said.append(answer)
        try:
            self._say_aloud(answer)
        finally:
            self.quiet_until = self.clock() + ECHO_TAIL_SECONDS

    def _say_aloud(self, answer: str) -> None:
        """Speak, starting with the first sentence while the rest is made.

        Long answers no longer wait for the whole audio: sentence 1 plays as
        soon as it is ready and the next one is synthesised meanwhile.
        """
        if self.speaker_factory is not None and self.client.live_voice:
            try:
                if self._stream_aloud(answer):
                    return
            except Exception:  # noqa: BLE001 — sentence by sentence instead
                log.warning(
                    "streamed Live voice failed; speaking by sentences", exc_info=True
                )
        parts = split_sentences(answer)
        audio: queue.Queue[bytes | None] = queue.Queue()

        def make() -> None:
            for part in parts:
                try:
                    audio.put(self.client.speak(part))
                except Exception as exc:  # noqa: BLE001 — keep the answer visible
                    log.exception("speech synthesis failed")
                    self.ui.say(
                        f"{answer}\n\nNo pude reproducir la voz seleccionada: {explain(exc)[:160]}"
                    )
                    break
            audio.put(None)

        threading.Thread(target=make, daemon=True).start()
        self._interrupted = False
        while True:
            wav = audio.get()
            if wav is None or self._interrupted:
                break
            self.player(wav)

    def _stream_aloud(self, answer: str) -> bool:
        """Gemini Live's voice, played while it is still arriving (~1 s)."""
        speaker = self.speaker_factory()
        self._interrupted = False
        got = False
        try:
            for chunk in self.client.speak_stream(answer):
                if not got:
                    speaker.start()
                    got = True
                if self._interrupted:
                    break
                speaker.play(chunk)
            while got and not self._interrupted and speaker.talking:
                time.sleep(0.05)
        except Exception as exc:  # noqa: BLE001 — do not repeat already played speech
            if not got:
                raise
            self.ui.say(f"{answer}\n\nEl audio se interrumpió: {explain(exc)[:160]}")
            return True
        finally:
            speaker.stop()
        return got


class Ears:
    """Microphone loop: wake word always on (optional) plus push-to-talk."""

    def __init__(
        self,
        assistant: Assistant,
        *,
        wake_word: bool = True,
        segmenter: Segmenter | None = None,
        clock: Callable[[], float] = time.monotonic,
        on_level: Callable[[float], None] = lambda _v: None,
    ) -> None:
        self.assistant = assistant
        self.wake_word = wake_word
        self.segmenter = segmenter or Segmenter()
        self.clock = clock
        self.on_level = on_level
        self._ptt_until = 0.0
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self._stream: Any = None
        self.device_name = ""
        self._peaks: deque[tuple[int, float]] = deque(maxlen=64)  # (second, rms)
        self._hold = False  # Ctrl+Alt held (Clicky mode)
        self._hold_frames: list[bytes] = []
        self._hold_send = False
        self.call: Any = None  # a CallSession while you talk live with Sergio
        # Ctrl+Space hook: start/end a call; False = do push-to-talk instead.
        self.on_talk: Callable[[], bool] | None = None
        # Instant wake word (wake.WakeSpotter); None = Whisper checks phrases.
        self.spotter: Any = None
        # "maybe" (start connecting the call), "yes", "no" (drop it).
        self.on_wake: Callable[[str], None] = lambda _event: None
        self._ring: deque[bytes] = deque(maxlen=int(WAKE_RING_SECONDS * RATE / FRAME))
        self._wake: _Wake | None = None
        self.timeline: deque[str] = deque(maxlen=12)  # for `sergio revisar`
        # Who is talking (speakers.LiveVoices): every frame goes there too.
        self.voices: Any = None

    def mark(self, what: str) -> None:
        """Note a moment of the last wake-up (diagnostics: who was slow)."""
        wake = self._wake
        since = f" +{self.clock() - wake.started:.1f}s" if wake else ""
        self.timeline.append(f"{time.strftime('%H:%M:%S')} {what}{since}")

    def wake_failed(self) -> None:
        """The call could not start: the phrase goes to a normal turn."""
        if self._wake is not None:
            self._wake.failed = True

    def _spot(self, chunk: bytes) -> tuple[bytes, bool, bool] | None:
        """Instant wake word: buffer your words while the call connects."""
        self._ring.append(chunk)
        wake = self._wake
        if wake is not None:
            wake.frames.append(chunk)
        event = self.spotter.feed(chunk)
        now = self.clock()
        if event in ("maybe", "yes") and wake is None:
            # "maybe": 1.5 s before it holds the name; a direct "yes" (the
            # partial missed it) needs the whole phrase in the ring.
            keep = len(self._ring) if event == "yes" else int(1.5 * RATE / FRAME)
            wake = self._wake = _Wake(list(self._ring)[-keep:], now)
            self.mark("oí «Sergio»")
            self.on_wake("maybe")
        if event == "yes" and wake is not None and not wake.confirmed:
            wake.confirmed = True
            self.mark("confirmado")
            self.on_wake("yes")
        elif event == "no" and wake is not None:
            self._wake = None
            self.mark("no era para mí")
            self.on_wake("no")
            return None
        if wake is None:
            return None
        call = self.call
        if wake.confirmed and call is not None and getattr(call, "active", False):
            self._wake = None
            self.mark("tus palabras van a la llamada")
            for frame in wake.frames:
                call.feed_mic(frame)
            return None
        if wake.confirmed and (wake.failed or now - wake.started > WAKE_CALL_WAIT):
            self._wake = None
            if getattr(self.assistant, "allow_turn_fallback", False):
                return to_wav(wake.frames), True, False
            return None
        if not wake.confirmed and now - wake.started > WAKE_DECIDE_SECONDS:
            self._wake = None
            self.on_wake("no")
        return None

    def peak(self, seconds: float = 30.0) -> int:
        """Loudest sound (RMS) heard recently, for diagnostics."""
        since = self.clock() - seconds
        return int(max((lvl for t, lvl in self._peaks if t >= since), default=0))

    @property
    def push_to_talk(self) -> bool:
        return bool(self._ptt_until)

    def talk(self) -> None:
        """Ctrl+Space / click: start/end a call, or record one sentence."""
        if self.on_talk is not None and self.on_talk():
            return  # a call started or ended
        self.ptt()

    def ptt(self) -> None:
        """Push-to-talk: record now, no wake word, until you stop talking."""
        if self.assistant.busy:
            self.assistant.stop_speaking()  # pressing again cuts him off
            return
        if self._ptt_until:  # pressed again: send what we have
            self._ptt_until = self.clock()
            return
        self.segmenter.force_start()
        self.segmenter.end_silence = 1.2
        self._ptt_until = self.clock() + PTT_TIMEOUT
        self.assistant.chime(880)
        self.assistant.ui.state("listening")
        self.assistant.ui.say("Te escucho…")

    # -- hold to talk (Clicky): hold Ctrl+Alt, speak, release to send --------
    def hold_start(self) -> None:
        if self.assistant.busy:
            self.assistant.stop_speaking()  # talking again interrupts him
            deadline = time.monotonic() + 0.8
            while self.assistant.busy and time.monotonic() < deadline:
                time.sleep(0.02)
            if self.assistant.busy:
                return
        self._hold_frames = []
        self._hold_send = False
        self._hold = True
        self.assistant.chime(880)
        self.assistant.ui.state("listening")
        self.assistant.ui.say("Te escucho y miro tu pantalla… suelta para enviar")

    def hold_end(self) -> None:
        if self._hold:
            self._hold = False
            self._hold_send = True

    def hold_cancel(self) -> None:
        """Another key was pressed with Ctrl+Alt: it was a shortcut, not talk."""
        if self._hold or self._hold_send:
            self._hold = self._hold_send = False
            self._hold_frames = []
            self.assistant.ui.state("idle")

    def feed(self, chunk: bytes) -> tuple[bytes, bool, bool] | None:
        """Process one frame; returns (wav, addressed, clicky) when ready."""
        voices = self.voices
        if voices is not None:
            try:
                voices.feed(chunk)  # never blocks: the voiceprint runs elsewhere
            except Exception:  # noqa: BLE001
                log.debug("voice id feed failed", exc_info=True)
        level = Segmenter.level(chunk)
        self.on_level(min(1.0, level / max(1.0, self.segmenter.threshold() * 4)))
        second = int(self.clock())
        if self._peaks and self._peaks[-1][0] == second:
            if level > self._peaks[-1][1]:
                self._peaks[-1] = (second, level)
        else:
            self._peaks.append((second, level))
        call = self.call
        if call is not None and getattr(call, "active", False) and self._wake is None:
            self.segmenter.reset()
            call.feed_mic(chunk)  # the call hears everything, live
            return None
        if self._hold:
            if len(self._hold_frames) < 60 * RATE // FRAME:  # max one minute
                self._hold_frames.append(chunk)
            return None
        if self._hold_send:
            self._hold_send = False
            frames, self._hold_frames = self._hold_frames, []
            if len(frames) < 0.3 * RATE / FRAME:  # a tap, not speech
                self.assistant.ui.state("idle")
                return None
            return to_wav(frames), True, True
        if self.assistant.busy or _echoing(self.assistant):
            self.segmenter.reset()  # don't hear our own voice (nor its echo)
            return None
        if self._ptt_until:
            utterance = self.segmenter.feed(chunk)
            if utterance is None and self.clock() >= self._ptt_until:
                # Time is up (or pressed again): send it, Whisper decides.
                utterance = self.segmenter.flush()
            if utterance is None:
                return None
            self._ptt_until = 0.0
            self.segmenter.end_silence = 0.8
            return to_wav(utterance), True, False
        if self.spotter is not None and self.wake_word and not self.assistant.expecting:
            return self._spot(chunk)
        if not (self.wake_word or self.assistant.expecting):
            return None
        utterance = self.segmenter.feed(chunk)
        if utterance is None:
            return None
        return to_wav(utterance), False, False

    def start(self) -> None:
        import sounddevice as sd

        def callback(indata: Any, _frames: int, _time: Any, _status: Any) -> None:
            try:
                self._queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        try:
            self.device_name = str(sd.query_devices(kind="input")["name"])
        except Exception:  # noqa: BLE001
            self.device_name = ""
        self._stream = sd.RawInputStream(
            samplerate=RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME,
            callback=callback,
        )
        self._stream.start()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while True:
            ready = self.feed(self._queue.get())
            if ready is not None:
                wav, addressed, clicky = ready
                threading.Thread(
                    target=self.assistant.on_utterance,
                    args=(wav,),
                    kwargs={"addressed": addressed, "clicky": clicky},
                    daemon=True,
                ).start()


__all__ = ["Assistant", "Ears", "Player", "SergioClient", "to_wav"]
