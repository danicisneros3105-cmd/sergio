"""Only one job: the best moments of a long video, cut as shorts.

The owner (4 Nov 2026): «mejora las herramientas de creadores de contenido un
2x». A creator with a podcast, a stream or a long video wants the 20-60 s
pieces that stand on their own. This finds them **by measuring the words**,
not by guessing:

1. The audio is transcribed with word times (faster-whisper on this computer;
   or the person's own .srt).
2. Every window that starts at the start of a sentence and ends at the end of
   one, between ``min_s`` and ``max_s`` seconds, is a candidate.
3. Each is scored with plain rules: does the first sentence work as a hook
   (the same rules as the scripts, :mod:`video_essay.partes`), how much of it
   is concrete (numbers, names, quotes), does it open a question and close it,
   is the pace right for a short (2-3.5 words a second), how many filler
   words («eh», «o sea», «um»). Each moment says why it scored what it scored.
4. The best ones that do not overlap are kept; ``cortar`` cuts them, reframes
   them to 9:16 following what moves, and burns the captions in.

Nothing is posted. The clips are the person's own video.
"""

from __future__ import annotations

import math
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

FILLERS = ("eh", "em", "este", "o sea", "pues", "bueno", "um", "uh", "like", "you know",
           "basicamente", "básicamente", "digamos")  # fmt: skip
GAP_S = 0.7  # a pause this long ends a sentence even without punctuation
PACE = (2.0, 3.6)  # words per second that feel right in a short


@dataclass
class W:
    text: str
    start: float
    end: float


@dataclass
class Moment:
    start: float
    end: float
    text: str
    hook: str
    score: int
    reasons: List[str] = field(default_factory=list)

    @property
    def seconds(self) -> float:
        return round(self.end - self.start, 1)


def _words(words: Iterable[Any]) -> List[W]:
    out = []
    for w in words:
        if isinstance(w, W):
            out.append(w)
        elif isinstance(w, dict):
            out.append(W(str(w.get("text", "")), float(w["start"]), float(w["end"])))
        else:
            out.append(W(str(w.text), float(w.start), float(w.end)))
    out = [w for w in out if w.text.strip()]
    if any(
        not math.isfinite(w.start)
        or not math.isfinite(w.end)
        or w.start < 0
        or w.end <= w.start
        for w in out
    ):
        raise ValueError("La transcripción contiene tiempos inválidos.")
    if any(b.start < a.start for a, b in zip(out, out[1:])):
        raise ValueError("Las palabras deben estar ordenadas por tiempo.")
    return out


def sentences(words: Iterable[Any]) -> List[List[W]]:
    """Words grouped in sentences (punctuation or a pause ends one)."""
    ws = _words(words)
    out: List[List[W]] = [[]]
    for i, w in enumerate(ws):
        out[-1].append(w)
        gap = ws[i + 1].start - w.end if i + 1 < len(ws) else 0
        if w.text.rstrip()[-1:] in ".!?…" or gap >= GAP_S:
            out.append([])
    return [s for s in out if s]


def _say(sentence: Sequence[W]) -> str:
    return " ".join(w.text.strip() for w in sentence)


def judge(group: Sequence[Sequence[W]]) -> tuple[int, List[str]]:
    """0-100 and the reasons, for a run of sentences."""
    from openjarvis.video_essay import partes

    text = " ".join(_say(s) for s in group)
    first = _say(group[0])
    low = f" {text.lower()} "
    reasons: List[str] = []
    score = 50
    hook = partes.hook_problems(first)
    if not hook:
        score += 18
        reasons.append("empieza con un gancho")
        if re.search(r"\d", first):  # a figure in the first line holds people best
            score += 6
            reasons.append("abre con una cifra")
    else:
        score -= 6 * len(hook)
    concrete = sum(1 for s in group if partes.concrete(_say(s))) / len(group)
    score += round(20 * concrete)
    if concrete >= 0.5:
        reasons.append("datos concretos")
    if "?" in text or any(w in low for w in partes.LOOP_WORDS):
        score += 8
        reasons.append("abre una duda")
    seconds = max(0.1, group[-1][-1].end - group[0][0].start)
    pace = sum(len(s) for s in group) / seconds
    if PACE[0] <= pace <= PACE[1]:
        score += 6
        reasons.append("buen ritmo")
    elif pace < PACE[0] - 0.5:
        score -= 8
        reasons.append("muy lento")
    fillers = sum(low.count(f" {f} ") for f in FILLERS)
    if fillers:
        score -= min(15, 3 * fillers)
        reasons.append(f"{fillers} muletillas")
    if partes.STOCK and any(p in low for p in partes.STOCK):
        score -= 6
    if group[-1] and _say(group[-1]).rstrip()[-1:] in ".!?…":
        score += 4
        reasons.append("cierra la idea")
    return max(0, min(100, score)), reasons


def moments(
    words: Iterable[Any], *, min_s: float = 20, max_s: float = 60, n: int = 5
) -> List[Moment]:
    """The *n* best moments that do not overlap, best first."""
    if (
        not math.isfinite(min_s)
        or not math.isfinite(max_s)
        or not 0 < min_s <= max_s <= 300
    ):
        raise ValueError("Use una duración válida entre 0 y 300 segundos.")
    if not 0 <= n <= 20:
        raise ValueError("Pida entre 0 y 20 recortes.")
    if n == 0:
        return []
    sents = sentences(words)
    cands: List[Moment] = []
    for i in range(len(sents)):
        for j in range(i, len(sents)):
            start, end = sents[i][0].start, sents[j][-1].end
            if end - start > max_s:
                break
            if end - start < min_s:
                continue
            group = sents[i : j + 1]
            score, reasons = judge(group)
            padding = min(0.4, max(0, max_s - (end - start)))
            lead = min(start, padding * 0.375)
            cands.append(Moment(
                round(start - lead, 3), round(end + padding - lead, 3),
                " ".join(_say(s) for s in group), _say(group[0]), score, reasons,
            ))  # fmt: skip
    cands.sort(key=lambda m: (-m.score, m.start))
    kept: List[Moment] = []
    for m in cands:
        if all(m.end <= k.start or m.start >= k.end for k in kept):
            kept.append(m)
            if len(kept) >= n:
                break
    return kept


def from_srt(text: str) -> List[W]:
    """Words with times from a .srt (each cue's words spread over it)."""
    out: List[W] = []
    stamp = r"(\d+):(\d+):(\d+)[,.](\d+)"
    for block in re.split(r"\n\s*\n", text or ""):
        m = re.search(stamp + r"\s*-->\s*" + stamp, block)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 10 ** len(m.groups()[3])
        b = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 10 ** len(m.groups()[7])
        if b <= a:
            continue
        body = " ".join(re.sub(r"<[^>]+>|\{[^}]+\}", "", block[m.end() :]).split())
        tokens = body.split()
        for k, tok in enumerate(tokens):
            span = (b - a) / max(1, len(tokens))
            out.append(W(tok, a + k * span, a + (k + 1) * span))
    return out


def _ffmpeg() -> str:
    from openjarvis.video_essay import render

    return render.ffmpeg()


def transcribe(video: Path, language: str = "es") -> List[W]:
    """Word times of *video*'s audio (a .srt next to it wins)."""
    srt = video.with_suffix(".srt")
    if srt.is_file():
        return from_srt(srt.read_text("utf-8", errors="replace"))
    from openjarvis.video_essay import script

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        subprocess.run(
            [_ffmpeg(), "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
             "-ar", "16000", str(wav)],
            check=True, timeout=1800,
        )  # fmt: skip
        return _words(script.recognise(wav.read_bytes(), language))


def find(path: str, *, n: int = 5, min_s: float = 20, max_s: float = 60,
         language: str = "es") -> Dict[str, Any]:  # fmt: skip
    video = Path(path).expanduser()
    if not video.is_file():
        raise FileNotFoundError(f"No encuentro el video: {path}")
    words = transcribe(video, language)
    if not words:
        raise RuntimeError(
            "No pude transcribir el audio (falta faster-whisper en este equipo). "
            "Ponga un .srt con el mismo nombre al lado del video y vuelva a pedirlo."
        )
    found = moments(words, min_s=min_s, max_s=max_s, n=n)
    return {"video": str(video), "palabras": len(words), "momentos": [
        {"n": i + 1, "desde": m.start, "hasta": m.end, "segundos": m.seconds,
         "gancho": m.hook[:140], "puntos": m.score, "por_que": m.reasons}
        for i, m in enumerate(found)
    ]}  # fmt: skip


def _captions(
    words: List[W], start: float, end: float, w: int, h: int, folder: Path
) -> Optional[Path]:
    from openjarvis.video_essay import captions

    inside = [x for x in words if x.start >= start and x.end <= end + 0.3]
    groups = sentences(inside)
    if not groups:
        return None
    lines = [_say(g) for g in groups]
    starts = [g[0].start - start for g in groups] + [end - start]
    lead = max(0.0, starts[0])
    durations = [max(0.3, starts[k + 1] - starts[k]) for k in range(len(lines))]
    if lead > 0.05:  # silence before the first words
        lines, durations = [" "] + lines, [lead] + durations
    path = folder / "subs.ass"
    path.write_text(captions.ass_document(lines, durations, w, h), "utf-8")
    return path


def cut(path: str, picks: Sequence[Dict[str, Any]], *, aspect: str = "9:16",
        subtitles: bool = True, language: str = "es") -> List[str]:  # fmt: skip
    """The chosen moments as separate files next to the video."""
    import shutil

    from openjarvis.video_essay import captions as _c  # noqa: F401 — fonts present
    from openjarvis.video_essay import pro

    video = Path(path).expanduser()
    if not video.is_file():
        raise FileNotFoundError(f"No encuentro el video: {path}")
    validated = []
    if not 1 <= len(picks) <= 20:
        raise ValueError("Elija entre 1 y 20 recortes.")
    if aspect not in ("9:16", "16:9", "1:1"):
        raise ValueError("Formato no compatible.")
    for m in picks:
        a, b = float(m["desde"]), float(m["hasta"])
        if (
            not math.isfinite(a)
            or not math.isfinite(b)
            or a < 0
            or not a < b
            or b - a > 300
        ):
            raise ValueError("El recorte tiene tiempos inválidos.")
        validated.append((a, b))
    ff = _ffmpeg()
    probe = shutil.which("ffprobe") or "ffprobe"
    words = transcribe(video, language) if subtitles else []
    if subtitles and not words:
        raise RuntimeError("No hay palabras con tiempos para crear los subtítulos.")
    out_dir = video.with_name(video.stem + "-recortes")
    out_dir.mkdir(exist_ok=True)
    made: List[str] = []
    for k, (a, b) in enumerate(validated, 1):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.mp4"
            subprocess.run(
                [ff, "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", str(video), "-t", f"{b-a:.3f}",
                 "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
                 str(raw)],
                check=True, timeout=1800,
            )  # fmt: skip
            framed = (
                pro.reframe(raw, aspect, ff, probe, Path(tmp) / "framed.mp4") or raw
            )
            final = out_dir / f"recorte-{k:02d}.mp4"
            suffix = 2
            while final.exists():
                final = out_dir / f"recorte-{k:02d}-{suffix}.mp4"
                suffix += 1
            info = pro._probe(framed, probe)
            ass = (
                _captions(words, a, b, info["w"], info["h"], Path(tmp))
                if words
                else None
            )
            if ass is not None:
                from openjarvis.video_essay import captions

                done = subprocess.run(
                    [ff, "-y", "-v", "error", "-i", str(framed), "-vf", captions.filter_for(ass),
                     "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "copy",
                     "-movflags", "+faststart", str(final)],
                    timeout=1800,
                )  # fmt: skip
                if done.returncode != 0:
                    final.unlink(missing_ok=True)
                    raise RuntimeError(
                        "No pude incrustar los subtítulos; no entregué un recorte sin ellos."
                    )
            else:
                shutil.copyfile(framed, final)
            check = pro._probe(final, probe)
            aw, ah = (int(x) for x in aspect.split(":"))
            if (
                check["w"] <= 0
                or check["h"] <= 0
                or check["dur"] <= 0
                or abs(check["w"] / max(1, check["h"]) - aw / ah) > 0.02
                or abs(check["dur"] - (b - a)) > max(0.2, (b - a) * 0.05)
            ):
                final.unlink(missing_ok=True)
                raise RuntimeError("No pude verificar el video exportado.")
        made.append(str(final))
    return made


def texto(result: Dict[str, Any]) -> str:
    rows = result.get("momentos") or []
    if not rows:
        return "No encontré momentos de 20-60 s que se sostengan solos en ese video."
    lines = [
        f"Los {len(rows)} mejores momentos de {Path(result['video']).name} (de {result['palabras']} palabras):"
    ]
    for m in rows:
        why = ", ".join(m["por_que"]) or "sin señales claras"
        lines.append(
            f"{m['n']}. {_clock(m['desde'])}-{_clock(m['hasta'])} ({m['segundos']} s), {m['puntos']}/100: "
            f"«{m['gancho']}» ({why})"
        )
    lines.append(
        "Diga cuáles corto (o «todos»): salen en 9:16 con subtítulos, junto al video."
    )
    return "\n".join(lines)


def _clock(s: float) -> str:
    s = int(s)
    return (
        f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
        if s >= 3600
        else f"{s // 60}:{s % 60:02d}"
    )


__all__ = [
    "Moment",
    "cut",
    "find",
    "from_srt",
    "judge",
    "moments",
    "sentences",
    "texto",
    "transcribe",
]
