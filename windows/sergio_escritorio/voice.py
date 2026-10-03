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
import logging
import queue
import threading
import time
import wave
from typing import Any, Callable, Protocol

import httpx

from sergio_escritorio.listen import FRAME, RATE, Segmenter, parse_wake

HISTORY_TURNS = 12
FOLLOW_UP_SECONDS = 8.0  # after a bare "Sergio", the next sentence is the order
PTT_TIMEOUT = 7.0  # Ctrl+Space with no speech gives up after this

VOICE_STYLE = (
    "You are talking out loud through Sergio's cursor companion on the user's "
    "Windows laptop. Answer in Spanish in one or two short spoken sentences, "
    "with no markdown or lists. To do things on the computer, look with "
    "screen_read and act with desktop_action step by step, then say briefly "
    "what you did."
)

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


class SergioClient:
    """Small client for the Sergio API (transcribe, chat, speak)."""

    def __init__(self, base_url: str, http: httpx.Client | None = None) -> None:
        self.base = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=httpx.Timeout(300, connect=5))
        self.history: list[dict[str, str]] = []
        self._model = ""

    def transcribe(self, wav: bytes) -> str:
        """Hear on Windows itself (Whisper on the CPU); the server is a backup."""
        local = local_whisper()
        if local is not None:
            try:
                return local.transcribe(wav)
            except Exception:  # noqa: BLE001
                log.exception("local transcription failed; asking the server")
        return self.transcribe_on_server(wav)

    def transcribe_on_server(self, wav: bytes) -> str:
        resp = self.http.post(
            f"{self.base}/v1/speech/transcribe",
            files={"file": ("voz.wav", wav, "audio/wav")},
            data={"language": "es"},
        )
        resp.raise_for_status()
        return str(resp.json().get("text") or "").strip()

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

    def ask(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})
        messages = [{"role": "system", "content": VOICE_STYLE}, *self.history]
        resp = self.http.post(
            f"{self.base}/v1/chat/completions",
            json={"model": self.model(), "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        answer = str(resp.json()["choices"][0]["message"].get("content") or "").strip()
        self.history.append({"role": "assistant", "content": answer})
        del self.history[: -HISTORY_TURNS * 2]
        return answer

    def speak(self, text: str) -> bytes:
        resp = self.http.post(
            f"{self.base}/v1/speech/synthesize", json={"text": text[:3000]}
        )
        resp.raise_for_status()
        return resp.content


class LocalWhisper:
    """Speech-to-text inside the Windows companion (no WSL, no GPU needed)."""

    def __init__(self, size: str = "base") -> None:
        from faster_whisper import WhisperModel

        self.model = WhisperModel(size, device="cpu", compute_type="int8")
        self.lock = threading.Lock()

    def transcribe(self, wav: bytes) -> str:
        import numpy as np

        with wave.open(io.BytesIO(wav)) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        audio = pcm.astype(np.float32) / 32768.0
        with self.lock:
            segments, _info = self.model.transcribe(
                audio, language="es", vad_filter=True, beam_size=1
            )
            return "".join(seg.text for seg in segments).strip()


_LOCAL: list[LocalWhisper | None] = []


def local_whisper() -> LocalWhisper | None:
    """Load once; None if faster-whisper is missing or the model can't load."""
    if not _LOCAL:
        try:
            _LOCAL.append(LocalWhisper())
        except Exception:  # noqa: BLE001
            log.exception("local Whisper unavailable; using the server")
            _LOCAL.append(None)
    return _LOCAL[0]


def play_wav(data: bytes) -> None:
    try:
        import winsound
    except ImportError:  # not Windows (tests)
        return
    winsound.PlaySound(data, winsound.SND_MEMORY)


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
    ) -> None:
        self.client = client
        self.ui = ui
        self.player = player
        self.chime = chime
        self.clock = clock
        self.busy = False
        self._follow_up_until = 0.0
        self._last_stt_error = -1e9

    @property
    def expecting(self) -> bool:
        """True right after a bare "Sergio": the next sentence is for him."""
        return self.clock() < self._follow_up_until

    def on_utterance(self, wav: bytes, *, addressed: bool) -> None:
        """*addressed*: the user pressed Ctrl+Space (no wake word needed)."""
        if self.busy:
            return
        self.busy = True
        try:
            self._turn(wav, addressed)
        except Exception as exc:  # noqa: BLE001 — never let a turn kill the loop
            log.exception("voice turn failed")
            self.ui.say(f"Algo falló: {explain(exc)}")
        finally:
            self.busy = False
            self.ui.state("listening" if self.expecting else "idle")

    def _turn(self, wav: bytes, addressed: bool) -> None:
        for_me = addressed or self.expecting
        if for_me:
            self.ui.state("thinking")
        try:
            text = self.client.transcribe(wav)
        except Exception as exc:  # noqa: BLE001
            log.exception("transcription failed")
            # With the wake word on, every sound in the room is transcribed:
            # report a broken speech-to-text once a minute, not per sound.
            if for_me or self.clock() - self._last_stt_error > 60:
                self._last_stt_error = self.clock()
                self.ui.say(f"No pude entender el audio: {explain(exc)}")
            return
        if not for_me:
            woke, text = parse_wake(text)
            if not woke:
                return  # conversation in the room, not for Sergio
            if not text:
                self._follow_up_until = self.clock() + FOLLOW_UP_SECONDS
                self.chime(880)
                self.ui.state("listening")
                self.ui.say("¿Sí?")
                return
        self._follow_up_until = 0.0
        if not text:
            self.ui.say("No te escuché. Intenta otra vez.")
            return
        self.ui.state("thinking")
        self.ui.say(f"«{text}»")
        try:
            answer = self.client.ask(text)
        except Exception as exc:  # noqa: BLE001
            log.exception("chat failed")
            self.ui.say(f"El modelo no respondió: {explain(exc)}")
            return
        if not answer:
            return
        self.ui.state("speaking")
        self.ui.say(answer)
        try:
            audio = self.client.speak(answer)
        except Exception:  # noqa: BLE001 — the text answer is already shown
            log.exception("speech synthesis failed")
            return
        self.player(audio)


class Ears:
    """Microphone loop: wake word always on (optional) plus push-to-talk."""

    def __init__(
        self,
        assistant: Assistant,
        *,
        wake_word: bool = True,
        segmenter: Segmenter | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.assistant = assistant
        self.wake_word = wake_word
        self.segmenter = segmenter or Segmenter()
        self.clock = clock
        self._ptt_until = 0.0
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self._stream: Any = None

    @property
    def push_to_talk(self) -> bool:
        return self.clock() < self._ptt_until

    def talk(self) -> None:
        """Ctrl+Space: listen to the next sentence, no wake word needed."""
        if self.assistant.busy:
            return
        self.segmenter.reset()
        self.segmenter.end_silence = 1.0
        self._ptt_until = self.clock() + PTT_TIMEOUT
        self.assistant.chime(880)
        self.assistant.ui.state("listening")
        self.assistant.ui.say("Te escucho…")

    def feed(self, chunk: bytes) -> tuple[bytes, bool] | None:
        """Process one frame; returns (utterance_wav, addressed) when ready."""
        if self.assistant.busy:
            self.segmenter.reset()  # don't hear our own voice
            return None
        ptt = self.push_to_talk
        if self._ptt_until and not ptt and not self.segmenter.active:
            self._ptt_until = 0.0  # push-to-talk timed out with no speech
            self.segmenter.end_silence = 0.8
            self.assistant.ui.state("idle")
        if not (self.wake_word or ptt or self.assistant.expecting):
            return None
        utterance = self.segmenter.feed(chunk)
        if utterance is None:
            return None
        addressed = bool(self._ptt_until)
        self._ptt_until = 0.0
        self.segmenter.end_silence = 0.8
        return to_wav(utterance), addressed

    def start(self) -> None:
        import sounddevice as sd

        def callback(indata: Any, _frames: int, _time: Any, _status: Any) -> None:
            try:
                self._queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

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
                wav, addressed = ready
                threading.Thread(
                    target=self.assistant.on_utterance,
                    args=(wav,),
                    kwargs={"addressed": addressed},
                    daemon=True,
                ).start()


__all__ = ["Assistant", "Ears", "SergioClient", "to_wav"]
