"""Editing the creator's own takes to the plan (``planear.py``).

The creator films each shot of the plan and uploads it; Sergio:

* cuts each take: a take to camera starts just before the first word and ends
  just after the last (the dead air at the head and tail goes, like a jump
  cut); a b-roll take gives its steadiest middle part of the planned length;
* frames it (cover-crop to 9:16 or 16:9) and moves it as planned (a slow push
  in or pull out), at 30 fps;
* a shot with no take yet is filled with its storyboard frame, and the result
  says which ones are missing;
* the words said become captions (2-3 words, the one said lit) and the plan's
  on-screen words are placed on top;
* the sound: the takes' own voice in front, music and the plan's effects on the
  cuts, through the studio master (stereo, ducking, -14 LUFS).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

FPS = 30
SFX_WORDS = {"whoosh": "whoosh", "swish": "whoosh", "hit": "impact", "golpe": "impact", "impact": "impact",
             "riser": "riser", "sube": "riser", "boom": "subdrop", "drop": "subdrop", "reverse": "reverse",
             "swell": "reverse", "glitch": "glitch", "shutter": "shutter", "foto": "shutter", "obturador": "shutter",
             "swipe": "swipe", "desliza": "swipe", "pop": "pop", "click": "click", "ding": "ding"}  # fmt: skip


SILENCE_WORDS = (
    "silencio",
    "silence",
    "sin musica",
    "sin música",
    "corte de musica",
    "music cut",
)
LIFT_WORDS = (
    "drop",
    "music up",
    "sube la musica",
    "sube la música",
    "musica arriba",
    "música arriba",
)


def music_cues(shots: List[Tuple[float, str]], total: float, sr: int) -> "Any":
    """The music's volume along the cut (``viral.MUSICA``): quiet under the
    hook, out on a shot marked «silencio» (the beat before the payoff), up on
    a «drop». *shots*: (seconds, its planned sound) in order. Gains are
    smoothed over 60 ms so nothing clicks."""
    import numpy as np

    gain = np.ones(int(total * sr) + 1, dtype=np.float32)
    at = 0.0
    for k, (secs, sound) in enumerate(shots):
        a, b = int(at * sr), int((at + secs) * sr)
        low = (sound or "").lower()
        if any(w in low for w in SILENCE_WORDS):
            gain[a:b] = 0.0
        elif any(w in low for w in LIFT_WORDS):
            gain[a:b] = 1.5
        elif (
            k == 0
            and len(shots) > 2
            and "music" not in low
            and "musica" not in low
            and "música" not in low
        ):
            gain[a:b] = 0.25  # the hook speaks first; the music enters after it
        at += secs
    w = max(1, int(0.06 * sr))
    return np.convolve(gain, np.ones(w, dtype=np.float32) / w, mode="same")[
        : int(total * sr)
    ]


def probe(path: Path, ffmpeg: str) -> Tuple[float, bool]:
    """(length in seconds, has sound) of a take."""
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    import re

    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    dur = (
        int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    )
    return dur, "Audio:" in r.stderr


def speech_span(path: Path, ffmpeg: str) -> Optional[Tuple[float, float]]:
    """Where the talking is in a take (first and last voiced moment)."""
    import numpy as np

    from openjarvis.video_essay import audio

    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(audio.SR), "-f", "f32le", "-"],
        capture_output=True, timeout=300,
    ).stdout  # fmt: skip
    x = np.frombuffer(raw, dtype=np.float32)
    if len(x) < audio.SR // 4:
        return None
    spans = audio.voiced_spans(x, audio.SR, floor=0.18)
    if not spans:
        return None
    return spans[0][0], spans[-1][1]


def cut_window(
    kind: str, planned: float, length: float, speech: Optional[Tuple[float, float]]
) -> Tuple[float, float]:
    """(start, seconds) of the take that goes into the edit."""
    if kind == "cara" and speech:
        start = max(0.0, speech[0] - 0.12)
        end = min(length, speech[1] + 0.25)
        return start, max(0.5, end - start)
    secs = min(planned, length) if length else planned
    return max(0.0, (length - secs) / 2), secs


def _move(mv: str, frames: int) -> str:
    mv = (mv or "").lower()
    if "push" in mv or "acerc" in mv or "zoom in" in mv:
        return f"zoompan=z='1+0.08*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1"
    if "pull" in mv or "alej" in mv or "zoom out" in mv:
        return f"zoompan=z='1.08-0.08*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1"
    return ""


FONTS = Path(__file__).parent / "fonts"


def _label(text: str, h: int) -> str:
    """The plan's on-screen words (max 5) over a real take: big, high, with a
    soft shadow, in the punch face (``typo``: «impacto»)."""
    t = (text or "").strip().upper()[:40]
    if not t:
        return ""
    t = t.replace("\\", "").replace("'", "’")  # inside '…' nothing else is special
    font = (FONTS / "Anton-Regular.ttf").as_posix()
    size = max(28, int(h * (0.075 if len(t) <= 6 else 0.05)))
    return (f"drawtext=fontfile='{font}':text='{t}':expansion=none:fontsize={size}:fontcolor=white:"
            f"shadowcolor=black@0.55:shadowx=0:shadowy={max(2, size // 14)}:x=(w-tw)/2:y=h*0.14")  # fmt: skip


def segment(src: Path, out: Path, *, start: float, seconds: float, size: Tuple[int, int], move: str,
            ffmpeg: str, still: bool = False, label: str = "") -> Path:  # fmt: skip
    w, h = size
    frames = max(2, int(round(seconds * FPS)))
    vf = [
        f"scale={w}:{h}:force_original_aspect_ratio=increase",
        f"crop={w}:{h}",
        f"fps={FPS}",
    ]
    zp = _move(move, frames)
    if zp:
        vf.append(zp + f":s={w}x{h}:fps={FPS}")
    drawn = _label(label, h) if not still else ""
    if drawn:
        vf.append(drawn)
    vf.append("format=yuv420p")
    cmd = [ffmpeg, "-y", "-v", "error"]
    if still:
        cmd += ["-loop", "1", "-t", f"{seconds:.3f}", "-i", str(src), "-f", "lavfi", "-t", f"{seconds:.3f}",
                "-i", "anullsrc=r=48000:cl=stereo"]  # fmt: skip
    else:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(src)]
    cmd += [
        "-vf",
        ",".join(vf),
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
    ]
    if still:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    except subprocess.CalledProcessError:
        if not drawn:
            raise
        # an ffmpeg without drawtext: the take without its words, never no take
        i = cmd.index(",".join(vf))
        cmd[i] = ",".join(x for x in vf if x != drawn)
        subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    return out


def edit(
    pid: str,
    *,
    ffmpeg: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """The edit of a plan with the takes uploaded so far."""
    from openjarvis.creator import studio
    from openjarvis.video_essay import audio, captions, mezcla, planear

    if ffmpeg is None:
        from openjarvis.video_essay import render

        ffmpeg = render.ffmpeg()
    plan = planear.load(pid)
    base = planear.folder(pid)
    work = base / "montaje"
    work.mkdir(parents=True, exist_ok=True)
    size = (1080, 1920) if plan.get("vertical", True) else (1920, 1080)
    pieces, missing, said, lengths, fx = [], [], [], [], []
    at = 0.0
    for shot in plan["tomas"]:
        take = base / "tomas" / shot["archivo"] if shot.get("archivo") else None
        piece = work / f"{shot['n']:02d}.mp4"
        if take is not None and take.is_file():
            length, has_audio = probe(take, ffmpeg)
            span = (
                speech_span(take, ffmpeg)
                if has_audio and shot["tipo"] == "cara"
                else None
            )
            start, secs = cut_window(shot["tipo"], shot["segundos"], length, span)
            if not has_audio:  # a silent take: silence under it so the joins line up
                tmp = work / f"{shot['n']:02d}-a.mp4"
                subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(take), "-f", "lavfi", "-i",
                                "anullsrc=r=48000:cl=stereo", "-shortest", "-c:v", "copy", "-c:a", "aac", str(tmp)],
                               check=True, capture_output=True, timeout=600)  # fmt: skip
                take = tmp
            segment(
                take,
                piece,
                start=start,
                seconds=secs,
                size=size,
                move=shot.get("movimiento", ""),
                ffmpeg=ffmpeg,
                label=shot.get("texto", ""),
            )
        else:
            missing.append(shot["n"])
            frame = base / "cuadros" / (shot.get("cuadro") or "")
            if not frame.is_file():
                planear.draw_frame(shot, size).save(work / f"{shot['n']:02d}.png")
                frame = work / f"{shot['n']:02d}.png"
            secs = shot["segundos"]
            segment(frame, piece, start=0, seconds=secs, size=size, move=shot.get("movimiento", ""), ffmpeg=ffmpeg,
                    still=True)  # fmt: skip
        pieces.append(piece)
        said.append(shot.get("dice") or "")
        lengths.append(secs)
        sound = next(
            (
                v
                for k, v in SFX_WORDS.items()
                if k in (shot.get("sonido") or "").lower()
            ),
            "",
        )
        if sound and at > 0:
            fx.append((at, sound))
        at += secs
        if progress:
            progress(f"toma {shot['n']} de {len(plan['tomas'])}")
    listing = work / "lista.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in pieces), "utf-8")
    joined = work / "unido.mp4"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                    str(joined)], check=True, capture_output=True, timeout=900)  # fmt: skip
    total = sum(lengths)
    # captions of what is said, and the plan's words on screen
    ass = work / "subtitulos.ass"
    ass.write_text(captions.ass_document(said, lengths, size[0], size[1]), "utf-8")
    picture = work / "imagen.mp4"
    try:
        subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(joined), "-vf", captions.filter_for(ass), "-an",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "17", str(picture)],
                       check=True, capture_output=True, timeout=1800)  # fmt: skip
    except (
        subprocess.CalledProcessError
    ):  # an ffmpeg without libass: no captions, said so
        subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(joined), "-an", "-c:v", "copy", str(picture)],
                       check=True, capture_output=True, timeout=600)  # fmt: skip
        plan.setdefault("avisos", []).append(
            "Este ffmpeg no tiene libass: el video va sin subtítulos."
        )
    # the sound: the takes' voice, music, effects, mastered
    voice = work / "voz.wav"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(joined), "-vn", "-ac", "1", "-ar", "48000", str(voice)],
                   check=True, capture_output=True, timeout=600)  # fmt: skip
    bed = work / "musica.wav"
    music = audio.music_bed(total)
    cues = music_cues(
        [(sec, sh.get("sonido") or "") for sec, sh in zip(lengths, plan["tomas"])],
        total,
        audio.SR,
    )
    n = min(len(music), len(cues))
    shaped = music[:n] * cues[:n]
    peak = float(abs(shaped).max()) if n else 0.0
    bed.write_bytes(
        audio.write_wav(shaped * (0.98 / peak if peak > 0.98 else 1.0))
    )  # never clipped
    fx_file = work / "efectos.wav"
    fx_file.write_bytes(
        audio.write_wav(
            audio.effects_stereo(audio.thin(fx, total, gap=0.9, per_minute=28), total)
        )
    )
    mix = work / "mezcla.wav"
    sound = mezcla.master(
        mix,
        voice=voice,
        music=bed,
        fx=fx_file if fx else None,
        total=total,
        ffmpeg=ffmpeg,
    )
    name = studio.media_name("video", ".mp4")
    final = studio.projects_root() / "videos" / name
    final.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(picture), "-i", str(mix), "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "256k", "-shortest", "-movflags", "+faststart", str(final)],
                   check=True, capture_output=True, timeout=900)  # fmt: skip
    plan["montaje"] = {"url": f"/v1/creator/media/{name}", "faltan": missing, "sonido": sound,
                       "segundos": round(total, 1), "cuando": time.time()}  # fmt: skip
    planear.save(pid, plan)
    return plan["montaje"]


def status_line(m: Dict[str, Any]) -> str:
    if not m:
        return "Todavía no hay montaje."
    miss = m.get("faltan") or []
    extra = (
        f" Faltan las tomas {', '.join(map(str, miss))} (puse su cuadro del storyboard)."
        if miss
        else ""
    )
    return (
        f"Montaje listo: {m['segundos']} s, sonido a {m['sonido']['lufs']} LUFS.{extra}"
    )


__all__ = [
    "cut_window",
    "edit",
    "music_cues",
    "probe",
    "segment",
    "speech_span",
    "status_line",
]
