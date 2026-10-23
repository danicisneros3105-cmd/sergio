"""The words of a video essay: the script, Sergio's narration and when each
word is said.

* :func:`write` — the strongest model writes the narration in the
  reference's structure (hook, problem, turn, story, contrast, payoff, call),
  at the pace Sergio's voice reads (about 1.9 words a second).
* :func:`narrate` — Sergio reads it in his own (male) voice. The voice
  takes at most 2500 characters at a time, so the text goes in pieces cut at
  the end of sentences, joined with a short breath.
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


def narrate(
    text: str, *, speak: Optional[Callable[[str], bytes]] = None, breath: float = 0.28
) -> bytes:
    """WAV (48 kHz mono) of the whole narration in Sergio's voice."""
    if speak is None:
        from openjarvis.speech import gemini_voice

        def speak(part: str) -> bytes:
            return gemini_voice.speak(part, gemini_voice.sergio_voice(""))

    pieces: List[np.ndarray] = []
    gap = np.zeros(int(breath * audio.SR), dtype=np.float32)
    for part in chunks(text):
        if pieces:
            pieces.append(gap)
        pieces.append(audio.read_wav(speak(part)))
    if not pieces:
        raise ValueError("Nada que narrar.")
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
