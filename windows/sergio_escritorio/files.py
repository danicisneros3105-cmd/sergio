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
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from sergio_escritorio.media import resolve
from sergio_escritorio.process_runner import run_bounded

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
_FILE_LOCK = threading.RLock()


def _save_moves(path: Path, moved: list[list[str]]) -> None:
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(moved, handle, ensure_ascii=False, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def _kind(path: Path) -> str:
    ext = path.suffix.lower()
    for name, exts in KINDS.items():
        if ext in exts:
            return name
    return "Otros"


def _month(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m")


def _free(target: Path, reserved: set[str] | None = None) -> Path:
    """Never overwrite: 'foto.jpg' -> 'foto (2).jpg'."""
    candidate, n = target, 2
    while candidate.exists() or os.path.normcase(str(candidate)) in (reserved or set()):
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        n += 1
    return candidate


def _move_exclusive(source: Path, destination: Path) -> None:
    """Reserve the destination atomically; never replace another file.

    Both files are on the same filesystem. Failure leaves a recoverable log;
    a crash between link and unlink leaves both names for undo to reconcile.
    """
    os.link(source, destination, follow_symlinks=False)
    source.unlink()


def organize(
    folder: str, by: str = "type", apply: bool = False, home: Path | None = None
) -> dict:
    with _FILE_LOCK:
        return _organize(folder, by, apply, home)


def _organize(folder: str, by: str, apply: bool, home: Path | None) -> dict:
    root = resolve(folder, home)
    if not root.is_dir():
        raise ValueError(f"No encontré la carpeta {folder!r}.")
    files = [
        p
        for p in sorted(root.iterdir())
        if p.is_file() and not p.is_symlink() and not p.name.startswith(".")
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
    UNDO_DIR.mkdir(parents=True, exist_ok=True)
    log = UNDO_DIR / (
        f"orden-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns():020d}-{uuid.uuid4().hex}.json"
    )
    moved: list[list[str]] = []
    reserved: set[str] = set()
    for src, dst in plan:
        if dst.parent.is_symlink():
            raise ValueError("La carpeta de destino no puede ser un enlace simbólico.")
        dst.parent.mkdir(exist_ok=True)
        final = _free(dst, reserved)
        reserved.add(os.path.normcase(str(final)))
        moved.append([str(src), str(final)])
    # One durable plan before any move: O(N), rather than rewriting N times.
    _save_moves(log, moved)
    for src, final in moved:
        _move_exclusive(Path(src), Path(final))
    result.update(applied=True, undo=str(log))
    return result


def undo(log: str = "") -> int:
    """Put back the files of the last (or the given) organize run."""
    with _FILE_LOCK:
        return _undo(log)


def _undo(log: str) -> int:
    logs = sorted(UNDO_DIR.glob("orden-*.json")) if not log else [Path(log)]
    if not logs:
        raise ValueError("No hay nada que deshacer.")
    path = logs[-1]
    moved = json.loads(path.read_text(encoding="utf-8"))
    back = 0
    pending = []
    for original, now in reversed(moved):
        if Path(now).exists() and Path(original).exists():
            if os.path.samefile(now, original):
                Path(now).unlink()
                back += 1
                continue
            pending.append([original, now])
            continue
        if Path(now).exists() and not Path(original).exists():
            try:
                _move_exclusive(Path(now), Path(original))
            except FileExistsError:
                pending.append([original, now])
                continue
            back += 1
            try:
                Path(now).parent.rmdir()  # only if it is empty now
            except OSError:
                pass
    if pending:
        _save_moves(path, list(reversed(pending)))
    else:
        path.rename(path.with_suffix(".hecho"))
    return back


def run_python(code: str, timeout: float = 120, workdir: str = "") -> dict:
    folder = Path(workdir) if workdir else Path.home() / "Documents" / "Sergio"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8", dir=folder, prefix="sergio-"
    ) as script:
        script.write(code)
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
    try:
        done = run_bounded(
            [str(python), script.name],
            timeout=timeout,
            cwd=folder,
            env=_execution_env(),
            max_output_bytes=MAX_OUTPUT,
        )
        out, err, code_ = done.stdout, done.stderr, done.returncode
        if done.timed_out:
            err += f"Se pasó de {timeout:g} s y lo detuve."
    except (OSError, ValueError) as exc:
        out, err, code_ = "", str(exc), -1
    return {
        "exit_code": code_,
        "stdout": out,
        "stderr": err,
        "script": script.name,
        "folder": str(folder),
    }


def _execution_env() -> dict[str, str]:
    import os

    keys = (
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "TERM",
        "SystemRoot",
        "SystemDrive",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
    )
    return {
        **{key: os.environ[key] for key in keys if key in os.environ},
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
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
    try:
        done = run_bounded(
            argv or shell_command(command),
            timeout=timeout,
            cwd=folder,
            env=_execution_env(),
            max_output_bytes=MAX_OUTPUT,
        )
        out, err, code = done.stdout, done.stderr, done.returncode
        if done.timed_out:
            err += f"Se pasó de {timeout:g} s y lo detuve."
    except (OSError, ValueError) as exc:
        out, err, code = "", str(exc), -1
    return {"exit_code": code, "stdout": out, "stderr": err}


__all__ = ["KINDS", "organize", "run_python", "run_shell", "shell_command", "undo"]
