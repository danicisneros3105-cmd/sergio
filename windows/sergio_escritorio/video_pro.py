"""Video Pro on the laptop: contact sheets for the editor, and the render.

``contact_sheet`` gives Gemini a look at each clip (12 time-stamped frames).
``render_command`` turns the editor's plan into one ffmpeg command: each
moment trimmed and framed (9:16 or 16:9), soft cross fades between them,
short captions, the opening title, loudness normalised (-14 LUFS, what
YouTube uses) and optional music kept under the voices.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from sergio_escritorio.media import FONT, SIZES, _escape, ffmpeg, find_clips, probe

FADE = 0.35  # seconds of cross fade between moments


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


def render_command(
    clips: list[Path],
    plan: dict[str, Any],
    out: Path,
    *,
    has_audio: list[bool],
    music: str = "",
    exe: str = "ffmpeg",
) -> list[str]:
    """The ffmpeg command for the editor's plan (pure, tested without ffmpeg)."""
    width, height = SIZES.get(plan.get("aspect", "16:9"), SIZES["16:9"])
    segments = plan["segments"]
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
    for k, seg in enumerate(segments):
        i, start, end = seg["clip"], seg["start"], seg["end"]
        video = (
            f"[{i}:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps=30,format=yuv420p,setsar=1"
        )
        if seg.get("caption"):
            video += (
                f",drawtext=fontfile='{FONT}':text='{_escape(seg['caption'])}':fontcolor=white:"
                f"fontsize={int(height * 0.045)}:borderw=5:bordercolor=black@0.7:"
                "x=(w-text_w)/2:y=h*0.78"
            )
        parts.append(video + f"[v{k}]")
        src = f"{i}:a" if has_audio[i] else f"{silence}:a"
        parts.append(
            f"[{src}]atrim=start={start if has_audio[i] else 0}:end={end if has_audio[i] else end - start},"
            f"asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{k}]"
        )
    # Cross fades, chained: [v0][v1]xfade -> [x1], [x1][v2]xfade -> [x2] ...
    vlast, alast, offset = "[v0]", "[a0]", 0.0
    for k in range(1, len(segments)):
        prev = segments[k - 1]
        offset += (prev["end"] - prev["start"]) - FADE
        parts.append(f"{vlast}[v{k}]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[x{k}]")
        parts.append(f"{alast}[a{k}]acrossfade=d={FADE}[y{k}]")
        vlast, alast = f"[x{k}]", f"[y{k}]"
    video_out = vlast
    if plan.get("title_overlay"):
        parts.append(
            f"{vlast}drawtext=fontfile='{FONT}':text='{_escape(plan['title_overlay'])}':"
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
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
    ]
    return cmd


def edit(
    source: str,
    request: str,
    planner: Any,
    *,
    music: str = "",
) -> dict[str, Any]:
    """Clips in *source* -> an edited video (+ its YouTube metadata file)."""
    clips = find_clips(source)[:12]
    exe = ffmpeg()
    probes = [probe(c) for c in clips]
    lengths = [d for _, d in probes]
    sheets = [contact_sheet(c, max(d, 1.0), exe=exe) for c, d in zip(clips, lengths)]
    plan = planner(request, sheets, lengths)
    out_dir = Path.home() / "Videos" / "Sergio"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"video-pro-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    cmd = render_command(clips, plan, out, has_audio=[a for a, _ in probes], music=music, exe=exe)
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if done.returncode != 0 or not out.exists():
        raise RuntimeError("ffmpeg falló: " + done.stderr[-500:])
    yt = plan["youtube"]
    meta = out.with_suffix(".txt")
    meta.write_text(
        f"TÍTULO:\n{yt['title']}\n\nDESCRIPCIÓN:\n{yt['description']}\n\nETIQUETAS:\n{', '.join(yt['tags'])}\n",
        encoding="utf-8",
    )
    return {"path": str(out), "meta": str(meta), "plan": plan}


__all__ = ["contact_sheet", "edit", "render_command"]
