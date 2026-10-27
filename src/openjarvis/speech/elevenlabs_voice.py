"""ElevenLabs voice for Sergio: streamed, the lowest delay we have.

The voice is "J Thomas — Warm, Raspy & Real", an original voice from the
ElevenLabs library (deep, warm, a rasp in the low register, relaxed). It is
not a copy of any real person's voice. Flash v2.5 starts speaking in about
a tenth of a second.

Many languages, one voice: code works out the language of each sentence
(Spanish, English, French, Portuguese, Italian, German…) and tells
ElevenLabs, so an English sentence is read as English and not with a Spanish
accent — that mismatch is what made it sound robotic. The text is cleaned
for speaking first (no asterisks, hashes or raw links read aloud), and the
sentence before is passed along so the intonation flows from one sentence
to the next. ``SERGIO_VOZ_CALIDAD=alta`` swaps Flash for Multilingual v2:
richer, slower to start.

Needs ``ELEVENLABS_API_KEY`` (``sergio nube voz --elevenlabs CLAVE``). Without
it, or out of credit, Sergio uses Gemini's Algenib voice.
"""

from __future__ import annotations

import io
import os
import re
import unicodedata
import wave
from typing import AsyncIterator, Dict

API = "https://api.elevenlabs.io/v1"
VOICE_ID = "f5gk6ENs9vgDBvfkTj7e"  # J Thomas — Warm, Raspy & Real
VOICE_NAME = "J Thomas - Warm, Raspy & Real"
MODEL = "eleven_flash_v2_5"
QUALITY_MODEL = "eleven_multilingual_v2"  # no language_code: it reads the text
RATE = 24000
SETTINGS = {
    "stability": 0.42,  # some life in the delivery
    "similarity_boost": 0.85,
    "style": 0.15,
    "use_speaker_boost": True,
    "speed": 0.97,  # relaxed, never rushed
}


def key() -> str:
    found = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not found:
        raise RuntimeError(
            "Falta ELEVENLABS_API_KEY (sergio nube voz --elevenlabs CLAVE)"
        )
    return found


# -- which language is this sentence in ---------------------------------------
# Short, frequent words that only (or mostly) one language uses.
WORDS: Dict[str, set] = {
    "es": set(
        "el la los las de del que y en un una por para con no es está son pero "
        "como más muy ya también señor usted qué cómo cuándo dónde hay esto eso "
        "hola gracias aquí ahora tengo puede le lo se su sus".split()
    ),
    "en": set(
        "the and of to is are was were you your it this that with for not have "
        "has be will would can could what how when where there here hello thanks "
        "please sir i my we they he she do does".split()
    ),
    "fr": set(
        "le la les des du et est sont une un pour avec pas que qui je vous nous "
        "ils elle mais très bien bonjour merci oui monsieur ce cette dans sur au "
        "aux c'est il".split()
    ),
    "pt": set(
        "o a os as do da dos das e é são um uma para com não que em no na mas "
        "muito obrigado olá você senhor isso está estão também".split()
    ),
    "it": set(
        "il lo la gli le di del della che e è sono un una per con non ma molto "
        "grazie ciao signore questo questa anche sei è buongiorno buonasera "
        "ecco perché".split()
    ),
    "de": set(
        "der die das und ist sind ein eine nicht mit für zu ich sie wir aber "
        "sehr danke hallo herr auch auf dem den".split()
    ),
}
MARKS = {  # letters that give a language away
    "es": "ñ¿¡",
    "fr": "çàùâêîôûëïœ",  # not «è»: Italian's «è» would count for French
    "pt": "ãõ",
    "de": "ßäöü",
    "it": "",
    "en": "",
}


def detect_language(text: str, default: str = "es") -> str:
    """The language of *text* (ISO 639-1), or *default* when unsure."""
    low = (text or "").lower()
    words = re.findall(r"[a-zà-ÿœß']+", low)
    if not words:
        return default
    score = {lang: sum(w in vocab for w in words) for lang, vocab in WORDS.items()}
    for lang, marks in MARKS.items():
        score[lang] += 2 * sum(low.count(m) for m in marks)
    best = max(score, key=lambda k: (score[k], k == default))
    ranked = sorted(score.values(), reverse=True)
    if ranked[0] == 0 or (len(words) < 3 and ranked[0] < 2):
        return default
    if ranked[0] == ranked[1] and score.get(default, 0) == ranked[0]:
        return default
    return best


LINK_WORD = {
    "es": "el enlace",
    "en": "the link",
    "fr": "le lien",
    "pt": "o link",
    "it": "il link",
    "de": "der Link",
}


def speakable(text: str, language: str = "es") -> str:
    """What should be heard: Markdown, raw links and emoji left out."""
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)  # code is for reading
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # [label](url) -> label
    text = re.sub(
        r"https?://(?:www\.)?([^/\s]+)\S*",
        lambda m: (
            m.group(1) if len(m.group(1)) < 30 else LINK_WORD.get(language, "el enlace")
        ),
        text,
    )
    text = re.sub(  # a heading is a short sentence of its own
        r"^[ \t]{0,3}#{1,6}[ \t]*(.*?)[ \t.:]*$", r"\1.", text, flags=re.M
    )
    text = re.sub(r"^[ \t]*[-*+•][ \t]+", "", text, flags=re.M)  # bullets
    text = re.sub(r"^[ \t]*\|?[ \t]*:?-{2,}.*$", "", text, flags=re.M)  # table rules
    text = re.sub(  # a table row is read as one short sentence
        r"^[ \t]*\|(.*)\|[ \t]*$",
        lambda m: (
            ", ".join(c.strip() for c in m.group(1).split("|") if c.strip()) + "."
        ),
        text,
        flags=re.M,
    )
    text = text.replace("|", ", ")
    text = re.sub(r"(\*\*|__|\*|_|`|~~)", "", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("So", "Cs"))
    text = re.sub(r"\s*\n\s*\n\s*", ". ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return re.sub(r"([.,;:!?])\s*\.", r"\1", text)


def model() -> str:
    quality = os.environ.get("SERGIO_VOZ_CALIDAD", "").strip().lower()
    return QUALITY_MODEL if quality in ("alta", "high", "max") else MODEL


def voice_of(name: str) -> str:
    """'elevenlabs:ID' or 'ID' -> ID (the default voice when empty)."""
    voice = (
        name.split(":", 1)[-1].strip()
        or os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
        or VOICE_ID
    )
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", voice):
        raise ValueError("ID de voz de ElevenLabs inválido.")
    return voice


def request(
    text: str,
    voice: str,
    language: str = "",
    previous: str = "",
    hint: str = "",
    model_id: str = "",
) -> tuple[str, dict, dict]:
    """*language*: ISO 639-1, or "" to work it out from the text — and, when
    the sentence is too short to tell («OK»), from *previous* (the sentence
    spoken just before, which also smooths the intonation), then *hint*."""
    fallback = detect_language(previous, (hint or "es").lower()[:2])
    lang = (language or detect_language(text, fallback)).lower()[:2]
    url = f"{API}/text-to-speech/{voice_of(voice)}/stream"
    params = {"output_format": f"pcm_{RATE}", "optimize_streaming_latency": "3"}
    model_id = model_id or model()
    body = {
        "text": speakable(text, lang)[:2500] or text[:2500],
        "model_id": model_id,
        "voice_settings": SETTINGS,
    }
    if model_id == MODEL:  # only Flash/Turbo take a language to enforce
        body["language_code"] = lang
    if previous.strip():
        body["previous_text"] = speakable(previous, lang)[-600:]
    return url, params, body


async def stream_pcm(
    text: str, voice: str = "", language: str = "", previous: str = "", hint: str = ""
) -> AsyncIterator[bytes]:
    """Raw PCM 24 kHz int16 chunks as ElevenLabs makes them."""
    import httpx

    url, params, body = request(text, voice, language, previous, hint)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5)) as http:
        async with http.stream(
            "POST", url, params=params, json=body, headers={"xi-api-key": key()}
        ) as resp:
            if resp.status_code != 200:
                detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                raise RuntimeError(f"ElevenLabs {resp.status_code}: {detail}")
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk


def pcm(
    text: str,
    voice: str = "",
    language: str = "",
    previous: str = "",
    hint: str = "",
    model_id: str = "",
    timeout: float = 30,
) -> bytes:
    """The whole sentence as raw PCM 24 kHz int16 (Sergio's own voice speaks
    phrase by phrase with it; the video narrator uses Multilingual v2)."""
    import httpx

    url, params, body = request(text, voice, language, previous, hint, model_id)
    resp = httpx.post(
        url,
        params=params,
        json=body,
        headers={"xi-api-key": key()},
        timeout=httpx.Timeout(timeout, connect=5),
    )
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs {resp.status_code}: {resp.text[:300]}")
    return resp.content


def speak_wav(
    text: str, voice: str = "", language: str = "", previous: str = "", hint: str = ""
) -> bytes:
    """The whole sentence as a WAV (for the non-streamed path)."""
    raw = pcm(text, voice, language, previous, hint)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(raw)
    return buf.getvalue()


__all__ = [
    "VOICE_ID",
    "VOICE_NAME",
    "detect_language",
    "pcm",
    "speak_wav",
    "speakable",
    "stream_pcm",
    "voice_of",
]
