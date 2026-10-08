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


def run_blender_background(script: str, timeout: float = 300.0) -> str:
    """Run a bpy script in Blender without a window; returns its log."""
    folder = HOME / "blender"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"pro-{time.strftime('%Y%m%d-%H%M%S')}.py"
    path.write_text(script, encoding="utf-8")
    try:
        done = subprocess.run(
            [find_blender(), "-b", "--python", str(path)],
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return "Blender tardó demasiado (más de 5 minutos) y lo detuve."
    out = done.stdout.decode("utf-8", "replace") + done.stderr.decode("utf-8", "replace")
    return out[-24000:]  # room for every part's SERGIO_BBOX line (surgical edits)


def blender_score(log: str) -> float:
    """How good a Blender Pro build is, from its log: parts built minus
    failed steps (a build that never saved is worst)."""
    import re

    if "SERGIO_SAVED" not in log:
        return -1.0
    found = re.search(r"SERGIO_PARTS (\d+)", log) or re.search(r"SERGIO_SAVED .* (\d+)\s*$", log, re.M)
    meshes = int(found.group(1)) if found else 0
    errors = sum(1 for line in log.splitlines() if line.startswith("SERGIO_STEP_ERROR"))
    # Spatial sense counts too: a part in the air or out of its planned place
    # makes a worse build than one with every part where it belongs.
    misplaced = sum(1 for line in log.splitlines()
                    if line.startswith(("SERGIO_FLOATING", "SERGIO_BELOW_GROUND", "SERGIO_LAYOUT_OFF")))
    return max(meshes - 2 * errors - 0.5 * misplaced, 0) + 0.5


def worse_build(new: float, best: float) -> bool:
    """A rewrite that lost a quarter of the model (or stopped saving)."""
    return new < 0 <= best or new < best * 0.75


def build_rank(score: float, verdict: dict | None) -> float:
    """How good a build is, overall: what the vision check sees first (is it
    recognisably the object? 0-10, unknown counts as 5), then what Blender
    measured (parts built, failed steps, misplaced parts)."""
    if score < 0:
        return -1.0
    vision = float(verdict.get("score", 5)) if verdict else 5.0
    return vision * 10 + min(score, 30.0) / 3


_NOISE = ("SERGIO_BBOX ", "EGL Error", "Color management", "Read prefs", "Blender quit")


def review_log(log: str) -> str:
    """The log without the per-part boxes and Blender's noise: what the
    reviewer needs (errors, plan checks, sizes) fits in its budget."""
    return "\n".join(ln for ln in log.splitlines() if ln.strip() and not ln.startswith(_NOISE) and
                     "cycles " not in ln)


def vision_lines(verdict: dict | None) -> str:
    """The vision verdict as log lines for the next review round."""
    if not verdict:
        return ""
    head = (f"SERGIO_VISION score {verdict.get('score')}/10; a stranger would say it is: "
            f"«{verdict.get('looks_like', '')}»")
    if not verdict.get("is_it"):
        head += " — NOT recognisable as the request yet: fix the silhouette first"
    return "\n".join([head] + [f"SERGIO_VISION_FIX {p}" for p in verdict.get("problems", [])[:8]])


def vision_sentence(verdict: dict | None) -> str:
    """One honest clause for the user about the vision check."""
    if not verdict:
        return ""
    score, looks = verdict.get("score", 0), verdict.get("looks_like", "")
    if verdict.get("is_it") and score >= 7:
        return f"; la revisión visual le da {score:g}/10 y lo reconoce como «{looks}»"
    return f"; ojo: la revisión visual solo le da {score:g}/10 (le parece «{looks}»), aún puede mejorar"


def bboxes(log: str) -> dict[str, tuple[float, ...]]:
    """Each part's measured box: name -> (cx, cy, cz, sx, sy, sz) in cm."""
    out: dict[str, tuple[float, ...]] = {}
    for line in log.splitlines():
        if line.startswith("SERGIO_BBOX "):
            try:
                name, centre, size = line[len("SERGIO_BBOX "):].split(" | ")
                out[name.strip()] = tuple(float(v) for v in (*centre.split(), *size.split()))
            except ValueError:
                continue
    return out


def surgical_report(before: str, after: str, changed: list[str], tol_cm: float = 0.3) -> dict:
    """What an edit really touched: allowed parts (*changed*, by name or
    prefix) and collateral ones it should have left alone."""
    a, b = bboxes(before), bboxes(after)
    allowed = [c.lower() for c in changed if c]

    def ok(name: str) -> bool:
        low = name.lower()
        return any(low == c or low.startswith(c) or c.startswith(low.split("_")[0]) for c in allowed)

    moved = [n for n in a if n in b and max(abs(x - y) for x, y in zip(a[n], b[n])) > tol_cm]
    removed = [n for n in a if n not in b]
    added = [n for n in b if n not in a]
    return {
        "kept": sum(1 for n in a if n in b and n not in moved),
        "edited": [n for n in moved + removed + added if ok(n) or n in added],
        "moved": moved,
        "removed": removed,
        "added": added,
        "collateral": [n for n in moved + removed if not ok(n)],
    }


_version: list[str] = []


def blender_version() -> str:
    """The installed Blender's version ("4.2.1"), so scripts use its API."""
    if not _version:
        try:
            out = subprocess.run([find_blender(), "--version"], capture_output=True, text=True, timeout=40,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            found = re.search(r"Blender (\d+\.\d+(?:\.\d+)?)", out)
            _version.append(found.group(1) if found else "")
        except Exception:  # noqa: BLE001 — unknown version: the kit copes
            _version.append("")
    return _version[0]


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def find_image(hint: str = "", folders: list[Path] | None = None, max_age_h: float = 6.0) -> tuple[bytes, str]:
    """The image to model: a path in *hint*, else the image copied to the
    clipboard, else the newest image in Descargas / Escritorio / Imágenes.
    Returns (bytes, where it came from) or (b"", "")."""
    if hint:
        path = Path(hint.strip().strip('"'))
        if path.is_file() and path.suffix.lower() in IMAGE_EXT:
            return path.read_bytes(), path.name
    try:  # the clipboard (Windows): an image, or files copied in Explorer
        import io

        from PIL import ImageGrab

        clip = ImageGrab.grabclipboard()
        if isinstance(clip, list):
            for item in clip:
                if str(item).lower().endswith(IMAGE_EXT) and Path(item).is_file():
                    return Path(item).read_bytes(), f"copiada: {Path(item).name}"
        elif clip is not None:
            buf = io.BytesIO()
            clip.convert("RGB").save(buf, "PNG")
            return buf.getvalue(), "la imagen copiada"
    except Exception:  # noqa: BLE001 — no clipboard image
        pass
    home = Path.home()
    folders = folders or [home / "Downloads", home / "Descargas", home / "Desktop", home / "Escritorio",
                          home / "Pictures", home / "Imágenes", home / "OneDrive" / "Desktop"]
    newest: tuple[float, Path] | None = None
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.suffix.lower() in IMAGE_EXT and path.is_file():
                mtime = path.stat().st_mtime
                if newest is None or mtime > newest[0]:
                    newest = (mtime, path)
    if newest and time.time() - newest[0] < max_age_h * 3600:
        return newest[1].read_bytes(), f"la última de {newest[1].parent.name}: {newest[1].name}"
    return b"", ""


# The model's feature edges for its CAD drawing (same as the server's
# openjarvis.tools.cad.EDGES_SCRIPT; a test keeps them equal).
EDGES_SCRIPT = r'''
import bpy, bmesh, json, math
_out = {}
_deps = bpy.context.evaluated_depsgraph_get()
for _o in bpy.context.scene.objects:
    if _o.type != "MESH" or _o.get("sergio_cutter") or _o.hide_render:
        continue
    _bm = bmesh.new()
    _bm.from_object(_o, _deps)
    _bm.transform(_o.matrix_world)
    _edges = []
    for _e in _bm.edges:
        if len(_e.link_faces) != 2 or _e.calc_face_angle(0.0) > math.radians(25):
            _a, _b = _e.verts
            _edges.append([round(c, 5) for c in (*_a.co, *_b.co)])
    _bm.free()
    if _edges:
        _out[_o.name] = _edges[:20000]
print("SERGIO_EDGES " + json.dumps(_out))
'''


def blender_edges(blend: str) -> str:
    """Open *blend* in Blender (no window) and print its feature edges."""
    return run_blender_background(
        f"import bpy\nbpy.ops.wm.open_mainfile(filepath={blend!r})\n" + EDGES_SCRIPT, timeout=300
    )


def cad_folder() -> Path:
    folder = Path.home() / "Documents" / "Sergio" / "CAD"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def open_in_blender(blend: str) -> None:
    """Open a finished .blend project in Blender, for the user."""
    subprocess.Popen([find_blender(), blend])


__all__ = [
    "build_command",
    "find_clips",
    "make_video",
    "blender_score",
    "open_in_blender",
    "resolve",
    "run_blender",
    "run_blender_background",
    "worse_build",
]
