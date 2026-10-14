"""«Actualizar» from inside Sergio: the owner's universal command, one click.

It runs exactly what the owner would type in PowerShell — fetch main, put
the local ``main`` on it and ``scripts/actualizar-sergio.sh main`` — but in
its own systemd scope (or a new session), because the update restarts this
very server. Only from this computer (never through a tunnel).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/v1/sistema", tags=["sistema"])
ROOT = Path(__file__).resolve().parents[3]
COMMAND = (
    "git fetch origin main && git checkout -B main origin/main && "
    "bash scripts/actualizar-sergio.sh main"
)


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
        f"cd {shlex.quote(str(root))} && date +%s > {shlex.quote(str(lock))} && "
        f"( {COMMAND} ) >> {shlex.quote(str(log))} 2>&1; "
        f'echo "== fin: $? ($(date))" >> {shlex.quote(str(log))}; rm -f {shlex.quote(str(lock))}'
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
    if running():
        return {"started": False, "running": True}
    log_path().parent.mkdir(parents=True, exist_ok=True)
    with log_path().open("a", encoding="utf-8") as f:
        f.write(f"\n== Actualización pedida desde Sergio ({time.ctime()})\n")
    popen(
        launcher(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"started": True, "running": True}


def status() -> Dict[str, Any]:
    try:
        tail = (
            log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
        )
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
    return {"running": running(), "version": version, "log": tail}


def _local_only(request: Request) -> None:
    from openjarvis.server.vision_routes import from_this_computer

    if not from_this_computer(request):
        raise HTTPException(status_code=403, detail="Solo desde este equipo.")


@router.get("/actualizar")
async def update_status(request: Request) -> Dict[str, Any]:
    _local_only(request)
    return status()


@router.post("/actualizar")
async def update_now(request: Request) -> Dict[str, Any]:
    _local_only(request)
    return start()


__all__ = ["COMMAND", "launcher", "router", "running", "start", "status"]
