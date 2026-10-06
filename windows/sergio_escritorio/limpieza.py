"""Keep only the latest: clean what updates and Blender leave behind.

Run by the update command (``sergio escritorio instalar``) on both sides,
Ubuntu and Windows, and after every Blender Pro job:

- uv's download cache (``uv cache prune``: only what nothing uses),
- older patch releases of a Python that uv installed when a newer one of
  the same version is there (never the one Sergio runs on, never the
  system's own Pythons),
- git's loose objects (``git gc --auto``),
- Blender's backups (``.blend1``, ``.blend2``…), the single views of the
  review sheet and the scripts of old runs (the last few are kept),
  and the files of attempts that never produced a model.

Only standard library: the Ubuntu side loads this same file.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

Run = Callable[..., Any]
KEEP_SCRIPTS = 5


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def stale_pythons(installed: list[dict[str, Any]], managed_dir: str, in_use: list[str]) -> list[str]:
    """The uv-managed Pythons superseded by a newer patch of the same version.

    *installed*: ``uv python list --only-installed --output-format json``;
    *in_use*: the interpreters Sergio's environments point at (kept)."""
    root = str(Path(managed_dir).resolve()).lower() if managed_dir else ""
    used = [str(Path(p).resolve()).lower() for p in in_use if p]
    managed: dict[str, dict[str, Any]] = {}
    for item in installed:
        path = str(Path(str(item.get("path") or "")).resolve()).lower()
        if not root or not path.startswith(root):
            continue  # the system's own Python: never touched
        managed.setdefault(str(item.get("key") or ""), {**item, "_path": path})
    newest: dict[tuple[str, tuple[int, ...]], tuple[int, ...]] = {}
    for item in managed.values():
        ver = _version(str(item.get("version") or ""))
        line = (str(item.get("implementation") or ""), ver[:2])
        newest[line] = max(newest.get(line, ver), ver)
    stale = []
    for key, item in managed.items():
        ver = _version(str(item.get("version") or ""))
        line = (str(item.get("implementation") or ""), ver[:2])
        install_dir = str(Path(item["_path"]).parent.parent) if item["_path"] else ""
        busy = any(u.startswith(install_dir) for u in used if install_dir)
        if key and ver < newest[line] and not busy:
            stale.append(key)
    return sorted(stale)


def clean_python(uv: str, in_use: list[str], run: Run = subprocess.run) -> list[str]:
    """``uv cache prune`` and the superseded Pythons; returns what was removed."""
    removed: list[str] = []
    run([uv, "cache", "prune"], capture_output=True, check=False)
    try:
        listed = run(
            [uv, "python", "list", "--only-installed", "--output-format", "json"],
            capture_output=True, text=True, check=False,
        )
        managed = run([uv, "python", "dir"], capture_output=True, text=True, check=False)
        installed = json.loads(listed.stdout or "[]")
        managed_dir = (managed.stdout or "").strip()
    except (ValueError, OSError):
        return removed
    for key in stale_pythons(installed, managed_dir, in_use):
        done = run([uv, "python", "uninstall", key], capture_output=True, check=False)
        if getattr(done, "returncode", 1) == 0:
            removed.append(key)
    return removed


def clean_git(repo: Path, run: Run = subprocess.run) -> None:
    """Pack loose objects (only when git thinks it is worth it)."""
    if (repo / ".git").exists():
        run(["git", "-C", str(repo), "gc", "--auto", "--quiet"], capture_output=True, check=False)


def clean_blender(projects: Path, scripts: Path | None = None, keep_scripts: int = KEEP_SCRIPTS) -> int:
    """Blender's leftovers; returns how many files went away."""
    gone = 0
    if projects.is_dir():
        for item in projects.iterdir():
            if not item.is_file():
                continue
            backup = re.search(r"\.blend\d+$", item.name)
            single_view = re.search(r"-vista-(beauty|front|right|top)\.png$", item.name)
            # A review sheet whose project was never saved: a failed attempt.
            orphan = item.name.endswith("-vista.png") and not (
                projects / (item.name[: -len("-vista.png")] + ".blend")
            ).exists()
            if backup or single_view or orphan:
                item.unlink(missing_ok=True)
                gone += 1
    if scripts is not None and scripts.is_dir():
        runs = sorted(scripts.glob("pro-*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in runs[keep_scripts:]:
            old.unlink(missing_ok=True)
            gone += 1
    return gone


def forget_attempt(blend: str) -> None:
    """A Blender Pro job that never produced a model: remove its files."""
    stem = blend[:-6] if blend.endswith(".blend") else blend
    for suffix in (".blend", ".blend1", "-vista.png", "-planos.png"):
        Path(stem + suffix).unlink(missing_ok=True)


def main() -> None:
    """Windows side, run by the installer: ``python -m sergio_escritorio.limpieza UV``."""
    import os
    import sys

    uv = sys.argv[1] if len(sys.argv) > 1 else "uv"
    removed = clean_python(uv, [sys.executable, getattr(sys, "_base_executable", "")])
    scripts = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SergioEscritorio" / "blender"
    gone = clean_blender(Path.home() / "Documents" / "Sergio" / "Blender", scripts)
    print(f"Limpieza: {gone} archivos viejos de Blender, Pythons viejos quitados: {len(removed)}")


if __name__ == "__main__":
    main()


__all__ = ["clean_blender", "clean_git", "clean_python", "forget_attempt", "stale_pythons"]
