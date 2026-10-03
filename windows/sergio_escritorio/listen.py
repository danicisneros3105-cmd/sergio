"""Hearing: split the microphone into utterances and spot the word "Sergio".

Pure logic (no audio device), so it is easy to test:

* ``Segmenter`` turns 16 kHz int16 frames into utterances with a simple
  energy detector that adapts to the room's noise floor.
* ``parse_wake`` decides whether an utterance is addressed to Sergio
  ("Sergio, abre Spotify", "oye Sergio ...") and returns the command part.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections import deque
from dataclasses import dataclass, field

import numpy as np

RATE = 16_000
FRAME = 512  # 32 ms
WAKE = "sergio"
_FILLERS = {"oye", "hey", "ey", "hola", "ok", "okay", "eh", "este", "a", "ya"}


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def parse_wake(text: str) -> tuple[bool, str]:
    """(addressed_to_sergio, command). Tolerates Whisper spellings (Cergio, Sergió).

    The name must come first, optionally after a filler ("oye Sergio, ...").
    """
    for count, match in enumerate(re.finditer(r"[^\W_]+", text)):
        if count >= 4:
            break
        word = _plain(match.group())
        if word in _FILLERS:
            continue
        if difflib.SequenceMatcher(None, word, WAKE).ratio() >= 0.8:
            return True, text[match.end() :].strip(" ,.;:!?¡¿\n")
        break
    return False, ""


@dataclass
class Segmenter:
    """Energy-based utterance detector with an adaptive noise floor."""

    rate: int = RATE
    frame: int = FRAME
    start_frames: int = 3  # ~100 ms of voice to start
    end_silence: float = 0.8  # seconds of quiet that end an utterance
    max_seconds: float = 15.0
    pre_roll: float = 0.3
    min_level: float = 350.0  # int16 RMS; quieter is never speech
    floor: float = 200.0
    _voiced: int = 0
    _quiet: int = 0
    _active: bool = False
    _frames: list = field(default_factory=list)
    _pre: deque = field(default_factory=deque)

    def __post_init__(self) -> None:
        self._pre = deque(maxlen=max(1, int(self.pre_roll * self.rate / self.frame)))

    @staticmethod
    def level(chunk: bytes) -> float:
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0

    @property
    def active(self) -> bool:
        """True while an utterance is being recorded."""
        return self._active

    def threshold(self) -> float:
        return max(self.min_level, self.floor * 3.0)

    def reset(self) -> None:
        self._voiced = self._quiet = 0
        self._active = False
        self._frames = []
        self._pre.clear()

    def feed(self, chunk: bytes) -> bytes | None:
        """Add one frame; returns a finished utterance (raw int16) or None."""
        level = self.level(chunk)
        speech = level > self.threshold()
        if not self._active:
            if not speech:
                # Learn the room: slow moving average of the quiet level.
                self.floor = 0.95 * self.floor + 0.05 * level
                self._voiced = 0
                self._pre.append(chunk)
                return None
            self._voiced += 1
            self._pre.append(chunk)
            if self._voiced >= self.start_frames:
                self._active = True
                self._frames = list(self._pre)
                self._pre.clear()
                self._quiet = 0
            return None
        self._frames.append(chunk)
        self._quiet = 0 if speech else self._quiet + 1
        seconds = len(self._frames) * self.frame / self.rate
        if seconds >= self.max_seconds and self._steady():
            # A long, even sound (TV, fan, music) is the room, not a person:
            # drop it and raise the floor so it stops triggering.
            self.floor = max(self.floor, 0.8 * self._median_level())
            self.reset()
            return None
        if (
            self._quiet * self.frame / self.rate >= self.end_silence
            or seconds >= self.max_seconds
        ):
            utterance = b"".join(self._frames)
            self.reset()
            return utterance
        return None

    def _levels(self) -> np.ndarray:
        return np.array([self.level(f) for f in self._frames], dtype=np.float32)

    def _median_level(self) -> float:
        return float(np.median(self._levels()))

    def _steady(self) -> bool:
        """Speech has pauses and stresses; steady noise barely varies."""
        levels = self._levels()
        mean = float(levels.mean()) if levels.size else 0.0
        return bool(mean) and float(levels.std()) / mean < 0.25


__all__ = ["FRAME", "RATE", "Segmenter", "parse_wake"]
