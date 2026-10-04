"""Hearing the word "Sergio" at once, while you are still talking.

Before, every sound in the room went through Whisper to look for "Sergio":
seconds per sound on a laptop CPU, and the microphone was deaf meanwhile, so
orders were missed or answered late. Now a tiny streaming recogniser (Vosk,
a 40 MB Spanish model whose grammar only knows the wake word) listens to
every 32 ms frame:

* ``maybe``: it *thinks* it heard "Sergio" (partial result, ~0.3 s after the
  word). The call starts connecting right away and your words are buffered.
* ``yes``: the phrase ended and "Sergio" was really at its start. The buffer
  goes to the call, which already is on the line: he answers within a second
  of you finishing "Sergio, abre Spotify".
* ``no``: it was something else ("ayer vi a Sergio..."): the call is
  dropped before it hears anything.

Pure logic plus a thin Vosk loader, so it is easy to test.
"""

from __future__ import annotations

import json
import logging
import threading
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

MODEL_NAME = "vosk-model-small-es-0.42"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
RATE = 16_000
# "Sergio" must open the phrase: at most this long after its first word
# ("oye Sergio, ..." is fine; "ayer hablé con Sergio" is not).
MAX_LEAD = 1.2
MIN_CONF = 0.5
# Words that sound like the name; Vosk's grammar needs real dictionary words.
SOUNDALIKES = ("sergio",)
FILLERS = ("oye", "hey", "hola", "ok")


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


class WakeSpotter:
    """Turns microphone frames into "maybe" / "yes" / "no" about the name."""

    def __init__(
        self,
        recognizer: Callable[[list[str]], Any],
        names: tuple[str, ...] | list[str] = SOUNDALIKES,
        *,
        max_lead: float = MAX_LEAD,
        min_conf: float = MIN_CONF,
    ) -> None:
        self.names = tuple(dict.fromkeys(_plain(n) for n in names if n.strip()))
        self._factory = recognizer
        self.max_lead = max_lead
        self.min_conf = min_conf
        self._rec = recognizer(list(self.names) + list(FILLERS) + ["[unk]"])
        self._maybe = False

    def reset(self) -> None:
        self._maybe = False
        try:
            self._rec.Reset()
        except Exception:  # noqa: BLE001 — a fresh one then
            self._rec = self._factory(list(self.names) + list(FILLERS) + ["[unk]"])

    def feed(self, frame: bytes) -> str | None:
        """One frame of 16 kHz int16 audio -> "maybe" | "yes" | "no" | None."""
        if self._rec.AcceptWaveform(frame):
            return self._final(json.loads(self._rec.Result() or "{}"))
        if self._maybe:
            return None
        partial = json.loads(self._rec.PartialResult() or "{}").get("partial", "")
        words = _plain(partial).split()
        if any(w in self.names for w in words[:3]):
            self._maybe = True
            return "maybe"
        return None

    def _final(self, result: dict) -> str | None:
        was_maybe, self._maybe = self._maybe, False
        words = result.get("result") or []
        if self._addressed(words):
            return "yes"
        return "no" if was_maybe else None

    def _addressed(self, words: list[dict]) -> bool:
        if not words:
            return False
        first = float(words[0].get("start", 0.0))
        for word in words:
            name = _plain(str(word.get("word", "")))
            if name in self.names:
                lead = float(word.get("start", first)) - first
                return (
                    lead <= self.max_lead
                    and float(word.get("conf", 1.0)) >= self.min_conf
                )
        return False


# -- the Vosk model --------------------------------------------------------
def model_dir(home: Path) -> Path:
    return home / "modelos" / MODEL_NAME


def download_model(
    home: Path, url: str = MODEL_URL, fetch: Callable[[str, Path], None] | None = None
) -> Path:
    """Download and unzip the Spanish model once (~40 MB)."""
    target = model_dir(home)
    if (target / "am").exists() or (target / "conf").exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    archive = target.parent / f"{MODEL_NAME}.zip"
    if fetch is None:
        import urllib.request

        def fetch(src: str, dst: Path) -> None:
            part = dst.with_suffix(".part")
            with (
                urllib.request.urlopen(src, timeout=60) as resp,
                part.open("wb") as out,
            ):
                while chunk := resp.read(1 << 16):
                    out.write(chunk)
            part.replace(dst)

    fetch(url, archive)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target.parent)
    archive.unlink(missing_ok=True)
    return target


def load_spotter(
    home: Path, names: list[str] | tuple[str, ...] = SOUNDALIKES
) -> WakeSpotter | None:
    """A ready spotter, or None (no vosk / no model: Whisper does it)."""
    try:
        import vosk
    except Exception as exc:  # noqa: BLE001
        log.info("instant wake word unavailable (vosk: %s); using Whisper", exc)
        return None
    try:
        vosk.SetLogLevel(-1)
        model = vosk.Model(str(download_model(home)))
    except Exception:  # noqa: BLE001
        log.warning("could not load the wake word model; using Whisper", exc_info=True)
        return None

    def recognizer(grammar: list[str]) -> Any:
        rec = vosk.KaldiRecognizer(model, RATE, json.dumps(grammar, ensure_ascii=False))
        rec.SetWords(True)
        return rec

    log.info("instant wake word ready (%s)", MODEL_NAME)
    return WakeSpotter(recognizer, names)


def load_in_background(
    home: Path, names: list[str], done: Callable[[WakeSpotter | None], None]
) -> None:
    threading.Thread(
        target=lambda: done(load_spotter(home, names)), daemon=True
    ).start()


__all__ = [
    "MODEL_NAME",
    "MODEL_URL",
    "WakeSpotter",
    "download_model",
    "load_in_background",
    "load_spotter",
    "model_dir",
]
