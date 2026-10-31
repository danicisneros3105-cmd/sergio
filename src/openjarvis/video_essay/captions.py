"""Captions that move, like good short videos (ASS, burned in by ffmpeg).

The owner (26 Oct 2026): «subtítulos cool y no simplones en una línea». The
quick videos used to show each whole sentence in a black box. Now the words
come two or three at a time, big, with a black outline that reads on any
picture; each chunk pops in, and the word being said lights up in the accent
colour (the «karaoke» look of the best short videos).

There are no word timestamps here, so the time of each word comes from its
length inside its sentence (long words take longer to say). ffmpeg draws it
with libass (``ass=`` filter); :func:`ass_document` is pure, for the tests.

27 Oct 2026, «diferentes tipografías en diferentes partes, como NextCore»:
with ``varied`` (the default) each chunk takes the face its words ask for
(:func:`openjarvis.video_essay.typo.face_for`): one or two punch words in
tall condensed capitals in the middle of the frame, numbers in the
technical face at the top, a quote or a feeling in the serif italic, the
rest in the house face at the bottom.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Sequence, Tuple

FONTS = Path(__file__).with_name("fonts")
FAMILY = "Inter Display"
WORDS_PER_CHUNK = 3
# ASS colours are &HAABBGGRR.
WHITE = "&H00FFFFFF"
ACCENT = "&H0000D7FF"  # warm yellow (#FFD700): the word being said
OUTLINE = "&H00000000"
SHADOW = "&H64000000"


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(word: str) -> str:
    return word.replace("\\", "").replace("{", "(").replace("}", ")")


def word_times(
    sentence: str, start: float, duration: float
) -> List[Tuple[str, float, float]]:
    """(word, start, end) for each word, by its share of the letters."""
    words = sentence.split()
    if not words or duration <= 0:
        return []
    weights = [len(re.sub(r"\W", "", w)) + 2 for w in words]
    total = sum(weights)
    out, t = [], start
    for word, weight in zip(words, weights):
        span = duration * weight / total
        out.append((word, t, t + span))
        t += span
    return out


def chunks(
    timed: Sequence[Tuple[str, float, float]], size: int = WORDS_PER_CHUNK
) -> List[List[Tuple[str, float, float]]]:
    """Two or three words that belong together: a chunk ends at punctuation."""
    out: List[List[Tuple[str, float, float]]] = [[]]
    for item in timed:
        out[-1].append(item)
        if len(out[-1]) >= size or item[0][-1:] in ",.;:!?…":
            out.append([])
    return [c for c in out if c]


def ass_document(
    sentences: Sequence[str],
    durations: Sequence[float],
    width: int,
    height: int,
    *,
    upper: bool = True,
    varied: bool = True,
    accent: str = ACCENT,
) -> str:
    """The whole video's captions, as an ASS script."""
    vertical = height > width
    size = max(28, int(min(width, height * 1.2) * (0.092 if vertical else 0.072)))
    # Vertical (Shorts, Reels, TikTok): above the app's buttons and captions.
    margin_v = int(height * (0.24 if vertical else 0.1))
    fields = (
        "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    side = int(width * 0.08)
    from openjarvis.video_essay import typo

    def style_line(name: str, family: str, fsize: int, italic: int) -> str:
        return ",".join(
            str(v)
            for v in (name, family, fsize, WHITE, accent, OUTLINE, SHADOW, 0 if italic else -1, italic,
                      0, 0, 100, 100, -1, 0, 1, max(3, fsize // 11), max(2, fsize // 18), 2, side, side, margin_v, 1)
        )  # fmt: skip

    styles = [style_line("Pop", FAMILY, size, 0)]
    names = {"base": "Pop"}
    if varied:
        for face in ("impacto", "elegante", "tecnica"):
            f = typo.FACES[face]
            names[face] = face.capitalize()
            styles.append(
                style_line(
                    names[face],
                    f.family,
                    int(size * f.scale),
                    -1 if face == "elegante" else 0,
                )
            )
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        f"[V4+ Styles]\nFormat: {fields}\n"
        + "".join(f"Style: {st}\n" for st in styles)
        + "\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines: List[str] = []
    t = 0.0
    prev = ""
    for sentence, duration in zip(sentences, durations):
        for chunk in chunks(word_times(sentence, t, duration)):
            start, end = chunk[0][1], chunk[-1][2]
            face = "base"
            if varied:
                face = typo.face_for(
                    " ".join(w for w, _s, _e in chunk), tuple(names), prev
                )
                if face == "impacto" and len(chunk) > 2:
                    face = "base"
            prev = face
            style = names.get(face, "Pop")
            # where it sits: punch words in the middle, numbers up top
            place = {"impacto": "{\\an5}", "tecnica": "{\\an8}"}.get(face, "")
            caps = (upper and face != "elegante") or face in ("impacto", "tecnica")
            # Every word is its own event slice so the lit word moves along.
            for i, (_w, w_start, w_end) in enumerate(chunk):
                parts = []
                for j, (word, _s, _e) in enumerate(chunk):
                    text = _escape(word.upper() if caps else word)
                    parts.append(
                        f"{{\\c{ACCENT}}}{text}{{\\c{WHITE}}}" if j == i else text
                    )
                pop = (
                    "{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" if i == 0 else ""
                )
                slice_end = end if i == len(chunk) - 1 else w_end
                when = f"{_ts(w_start if i else start)},{_ts(slice_end)}"
                lines.append(
                    f"Dialogue: 0,{when},{style},,0,0,0,,{place}{pop}{' '.join(parts)}"
                )
        t += duration
    return head + "\n".join(lines) + "\n"


def filter_for(ass_path: Path) -> str:
    """The ffmpeg video filter that burns *ass_path* in with Sergio's font."""

    def q(p: Path) -> str:  # ffmpeg filter quoting (Windows drive colons too)
        return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    return f"ass='{q(ass_path)}':fontsdir='{q(FONTS)}'"


__all__ = ["ass_document", "chunks", "filter_for", "word_times"]
