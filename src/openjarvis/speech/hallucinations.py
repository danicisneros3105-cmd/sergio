"""Filters for Whisper-style STT hallucinations on silence or noise.

Whisper (and faster-whisper) famously "hears" things that were never said
when the audio is silence, breathing, or background noise — classic outputs
are "Gracias por ver el vídeo", "Suscríbete", "Subtítulos por …".  Without a
filter those hallucinations reach the agent as if they were user commands,
which is why Sergio sometimes says random things at random moments.
"""

from __future__ import annotations

import re
import unicodedata

# Exact hallucinated phrases (after normalization: lowercase, no accents,
# no punctuation).  Conservative on purpose: multi-word classics that a
# person would rarely say as a complete utterance.
_PHRASES = {
    "gracias por ver",
    "gracias por ver el video",
    "gracias por ver este video",
    "gracias por verlo",
    "suscribete",
    "suscribete al canal",
    "suscribete y dale like",
    "dale like y suscribete",
    "subtitulos por",
    "musica",
    "aplausos",
    "risas",
    "silencio",
    "adios",
    "hasta la proxima",
    "nos vemos en el proximo video",
    "thank you for watching",
    "thanks for watching",
    "thank you so much for watching",
    "please subscribe",
    "subscribe to my channel",
    "dont forget to subscribe",
    "subtitles by",
    "captions by",
    "transcribed by",
    "bye bye",
    "see you next time",
}

# Bare filler sounds — noise pickups, never a real command.
_FILLERS = {"eh", "ah", "oh", "uh", "em", "hm", "mmm", "shh"}

# Patterns that are hallucination-shaped even with variable content.
_PATTERNS = [
    re.compile(r"^subtitulos (realizados |creados )?por\b"),
    re.compile(r"^subtitles (by|created by)\b"),
    re.compile(r"^transcribed by\b"),
    re.compile(r"^(musica|music)(\s+(de fondo|suave))?$"),
    re.compile(r"^\[(musica|aplausos|risas|music|applause|laughter)\]$"),
]

_MIN_CHARS = 2  # "ah", "eh", "…" carry no intent


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def is_hallucination(text: str | None) -> bool:
    """True when *text* looks like an STT hallucination, not real speech."""
    if not text:
        return True
    normalized = _normalize(text)
    if not normalized or len(normalized) < _MIN_CHARS:
        return True
    if normalized in _PHRASES or normalized in _FILLERS:
        return True
    # A single repeated token ("no no no no" from noise loops) is suspect
    # only when it is very long; short repetitions can be real emphasis.
    tokens = normalized.split()
    if len(tokens) >= 6 and len(set(tokens)) == 1:
        return True
    return any(pattern.search(normalized) for pattern in _PATTERNS)


__all__ = ["is_hallucination"]
