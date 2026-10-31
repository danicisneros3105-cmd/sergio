"""Sergio rewrites its own code to get better, safely (owner, 1 Nov 2026:
«haz que Sergio pueda alterar y reescribir su propio código cada vez para
mejorar… debe tener corrección de errores integrada»).

A change never touches the running copy first:

1. it is written in a separate working copy (``git worktree``) on its own
   branch, ``sergio/mejora-<id>``;
2. the checks run there: ruff on the changed files and the tests that cover
   them (the matching ``tests/**/test_<module>*.py``, else a quick import);
3. only if everything passes is it applied to Sergio's copy as one commit,
   so it can be undone with one call (``revert``); if anything fails the
   branch is dropped and the running app is untouched;
4. it is never pushed to GitHub by itself (``push`` stays off unless the
   owner turns it on), and every change is listed with its diff.

The log is ``~/.openjarvis/automejora/registro.json``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

MAX_CHANGE = 400  # lines a single self-change may touch
TEST_TIMEOUT = 600
_LOCK = threading.Lock()
Runner = Callable[..., subprocess.CompletedProcess]


class AutomejoraError(RuntimeError):
    """Why a self-change was not applied, in plain words."""


@dataclass
class Change:
    path: str  # repo-relative file
    old: str  # exact text to replace ('' with new file content to create)
    new: str


@dataclass
class Mejora:
    id: str
    reason: str
    files: List[str]
    state: str = "pendiente"  # pendiente | aplicada | rechazada | deshecha
    checks: str = ""
    diff: str = ""
    commit: str = ""
    created: float = field(default_factory=time.time)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def home() -> Path:
    from openjarvis.core.config import get_config_dir

    return Path(get_config_dir()) / "automejora"


def _git(
    root: Path, *args: str, run: Runner = subprocess.run, check: bool = True
) -> str:
    done = run(["git", *args], cwd=root, capture_output=True, text=True, timeout=120)
    if check and done.returncode != 0:
        raise AutomejoraError(
            f"git {' '.join(args[:2])}: {(done.stderr or done.stdout).strip()[:300]}"
        )
    return (done.stdout or "").strip()


def _safe_path(path: str) -> str:
    clean = Path(path).as_posix().lstrip("/")
    if ".." in Path(clean).parts or not clean.startswith(
        ("src/", "windows/", "frontend/src/", "tests/")
    ):
        raise AutomejoraError(
            f"Solo puedo cambiar mi propio código (src, windows, frontend/src, tests): {path}"
        )
    if re.search(r"(\.env|sergio\.env|secrets?|credentials?)", clean, re.I):
        raise AutomejoraError("Nunca toco archivos de claves.")
    return clean


def tests_for(root: Path, files: List[str]) -> List[str]:
    """The tests that cover these files (by module name)."""
    found: List[str] = []
    for f in files:
        if f.startswith("tests/") and f.endswith(".py"):
            found.append(f)
            continue
        stem = Path(f).stem
        if not stem or stem == "__init__":
            continue
        for t in sorted((root / "tests").rglob(f"test_{stem}*.py")):
            rel = t.relative_to(root).as_posix()
            if rel not in found:
                found.append(rel)
    return found[:12]


def _registro() -> Path:
    return home() / "registro.json"


def history() -> List[Dict]:
    try:
        return json.loads(_registro().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(m: Mejora) -> None:
    items = [x for x in history() if x.get("id") != m.id]
    items.append(asdict(m))
    _registro().parent.mkdir(parents=True, exist_ok=True)
    _registro().write_text(
        json.dumps(items[-200:], ensure_ascii=False, indent=1), encoding="utf-8"
    )


def improve(
    reason: str,
    changes: List[Change],
    *,
    root: Optional[Path] = None,
    run: Runner = subprocess.run,
    python: str = sys.executable,
    apply: bool = True,
) -> Mejora:
    """Try a self-change in a separate copy; apply it only if the checks pass."""
    root = Path(root or repo_root())
    if not changes:
        raise AutomejoraError("No hay cambios que probar.")
    files = [_safe_path(c.path) for c in changes]
    touched = sum(len(c.new.splitlines()) + len(c.old.splitlines()) for c in changes)
    if touched > MAX_CHANGE:
        raise AutomejoraError(
            f"El cambio es demasiado grande ({touched} líneas); hágalo por partes."
        )
    mid = time.strftime("%Y%m%d-%H%M%S") + f"-{abs(hash(reason)) % 10000:04d}"
    m = Mejora(mid, reason.strip()[:300], files)
    with _LOCK:
        base = _git(root, "rev-parse", "HEAD", run=run)
        work = Path(tempfile.mkdtemp(prefix="sergio-mejora-"))
        branch = f"sergio/mejora-{mid}"
        try:
            _git(root, "worktree", "add", "-q", "-b", branch, str(work), base, run=run)
            for c, rel in zip(changes, files):
                target = work / rel
                if c.old:
                    text = target.read_text(encoding="utf-8")
                    if text.count(c.old) != 1:
                        raise AutomejoraError(
                            f"El texto a cambiar no aparece una sola vez en {rel}."
                        )
                    target.write_text(text.replace(c.old, c.new, 1), encoding="utf-8")
                else:
                    if target.exists():
                        raise AutomejoraError(
                            f"{rel} ya existe; diga qué texto cambiar."
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(c.new, encoding="utf-8")
            m.diff = _git(work, "diff", run=run)[:20000]
            m.checks = _checks(work, files, run=run, python=python)
            _git(work, "add", "--", *files, run=run)
            _git(work, "-c", "user.name=Sergio", "-c", "user.email=sergio@localhost",
                 "commit", "-q", "-m", f"automejora: {m.reason[:72]}", run=run)  # fmt: skip
            m.commit = _git(work, "rev-parse", "HEAD", run=run)
            if apply:
                _git(root, "cherry-pick", "--no-edit", m.commit, run=run)
                m.commit = _git(root, "rev-parse", "HEAD", run=run)
                m.state = "aplicada"
        except AutomejoraError as exc:
            m.state = "rechazada"
            m.checks = (m.checks + "\n" + str(exc)).strip()
            if apply:
                _git(root, "cherry-pick", "--abort", run=run, check=False)
        finally:
            _git(root, "worktree", "remove", "--force", str(work), run=run, check=False)
            _git(root, "branch", "-D", branch, run=run, check=False)
            shutil.rmtree(work, ignore_errors=True)
        _save(m)
    return m


def _checks(work: Path, files: List[str], *, run: Runner, python: str) -> str:
    out = []
    py = [f for f in files if f.endswith(".py")]
    if py:
        lint = run(
            [python, "-m", "ruff", "check", *py],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out.append("ruff: " + ("bien" if lint.returncode == 0 else "falló"))
        if lint.returncode != 0:
            raise AutomejoraError(
                "ruff encontró errores:\n" + (lint.stdout or lint.stderr)[-1500:]
            )
    tests = tests_for(work, files)
    if tests:
        env_cmd = [python, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests]
        done = run(
            env_cmd, cwd=work, capture_output=True, text=True, timeout=TEST_TIMEOUT
        )
        out.append(
            f"pruebas ({len(tests)} archivos): "
            + ("bien" if done.returncode == 0 else "fallaron")
        )
        if done.returncode != 0:
            raise AutomejoraError(
                "Las pruebas fallaron:\n" + (done.stdout or done.stderr)[-2000:]
            )
    elif py:
        mods = [
            f[len("src/") : -3].replace("/", ".") for f in py if f.startswith("src/")
        ]
        if mods:
            done = run([python, "-c", "import " + ", ".join(mods)], cwd=work, capture_output=True, text=True,
                       timeout=120, env=None)  # fmt: skip
            out.append("importa: " + ("bien" if done.returncode == 0 else "falló"))
            if done.returncode != 0:
                raise AutomejoraError(
                    "El código no importa:\n" + (done.stderr or "")[-1500:]
                )
    return "; ".join(out) or "sin comprobaciones aplicables"


def revert(
    mid: str, *, root: Optional[Path] = None, run: Runner = subprocess.run
) -> Mejora:
    """Undo an applied self-change (one commit back out)."""
    root = Path(root or repo_root())
    item = next((x for x in history() if x.get("id") == mid), None)
    if not item or item.get("state") != "aplicada":
        raise AutomejoraError("Esa mejora no está aplicada.")
    m = Mejora(**item)
    with _LOCK:
        _git(root, "-c", "user.name=Sergio", "-c", "user.email=sergio@localhost",
             "revert", "--no-edit", m.commit, run=run)  # fmt: skip
    m.state = "deshecha"
    _save(m)
    return m


__all__ = [
    "AutomejoraError",
    "Change",
    "Mejora",
    "history",
    "improve",
    "revert",
    "tests_for",
]
