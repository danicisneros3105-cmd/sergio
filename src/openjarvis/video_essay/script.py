"""The words of a video essay: the script, Sergio's narration and when each
word is said.

* :func:`write` — the strongest model writes the narration in the
  reference's structure (hook, problem, turn, story, contrast, payoff, call),
  at the pace Sergio's voice reads (about 1.9 words a second).
* :func:`narrate` — Sergio reads it as a narrator (male voice). The owner,
  27 Oct 2026: «la voz es una mierda». The narration is directed now, not
  read: ElevenLabs Multilingual v2 with Sergio's ElevenLabs voice when
  ``ELEVENLABS_API_KEY`` is set, else Gemini's studio voices (Pro first)
  with a narrator's direction (:data:`NARRATOR`). Each voice call takes at
  most 2500 characters, so the text goes in pieces cut at the end of
  sentences, made three at a time and joined with a short breath; each piece
  knows the one before so the intonation runs on.
* :func:`timings` — when each word is said: a local recogniser
  (faster-whisper, ``SERGIO_WHISPER_MODEL``, "base" by default) gives the
  times and the script keeps its own spelling (:func:`align`); without it,
  the words are spread over the parts of the audio that have speech.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from openjarvis.video_essay import audio
from openjarvis.video_essay.plan import Word, estimate_words

WORDS_PER_SECOND = 1.9  # Sergio's narration, measured (Gemini voice, oct. 2026)
CHUNK = 1800  # characters per voice call, well under its 2500 limit
NARRATOR = (
    "Narra esto como el narrador de un gran video ensayo de YouTube: voz "
    "masculina grave, segura y cercana, con energía contenida y ritmo vivo; "
    "subraya las palabras clave, haz una pausa breve antes de cada giro y "
    "deja que las frases cortas peguen. Natural y humano, con intención en "
    "cada frase: nunca monótono, robótico ni de locutor de radio. No leas "
    "estas instrucciones. Di exactamente esto:"
)
# Gemini's studio voices for narration: the Pro voice first (richest)
NARRATION_MODELS = (
    "gemini-2.5-pro-preview-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
)

SCRIPT_PROMPT = """You write narration for top motivational / explainer video essays \
(the kind with a cut every 1-2 seconds and kinetic text). Write the narration in \
{language} about: «{topic}».

Length: about {words} words (it will be read in ~{seconds} seconds).
Structure, in this order: {structure}.
Style of the reference: {narration}
Rules: short spoken sentences, concrete images and numbers, one idea per \
sentence, a strong hook in the first 5 seconds, a clear turn, a real story or \
example (no invented quotes from real people, no false statistics), a payoff \
and a short call to action at the end. No emojis, no hashtags, no stage \
directions, no brand names.
Answer ONLY JSON: {{"title": "max 7 words", "beats": [{{"beat": "hook|problem|turn|story|contrast|payoff|cta", \
"text": "what the narrator says"}}]}}"""


def _check(text: str) -> Dict[str, Any]:
    data = json.loads(text)
    beats = [
        {
            "beat": str(b.get("beat") or ""),
            "text": " ".join(str(b.get("text") or "").split()),
        }
        for b in data.get("beats") or []
        if isinstance(b, dict) and str(b.get("text") or "").strip()
    ]
    if len(beats) < 2 or sum(len(b["text"].split()) for b in beats) < 20:
        raise ValueError("guion demasiado corto")
    return {"title": str(data.get("title") or "")[:70], "beats": beats}


def write(
    topic: str,
    seconds: float,
    style: Dict[str, Any],
    *,
    language: str = "Spanish",
    ask: Optional[Callable[..., str]] = None,
) -> Dict[str, Any]:
    """{"title", "beats": [{"beat", "text"}], "text"} for *topic*."""
    structure = style.get("structure") or [
        "hook", "problem", "turn", "story", "contrast", "payoff", "cta",
    ]  # fmt: skip
    prompt = SCRIPT_PROMPT.format(
        language=language,
        topic=topic,
        words=round(seconds * WORDS_PER_SECOND),
        seconds=round(seconds),
        structure=" → ".join(dict.fromkeys(str(s) for s in structure)),
        narration=str(style.get("narration") or "calm, intimate, then rising")[:400],
    )
    if ask is None:
        from openjarvis.creator.llm import ask as gemini_ask
        from openjarvis.video_essay.style import models

        def ask(p: str, **kw: Any) -> str:
            return gemini_ask(p, models=models(), effort="high", max_tokens=16000, **kw)

    data = _check(ask(prompt, json_mode=True, check=_check))
    data["text"] = " ".join(b["text"] for b in data["beats"])
    data["title"] = data["title"] or topic[:60]
    return data


def from_text(text: str, title: str = "") -> Dict[str, Any]:
    """The owner's own script, as is."""
    clean = " ".join(text.split())
    return {
        "title": title or " ".join(clean.split()[:6]),
        "beats": [{"beat": "", "text": clean}],
        "text": clean,
    }


def chunks(text: str, limit: int = CHUNK) -> List[str]:
    """*text* in pieces of at most *limit* characters, cut after a sentence."""
    sentences = re.split(r"(?<=[.!?…])\s+", " ".join(text.split()))
    out: List[str] = []
    cur = ""
    for s in sentences:
        while len(s) > limit:  # a run-on sentence: cut at the last comma or space
            cut = max(s.rfind(", ", 0, limit), s.rfind(" ", 0, limit))
            cut = cut if cut > 0 else limit
            head, s = s[: cut + 1].strip(), s[cut + 1 :].strip()
            if cur:
                out.append(cur)
                cur = ""
            out.append(head)
        if cur and len(cur) + 1 + len(s) > limit:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return [c for c in out if c]


TONE_NOTES = {
    "calm": "tranquilo y seguro, sin prisa",
    "warm": "cálido y cercano, con una sonrisa",
    "curious": "intrigado, como quien comparte un secreto",
    "urgent": "con urgencia contenida, más rápido",
    "excited": "con energía y emoción, que contagie",
    "serious": "serio y grave, más lento",
    "whisper": "casi en susurro, íntimo",
    "ironic": "con ironía amable",
    "triumphant": "triunfal, firme, más lento al final",
}


def groups(beats: List[Dict[str, Any]], limit: int = CHUNK) -> List[Dict[str, Any]]:
    """Beats joined while they share a tone (fewer voice calls), each group
    with its tone and the silence after it."""
    out: List[Dict[str, Any]] = []
    for b in beats:
        text = " ".join(str(b.get("text") or "").split())
        if not text:
            continue
        d = b.get("delivery") or {}
        tone, pause = str(d.get("tone") or ""), float(d.get("pause") or 0)
        last = out[-1] if out else None
        if (
            last
            and last["tone"] == tone
            and last["pause"] < 0.25
            and len(last["text"]) + len(text) < limit
        ):
            last["text"] += " " + text
            last["pause"] = pause
        else:
            out.append({"text": text, "tone": tone, "pause": pause})
    return out


def narrate_beats(
    beats: List[Dict[str, Any]],
    *,
    speak: Optional[Callable[[str], bytes]] = None,
    breath: float = 0.22,
) -> bytes:
    """The narration performed: each part in its tone, with its pause after
    (real silence), three parts made at a time."""
    from concurrent.futures import ThreadPoolExecutor

    parts: List[Dict[str, Any]] = []
    for g in groups(beats):
        pieces = chunks(g["text"])
        for i, piece in enumerate(pieces):
            last = i == len(pieces) - 1
            parts.append(
                {"text": piece, "tone": g["tone"], "pause": g["pause"] if last else 0.0}
            )
    if not parts:
        raise ValueError("Nada que narrar.")
    voice = narrator() if speak is None else None

    def say(i: int) -> bytes:
        if speak is not None:
            return speak(parts[i]["text"])
        return voice(
            parts[i]["text"], parts[i - 1]["text"][-600:] if i else "", parts[i]["tone"]
        )

    with ThreadPoolExecutor(max_workers=min(3, len(parts))) as pool:
        made = list(pool.map(say, range(len(parts))))
    pieces_out: List[np.ndarray] = [np.zeros(int(0.15 * audio.SR), dtype=np.float32)]
    for part, wav in zip(parts, made):
        pieces_out.append(audio.read_wav(wav))
        gap = max(breath, part["pause"])
        pieces_out.append(np.zeros(int(gap * audio.SR), dtype=np.float32))
    return audio.write_wav(np.concatenate(pieces_out))


def narrator() -> Callable[..., bytes]:
    """The narrator's voice: (text, the piece before) -> WAV. Every voice
    there is a key for, best first; when one fails (no credit, no quota)
    the next reads the piece: ElevenLabs, Gemini, OpenAI."""
    voices: List[Callable[..., bytes]] = []
    if os.environ.get("ELEVENLABS_API_KEY", "").strip():
        voices.append(_eleven_narrator)
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        voices.append(lambda part, previous, tone="": _gemini_narrator(part, tone))
    if os.environ.get("OPENAI_API_KEY", "").strip():
        voices.append(lambda part, previous, tone="": _openai_narrator(part, tone))
    if not voices:  # no key at all: Gemini's error says what is missing
        voices.append(lambda part, previous, tone="": _gemini_narrator(part, tone))

    def speak(part: str, previous: str, tone: str = "") -> bytes:
        last: Optional[Exception] = None
        for voice in voices:
            try:
                return voice(part, previous, tone)
            except Exception as exc:  # noqa: BLE001 — the next voice
                last = exc
        raise RuntimeError(f"Ninguna voz pudo narrar: {last}")

    return speak


def _direction(tone: str) -> str:
    note = TONE_NOTES.get(tone, "")
    return (
        NARRATOR.replace(
            "Di exactamente esto:", f"En esta parte, {note}. Di exactamente esto:"
        )
        if note
        else NARRATOR
    )


def _eleven_narrator(part: str, previous: str, tone: str = "") -> bytes:
    from openjarvis.speech import elevenlabs_voice as eleven
    from openjarvis.speech.gemini_voice import pcm_to_wav

    raw = eleven.pcm(
        part, previous=previous, model_id=eleven.QUALITY_MODEL, timeout=180
    )
    return pcm_to_wav(raw, eleven.RATE)


def _gemini_narrator(part: str, tone: str = "") -> bytes:
    from openjarvis.speech import gemini_voice

    return gemini_voice.speak(
        part,
        gemini_voice.sergio_voice(""),
        style=_direction(tone),
        models=NARRATION_MODELS,
    )


OPENAI_TTS = ("gpt-4o-mini-tts", "onyx")  # a male voice made for synthesis


def _openai_narrator(part: str, tone: str = "") -> bytes:
    import httpx

    resp = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY'].strip()}"},
        json={"model": OPENAI_TTS[0], "voice": OPENAI_TTS[1], "input": part,
              "instructions": _direction(tone), "response_format": "wav"},
        timeout=180,
    )  # fmt: skip
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI TTS {resp.status_code}: {resp.text[:200]}")
    return resp.content


def narrate(
    text: str, *, speak: Optional[Callable[[str], bytes]] = None, breath: float = 0.28
) -> bytes:
    """WAV (48 kHz mono) of the whole narration in Sergio's voice."""
    from concurrent.futures import ThreadPoolExecutor

    parts = chunks(text)
    if not parts:
        raise ValueError("Nada que narrar.")
    if speak is None:
        voice = narrator()

        def say(i: int) -> bytes:
            return voice(parts[i], parts[i - 1][-600:] if i else "")
    else:

        def say(i: int) -> bytes:
            return speak(parts[i])

    with ThreadPoolExecutor(max_workers=min(3, len(parts))) as pool:
        made = list(pool.map(say, range(len(parts))))  # in order
    pieces: List[np.ndarray] = []
    gap = np.zeros(int(breath * audio.SR), dtype=np.float32)
    for wav in made:
        if pieces:
            pieces.append(gap)
        pieces.append(audio.read_wav(wav))
    lead = np.zeros(int(0.15 * audio.SR), dtype=np.float32)
    return audio.write_wav(np.concatenate([lead, *pieces, gap]))


def _norm(w: str) -> str:
    import unicodedata

    w = unicodedata.normalize("NFKD", w.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", w)


def align(script: List[str], heard: List[Word], total: float) -> List[Word]:
    """The script's words with the recogniser's times: matching words take
    the times heard, the rest are placed between their matched neighbours."""
    if not heard:
        return []
    a = [_norm(w) for w in script]
    b = [_norm(w.text) for w in heard]
    times: List[Optional[tuple]] = [None] * len(script)
    for block in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_matching_blocks():
        for k in range(block.size):
            h = heard[block.b + k]
            times[block.a + k] = (h.start, h.end)
    if not any(times):
        return []
    out: List[Word] = []
    i = 0
    while i < len(script):
        if times[i] is not None:
            s, e = times[i]  # type: ignore[misc]
            out.append(Word(script[i], round(s, 3), round(e, 3)))
            i += 1
            continue
        j = i
        while j < len(script) and times[j] is None:
            j += 1
        left = out[-1].end if out else 0.0
        right = times[j][0] if j < len(script) else min(total, heard[-1].end + 0.4)  # type: ignore[index]
        right = max(right, left + 0.08 * (j - i))
        weights = [len(_norm(w)) + 1.5 for w in script[i:j]]
        step = (right - left) / sum(weights)
        at = left
        for w, wt in zip(script[i:j], weights):
            out.append(Word(w, round(at, 3), round(at + wt * step, 3)))
            at += wt * step
        i = j
    return out


def recognise(wav: bytes, language: str = "es") -> List[Word]:
    """Word times from faster-whisper (empty when it is not available)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    size = os.environ.get("SERGIO_WHISPER_MODEL", "base")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav)
        path = f.name
    try:
        model = WhisperModel(size, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(
            path, language=language[:2], word_timestamps=True, vad_filter=False
        )
        return [
            Word(w.word.strip(), float(w.start), float(w.end))
            for seg in segments
            for w in seg.words or []
            if w.word.strip()
        ]
    except Exception:  # noqa: BLE001 — no model offline: the energy method
        return []
    finally:
        Path(path).unlink(missing_ok=True)


def timings(
    text: str,
    wav: bytes,
    *,
    language: str = "es",
    recogniser: Optional[Callable[[bytes, str], List[Word]]] = None,
) -> tuple:
    """(words with times, how they were found)."""
    samples = audio.read_wav(wav)
    total = len(samples) / audio.SR
    script_words = text.split()
    heard = (recogniser or recognise)(wav, language)
    if heard:
        words = align(script_words, heard, total)
        if words:
            return words, "reconocedor"
    spans = audio.voiced_spans(samples, audio.SR)
    return estimate_words(text, spans, total), "energía"


__all__ = ["align", "chunks", "from_text", "narrate", "recognise", "timings", "write"]
