"""Video Pro on the laptop: contact sheets for the editor, and the render.

``contact_sheet`` gives Gemini a look at each clip (12 time-stamped frames).
``render_command`` turns the editor's plan into one ffmpeg command: each
moment trimmed and framed (9:16 or 16:9), soft cross fades between them,
short captions, the opening title, loudness normalised (-14 LUFS, what
YouTube uses), optional music kept under the voices, and the colour tagged
Rec.709.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any

from sergio_escritorio.media import FONT, SIZES, _escape, ffmpeg, find_clips, probe

FADE = 0.35  # seconds of cross fade between moments
# The output says what colour it is (Rec.709, the web and TV standard), so
# players and editors do not guess: an untagged H.264 is shown with
# different gamma on Windows, Mac and phones.
# HDR clips (iPhone HLG, PQ) mapped down to Rec.709 instead of being shown
# grey and flat: to linear light, tone-mapped, back to Rec.709 (needs the
# zscale filter; without it the clip is used as it is).
TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,"
)
HDR = re.compile(r"arib-std-b67|smpte2084|bt2020")
REC709 = ("-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv")


def contact_sheet(clip: Path, length: float, tiles: int = 12, exe: str = "") -> bytes:
    """A 4x3 grid of frames from *clip*, each stamped with its time (JPEG)."""
    step = max(length / tiles, 0.5)
    out = subprocess.run(
        [
            exe or ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(clip),
            "-vf",
            f"fps=1/{step:.3f},scale=320:-2,"
            f"drawtext=fontfile='{FONT}':text='%{{pts\\:hms}}':x=6:y=6:fontsize=20:"
            "fontcolor=yellow:box=1:boxcolor=black@0.6,tile=4x3",
            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-",
        ],
        capture_output=True,
        timeout=180,
        check=False,
    )
    return out.stdout


def is_hdr(clip: Path, exe: str = "") -> bool:
    info = subprocess.run([exe or ffmpeg(), "-hide_banner", "-i", str(clip)], capture_output=True,
                          text=True, check=False).stderr
    return bool(HDR.search(info))


def has_zscale(exe: str = "") -> bool:
    out = subprocess.run([exe or ffmpeg(), "-hide_banner", "-filters"], capture_output=True, text=True, check=False)
    return " zscale " in out.stdout


# Transitions into a moment: (xfade name, seconds). "cut" is a near-instant
# dissolve (one frame) so every boundary is one chain.
XFADE = {
    "cut": ("fade", 0.04),
    "flash": ("fadewhite", 0.22),
    "whip": ("slideleft", 0.18),
    "zoom": ("zoomin", 0.3),
    "fade": ("fade", FADE),
    "glitch": ("pixelize", 0.2),
}
POSITIONS = {"center": "(h-text_h)/2", "lower third": "h*0.72", "top": "h*0.14"}


def _hex(colour: str, default: str = "white") -> str:
    return "0x" + colour[1:] if re.fullmatch(r"#[0-9A-Fa-f]{6}", colour or "") else default


def grade_filter(grade: dict[str, Any]) -> str:
    """The learned colour look as ffmpeg filters ("" for none)."""
    if not grade:
        return ""
    contrast = min(max(float(grade.get("contrast", 1.0)), 0.7), 1.5)
    saturation = min(max(float(grade.get("saturation", 1.0)), 0.0), 1.8)
    brightness = min(max(float(grade.get("brightness", 0.0)), -0.2), 0.2)
    warmth = min(max(float(grade.get("warmth", 0.0)), -1.0), 1.0)
    out = [f"eq=contrast={contrast:.3f}:saturation={saturation:.3f}:brightness={brightness:.3f}"]
    if abs(warmth) > 0.02:
        w = warmth * 0.12
        out.append(f"colorbalance=rs={w:.3f}:bs={-w:.3f}:rm={w / 2:.3f}:bm={-w / 2:.3f}")
    if grade.get("vignette"):
        out.append("vignette=PI/5")
    if grade.get("grain"):
        out.append("noise=alls=7:allf=t")
    if grade.get("letterbox"):
        out.append("drawbox=y=0:w=iw:h=ih*0.09:color=black:t=fill,drawbox=y=ih*0.91:w=iw:h=ih*0.09:color=black:t=fill")
    return ",".join(out)


def caption_filter(caption: str, length: float, height: int, text: dict[str, Any] | None) -> str:
    """A caption: plain, or in the learned style (big, bold, word by word)."""
    text = text or {}
    words = caption.upper().split() if "caps" in str(text.get("style", "")).lower() else caption.split()
    size = int(height * (0.06 if text else 0.045))
    y = POSITIONS.get(str(text.get("position", "")).lower(), "h*0.78" if not text else "(h-text_h)/2")
    colour = _hex(str(text.get("color", "")))
    base = f"fontfile='{FONT}':fontcolor={colour}:fontsize={size}:borderw=6:bordercolor=black@0.75:x=(w-text_w)/2:y={y}"
    if not text.get("kinetic") or len(words) < 2:
        return f",drawtext={base}:text='{_escape(' '.join(words))}'"
    # Kinetic: words appear synced by syllable/character weight across the spoken span (zero lag).
    span = max(length * 0.92, 0.3)
    weights = [max(2, len(re.sub(r"\W", "", w)) + 2) for w in words]
    total_w = float(sum(weights))
    cursor = 0.0
    parts = []
    for i, wt in enumerate(weights):
        start = cursor
        cursor += span * (wt / total_w)
        stop = cursor if i < len(words) - 1 else length + 1
        shown = _escape(" ".join(words[: i + 1]))
        parts.append(f",drawtext={base}:text='{shown}':enable='between(t,{start:.2f},{stop:.2f})'")
    return "".join(parts)


def render_command(
    clips: list[Path],
    plan: dict[str, Any],
    out: Path,
    *,
    has_audio: list[bool],
    music: str = "",
    exe: str = "ffmpeg",
    hdr: list[bool] | None = None,
) -> list[str]:
    """The ffmpeg command for the editor's plan (pure, tested without ffmpeg).

    Each moment may carry its transition (cut, flash, whip, zoom, fade,
    glitch), a punch-in or slow push-in and a speed change; a learned style
    adds its colour look and its caption style."""
    width, height = SIZES.get(plan.get("aspect", "16:9"), SIZES["16:9"])
    segments = plan["segments"]
    style = plan.get("style") or {}
    cmd = [exe, "-y", "-hide_banner"]
    for clip in clips:
        cmd += ["-i", str(clip)]
    silence = len(clips)
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    music_index = None
    if music:
        music_index = len(clips) + 1
        cmd += ["-stream_loop", "-1", "-i", music]
    parts: list[str] = []
    lengths: list[float] = []
    for k, seg in enumerate(segments):
        i, start, end = seg["clip"], seg["start"], seg["end"]
        speed = min(max(float(seg.get("speed") or 1.0), 0.5), 2.0)
        length = (end - start) / speed
        lengths.append(length)
        video = (
            f"[{i}:v]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed:g},"
            + (TONEMAP if hdr and hdr[i] else "")
            + f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps=30,format=yuv420p,setsar=1"
        )
        zoom = seg.get("zoom") or "none"
        if zoom == "punch":  # a sudden 1.2x punch-in, centred
            video += f",scale={int(width * 1.2) // 2 * 2}:-2,crop={width}:{height}"
        elif zoom == "push":  # a slow push-in over the moment
            video += (
                f",zoompan=z='min(1+0.004*on,1.2)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":s={width}x{height}:fps=30"
            )
        if seg.get("caption"):
            video += caption_filter(seg["caption"], length, height, style.get("text"))
        parts.append(video + f"[v{k}]")
        src = f"{i}:a" if has_audio[i] else f"{silence}:a"
        a_start, a_end = (start, end) if has_audio[i] else (0, end - start)
        tempo = f",atempo={speed:g}" if abs(speed - 1.0) > 0.01 else ""
        parts.append(
            f"[{src}]atrim=start={a_start}:end={a_end},asetpts=PTS-STARTPTS{tempo},"
            f"aresample=48000,aformat=channel_layouts=stereo[a{k}]"
        )
    # Transitions, chained: [v0][v1]xfade -> [x1], [x1][v2]xfade -> [x2] ...
    vlast, alast, offset = "[v0]", "[a0]", 0.0
    for k in range(1, len(segments)):
        name, dur = XFADE.get(segments[k].get("transition") or "fade", XFADE["fade"])
        dur = min(dur, lengths[k - 1] / 2, lengths[k] / 2)
        offset += lengths[k - 1] - dur
        parts.append(f"{vlast}[v{k}]xfade=transition={name}:duration={round(dur, 3):g}:offset={offset:.3f}[x{k}]")
        parts.append(f"{alast}[a{k}]acrossfade=d={round(dur, 3):g}[y{k}]")
        vlast, alast = f"[x{k}]", f"[y{k}]"
    video_out = vlast
    look = grade_filter(style.get("grade") or {})
    if look:
        parts.append(f"{video_out}{look}[vg]")
        video_out = "[vg]"
    if plan.get("title_overlay"):
        parts.append(
            f"{video_out}drawtext=fontfile='{FONT}':text='{_escape(plan['title_overlay'])}':"
            f"fontcolor=white:fontsize={int(height * 0.06)}:borderw=5:bordercolor=black@0.6:"
            "x=(w-text_w)/2:y=h*0.12:enable='lt(t,3)'[vt]"
        )
        video_out = "[vt]"
    parts.append(f"{alast}loudnorm=I=-14:TP=-1.5:LRA=11[an]")
    audio_out = "[an]"
    if music_index is not None:
        # Music under the voices: ducked whenever someone speaks.
        parts.append(f"[{music_index}:a]volume=0.25[bg];[bg][an]sidechaincompress=threshold=0.05:ratio=8[duck]")
        parts.append("[an][duck]amix=inputs=2:duration=first:normalize=0[mix]")
        audio_out = "[mix]"
    cmd += ["-filter_complex", ";".join(parts), "-map", video_out, "-map", audio_out]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", *REC709,
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
    ]
    return cmd


def style_named(request: str) -> str:
    """The editing style named in the order ("... al estilo Dyson") or ""."""
    import unicodedata

    plain = "".join(c for c in unicodedata.normalize("NFKD", request.lower()) if not unicodedata.combining(c))
    found = re.search(r"\b(?:al|con el|en el)?\s*estilo\s+(?:de\s+|del\s+)?(?:canal\s+|anuncio\s+(?:de\s+)?)?(.+?)"
                      r"(?:\s+(?:para|con la carpeta|con los videos|de la carpeta|en)\b|[,.]|$)", plain)
    return found.group(1).strip() if found else ""


GROUP = 12  # clips the planner sees at once (one contact sheet each)
MAX_CLIPS = 400  # «casi sin límite si es solo editar» (owner, 2 Nov 2026)


def edit(
    source: str,
    request: str,
    planner: Any,
    *,
    music: str = "",
    clips: list[Path] | None = None,
) -> dict[str, Any]:
    """Clips in *source* (or the prepared *clips*) -> an edited video (+ its
    YouTube metadata file). More than :data:`GROUP` clips are edited a group
    at a time, in order, and the groups joined into one video."""
    clips = (clips or find_clips(source))[:MAX_CLIPS]
    out_dir = Path.home() / "Videos" / "Sergio"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"video-pro-{stamp}.mp4"
    exe = ffmpeg()
    if len(clips) <= GROUP:
        plan = _edit_group(clips, request, planner, music, out, exe)
    else:
        parts, plan = [], {}
        groups = [clips[i : i + GROUP] for i in range(0, len(clips), GROUP)]
        for n, group in enumerate(groups, 1):
            part = out_dir / f"video-pro-{stamp}-parte{n:02d}.mp4"
            note = f"{request}\n(Parte {n} de {len(groups)} de un video largo: sigue el mismo estilo.)"
            got = _edit_group(group, note, planner, music, part, exe)
            plan = plan or got
            parts.append(part)
        _join(parts, out, exe)
        for p in parts:
            p.unlink(missing_ok=True)
    yt = plan["youtube"]
    meta = out.with_suffix(".txt")
    meta.write_text(
        f"TÍTULO:\n{yt['title']}\n\nDESCRIPCIÓN:\n{yt['description']}\n\nETIQUETAS:\n{', '.join(yt['tags'])}\n",
        encoding="utf-8",
    )
    return {"path": str(out), "meta": str(meta), "plan": plan, "clips": len(clips)}


def _edit_group(
    clips: list[Path], request: str, planner: Any, music: str, out: Path, exe: str
) -> dict[str, Any]:
    probes = [probe(c) for c in clips]
    hdr = [is_hdr(c, exe) for c in clips]
    hdr = hdr if any(hdr) and has_zscale(exe) else None
    lengths = [d for _, d in probes]
    sheets = [contact_sheet(c, max(d, 1.0), exe=exe) for c, d in zip(clips, lengths)]
    plan = planner(request, sheets, lengths)
    cmd = render_command(clips, plan, out, has_audio=[a for a, _ in probes], music=music, exe=exe, hdr=hdr)
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if done.returncode != 0 or not out.exists():
        raise RuntimeError("ffmpeg falló: " + done.stderr[-500:])
    return plan


def _join(parts: list[Path], out: Path, exe: str) -> None:
    """The edited groups into one video (re-encoded once, so sizes and audio
    always match)."""
    listing = out.with_suffix(".partes.txt")
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    cmd = [
        exe, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
    ]  # fmt: skip
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    listing.unlink(missing_ok=True)
    if done.returncode != 0 or not out.exists():
        raise RuntimeError("ffmpeg no pudo unir las partes: " + done.stderr[-500:])


__all__ = ["contact_sheet", "edit", "render_command"]
