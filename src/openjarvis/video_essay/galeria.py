"""Safe local and uploaded video selection for Sergio edits."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Iterable

EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_CLIPS = 20
MAX_BATCH_BYTES = 512 * 1024 * 1024


def home() -> Path:
    from openjarvis.core.config import get_config_dir

    return Path(get_config_dir()) / "videos-galeria"


def batch_path(batch: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", batch or ""):
        raise ValueError("Identificador de clips no valido.")
    return home() / batch


def _allowed_roots() -> list[Path]:
    roots = [Path.home() / "Videos", Path.home() / "Downloads", home()]
    configured = os.environ.get("SERGIO_VIDEO_FOLDERS", "")
    roots.extend(Path(item).expanduser() for item in configured.split(os.pathsep) if item.strip())
    result = []
    for item in roots:
        try:
            resolved = item.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_dir() and resolved not in result:
            result.append(resolved)
    return result


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _walk(root: Path) -> Iterable[Path]:
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not name.startswith(".") and not (Path(current) / name).is_symlink()]
        for name in names:
            path = Path(current) / name
            if path.suffix.lower() in EXTENSIONS and not path.is_symlink() and path.is_file():
                yield path


def recent_local_clips(n: int, folder: str | Path | None = None) -> list[Path]:
    """Return the newest N videos from approved local folders, newest first.

    Extra roots must be explicitly configured in SERGIO_VIDEO_FOLDERS. This
    prevents a request from turning the local editor into a general file reader.
    """
    try:
        count = int(n)
    except (TypeError, ValueError):
        raise ValueError("Indica entre 1 y 20 clips.") from None
    if not 1 <= count <= MAX_CLIPS:
        raise ValueError("Indica entre 1 y 20 clips.")

    roots = _allowed_roots()
    if folder is not None:
        candidate = Path(folder).expanduser()
        try:
            candidate = candidate.resolve(strict=True)
        except OSError:
            raise ValueError("No encuentro esa carpeta de videos.") from None
        if not candidate.is_dir() or not any(_inside(candidate, root) for root in roots):
            raise ValueError("La carpeta debe estar dentro de Videos, Downloads o una carpeta permitida.")
        roots = [candidate]

    found: list[tuple[float, Path]] = []
    for root in roots:
        for path in _walk(root):
            try:
                found.append((path.stat().st_mtime, path))
            except OSError:
                continue
    found.sort(key=lambda row: (row[0], row[1].name.lower()), reverse=True)
    chosen = [path for _, path in found[:count]]
    if not chosen:
        raise ValueError("No encontre videos compatibles en las carpetas permitidas.")
    if sum(path.stat().st_size for path in chosen) > MAX_BATCH_BYTES:
        raise ValueError("Los clips mas recientes superan el limite de 512 MB; indica una carpeta o menos clips.")
    return chosen



def store(files: list[Path]) -> str:
    """Copy explicit local selections into a server-issued gallery batch."""
    if not 1 <= len(files) <= MAX_CLIPS:
        raise ValueError("Selecciona entre uno y veinte videos.")
    paths = [Path(item) for item in files]
    if any(path.is_symlink() or not path.is_file() or path.suffix.lower() not in EXTENSIONS for path in paths):
        raise ValueError("Uno de los archivos no es un video compatible.")
    if sum(path.stat().st_size for path in paths) > MAX_BATCH_BYTES:
        raise ValueError("El lote supera el limite de 512 MB.")
    batch = uuid.uuid4().hex
    folder = batch_path(batch)
    folder.mkdir(parents=True, exist_ok=False)
    try:
        for index, path in enumerate(paths, 1):
            target = folder / f"{index:02d}{path.suffix.lower()}"
            shutil.copyfile(path, target)
        (folder / "completo").touch()
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return batch


def extract_clips_voice(files: list[Path], out: Path, ffmpeg: str) -> bytes:
    """Extract and concatenate audible tracks in the selected clip order."""
    from openjarvis.video_essay import montaje

    if not files:
        raise ValueError("No hay clips de los que extraer voz.")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sergio-voice-", dir=out.parent) as temp:
        folder = Path(temp)
        audio_files = []
        for index, source in enumerate(files):
            _duration, has_audio = montaje.probe(Path(source), ffmpeg)
            if not has_audio:
                continue
            wav = folder / f"{index:02d}.wav"
            subprocess.run(
                [ffmpeg, "-y", "-v", "error", "-i", str(source), "-map", "0:a:0", "-vn",
                 "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(wav)],
                check=True, capture_output=True, timeout=600,
            )
            audio_files.append(wav)
        if not audio_files:
            raise ValueError("Los clips seleccionados no tienen audio para transcribir.")
        if len(audio_files) == 1:
            shutil.copyfile(audio_files[0], out)
        else:
            inputs = []
            labels = []
            for i, path in enumerate(audio_files):
                inputs.extend(["-i", str(path)])
                labels.append(f"[{i}:a]")
            graph = "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[a]"
            subprocess.run(
                [ffmpeg, "-y", "-v", "error", *inputs, "-filter_complex", graph,
                 "-map", "[a]", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(out)],
                check=True, capture_output=True, timeout=900,
            )
    return out.read_bytes()


def sources(batch: str) -> list[Path]:
    folder = batch_path(batch)
    if not (folder / "completo").is_file():
        raise ValueError("No encuentro los videos seleccionados en la galeria.")
    files = sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in EXTENSIONS and p.is_file() and not p.is_symlink()
    )
    if not 1 <= len(files) <= MAX_CLIPS:
        raise ValueError("Selecciona entre uno y veinte videos.")
    if sum(p.stat().st_size for p in files) > MAX_BATCH_BYTES:
        raise ValueError("El lote supera el limite de 512 MB.")
    return files


def fill(shots, files: list[Path], dest: Path, ffmpeg: str) -> None:
    """Use each selected clip in order and preserve its aspect ratio."""
    from openjarvis.video_essay import montaje

    if not 1 <= len(files) <= MAX_CLIPS:
        raise ValueError("Selecciona entre uno y veinte videos.")
    if len(shots) < len(files):
        raise RuntimeError("El plan necesita al menos una toma por clip seleccionado.")
    dest.mkdir(parents=True, exist_ok=True)
    for i, path in enumerate(files):
        group = shots[i * len(shots) // len(files) : (i + 1) * len(shots) // len(files)]
        length, _ = montaje.probe(path, ffmpeg)
        if length < 0.3:
            raise RuntimeError(f"No pude leer el video de galeria {i + 1}.")
        total = sum(shot.dur for shot in group)
        if length + 0.12 < total:
            raise RuntimeError(f"El video de galeria {i + 1} es demasiado corto para sus tomas.")
        offset = 0.0
        for j, shot in enumerate(group):
            start = max(0.0, min(offset, length - 0.15))
            key = f"{i:02d}-{j:03d}-{round(start * 1000)}-{round(shot.dur * 1000)}"
            out = dest / (key + ".mp4")
            if not out.is_file():
                tmp = dest / (key + ".tmp.mp4")
                subprocess.run(
                    [ffmpeg, "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(path),
                     "-t", f"{shot.dur:.3f}", "-map", "0:v:0", "-an",
                     "-vf", "scale=1920:1920:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos",
                     "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", str(tmp)],
                    check=True, capture_output=True, timeout=180,
                )
                tmp.replace(out)
            shot.kind = "broll"
            shot.asset = str(out)
            shot.source = "library"
            note = f"imagen: galeria seleccionada ({i + 1})"
            if note not in shot.notes:
                shot.notes.append(note)
            offset += shot.dur


__all__ = ["EXTENSIONS", "MAX_BATCH_BYTES", "MAX_CLIPS", "batch_path", "extract_clips_voice", "fill", "home", "recent_local_clips", "sources", "store"]
