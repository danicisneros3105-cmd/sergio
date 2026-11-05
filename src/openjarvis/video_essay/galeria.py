"""Import only the phone videos selected for this edit."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def home() -> Path:
    from openjarvis.core.config import get_config_dir

    return Path(get_config_dir()) / "videos-galeria"


def batch_path(batch: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", batch):
        raise ValueError("Identificador de clips no válido.")
    return home() / batch


def sources(batch: str) -> list[Path]:
    folder = batch_path(batch)
    if not (folder / "completo").is_file():
        raise ValueError("No encuentro los videos seleccionados en la galería.")
    files = sorted(
        p
        for p in folder.iterdir()
        if p.suffix in EXTENSIONS and p.is_file() and not p.is_symlink()
    )
    if not 1 <= len(files) <= 6:
        raise ValueError("Selecciona entre uno y seis videos.")
    return files


def fill(shots, files: list[Path], dest: Path, ffmpeg: str) -> None:
    """Use every selected video in order; never use search results in its place."""
    from openjarvis.video_essay import montaje

    if len(shots) < len(files):
        raise RuntimeError(
            "El guion tiene menos tomas que los clips seleccionados. Usa menos clips o aumenta la duración."
        )
    dest.mkdir(parents=True, exist_ok=True)
    for i, path in enumerate(files):
        group = shots[i * len(shots) // len(files) : (i + 1) * len(shots) // len(files)]
        length, _ = montaje.probe(path, ffmpeg)
        if length < 0.3:
            raise RuntimeError(f"No pude leer el video de galería {i + 1}.")
        total = sum(shot.dur for shot in group)
        if length + 0.12 < total:
            raise RuntimeError(
                f"El video de galería {i + 1} es demasiado corto para sus tomas. Reduce la duración o elige un clip más largo."
            )
        offset = 0.0
        for j, shot in enumerate(group):
            start = max(0.0, min(offset, length - 0.15))
            key = f"{i:02d}-{j:03d}-{round(start * 1000)}-{round(shot.dur * 1000)}"
            out = dest / (key + ".mp4")
            if not out.is_file():
                tmp = dest / (key + ".tmp.mp4")
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        f"{start:.3f}",
                        "-i",
                        str(path),
                        "-t",
                        f"{shot.dur:.3f}",
                        "-map",
                        "0:v:0",
                        "-an",
                        "-vf",
                        "scale=960:960:force_original_aspect_ratio=decrease:force_divisible_by=2",
                        "-c:v",
                        "libx264",
                        "-threads",
                        "2",
                        "-preset",
                        "veryfast",
                        str(tmp),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=180,
                )
                tmp.replace(out)
            shot.kind = "broll"
            shot.asset = str(out)
            shot.source = "library"
            note = f"imagen: galería seleccionada ({i + 1})"
            if note not in shot.notes:
                shot.notes.append(note)
            offset += shot.dur


__all__ = ["EXTENSIONS", "batch_path", "fill", "home", "sources"]
