"""Push-to-talk: press Ctrl+Alt+Space, talk, press it again; Sergio answers aloud.

Everything goes to the local Sergio server: speech-to-text (Whisper),
the agent (with all of Sergio's tools, including screen control) and the
Spanish voice. Nothing leaves the laptop unless a tool needs the internet.
"""

from __future__ import annotations

import io
import logging
import threading
import wave
from typing import Any, Callable

import httpx

RATE = 16_000
MAX_SECONDS = 60
HISTORY_TURNS = 12

log = logging.getLogger(__name__)


def to_wav(chunks: list[bytes], rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(chunks))
    return buf.getvalue()


class SergioClient:
    """Small client for the Sergio API (transcribe, chat, speak)."""

    def __init__(self, base_url: str, http: httpx.Client | None = None) -> None:
        self.base = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=httpx.Timeout(300, connect=5))
        self.history: list[dict[str, str]] = []
        self._model = ""

    def transcribe(self, wav: bytes) -> str:
        resp = self.http.post(
            f"{self.base}/v1/speech/transcribe",
            files={"file": ("voz.wav", wav, "audio/wav")},
        )
        resp.raise_for_status()
        return str(resp.json().get("text") or "").strip()

    def model(self) -> str:
        if not self._model:
            resp = self.http.get(f"{self.base}/v1/models")
            resp.raise_for_status()
            data = resp.json().get("data") or [{}]
            self._model = data[0].get("id") or "default"
        return self._model

    def ask(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})
        resp = self.http.post(
            f"{self.base}/v1/chat/completions",
            json={"model": self.model(), "messages": self.history, "stream": False},
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


def play_wav(data: bytes) -> None:
    try:
        import winsound
    except ImportError:  # not Windows (tests)
        return
    winsound.PlaySound(data, winsound.SND_MEMORY)


def beep(freq: int) -> None:
    try:
        import winsound

        winsound.Beep(freq, 120)
    except Exception:  # noqa: BLE001
        pass


class VoiceChat:
    def __init__(
        self,
        client: SergioClient,
        *,
        notify: Callable[[str], None],
        on_state: Callable[[str], None] = lambda _s: None,
        player: Callable[[bytes], None] = play_wav,
    ) -> None:
        self.client = client
        self.notify = notify
        self.on_state = on_state
        self.player = player
        self._chunks: list[bytes] = []
        self._stream: Any = None
        self._lock = threading.Lock()
        self.busy = False

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def toggle(self) -> None:
        with self._lock:
            if self._stream is None:
                self._start()
            else:
                self._stop()

    def _start(self) -> None:
        if self.busy:
            self.notify("Sergio todavía está respondiendo…")
            return
        import sounddevice as sd

        self._chunks = []

        def callback(indata: Any, _frames: int, _time: Any, _status: Any) -> None:
            if len(self._chunks) * 1024 < RATE * MAX_SECONDS:
                self._chunks.append(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=RATE,
            channels=1,
            dtype="int16",
            blocksize=1024,
            callback=callback,
        )
        self._stream.start()
        beep(880)
        self.on_state("listening")

    def _stop(self) -> None:
        stream, self._stream = self._stream, None
        stream.stop()
        stream.close()
        beep(660)
        chunks, self._chunks = self._chunks, []
        threading.Thread(
            target=self.process, args=(to_wav(chunks),), daemon=True
        ).start()

    def process(self, wav: bytes) -> None:
        self.busy = True
        self.on_state("thinking")
        try:
            text = self.client.transcribe(wav)
            if not text:
                self.notify("No te escuché. Intenta otra vez.")
                return
            self.notify(f"Tú: {text}")
            answer = self.client.ask(text)
            self.notify(f"Sergio: {answer[:200]}")
            self.on_state("speaking")
            if answer:
                self.player(self.client.speak(answer))
        except Exception as exc:  # noqa: BLE001
            log.exception("voice turn failed")
            self.notify(f"No pude responder: {exc}")
        finally:
            self.busy = False
            self.on_state("idle")


__all__ = ["SergioClient", "VoiceChat", "to_wav"]
