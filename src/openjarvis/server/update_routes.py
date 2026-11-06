"""Start the non-destructive WSL updater from the local Sergio app."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/v1/sistema", tags=["sistema"])
ROOT = Path(__file__).resolve().parents[3]
COMMAND = "bash scripts/actualizar-sergio.sh main"
_START_LOCK = threading.Lock()


def _home() -> Path:
    return Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")


def log_path() -> Path:
    return _home() / "logs" / "actualizacion.log"


def lock_path() -> Path:
    return _home() / "actualizando"


def running(now: float | None = None) -> bool:
    lock = lock_path()
    try:
        started = float(lock.read_text().strip() or 0)
    except (OSError, ValueError):
        return False
    return (now or time.time()) - started < 3600  # a stale lock expires


def launcher(root: Path = ROOT) -> List[str]:
    log, lock = log_path(), lock_path()
    script = (
        f"trap {shlex.quote('rm -f -- ' + shlex.quote(str(lock)))} EXIT; "
        f"( cd -- {shlex.quote(str(root))} && {COMMAND} ) "
        f">> {shlex.quote(str(log))} 2>&1; rc=$?; "
        f'echo "== fin: $rc ($(date))" >> {shlex.quote(str(log))}; exit "$rc"'
    )
    if shutil.which("systemd-run"):
        return [
            "systemd-run",
            "--user",
            "--collect",
            "--quiet",
            f"--unit=sergio-actualizar-{int(time.time())}",
            "bash",
            "-lc",
            script,
        ]
    return ["setsid", "bash", "-lc", script]


def start(popen: Callable[..., Any] = subprocess.Popen) -> Dict[str, Any]:
    with _START_LOCK:
        if running():
            return {"started": False, "running": True}
        log_path().parent.mkdir(parents=True, exist_ok=True)
        lock = lock_path()
        lock.write_text(str(time.time()), encoding="utf-8")
        try:
            with log_path().open("a", encoding="utf-8") as f:
                f.write(f"\n== Actualización pedida desde Sergio ({time.ctime()})\n")
                cmd = launcher()
                # A failed systemd launch (e.g. no user bus) must not leave
                # a permanent in-progress flag. Fall back to a detached shell.
                if cmd[0] == "systemd-run":
                    try:
                        subprocess.run(
                            cmd,
                            stdin=subprocess.DEVNULL,
                            stdout=f,
                            stderr=f,
                            check=True,
                            timeout=5,
                        )
                    except (OSError, subprocess.CalledProcessError):
                        cmd = ["setsid", *cmd[-3:]]
                    else:
                        return {"started": True, "running": True}
                popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=f,
                    stderr=f,
                    start_new_session=True,
                )
        except Exception:
            lock.unlink(missing_ok=True)
            raise
        return {"started": True, "running": True}


def status() -> Dict[str, Any]:
    try:
        with log_path().open("rb") as f:
            f.seek(max(f.seek(0, os.SEEK_END) - 65536, 0))
            tail = f.read().decode("utf-8", errors="replace").splitlines()[-12:]
    except OSError:
        tail = []
    try:
        version = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        version = ""
    completed = re.match(r"^== fin: (\d+) ", tail[-1]) if tail else None
    return {
        "running": running(),
        "version": version,
        "log": tail,
        "last_exit_code": int(completed[1]) if completed else None,
    }


def _local_only(request: Request) -> None:
    from openjarvis.server.vision_routes import from_this_computer

    if not from_this_computer(request):
        raise HTTPException(status_code=403, detail="Solo desde este equipo.")


@router.get("/actualizar")
async def update_status(request: Request) -> Dict[str, Any]:
    _local_only(request)
    return status()


@router.post("/actualizar")
def update_now(request: Request) -> Dict[str, Any]:
    _local_only(request)
    if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
        raise HTTPException(status_code=403, detail="Actualización desde otro origen.")
    try:
        return start()
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(
            status_code=503,
            detail="No pude iniciar la actualización. Revisa el registro.",
        ) from exc


__all__ = ["COMMAND", "launcher", "router", "running", "start", "status"]
