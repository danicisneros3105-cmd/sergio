"""Hands-on work in Windows: tidy folders and run small Python programs.

* ``organize`` sorts a folder's loose files into subfolders by kind (Imágenes,
  Videos, Documentos...) or by month. It first returns a preview; with
  ``apply=True`` it moves the files and writes an undo log, so ``undo`` can
  put everything back.
* ``run_python`` runs Python code written by Sergio (with numpy, Pillow and
  OpenCV available) and returns what it printed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from sergio_escritorio.media import resolve

KINDS = {
    "Imágenes": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".svg"},
    "Videos": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv"},
    "Música": {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"},
    "Documentos": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md"},
    "Hojas de cálculo": {".xls", ".xlsx", ".csv", ".ods"},
    "Presentaciones": {".ppt", ".pptx", ".key", ".odp"},
    "Comprimidos": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Instaladores": {".exe", ".msi"},
    "Código": {".py", ".js", ".ts", ".html", ".css", ".json", ".ipynb"},
    "3D": {".blend", ".obj", ".fbx", ".stl", ".glb", ".gltf"},
}
UNDO_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SergioEscritorio" / "deshacer"
)
MAX_FILES = 5000
MAX_OUTPUT = 6000


def _kind(path: Path) -> str:
    ext = path.suffix.lower()
    for name, exts in KINDS.items():
        if ext in exts:
            return name
    return "Otros"


def _month(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m")


def _free(target: Path) -> Path:
    """Never overwrite: 'foto.jpg' -> 'foto (2).jpg'."""
    candidate, n = target, 2
    while candidate.exists():
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        n += 1
    return candidate


def organize(
    folder: str, by: str = "type", apply: bool = False, home: Path | None = None
) -> dict:
    root = resolve(folder, home)
    if not root.is_dir():
        raise ValueError(f"No encontré la carpeta {folder!r}.")
    files = [
        p for p in sorted(root.iterdir()) if p.is_file() and not p.name.startswith(".")
    ]
    files = [p for p in files if p.suffix.lower() not in {".lnk", ".ini"}][:MAX_FILES]
    group = _month if by == "month" else _kind
    plan = [(p, root / group(p) / p.name) for p in files]
    summary: dict[str, int] = {}
    for _src, dst in plan:
        summary[dst.parent.name] = summary.get(dst.parent.name, 0) + 1
    result = {
        "folder": str(root),
        "files": len(plan),
        "groups": summary,
        "applied": False,
    }
    if not apply or not plan:
        return result
    moved = []
    for src, dst in plan:
        dst.parent.mkdir(exist_ok=True)
        final = _free(dst)
        src.rename(final)
        moved.append([str(src), str(final)])
    UNDO_DIR.mkdir(parents=True, exist_ok=True)
    log = UNDO_DIR / f"orden-{time.strftime('%Y%m%d-%H%M%S')}.json"
    log.write_text(json.dumps(moved, ensure_ascii=False, indent=1), encoding="utf-8")
    result.update(applied=True, undo=str(log))
    return result


def undo(log: str = "") -> int:
    """Put back the files of the last (or the given) organize run."""
    logs = sorted(UNDO_DIR.glob("orden-*.json")) if not log else [Path(log)]
    if not logs:
        raise ValueError("No hay nada que deshacer.")
    path = logs[-1]
    moved = json.loads(path.read_text(encoding="utf-8"))
    back = 0
    for original, now in reversed(moved):
        if Path(now).exists() and not Path(original).exists():
            Path(now).rename(original)
            back += 1
            try:
                Path(now).parent.rmdir()  # only if it is empty now
            except OSError:
                pass
    path.rename(path.with_suffix(".hecho"))
    return back


def run_python(code: str, timeout: float = 120, workdir: str = "") -> dict:
    folder = Path(workdir) if workdir else Path.home() / "Documents" / "Sergio"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8", dir=folder, prefix="sergio-"
    ) as script:
        script.write(code)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":  # pythonw has no stdout
        python = python.with_name("python.exe")
    try:
        done = subprocess.run(
            [str(python), script.name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=folder,
            creationflags=flags,
            check=False,
        )
        out, err, code_ = done.stdout, done.stderr, done.returncode
    except subprocess.TimeoutExpired:
        out, err, code_ = "", f"Se pasó de {timeout:g} s y lo detuve.", -1
    return {
        "exit_code": code_,
        "stdout": out[-MAX_OUTPUT:],
        "stderr": err[-MAX_OUTPUT:],
        "script": script.name,
        "folder": str(folder),
    }


def shell_command(command: str) -> list[str]:
    """PowerShell command line with UTF-8 output (pure, testable)."""
    prelude = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        "$ProgressPreference='SilentlyContinue'; "
    )
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        prelude + command,
    ]


def run_shell(
    command: str, timeout: float = 120, workdir: str = "", argv: list[str] | None = None
) -> dict:
    """Run a PowerShell command in the user's home and return its output."""
    folder = Path(workdir) if workdir else Path.home()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(
            argv or shell_command(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=folder,
            creationflags=flags,
            check=False,
        )
        out, err, code = done.stdout, done.stderr, done.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", f"Se pasó de {timeout:g} s y lo detuve.", -1
    except OSError as exc:
        out, err, code = "", str(exc), -1
    return {"exit_code": code, "stdout": out[-MAX_OUTPUT:], "stderr": err[-MAX_OUTPUT:]}


__all__ = ["KINDS", "organize", "run_python", "run_shell", "shell_command", "undo"]
