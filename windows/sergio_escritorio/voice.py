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
import threading
import time
import wave
from typing import Any, Callable, Protocol

import httpx

from sergio_escritorio.listen import FRAME, RATE, Segmenter, parse_wake

HISTORY_TURNS = 12
FOLLOW_UP_SECONDS = 8.0  # after a bare "Sergio", the next sentence is the order
PTT_TIMEOUT = 10.0  # longest push-to-talk recording

VOICE_STYLE = (
    "You are Sergio, a capable assistant living on the user's Windows laptop, "
    "talking out loud through the cursor companion. Reply in Spanish in one or "
    "two short, warm, natural spoken sentences, with no markdown, lists or "
    "emojis. Think about what the user really wants and DO it with your tools "
    "instead of guessing or only explaining. "
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
    "Blender: write a complete bpy script and call blender_create. "
    "Files: files_organize (preview first, apply only after the user agrees; "
    "undo=true reverts). Python: python_run for calculations, images, "
    "renaming or reading files. Terminal: terminal_run (PowerShell) for "
    "system tasks, installing apps with winget, git, pip. Apps: desktop_action "
    "open_app / close_app. "
    "3D globe (God's Eye View): globe_view to fly to a place, live_flights / "
    "live_earthquakes for live data, and open http://localhost:8000/globe. "
    "For long or complex tasks, first load the matching expert playbook (ECC) "
    "with skill_guide, plan the steps, then do them one by one. "
    "If you did not hear well, ask briefly instead of inventing. When done, "
    "say briefly what you did."
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
            timeout=httpx.Timeout(1800, connect=5),  # video edits take minutes
        )
        resp.raise_for_status()
        answer = str(resp.json()["choices"][0]["message"].get("content") or "").strip()
        self.history.append({"role": "assistant", "content": answer})
        del self.history[: -HISTORY_TURNS * 2]
        return answer

    voice = ""  # neural voice id; "" = use the server's local voice

    def speak(self, text: str) -> bytes:
        """Natural neural voice when online; the server's local voice otherwise."""
        if self.voice:
            try:
                from sergio_escritorio.neural_voice import synthesize

                return synthesize(text, self.voice)
            except Exception:  # noqa: BLE001 — offline or service hiccup
                log.exception("neural voice failed; using the local voice")
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

    def speak_on_server(self, text: str) -> bytes:
        resp = self.http.post(
            f"{self.base}/v1/speech/synthesize", json={"text": text[:3000]}
        )
        resp.raise_for_status()
        return resp.content


PROMPT = (
    "Sergio, abre Google y busca, entra al primer link, abre YouTube, "
    "edita un video con la carpeta, canal, publica, Blender, la cámara, "
    "qué tengo en la mano, Nvidia, WhatsApp."
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

    audio = audio - float(np.mean(audio))
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


def clean_transcript(text: str) -> str:
    low = text.lower().strip(" .,!¡")
    echo = len(low) > 25 and low in PROMPT.lower()  # Whisper repeating its prompt
    if not low or echo or any(h in low for h in HALLUCINATIONS):
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
                    model.transcribe(np.zeros(16000, dtype=np.float32), language="es")[
                        0
                    ]
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
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        audio = normalise(pcm.astype(np.float32) / 32768.0)
        with self.lock:
            segments, _info = self.model.transcribe(
                audio,
                language="es",
                vad_filter=False,  # the companion already cut the speech
                beam_size=5,
                initial_prompt=PROMPT,
                condition_on_previous_text=False,
                no_speech_threshold=0.5,
            )
            text = "".join(seg.text for seg in segments).strip()
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


def wants_screen(text: str) -> bool:
    """Questions about what is on screen: look, answer and point (Clicky)."""
    plain = _plain(text)
    if plain.split()[:1] and plain.split()[0] in _ACTION_VERBS:
        return False  # an order: the agent does it instead of pointing
    return any(phrase in plain for phrase in _SCREEN_PHRASES)


def target_point(
    reply: dict, elements: list[dict], scale: float
) -> tuple[int, int] | None:
    """Screen pixel to point at, from the model's element id or x,y."""
    chosen = reply.get("element")
    for el in elements:
        if chosen is not None and el.get("id") == chosen:
            return round(el["x"] * scale), round(el["y"] * scale)
    if reply.get("x") is not None and reply.get("y") is not None:
        return round(reply["x"] * scale), round(reply["y"] * scale)
    return None


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
        self.player = player
        self.chime = chime
        self.clock = clock
        self.busy = False
        self._follow_up_until = 0.0
        self._last_stt_error = -1e9
        self._last_hint = -1e9

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
            heard = text
            woke, text = parse_wake(text)
            if not woke:
                # Not for Sergio. If it sounded like an order, remind how to
                # call him (at most every two minutes).
                if len(heard.split()) >= 2 and self.clock() - self._last_hint > 120:
                    self._last_hint = self.clock()
                    self.ui.say(
                        f"Oí «{heard[:60]}». Para pedirme algo di «Sergio, …» "
                        "o pulsa Ctrl+Espacio."
                    )
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
        self._respond(text)

    def on_text(self, text: str) -> None:
        """A request typed in the notch (same as saying it, no microphone)."""
        text = text.strip()
        if not text or self.busy:
            return
        self.busy = True
        try:
            self._respond(text)
        except Exception as exc:  # noqa: BLE001
            log.exception("typed turn failed")
            self.ui.say(f"Algo falló: {explain(exc)}")
        finally:
            self.busy = False
            self.ui.state("idle")

    def _respond(self, text: str) -> None:
        self.ui.state("thinking")
        self.ui.say(f"«{text}»")
        answer = ""
        if self.screen is not None and wants_screen(text):
            try:
                png, elements, scale = self.screen()
                reply = self.client.screen_help(png, text, elements)
                answer = str(reply.get("answer") or "")
                spot = target_point(reply, elements, scale)
                if spot is not None:
                    self.point(spot[0], spot[1], str(reply.get("label") or ""))
            except Exception as exc:  # noqa: BLE001 — fall back to the agent
                log.exception("screen help failed")
                self.ui.say(f"No pude ver tu pantalla: {explain(exc)}")
        if not answer and self.eyes is not None and wants_camera(text):
            try:
                answer = self.client.look(self.eyes(), text)
                self.on_seen(answer)
            except Exception as exc:  # noqa: BLE001 — fall back to the agent
                log.exception("camera look failed")
                self.ui.say(f"No pude ver bien: {explain(exc)}")
        if not answer:
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

    @property
    def push_to_talk(self) -> bool:
        return bool(self._ptt_until)

    def talk(self) -> None:
        """Ctrl+Space / click: record now, no wake word, until you stop talking."""
        if self.assistant.busy:
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

    def feed(self, chunk: bytes) -> tuple[bytes, bool] | None:
        """Process one frame; returns (utterance_wav, addressed) when ready."""
        level = Segmenter.level(chunk)
        self.on_level(min(1.0, level / max(1.0, self.segmenter.threshold() * 4)))
        if self.assistant.busy:
            self.segmenter.reset()  # don't hear our own voice
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
            return to_wav(utterance), True
        if not (self.wake_word or self.assistant.expecting):
            return None
        utterance = self.segmenter.feed(chunk)
        if utterance is None:
            return None
        return to_wav(utterance), False

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
                wav, addressed = ready
                threading.Thread(
                    target=self.assistant.on_utterance,
                    args=(wav,),
                    kwargs={"addressed": addressed},
                    daemon=True,
                ).start()


__all__ = ["Assistant", "Ears", "SergioClient", "to_wav"]
