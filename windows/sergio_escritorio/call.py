"""Talk with Sergio like a phone call (Gemini Live through Sergio's server).

While a call is on, the microphone streams to the server and Sergio's voice
streams back: he answers within a second, you can interrupt him mid-sentence
just by talking, and he can see the camera or your screen. After two seconds
of silence the microphone stops streaming (with 400 ms kept back, so the
next word arrives whole): an always-on call does not send hours of silence.

Laptop speakers sit right next to the microphone, so Sergio would hear
himself and cut himself off. Every 10 ms of microphone audio goes through
WebRTC's echo canceller (LiveKit's audio processing) with what the speakers
are playing as the reference. Without it (not installed), the microphone is
muted while he talks unless you speak clearly over him.

No Qt here: the app gives the call its callbacks (state, captions, tools).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

log = logging.getLogger(__name__)

RATE_IN = 16_000  # microphone -> Gemini
RATE_OUT = 24_000  # Gemini's voice
FRAME_BYTES = 320  # 10 ms at 16 kHz, int16 (what the echo canceller takes)
SEND_BYTES = 3_200  # 100 ms of audio per message to the server
IDLE_HANG_UP = 60.0  # seconds with nobody talking: the call ends by itself
ALWAYS_ON = float("inf")  # an always-on call never hangs up on silence
GATE_AFTER = 2.0  # seconds of silence before the microphone stops streaming
PREROLL_FRAMES = 40  # 400 ms kept while gated: the first syllable is never lost
VIDEO_EVERY = 1.0  # seconds between camera/screen frames while sharing
REF_MAX = 60  # at most 600 ms of speaker reference waiting for the mic
PREBUFFER = RATE_OUT * 2 * 150 // 1000  # 150 ms of his voice before he starts


def rms(data: bytes | np.ndarray) -> float:
    samples = (
        np.frombuffer(data, dtype=np.int16) if isinstance(data, bytes) else data
    ).astype(np.float32)
    return float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0


def resample(pcm: bytes, src: int, dst: int) -> bytes:
    """Linear resampling of int16 mono PCM (good enough for a reference)."""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if src == dst or x.size == 0:
        return pcm
    n = max(1, int(round(x.size * dst / src)))
    y = np.interp(np.linspace(0, x.size - 1, n), np.arange(x.size), x)
    return np.clip(y, -32768, 32767).astype(np.int16).tobytes()


class EchoCanceller:
    """WebRTC echo cancellation + noise suppression, 10 ms at a time."""

    def __init__(self, factory: Callable[[], Any] | None = None) -> None:
        self.kind = "gate"
        self._apm: Any = None
        self._rtc: Any = None
        try:
            if factory is not None:
                self._apm = factory()
            else:
                from livekit import rtc

                self._rtc = rtc
                self._apm = rtc.AudioProcessingModule(
                    echo_cancellation=True,
                    noise_suppression=True,
                    high_pass_filter=True,
                    # Gain control would also raise the leftover echo.
                    auto_gain_control=False,
                )
            self.kind = "webrtc"
        except Exception as exc:  # noqa: BLE001 — works without it (gate)
            log.info("echo canceller unavailable (%s): gating instead", exc)

    def process(self, mic: bytes, ref: bytes) -> bytes:
        if self._apm is None:
            return mic
        if self._rtc is None:  # injected (tests)
            return self._apm(mic, ref)
        rtc = self._rtc
        far = rtc.AudioFrame(ref, RATE_IN, 1, FRAME_BYTES // 2)
        self._apm.process_reverse_stream(far)
        near = rtc.AudioFrame(mic, RATE_IN, 1, FRAME_BYTES // 2)
        self._apm.process_stream(near)
        return bytes(near.data)


class Speaker:
    """Plays Sergio's streamed voice and keeps it as the echo reference."""

    def __init__(self, stream_factory: Callable[..., Any] | None = None) -> None:
        self._factory = stream_factory
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._ref = bytearray()  # what was played, 16 kHz, for the mic side
        self._playing = False
        self._last_push = 0.0
        self._stream: Any = None
        self.level = 0.0  # 0..1, for the waveform
        self.last_sound = 0.0

    def start(self) -> None:
        if self._stream is not None:
            return
        if self._factory is not None:
            self._stream = self._factory(self._callback)
        else:
            import sounddevice as sd

            self._stream = sd.RawOutputStream(
                samplerate=RATE_OUT,
                channels=1,
                dtype="int16",
                blocksize=480,  # 20 ms
                latency=0.08,  # a little margin: no clicks or gaps
                callback=self._callback,
            )
        self._stream.start()

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
        self.flush()

    def _callback(self, outdata: Any, frames: int, _time: Any, _status: Any) -> None:
        need = frames * 2
        with self._lock:
            # Jitter buffer: start a sentence only with ~150 ms ready (or when
            # no more is coming), so network hiccups never chop the words.
            ready = len(self._buf)
            if (
                not self._playing
                and ready
                and (ready >= PREBUFFER or time.monotonic() - self._last_push > 0.2)
            ):
                self._playing = True
            if self._playing:
                chunk = bytes(self._buf[:need])
                del self._buf[:need]
                if not self._buf:
                    self._playing = False
            else:
                chunk = b""
        if len(chunk) < need:
            chunk += b"\0" * (need - len(chunk))
        outdata[:] = chunk
        loud = rms(chunk)
        self.level = min(1.0, loud / 6000.0)
        if loud > 200:
            self.last_sound = time.monotonic()
        ref = resample(chunk, RATE_OUT, RATE_IN)
        with self._lock:
            self._ref.extend(ref)
            extra = len(self._ref) - REF_MAX * FRAME_BYTES
            if extra > 0:  # clocks drift: keep the reference recent
                del self._ref[:extra]

    def play(self, pcm: bytes) -> None:
        with self._lock:
            if len(self._buf) + len(pcm) > RATE_OUT * 2 * 12:
                raise BufferError("La voz llegó demasiado adelantada para reproducirla en vivo.")
            self._buf.extend(pcm)
            self._last_push = time.monotonic()

    def flush(self) -> None:
        """Stop talking now (he was interrupted)."""
        with self._lock:
            self._buf.clear()
            self._playing = False

    @property
    def talking(self) -> bool:
        with self._lock:
            pending = len(self._buf)
        return pending > 0 or time.monotonic() - self.last_sound < 0.3

    def take_ref(self, size: int = FRAME_BYTES) -> bytes:
        with self._lock:
            ref = bytes(self._ref[:size])
            del self._ref[:size]
        return ref + b"\0" * (size - len(ref))


@dataclass
class ClientTool:
    """A tool the companion runs itself (camera, hands, timers, hang up...)."""

    name: str
    description: str
    run: Callable[[dict[str, Any]], str]
    parameters: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    def declaration(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


def ws_url(server_url: str) -> str:
    # "localhost" on Windows can try IPv6 first and hang until the timeout
    # (WSL forwards IPv4): the call goes straight to 127.0.0.1.
    base = server_url.rstrip("/").replace("://localhost", "://127.0.0.1")
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :] + "/v1/live"
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :] + "/v1/live"
    return base + "/v1/live"


class CallSession:
    """One call with Sergio. ``start()`` -> talk -> ``hang_up()``."""

    def __init__(
        self,
        server_url: str,
        *,
        voice: str = "",
        personality: str = "",
        context: Callable[[], str] = lambda: "",
        tools: list[ClientTool] | None = None,
        on_state: Callable[[str], None] = lambda _s: None,
        on_caption: Callable[[str], None] = lambda _t: None,
        on_heard: Callable[[str], None] = lambda _t: None,
        on_turn: Callable[[str, str], None] = lambda _heard, _said: None,
        on_level: Callable[[float], None] = lambda _v: None,
        on_end: Callable[[str], None] = lambda _why: None,
        video: Callable[[], tuple[bytes, str] | None] = lambda: None,
        connect: Callable[..., Any] | None = None,
        speaker: Speaker | None = None,
        echo: EchoCanceller | None = None,
        clock: Callable[[], float] = time.monotonic,
        idle_hang_up: float = IDLE_HANG_UP,
        language: str = "es",
        gate_after: float = GATE_AFTER,
        api_key: str = "",
    ) -> None:
        self.url = ws_url(server_url)
        self.api_key = api_key or os.environ.get("SERGIO_SERVER_API_KEY", "")
        self.voice = voice.split(":", 1)[-1] if voice.startswith("gemini:") else voice
        if self.voice.lower() in ("predeterminada", "default"):
            self.voice = ""  # Gemini Live's own default voice
        if ":" in self.voice or re.match(r"^[a-z]{2}-[A-Z]{2}-", self.voice):
            raise ValueError(
                "Esta voz requiere conversación por turnos; Gemini Live no conserva su identidad."
            )
        self.personality = personality
        self.context = context
        self.tools = {t.name: t for t in tools or []}
        self.on_state = on_state
        self.on_caption = on_caption
        self.on_heard = on_heard
        self.on_turn = on_turn
        self.on_level = on_level
        self.on_end = on_end
        self.video = video
        self._connect = connect
        self.speaker = speaker or Speaker()
        self.echo = echo or EchoCanceller()
        self.clock = clock
        self.idle_hang_up = idle_hang_up
        self.language = language
        self.gate_after = gate_after
        self._gated = False
        self._preroll: list[bytes] = []
        self.model = ""
        self.active = False
        self.error = ""
        self._ws: Any = None
        self._send_lock = threading.Lock()
        self._mic = bytearray()
        self._out = bytearray()
        self._said: list[str] = []
        self._heard: list[str] = []
        self._last_activity = 0.0
        self._noise = 120.0
        self._hang_up_after_turn = False
        self._state = ""
        self.share_screen = False
        self._audio_queue: queue.Queue[bytes | str] = queue.Queue(maxsize=8)
        self._audio_stalled = False
        self.heard_anything = False  # Gemini heard or said something already

    # -- lifecycle ------------------------------------------------------------
    def start(self, prefill: bytes = b"", timeout: float = 20.0) -> bool:
        """Connect and wait until Sergio is on the line. False = no call."""
        try:
            connect = self._connect
            if connect is None:
                from websockets.sync.client import connect
            try:
                auth = {"additional_headers": {"Authorization": f"Bearer {self.api_key}"}} if self.api_key else {}
                self._ws = connect(self.url, max_size=2_000_000, open_timeout=8, **auth)
            except TimeoutError as exc:
                raise TimeoutError(
                    f"no pude conectar con el servidor ({self.url}) en 8 s"
                ) from exc
            self._ws.send(
                json.dumps(
                    {
                        "type": "start",
                        "voice": self.voice,
                        "name": "Sergio",
                        "language": self.language,
                        "personality": self.personality,
                        "context": self.context(),
                        "tools": [t.declaration() for t in self.tools.values()],
                        "attention": "addressed",
                    }
                )
            )
            deadline = self.clock() + timeout
            while True:
                left = max(0.1, deadline - self.clock())
                try:
                    msg = self._ws.recv(timeout=left)
                except TimeoutError as exc:
                    raise TimeoutError(
                        f"el servidor no abrió Gemini Live en {timeout:.0f} s "
                        "(mira «sergio probar»: errores de Live del servidor)"
                    ) from exc
                if isinstance(msg, bytes):
                    continue
                event = json.loads(msg)
                if event.get("type") == "ready":
                    self.model = str(event.get("model") or "")
                    break
                if event.get("type") == "error":
                    raise RuntimeError(event.get("message") or "error")
                if self.clock() > deadline:
                    raise TimeoutError("Sergio no contestó la llamada")
        except Exception as exc:  # noqa: BLE001 — the caller falls back
            self.error = str(exc)[:300]
            log.warning("call could not start: %s", exc)
            self._close_ws()
            return False
        self.active = True
        threading.Thread(target=self._send_audio_loop, daemon=True,
                         name="live-audio-send").start()
        self._hang_up_after_turn = False
        self._last_activity = self.clock()
        try:
            self.speaker.start()
        except Exception as exc:  # noqa: BLE001 — no speakers: captions only
            log.warning("speaker unavailable: %s", exc)
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._watch, daemon=True).start()
        if prefill:  # the sentence that woke him ("Sergio, abre Spotify")
            for i in range(0, len(prefill), SEND_BYTES):
                self._send(prefill[i : i + SEND_BYTES])
        self._set_state("listening")
        return True

    def _set_state(self, name: str) -> None:
        if name != self._state:
            self._state = name
            self.on_state(name)

    def hang_up(self, why: str = "colgaste") -> None:
        if not self.active:
            return
        self.active = False
        try:
            self._send(json.dumps({"type": "end"}))
        except Exception:  # noqa: BLE001
            pass
        self._close_ws()
        self.speaker.stop()
        self.on_level(0.0)
        self._set_state("idle")
        self.on_end(why)

    def _close_ws(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def _send(self, data: bytes | str) -> None:
        ws = self._ws
        if ws is None:
            return
        with self._send_lock:
            ws.send(data)

    def _queue_audio(self, data: bytes | str) -> None:
        """Never wait for the network in the microphone callback.

        A stalled connection ends visibly rather than replaying old speech.
        Both PCM and its end marker use the same FIFO to preserve order.
        """
        try:
            self._audio_queue.put_nowait(data)
        except queue.Full:
            if not self._audio_stalled:
                self._audio_stalled = True
                threading.Thread(target=self._lost, args=(RuntimeError(
                    "La red no está enviando el audio a tiempo; reconectando."
                ),), daemon=True).start()

    def _send_audio_loop(self) -> None:
        while self.active:
            try:
                data = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._send(data)
            except Exception as exc:  # noqa: BLE001
                self._lost(exc)
                return
            finally:
                self._audio_queue.task_done()

    # -- what the companion sends -------------------------------------------
    def feed_mic(self, chunk: bytes) -> None:
        """One microphone frame (16 kHz int16) while the call is on."""
        if not self.active:
            return
        self._mic.extend(chunk)
        while len(self._mic) >= FRAME_BYTES:
            frame = bytes(self._mic[:FRAME_BYTES])
            del self._mic[:FRAME_BYTES]
            ref = self.speaker.take_ref(FRAME_BYTES)
            clean = self.echo.process(frame, ref)
            level = rms(clean)
            talking = self.speaker.talking
            if talking and self._echo_like(level, rms(ref)):
                clean = b"\0" * FRAME_BYTES  # his own voice: not for Gemini
                level = 0.0
            if not talking and level < self._noise * 3:
                self._noise = 0.98 * self._noise + 0.02 * max(level, 30.0)
            voiced = level > max(250.0, self._noise * 3)
            if voiced:
                self._last_activity = self.clock()
            if self._gate(clean, voiced or talking):
                continue
            self._out.extend(clean)
            if len(self._out) >= SEND_BYTES:
                data, self._out = bytes(self._out), bytearray()
                try:
                    self._queue_audio(data)
                except Exception as exc:  # noqa: BLE001
                    self._lost(exc)
                    return
        if not self.speaker.talking:
            self.on_level(min(1.0, rms(chunk) / 2500.0))

    def _gate(self, frame: bytes, live: bool) -> bool:
        """True when this frame is held back (silence after *gate_after* s).

        Voice (or his own speech, so you can still interrupt him) opens the
        gate again: the 400 ms before it go first, then the live audio.
        """
        if live or self.clock() - self._last_activity < self.gate_after:
            if self._gated:
                self._gated = False
                self._out.extend(b"".join(self._preroll))
                self._preroll.clear()
            return False
        if not self._gated:
            self._gated = True
            self._flush_out()
            try:
                self._queue_audio(json.dumps({"type": "audio_end"}))
            except Exception as exc:  # noqa: BLE001
                self._lost(exc)
        self._preroll.append(frame)
        if len(self._preroll) > PREROLL_FRAMES:
            del self._preroll[0]
        return True

    def _flush_out(self) -> None:
        if self._out:
            data, self._out = bytes(self._out), bytearray()
            try:
                self._queue_audio(data)
            except Exception as exc:  # noqa: BLE001
                self._lost(exc)

    def _echo_like(self, level: float, ref_level: float) -> bool:
        """While he talks, is this frame just his voice coming back?"""
        if self.echo.kind == "webrtc":
            return level < 200.0  # leftover echo after cancellation is faint
        # No canceller: only a voice clearly louder than the room interrupts.
        return level < max(1500.0, self._noise * 8, ref_level * 0.5)

    def send_image(self, jpeg: bytes, source: str = "cámara") -> None:
        if self.active and jpeg:
            self._send(
                json.dumps(
                    {
                        "type": "image",
                        "source": source,
                        "data": base64.b64encode(jpeg).decode("ascii"),
                    }
                )
            )

    def send_text(self, text: str) -> None:
        """Tell Sergio something during the call (task done, a reminder...)."""
        if self.active and text:
            self._send(json.dumps({"type": "text", "text": text}))

    def send_note(self, text: str) -> None:
        """Context Sergio should know but not answer ("now Ana is talking")."""
        if self.active and text:
            try:
                self._send(json.dumps({"type": "note", "text": text}))
            except Exception as exc:  # noqa: BLE001
                self._lost(exc)

    def interrupt(self) -> None:
        self.speaker.flush()

    # -- what Sergio sends ----------------------------------------------------
    def _reader(self) -> None:
        while self.active:
            ws = self._ws
            if ws is None:
                return
            try:
                msg = ws.recv(timeout=0.5)
            except TimeoutError:
                continue
            except Exception as exc:  # noqa: BLE001 — connection lost
                self._lost(exc)
                return
            try:
                self._handle(msg)
            except Exception:  # noqa: BLE001 — keep the call going
                log.exception("call message failed")

    def _handle(self, msg: bytes | str) -> None:
        if isinstance(msg, bytes):
            self.heard_anything = True
            try:
                self.speaker.play(msg)
            except BufferError as exc:
                self._lost(exc)
                return
            self._last_activity = self.clock()
            self._set_state("speaking")
            return
        event = json.loads(msg)
        kind = event.get("type")
        if kind == "said":
            self._said.append(str(event.get("text") or ""))
            self.on_caption("".join(self._said).strip())
        elif kind == "heard":
            self.heard_anything = True
            self._heard.append(str(event.get("text") or ""))
            self._last_activity = self.clock()
            self.on_heard("".join(self._heard).strip())
            self._said = []
        elif kind == "interrupted":
            self.speaker.flush()
            self._said = []
            self._set_state("listening")
        elif kind == "turn_complete":
            heard, said = "".join(self._heard).strip(), "".join(self._said).strip()
            if heard and said:
                self.on_turn(heard, said)
            self._heard = []
            self._said = []
            if self._hang_up_after_turn:
                threading.Thread(target=self._hang_up_when_quiet, daemon=True).start()
        elif kind == "tool":
            if event.get("status") == "running":
                self._set_state("acting")
        elif kind == "call":
            threading.Thread(target=self._run_tool, args=(event,), daemon=True).start()
        elif kind == "error":
            self.error = str(event.get("message") or "")
            self.on_caption(f"La llamada falló: {self.error[:120]}")
            self.hang_up("error")

    def _run_tool(self, event: dict[str, Any]) -> None:
        name = str(event.get("name") or "")
        tool = self.tools.get(name)
        self._set_state("acting")
        try:
            result = tool.run(dict(event.get("args") or {})) if tool else ""
            result = result or ("Hecho." if tool else f"No conozco {name}.")
        except PermissionError:
            result = "El control está en pausa (Ctrl+Alt+Fin para reanudarlo)."
        except Exception as exc:  # noqa: BLE001 — the model hears the error
            log.exception("client tool %s failed", name)
            result = f"Error: {exc}"
        try:
            self._send(
                json.dumps(
                    {"type": "tool_result", "id": event.get("id"), "result": result}
                )
            )
        except Exception as exc:  # noqa: BLE001
            self._lost(exc)

    def hang_up_after_goodbye(self) -> None:
        """'colgar': let him finish his goodbye, then end the call."""
        self._hang_up_after_turn = True
        threading.Thread(target=self._hang_up_when_quiet, daemon=True).start()

    def _hang_up_when_quiet(self) -> None:
        start = self.clock()
        # His goodbye may still be on its way: give it a moment to arrive...
        while self.active and not self.speaker.talking and self.clock() - start < 2.5:
            time.sleep(0.05)
        # ...then let him finish it.
        while self.active and self.speaker.talking and self.clock() - start < 12.0:
            time.sleep(0.1)
        self.hang_up("te despediste")

    def _lost(self, exc: Exception) -> None:
        if self.active:
            log.warning("call lost: %s", exc)
            self.error = str(exc)[:200]
            self.on_caption("La conexión de voz se interrumpió; reconectando.")
            self.hang_up("se cortó")

    def _watch(self) -> None:
        """Camera/screen frames while sharing; hang up when nobody talks."""
        last_frame = 0.0
        while self.active:
            now = self.clock()
            if now - last_frame >= VIDEO_EVERY:
                last_frame = now
                try:
                    shot = self.video()
                except Exception:  # noqa: BLE001
                    shot = None
                if shot:
                    try:
                        self.send_image(shot[0], shot[1])
                    except Exception as exc:  # noqa: BLE001
                        self._lost(exc)
                        return
            if self.speaker.talking:
                self._last_activity = now
                self.on_level(self.speaker.level)
            else:
                if self._state == "speaking":
                    self._set_state("listening")
                if now - self._last_activity > self.idle_hang_up:
                    self.hang_up("silencio")
                    return
            time.sleep(0.1)


__all__ = [
    "ALWAYS_ON",
    "CallSession",
    "ClientTool",
    "EchoCanceller",
    "Speaker",
    "resample",
    "rms",
    "ws_url",
]
