"""Creative work on Windows: edit videos with ffmpeg and build scenes in Blender.

* ``make_video`` cuts and joins the clips of a folder (or a file) into one
  video with a format (16:9, 9:16, 1:1), clip length, optional title and
  background music, then opens it so the user can review it.
* ``run_blender`` saves a Blender Python script written by Sergio and opens
  Blender running it, so the model appears ready to look at and tweak.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv"}
SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
FONT = r"C:\Windows\Fonts\segoeuib.ttf"
HOME = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SergioEscritorio"


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def user_folders(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    names = ("Videos", "Desktop", "Downloads", "Documents", "Pictures")
    roots = [home, home / "OneDrive"] + [
        Path(p) for p in glob.glob(str(home / "OneDrive*"))
    ]
    seen: list[Path] = []
    for root in roots:
        for folder in [root, *(root / n for n in names)] + [
            root / "Escritorio",
            root / "Descargas",
            root / "Documentos",
            root / "Vídeos",
        ]:
            if folder.is_dir() and folder not in seen:
                seen.append(folder)
    return seen


def resolve(source: str, home: Path | None = None) -> Path:
    """A path as said out loud ("la carpeta Viaje") -> a real path.

    Exact paths win; otherwise look for a folder/file with that name (case
    insensitive) in the usual places: Videos, Escritorio, Descargas, OneDrive…
    """
    raw = source.strip().strip('"').strip("'")
    path = Path(os.path.expandvars(os.path.expanduser(raw)))
    if path.exists() or any(ch in raw for ch in "*?"):
        return path
    wanted = raw.lower()
    for folder in user_folders(home):
        try:
            for child in folder.iterdir():
                if child.name.lower() == wanted or child.stem.lower() == wanted:
                    return child
        except OSError:
            continue
    for folder in user_folders(home):  # one level deeper, partial names
        try:
            for child in folder.iterdir():
                if child.is_dir() and wanted in child.name.lower():
                    return child
        except OSError:
            continue
    return path


def find_clips(source: str, home: Path | None = None) -> list[Path]:
    """Video files in a folder (sorted by name), a single file, or a glob."""
    path = resolve(source, home)
    if path.is_dir():
        clips = [p for p in sorted(path.iterdir()) if p.suffix.lower() in VIDEO_EXT]
    elif path.is_file():
        clips = [path]
    else:
        clips = [
            Path(p)
            for p in sorted(glob.glob(str(path)))
            if Path(p).suffix.lower() in VIDEO_EXT
        ]
    if not clips:
        raise ValueError(f"No encontré videos en {source!r}.")
    return clips[:40]


def probe(clip: Path) -> tuple[bool, float]:
    """(has an audio track, duration in seconds; 0 if unknown)."""
    info = subprocess.run(
        [ffmpeg(), "-hide_banner", "-i", str(clip)],
        capture_output=True,
        text=True,
        check=False,
    ).stderr
    found = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", info)
    seconds = (
        int(found[1]) * 3600 + int(found[2]) * 60 + float(found[3]) if found else 0.0
    )
    return "Audio:" in info, seconds


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")[:80]


def build_command(
    clips: list[Path],
    out: Path,
    *,
    aspect: str = "16:9",
    clip_seconds: float = 0,
    max_seconds: float = 0,
    title: str = "",
    music: str = "",
    audio: list[bool] | None = None,
    durations: list[float] | None = None,
    ffmpeg_exe: str = "ffmpeg",
) -> list[str]:
    """The ffmpeg command line (pure, so it can be tested without ffmpeg)."""
    width, height = SIZES.get(aspect, SIZES["16:9"])
    audio = audio if audio is not None else [True] * len(clips)
    durations = durations or [0.0] * len(clips)
    cmd = [ffmpeg_exe, "-y", "-hide_banner"]
    for clip in clips:
        if clip_seconds:
            cmd += ["-t", f"{clip_seconds:g}"]
        cmd += ["-i", str(clip)]
    silent_inputs = {}
    for i, has in enumerate(audio):
        if not has:
            silent_inputs[i] = len(clips) + len(silent_inputs)
            # Silence exactly as long as the clip's part, or concat stretches it.
            known = [x for x in (clip_seconds, durations[i]) if x]
            cmd += [
                "-f",
                "lavfi",
                "-t",
                f"{min(known) if known else 3600:g}",
                "-i",
                "anullsrc=r=48000:cl=stereo",
            ]
    music_index = None
    if music:
        music = str(resolve(music))
        music_index = len(clips) + len(silent_inputs)
        cmd += ["-stream_loop", "-1", "-i", music]

    parts = []
    for i in range(len(clips)):
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps=30,format=yuv420p,setsar=1[v{i}]"
        )
        src = f"{silent_inputs[i]}:a" if i in silent_inputs else f"{i}:a"
        parts.append(f"[{src}]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(clips)))
    parts.append(f"{joined}concat=n={len(clips)}:v=1:a=1[vcat][acat]")
    video = "[vcat]"
    if title:
        parts.append(
            f"[vcat]drawtext=fontfile='{FONT}':text='{_escape(title)}':fontcolor=white:"
            f"fontsize={int(height * 0.06)}:borderw=4:bordercolor=black@0.6:"
            "x=(w-text_w)/2:y=h*0.12:enable='lt(t,3.5)'[vtitle]"
        )
        video = "[vtitle]"
    sound = "[acat]"
    if music_index is not None:
        parts.append(
            f"[{music_index}:a]volume=0.22[bg];[acat][bg]amix=inputs=2:duration=first[amix]"
        )
        sound = "[amix]"
    cmd += ["-filter_complex", ";".join(parts), "-map", video, "-map", sound]
    if max_seconds:
        cmd += ["-t", f"{max_seconds:g}"]
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(out),
    ]
    return cmd


def make_video(
    source: str,
    *,
    aspect: str = "16:9",
    clip_seconds: float = 0,
    max_seconds: float = 0,
    title: str = "",
    music: str = "",
    name: str = "",
    open_when_done: bool = True,
) -> str:
    clips = find_clips(source)
    out_dir = Path.home() / "Videos" / "Sergio"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\- ]", "", name or "video").strip() or "video"
    out = out_dir / f"{safe}-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    exe = ffmpeg()
    probes = [probe(c) for c in clips]
    cmd = build_command(
        clips,
        out,
        aspect=aspect,
        clip_seconds=clip_seconds,
        max_seconds=max_seconds,
        title=title,
        music=music,
        audio=[a for a, _ in probes],
        durations=[d for _, d in probes],
        ffmpeg_exe=exe,
    )
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if done.returncode != 0 or not out.exists():
        raise RuntimeError("ffmpeg falló: " + done.stderr[-600:])
    if open_when_done and hasattr(os, "startfile"):
        os.startfile(str(out))  # type: ignore[attr-defined]  # open for review
    return str(out)


def find_blender() -> str:
    found = shutil.which("blender")
    if found:
        return found
    candidates = sorted(
        glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"),
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise RuntimeError(
        "No encontré Blender. Instálalo (winget install BlenderFoundation.Blender) "
        "y vuelve a pedírmelo."
    )


def run_blender(script: str) -> str:
    """Save Sergio's bpy script and open Blender running it."""
    folder = HOME / "blender"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"escena-{time.strftime('%Y%m%d-%H%M%S')}.py"
    path.write_text(script, encoding="utf-8")
    subprocess.Popen([find_blender(), "--python", str(path)])
    return str(path)


__all__ = ["build_command", "find_clips", "make_video", "resolve", "run_blender"]
