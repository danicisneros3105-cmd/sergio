"""Sergio's own voice: hear, think and speak at the same time, on the computer.

The owner (27 Oct 2026): «pongamos voz propia… un ultrarrápido proceso de
transcripción al mismo tiempo que se escribe la respuesta (menos de 0,5 s de
procesamiento)», and chose it as the voice always, with Gemini Live only as
the backup. :class:`OwnVoiceCall` speaks the same ``/v1/live`` protocol as
:class:`~openjarvis.speech.gemini_live.LiveCall` (microphone PCM 16 kHz in,
Sergio's voice PCM 24 kHz out, ``heard``/``said``/``turn_complete``), so the
web and the desktop need no change:

* **Hearing** — while the person talks, faster-whisper transcribes what is
  there every ~0.6 s (``hearing`` partials); a short silence (or the
  client's ``audio_end``) closes the turn and only the last stretch is left
  to transcribe.
* **Thinking** — the owner's turn goes to his agent with its tools, written
  live (``agents/_stubs.stream_tokens``); a customer's goes straight to the
  model through their own key, without tools or the owner's memory.
* **Speaking** — the answer is cut into phrases as it is written (the first
  one early, at the first comma) and each phrase is spoken while the next is
  still being written. Talking over Sergio stops him.

Which voice speaks (the owner, 27 Oct 2026: «la voz es una mierda» — the
local Kokoro ``em_alex`` was not good enough in Spanish): ElevenLabs Flash
with Sergio's ElevenLabs voice (an original library voice, nobody cloned)
when ``ELEVENLABS_API_KEY`` is set. Without that key the own voice is off
and the call goes to Gemini Live (Algenib), which sounds far better than
Kokoro. ``SERGIO_VOZ=propia`` still forces the own voice (Kokoro without
the key); ``SERGIO_VOZ=gemini`` always uses Gemini Live.

``latency`` reports what Sergio's own processing took (hearing the end,
cutting, first audio) apart from what the AI model took to start writing:
the first part is the one that should stay under half a second.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Iterable, Iterator, List, Optional

import numpy as np

log = logging.getLogger(__name__)

IN_RATE = 16000
OUT_RATE = 24000
VOICE = os.environ.get("SERGIO_VOZ_PROPIA", "em_alex")
STT_MODEL = os.environ.get("SERGIO_STT_MODELO", "base")
SILENCE_END = 0.45  # seconds of quiet that close a turn
PARTIAL_EVERY = 0.6  # seconds of new speech between partial transcripts
MIN_SPEECH = 0.25  # shorter sounds are not words
FIRST_CUT_WORDS = 3  # the first phrase is cut early to start speaking soon
# If the first phrase is not ready this soon after the person stops, a short
# word that is already synthesized ("Claro,") is said first, as people do.
ACK_AFTER = float(os.environ.get("SERGIO_VOZ_ACUSE", "0.35"))
ACKS = ("Claro,", "A ver,", "Vale,", "Bien,")
# While Sergio works on something long (a tool, a search) and nothing has been
# heard for this many seconds, he says so, like a person would, instead of
# leaving a silence that feels like a crash (owner, 28 Oct 2026: «más
# presente y más productiva»). At most twice per answer.
STILL_AFTER = float(os.environ.get("SERGIO_VOZ_SIGO", "4.0"))
STILL = ("Sigo con eso, un momento más.", "Ya casi lo tengo.", "Un segundo más, lo estoy terminando.")
_END = re.compile(r"[.!?…:;]\s|[.!?…]$|\n")
_SOFT = re.compile(r"[,—]\s")


# -- phrases -------------------------------------------------------------------
class Cutter:
    """Cuts text that arrives in pieces into phrases to speak as soon as each
    one is whole; the first one is cut at a comma too, to start sooner."""

    def __init__(self) -> None:
        self.buf = ""
        self.first = True

    def add(self, piece: str) -> List[str]:
        self.buf += piece
        out = []
        while True:
            m = _END.search(self.buf)
            if not m and self.first and len(self.buf.split()) > FIRST_CUT_WORDS:
                # The first few words go out at once, even without a comma.
                m = _SOFT.search(self.buf) or re.match(
                    r"\s*(?:\S+\s+){%d}" % FIRST_CUT_WORDS, self.buf
                )
            if not m:
                return out
            cut = self.buf[: m.end()].strip()
            self.buf = self.buf[m.end() :]
            if cut:
                self.first = False
                out.append(cut)

    def rest(self) -> List[str]:
        tail, self.buf = self.buf.strip(), ""
        return [tail] if tail else []


def phrases(pieces: Iterable[str]) -> Iterator[str]:
    cutter = Cutter()
    for piece in pieces:
        yield from cutter.add(piece)
    yield from cutter.rest()


def clean_for_voice(text: str) -> str:
    """What is said aloud: no markdown, links or code."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#>|]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


# -- engines (loaded once, shared) ---------------------------------------------
_LOCK = threading.Lock()
_stt: Any = None
_tts: Any = None


def _choice() -> str:
    return os.environ.get("SERGIO_VOZ", "").strip().lower()


def engine() -> str:
    """The voice that speaks: "elevenlabs", "kokoro" (only when forced) or
    "" (no own voice: Gemini Live speaks)."""
    if _choice() == "gemini":
        return ""
    if os.environ.get("ELEVENLABS_API_KEY", "").strip():
        return "elevenlabs"
    if _choice() == "propia":
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return ""
        return "kokoro"
    return ""


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return bool(engine())


def stt() -> Any:
    global _stt
    with _LOCK:
        if _stt is None:
            from faster_whisper import WhisperModel

            device = "cuda" if _has_cuda() else "cpu"
            _stt = WhisperModel(
                STT_MODEL,
                device=device,
                compute_type="float16" if device == "cuda" else "int8",
                cpu_threads=max(2, (os.cpu_count() or 4) // 2),
            )
        return _stt


def tts() -> Any:
    global _tts
    with _LOCK:
        if _tts is None:
            from openjarvis.speech.kokoro_onnx_tts import KokoroOnnxTTSBackend

            _tts = KokoroOnnxTTSBackend()
            _tts._ensure()
        return _tts


def _has_cuda() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001
        return False


_ACK_PCM: List[bytes] = []


def warm() -> None:
    """Load both engines and run them once, so the first turn is fast; the
    short acknowledgements are synthesized now, ready to sound at once."""
    transcribe(np.zeros(IN_RATE // 2, dtype=np.float32))
    if not _ACK_PCM and engine():
        _ACK_PCM.extend(speak_pcm(word) for word in ACKS)


_READY: List[bool] = []


def ready() -> bool:
    """Both engines load and run (models downloaded); False means use the
    Gemini Live backup. Checked once per server run."""
    if not _READY:
        try:
            warm()
            _READY.append(True)
        except Exception as exc:  # noqa: BLE001
            log.warning("own voice not ready, Gemini Live is used: %s", exc)
            _READY.append(False)
    return _READY[0]


def transcribe(audio: np.ndarray, language: str = "es") -> str:
    segments, _ = stt().transcribe(
        audio,
        language=language,
        beam_size=1,
        best_of=1,
        temperature=0.0,
        without_timestamps=True,
        condition_on_previous_text=False,
        vad_filter=False,
    )
    return " ".join(s.text.strip() for s in segments).strip()


def speak_pcm(text: str, speed: float = 1.05, previous: str = "") -> bytes:
    """One phrase in Sergio's voice: 16-bit PCM at 24 kHz. *previous*: the
    phrase said just before, so the intonation runs on (ElevenLabs)."""
    if engine() == "elevenlabs":
        from openjarvis.speech import elevenlabs_voice

        try:
            return elevenlabs_voice.pcm(text, previous=previous, timeout=12)
        except Exception as exc:  # noqa: BLE001 — out of credit or offline
            log.warning("ElevenLabs failed, local voice for this phrase: %s", exc)
    return _kokoro_pcm(text, speed)


def _kokoro_pcm(text: str, speed: float) -> bytes:
    engine = tts()
    kokoro = engine._ensure()
    voice = VOICE if VOICE in kokoro.voices else "em_alex"
    with engine._lock:
        samples, rate = kokoro.create(text, voice=voice, speed=speed, lang="es")
    samples = np.asarray(samples, dtype=np.float32)
    if rate != OUT_RATE:
        idx = np.linspace(0, len(samples) - 1, int(len(samples) * OUT_RATE / rate))
        samples = np.interp(idx, np.arange(len(samples)), samples).astype(np.float32)
    return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()


# -- hearing -------------------------------------------------------------------
class Ear:
    """Where speech starts and ends, from the microphone's loudness."""

    def __init__(self) -> None:
        self.floor = 0.004
        self.audio: List[np.ndarray] = []
        self.speaking = False
        self.voiced = 0.0
        self.quiet = 0.0
        self.since_partial = 0.0

    def feed(self, pcm: bytes) -> str:
        """Returns "start", "end", "partial" or ""."""
        chunk = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if not len(chunk):
            return ""
        seconds = len(chunk) / IN_RATE
        level = float(np.sqrt(np.mean(chunk * chunk)))
        loud = level > max(0.012, self.floor * 3.5)
        if not self.speaking and not loud:
            self.floor = 0.95 * self.floor + 0.05 * level
        if loud:
            self.quiet = 0.0
            if not self.speaking:
                self.speaking = True
                self.audio, self.voiced, self.since_partial = [], 0.0, 0.0
                self.audio.append(chunk)
                self.voiced += seconds
                return "start"
            self.voiced += seconds
        elif self.speaking:
            self.quiet += seconds
        if not self.speaking:
            return ""
        self.audio.append(chunk)
        self.since_partial += seconds
        if self.quiet >= SILENCE_END:
            return self.close()
        if self.since_partial >= PARTIAL_EVERY:
            self.since_partial = 0.0
            return "partial"
        return ""

    def close(self) -> str:
        if not self.speaking:
            return ""
        self.speaking = False
        return "end" if self.voiced >= MIN_SPEECH else ""

    def utterance(self) -> np.ndarray:
        return np.concatenate(self.audio) if self.audio else np.zeros(0, np.float32)


# -- the call ------------------------------------------------------------------
Think = Callable[[str, List[dict], Callable[[str], None]], str]


class OwnVoiceCall:
    """One conversation in Sergio's own voice over a ``/v1/live`` socket."""

    def __init__(
        self,
        ws: Any,
        start: dict,
        *,
        think: Think,
        remember: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.ws = ws
        self.start = start
        self.think = think
        self.remember = remember
        self.language = str(start.get("language") or "es")[:2]
        self.history: List[dict] = []
        self.ear = Ear()
        self.closed = False
        self.reply: Optional[asyncio.Task] = None
        self.partial_task: Optional[asyncio.Task] = None
        self.last_partial = ""
        self._sounded = False
        self._last_sound = time.monotonic()

    async def send_json(self, data: dict) -> None:
        with contextlib.suppress(Exception):
            await self.ws.send_text(json.dumps(data, ensure_ascii=False))

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, ready)
        await self.send_json({"type": "ready", "model": "voz-propia"})
        try:
            while not self.closed:
                msg = await self.ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data is not None:
                    if len(data) <= 64_000 and not len(data) % 2:
                        await self._audio(data)
                    continue
                try:
                    event = json.loads(msg.get("text") or "{}")
                except ValueError:
                    continue
                kind = event.get("type") if isinstance(event, dict) else None
                if kind == "end":
                    break
                if kind == "audio_end" and self.ear.close() == "end":
                    self._turn(time.monotonic())
                elif kind == "text" and event.get("text"):
                    self._answer(str(event["text"])[:4000], time.monotonic(), 0.0)
        finally:
            self.closed = True
            for task in (self.reply, self.partial_task):
                if task is not None:
                    task.cancel()

    async def _audio(self, pcm: bytes) -> None:
        said = self.ear.feed(pcm)
        if said == "start" and self.reply is not None and not self.reply.done():
            self.reply.cancel()  # talked over: Sergio stops at once
            await self.send_json({"type": "interrupted"})
        elif said == "partial" and (
            self.partial_task is None or self.partial_task.done()
        ):
            self.partial_task = asyncio.ensure_future(self._partial())
        elif said == "end":
            self._turn(time.monotonic() - self.ear.quiet)

    async def _partial(self) -> None:
        audio = self.ear.utterance()
        text = await asyncio.get_running_loop().run_in_executor(
            None, transcribe, audio, self.language
        )
        if text and text != self.last_partial:
            self.last_partial = text
            await self.send_json({"type": "hearing", "text": text})

    def _turn(self, ended: float) -> None:
        audio = self.ear.utterance()
        self.reply = asyncio.ensure_future(self._hear_and_answer(audio, ended))

    async def _hear_and_answer(self, audio: np.ndarray, ended: float) -> None:
        loop = asyncio.get_running_loop()
        t0 = time.monotonic()
        text = await loop.run_in_executor(None, transcribe, audio, self.language)
        stt_ms = (time.monotonic() - t0) * 1000
        self.last_partial = ""
        if not text:
            return
        await self.send_json({"type": "heard", "text": text})
        await self.send_json({"type": "thinking"})
        await self._speak_answer(text, ended, stt_ms)

    def _answer(self, text: str, ended: float, stt_ms: float) -> None:
        if self.reply is not None and not self.reply.done():
            self.reply.cancel()
        self.reply = asyncio.ensure_future(self._speak_answer(text, ended, stt_ms))

    async def _speak_answer(self, text: str, ended: float, stt_ms: float) -> None:
        loop = asyncio.get_running_loop()
        pieces: asyncio.Queue = asyncio.Queue()
        marks: dict = {"asked": time.monotonic()}

        def sink(piece: str) -> None:
            if piece:
                marks.setdefault("first_token", time.monotonic())
                loop.call_soon_threadsafe(pieces.put_nowait, piece)

        history = list(self.history[-12:])
        worker = loop.run_in_executor(None, self._think, text, history, sink)
        said: List[str] = []
        self._sounded = False
        ack = asyncio.ensure_future(self._acknowledge(ended, marks))
        still = asyncio.ensure_future(self._still_working(worker))
        self._last_sound = time.monotonic()

        async def stream() -> Any:
            while True:
                if worker.done() and pieces.empty():
                    return
                try:
                    yield await asyncio.wait_for(pieces.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue

        try:
            cutter = Cutter()
            first = True
            async for piece in stream():
                for phrase in cutter.add(piece):
                    first = await self._say(phrase, said, marks, ended, stt_ms, first)
            full = await worker
            rest = (
                cutter.rest() if said or cutter.buf.strip() else list(phrases([full]))
            )
            for phrase in rest:
                first = await self._say(phrase, said, marks, ended, stt_ms, first)
        except asyncio.CancelledError:
            ack.cancel()
            still.cancel()
            raise
        except Exception as exc:  # noqa: BLE001
            still.cancel()
            log.warning("own voice turn failed: %s", exc)
            await self.send_json({"type": "error", "message": str(exc)[:300]})
            return
        still.cancel()
        answer = " ".join(said)
        self.history += [
            {"role": "user", "content": text},
            {"role": "assistant", "content": answer},
        ]
        await self.send_json({"type": "said", "text": answer})
        await self.send_json({"type": "turn_complete"})
        if self.remember and answer:
            loop.run_in_executor(None, self.remember, text, answer)

    async def _still_working(self, worker: Any) -> None:
        """«Sigo con eso»: said when a long job leaves the line silent."""
        if self.language != "es":
            return
        spoken = 0
        while spoken < 2 and not worker.done():
            await asyncio.sleep(0.5)
            if time.monotonic() - self._last_sound < STILL_AFTER or worker.done():
                continue
            phrase = STILL[(len(self.history) // 2 + spoken) % len(STILL)]
            await self.send_json({"type": "working", "text": phrase})
            pcm = await asyncio.get_running_loop().run_in_executor(
                None, lambda: speak_pcm(phrase)
            )
            if worker.done():
                return
            self._last_sound = time.monotonic()
            await self.ws.send_bytes(pcm)
            spoken += 1

    async def _acknowledge(self, ended: float, marks: dict) -> None:
        wait = ACK_AFTER - (time.monotonic() - ended)
        if wait > 0:
            await asyncio.sleep(wait)
        if not self._sounded and _ACK_PCM:
            self._sounded = True
            marks["ack"] = time.monotonic()
            self._last_sound = marks["ack"]
            await self.ws.send_bytes(_ACK_PCM[len(self.history) % len(_ACK_PCM)])

    def _think(
        self, text: str, history: List[dict], sink: Callable[[str], None]
    ) -> str:
        return self.think(text, history, sink) or ""

    async def _say(
        self,
        phrase: str,
        said: List[str],
        marks: dict,
        ended: float,
        stt_ms: float,
        first: bool,
    ) -> bool:
        spoken = clean_for_voice(phrase)
        if not spoken:
            return first
        t0 = time.monotonic()
        previous = said[-1] if said else ""
        pcm = await asyncio.get_running_loop().run_in_executor(
            None, lambda: speak_pcm(spoken, previous=previous)
        )
        tts_ms = (time.monotonic() - t0) * 1000
        said.append(spoken)
        self._sounded = True
        self._last_sound = time.monotonic()
        await self.ws.send_bytes(pcm)
        if first:
            now = time.monotonic()
            model_ms = (
                marks.get("first_token", marks["asked"]) - marks["asked"]
            ) * 1000
            total_ms = (now - ended) * 1000
            await self.send_json(
                {
                    "type": "latency",
                    "voz": "propia",
                    "escuchar_ms": round(stt_ms),
                    "modelo_ms": round(model_ms),
                    "voz_ms": round(tts_ms),
                    "sergio_ms": round(total_ms - model_ms),
                    "total_ms": round(total_ms),
                    # When something was first heard (a short "Claro," if
                    # the first phrase was not ready yet).
                    "primer_sonido_ms": round(
                        ((marks.get("ack") or now) - ended) * 1000
                    ),
                }
            )
        return False


__all__ = [
    "Cutter",
    "Ear",
    "OwnVoiceCall",
    "available",
    "engine",
    "clean_for_voice",
    "phrases",
    "ready",
    "speak_pcm",
    "transcribe",
    "warm",
]
