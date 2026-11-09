"""Secure file and directory creation helpers.

All OpenJarvis data files under ``~/.openjarvis/`` should be created
through these helpers to ensure consistent, restrictive permissions.
"""

from __future__ import annotations

import csv
import functools
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any


@functools.lru_cache(maxsize=1)
def _windows_sid() -> str:
    done = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    rows = list(csv.reader(done.stdout.splitlines()))
    if not rows or len(rows[0]) < 2 or not rows[0][1].startswith("S-"):
        raise OSError("Could not determine the current Windows user SID")
    return rows[0][1]


@functools.lru_cache(maxsize=1)
def _windows_account() -> str:
    done = subprocess.run(
        ["whoami"], capture_output=True, text=True, check=True, timeout=10
    )
    return done.stdout.strip()


def _restrict_windows(path: Path) -> None:
    icacls = shutil.which("icacls")
    if not icacls:
        raise OSError("icacls is required to protect private files on Windows")

    def run(*args: str) -> None:
        subprocess.run(
            [icacls, str(path), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )

    sid = _windows_sid()
    account = _windows_account()
    run("/inheritance:r")
    for identity in _windows_identities(path):
        if identity.casefold() not in {sid.casefold(), account.casefold()}:
            target = f"*{identity}" if identity.startswith("S-") else identity
            run("/remove:g", target)
            run("/remove:d", target)
    run("/remove:d", account)
    rights = "(OI)(CI)(F)" if path.is_dir() else "(F)"
    run("/grant:r", f"*{sid}:{rights}")
    if not is_private(path):
        raise OSError(f"Could not restrict access to {path}")


def restrict_private(
    path: Path, *, directory: bool = False, mode: int | None = None
) -> Path:
    path = Path(path)
    if os.name == "nt":
        _restrict_windows(path)
    else:
        os.chmod(path, mode if mode is not None else (0o700 if directory else 0o600))
    return path


def _windows_identities(path: Path) -> set[str]:
    icacls = shutil.which("icacls")
    if not icacls:
        return set()
    done = subprocess.run(
        [icacls, str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    identities = set()
    lines = done.stdout.splitlines()
    if lines and lines[0].startswith(str(path)):
        lines[0] = lines[0][len(str(path)) :]
    for line in lines:
        match = re.match(r"\s*(.+?):\(", line)
        if match:
            identities.add(match.group(1).strip())
    return identities


def is_private(path: Path) -> bool:
    """Verify effective owner-only access, including Windows ACLs."""
    path = Path(path)
    try:
        if os.name != "nt":
            return not path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO)
        allowed = {_windows_sid().casefold(), _windows_account().casefold()}
        identities = _windows_identities(path)
        return bool(identities) and all(
            identity.casefold() in allowed for identity in identities
        )
    except (OSError, subprocess.SubprocessError):
        return False


def secure_mkdir(path: Path, mode: int = 0o700) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt" and is_private(path):
        return path
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) == mode:
        return path
    return restrict_private(path, directory=True, mode=mode)


def secure_create(path: Path, mode: int = 0o600) -> Path:
    secure_mkdir(path.parent, mode=0o700)
    if not path.exists():
        path.touch()
    return restrict_private(path, mode=mode)


def secure_write_text(
    path: Path,
    content: str,
    *,
    mode: int = 0o600,
    encoding: str = "utf-8",
) -> Path:
    """Atomically replace *path* with owner-only text content."""
    secure_mkdir(path.parent, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary_path = Path(temporary_name)
    try:
        restrict_private(temporary_path, mode=mode)
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        restrict_private(path, mode=mode)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
    return path


def secure_write_json(path: Path, payload: Any, *, mode: int = 0o600) -> Path:
    return secure_write_text(
        path,
        json.dumps(payload, indent=2),
        mode=mode,
        encoding="utf-8",
    )


__all__ = [
    "is_private",
    "restrict_private",
    "secure_create",
    "secure_mkdir",
    "secure_write_json",
    "secure_write_text",
]
