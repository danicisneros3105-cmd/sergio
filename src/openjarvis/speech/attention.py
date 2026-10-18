"""Bounded conversational attention, without pretending to identify people.

Speech recognition is not authentication. This policy only decides whether
Sergio should answer: his name opens a follow-up window; explicit room
conversation closes it. Known speaker changes require a fresh address.
Audio that sounds like a video, the TV, music or another language (a YouTube
video playing next to him) is not for him unless it calls him by name.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Callable


def normalized(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(c)
    )


# What videos, streams, the TV and songs say (and how transcription marks them).
_MEDIA = re.compile(
    r"(suscrib|dale like|deja tu like|activa la campanita|bienvenidos a(l| mi) canal|"
    r"en el video de hoy|en este video|patrocinad|link en la descripcion|"
    r"subscribe|like and subscribe|this video|my channel|sponsored|"
    # Only the transcription marks [música], (risas)…: the word alone is fine.
    r"[\[\(](musica|music|aplausos|applause|risas|laughter)[\]\)]|♪)"
)
_ENGLISH = {
    "the",
    "and",
    "you",
    "that",
    "this",
    "is",
    "are",
    "was",
    "what",
    "with",
    "for",
    "have",
    "it's",
    "i'm",
    "we",
    "they",
    "just",
    "going",
    "really",
    "about",
    "know",
    "like",
    "so",
    "but",
    "not",
    "your",
    "can",
    "do",
}
# One unaddressed turn longer than this is a monologue: a video or a talk.
_MONOLOGUE_WORDS = 45


def looks_like_media(text: str, language: str = "es") -> bool:
    """Speech that is almost surely a video, the TV or a song, not the owner."""
    text = normalized(text)
    if _MEDIA.search(text):
        return True
    words = re.findall(r"[a-z']+", text)
    if len(words) >= _MONOLOGUE_WORDS:
        return True
    if language.startswith("es") and len(words) >= 6:
        english = sum(1 for w in words if w in _ENGLISH)
        if english / len(words) >= 0.3:
            return True
    return False


class Attention:
    def __init__(
        self,
        name: str = "Sergio",
        *,
        window: float = 30,
        language: str = "es",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = re.escape(normalized(name))
        self.language = language
        self.clock, self.window = clock, window
        self.until = clock() + window  # opening a call explicitly addresses him
        self.other_speaker = False

    def speaker(self, owner: bool) -> None:
        self.other_speaker = not owner
        self.until = 0

    def answered(self) -> None:
        """Sergio just answered: a reply from the owner may follow without
        his name, for a short while (like talking to a person)."""
        self.until = self.clock() + self.window

    def accepts(self, text: str) -> bool:
        text = normalized(text)
        if re.search(
            r"\b(no te hablo|no era para ti|hablo con otra persona|"
            r"estoy hablando por telefono|no te estoy hablando)\b",
            text,
        ):
            self.until = 0
            return False
        # Mentioning him in the third person is not calling him.
        named = re.search(rf"\b{self.name}\b", text) is not None
        mention = re.search(rf"\b{self.name}\s+(dijo|dice|es|hizo|me dijo)\b", text)
        if named and not mention:
            self.until = self.clock() + self.window
            return True
        if looks_like_media(text, self.language):
            self.until = 0  # a video is playing: wait for his name again
            return False
        if mention or self.other_speaker or self.clock() >= self.until:
            return False
        self.until = self.clock() + self.window
        return True


__all__ = ["Attention", "looks_like_media"]
