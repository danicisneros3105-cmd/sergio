"""Bounded Conversational Attention Nexus with Biometric Voiceprint and Addressee Diarization.

Upgraded to Approach B (Edge Multimodal Diarization):
1. Acoustic Biometric Voiceprint Verification (ECAPA/Mel-Formant Embeddings): Rejects
   speech from TV, movies, and third parties at the acoustic wave layer.
2. System Loopback & Acoustic Echo Cancellation (WASAPI/PulseAudio): Suppresses mic
   bleed while media/series are playing.
3. Pragmatic Addressee Intent Classifier: Distinguishes speech directed to Sergio
   versus side-talk with family/phone calls.
4. Adaptive Turn-Taking Decay: Closes listening windows immediately when side-conversations
   or media playback occur, preventing unwanted barge-ins and interruptions.
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from typing import Any, Callable, Optional

from openjarvis.speech.addressee_classifier import AddresseeClassifier, AddresseeTarget
from openjarvis.speech.biometric_voiceprint import VoiceprintManager, get_voiceprint_manager
from openjarvis.speech.loopback_aec import LoopbackAEC, get_loopback_aec

log = logging.getLogger("openjarvis.speech.attention")


def normalized(text: str) -> str:
    """Normalize string by lowercasing and stripping diacritics."""
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
    norm = normalized(text)
    if _MEDIA.search(norm):
        return True
    words = re.findall(r"[a-z']+", norm)
    if len(words) >= _MONOLOGUE_WORDS:
        return True
    if language.startswith("es") and len(words) >= 6:
        english = sum(1 for w in words if w in _ENGLISH)
        if english / len(words) >= 0.3:
            return True
    return False


class Attention:
    """Intelligent conversational attention controller implementing Approach B."""

    def __init__(
        self,
        name: str = "Sergio",
        *,
        window: float = 30.0,
        language: str = "es",
        clock: Callable[[], float] = time.monotonic,
        enable_biometrics: bool = True,
        enable_aec: bool = True,
    ) -> None:
        self.name_raw = str(name)
        self.name = re.escape(normalized(name))
        self.language = language
        self.clock = clock
        self.window = window
        self.until = clock() + window  # opening a call explicitly addresses him
        self.other_speaker = False

        self.enable_biometrics = enable_biometrics
        self.enable_aec = enable_aec

        self.addressee_classifier = AddresseeClassifier(self.name_raw)
        self.voiceprint_mgr: VoiceprintManager = get_voiceprint_manager()
        self.loopback_aec: LoopbackAEC = get_loopback_aec()

    def speaker(self, owner: bool) -> None:
        """Inform attention that a speaker transition occurred."""
        self.other_speaker = not owner
        self.until = 0

    def answered(self) -> None:
        """Sergio just answered: adaptively configure the follow-up conversational window."""
        # Check if media is currently playing in the operating system
        if self.enable_aec:
            media_playing, _ = self.loopback_aec.should_suppress_mic_input()
            if media_playing:
                # During movies/music, close follow-up window immediately to prevent TV dialogue pickup
                self.until = 0
                return

        # Normal conversational follow-up window
        self.until = self.clock() + self.window

    def accepts(
        self,
        text: str,
        audio_pcm: Optional[bytes] = None,
    ) -> bool:
        """Evaluate whether the incoming utterance should be received and acted upon by Sergio."""
        norm = normalized(text)

        # 1. Acoustic Biometric Verification (if audio data is provided and profile is enrolled)
        if self.enable_biometrics and audio_pcm is not None and len(audio_pcm) > 3200:
            bio_res = self.voiceprint_mgr.verify_speaker(audio_pcm)
            if bio_res.is_enrolled and not bio_res.is_owner:
                log.info(
                    "Rechazado por biometría vocal: voz no autorizada (similitud: %.3f < %.3f)",
                    bio_res.similarity_score,
                    bio_res.threshold,
                )
                self.until = 0
                return False

        # 2. Check for explicit exclusion phrases (user telling Sergio not to listen / on phone)
        if re.search(
            r"\b(no te hablo|no era para ti|hablo con otra persona|"
            r"estoy hablando por telefono|no te estoy hablando)\b",
            norm,
        ):
            self.until = 0
            return False

        # 3. Explicit vocative address ("Sergio, ...")
        named = re.search(rf"\b{self.name}\b", norm) is not None
        mention = re.search(rf"\b{self.name}\s+(dijo|dice|es|era|hizo|me dijo)\b", norm)
        if named and not mention:
            self.other_speaker = False
            self.until = self.clock() + self.window
            return True

        # 4. Check for video / stream / media monologues
        if looks_like_media(norm, self.language):
            self.until = 0  # a video is playing: wait for his name again
            return False

        # 5. Pragmatic Addressee Intent Classification
        is_window_active = self.clock() < self.until and not self.other_speaker
        target, conf, reason = self.addressee_classifier.classify_utterance(
            norm, recent_exchange_active=is_window_active
        )

        if target == AddresseeTarget.OTHER_PERSON:
            log.info("Descartado: conversación dirigida a otra persona (%s)", reason)
            self.until = 0
            return False

        if target == AddresseeTarget.AMBIENT_MEDIA:
            log.info("Descartado: detectado diálogo de serie o medios (%s)", reason)
            self.until = 0
            return False

        # 6. Check system loopback (if media is playing on PC, require explicit vocative)
        if self.enable_aec:
            media_active, media_desc = self.loopback_aec.should_suppress_mic_input()
            if media_active and not named:
                log.info("Silenciado por loopback AEC: %s", media_desc)
                self.until = 0
                return False

        # 7. Check window expiration and third-person mentions
        if mention or self.other_speaker or not is_window_active:
            return False

        # Refresh adaptive follow-up window
        self.until = self.clock() + self.window
        return True


__all__ = ["Attention", "looks_like_media", "normalized"]
