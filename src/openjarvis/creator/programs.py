"""The real programs behind Creator, as one list the web shows.

* In Sergio's web, served from Ubuntu: OpenDesign (the Canva-like editor)
  and VSCodium (code), started on demand by the supervisor.
* In Windows, through Sergio Escritorio: ArtCraft and Kdenlive (images and
  video), FreeCAD, Blender with Bonsai and LibreCAD (architecture), Blender
  (3D) and VSCodium's desktop app.
* Here, in its own Python: Kronos (stock forecasts).
"""

from __future__ import annotations

import base64
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from openjarvis.creator import kronos
from openjarvis.creator.llm import CreatorError

ROOT = Path(__file__).resolve().parents[3]

PROGRAMS: list[dict[str, Any]] = [
    {
        "id": "opendesign",
        "name": "Diseño",
        "space": "diseno",
        "where": "web",
        "what": "Publicaciones, plantillas y marcas.",
        "license": "MIT",
    },
    {
        "id": "artcraft",
        "name": "Imagen",
        "space": "imagen",
        "where": "windows",
        "what": "Imagen y video con IA.",
        "license": "MIT / Apache-2.0",
    },
    {
        "id": "kdenlive",
        "name": "Video",
        "space": "imagen",
        "where": "windows",
        "what": "Edición de video.",
        "license": "GPL-3.0",
    },
    {
        "id": "freecad",
        "name": "Planos",
        "space": "arquitectura",
        "where": "windows",
        "what": "BIM: IFC, DXF y STEP.",
        "license": "LGPL-2.1",
    },
    {
        "id": "bonsai",
        "name": "BIM",
        "space": "arquitectura",
        "where": "windows",
        "what": "El edificio en IFC.",
        "license": "GPL-3.0",
    },
    {
        "id": "librecad",
        "name": "Plano 2D",
        "space": "arquitectura",
        "where": "windows",
        "what": "Dibujo en DXF.",
        "license": "GPL-2.0",
    },
    {
        "id": "blender",
        "name": "Estudio 3D",
        "space": "modelado",
        "where": "windows",
        "what": "Modelado 3D.",
        "license": "GPL-3.0",
    },
    {
        "id": "vscodium",
        "name": "Código",
        "space": "codigo",
        "where": "web",
        "what": "Editor de código.",
        "license": "MIT",
    },
    {
        "id": "kronos",
        "name": "Pronóstico",
        "space": "bolsa",
        "where": "local",
        "what": "Predicción de mercados.",
        "license": "MIT",
    },
]
BY_ID = {p["id"]: p for p in PROGRAMS}
WEB_APPS = ("opendesign", "vscodium")
WINDOWS_APPS = (
    "artcraft",
    "kdenlive",
    "freecad",
    "bonsai",
    "librecad",
    "blender",
    "vscodium",
)
OPENS = {  # which program opens which kind of file Sergio makes
    "dxf": ("librecad", "freecad"),
    "ifc": ("freecad", "bonsai"),
}

_cache: dict[str, Any] = {"at": 0.0, "windows": None}
_installing: dict[str, str] = {}


def _supervisor() -> Any:
    from openjarvis.core.config import load_config
    from openjarvis.unified.supervisor import Supervisor

    return Supervisor(load_config())


def _desktop(args: dict[str, Any]) -> Any:
    from openjarvis.server.desktop_routes import _skill

    return _skill("creator_apps", args)


def windows_status(max_age: float = 20.0) -> dict[str, Any] | None:
    """What Sergio Escritorio says is installed (None when it is not running)."""
    if _cache["windows"] is not None and time.monotonic() - _cache["at"] < max_age:
        return _cache["windows"]
    try:
        found = _desktop({"action": "status"})
    except Exception:  # noqa: BLE001 — the desktop app is closed or older
        found = None
    _cache.update(
        at=time.monotonic(), windows=found if isinstance(found, dict) else None
    )
    return _cache["windows"]


def status(local: bool) -> list[dict[str, Any]]:
    sup = _supervisor()
    web = {row["name"]: row for row in sup.status(creator=True)}
    win = windows_status()
    out = []
    for prog in PROGRAMS:
        row = dict(prog)
        pid = prog["id"]
        if pid in WEB_APPS:
            svc = web.get(pid, {})
            row["installed"] = bool(svc.get("available"))
            row["running"] = bool(svc.get("running"))
            row["installing"] = _installing.get(pid) == "installing"
            row["error"] = (
                "" if _installing.get(pid) in (None, "installing") else _installing[pid]
            )
            row["port"] = {"opendesign": 8790, "vscodium": 8791}[pid]
            if pid == "vscodium" and local and row["installed"]:
                row["token"] = sup.vscodium_token()
        elif pid == "kronos":
            row.update(kronos.status())
        if pid in WINDOWS_APPS:
            info = (win or {}).get(pid) or {}
            key = "windows" if pid in WEB_APPS else None
            entry = {
                "installed": bool(info.get("installed")),
                "installing": bool(info.get("installing")),
                "error": info.get("error", ""),
                "reachable": win is not None,
            }
            if key:
                row[key] = entry
            else:
                row.update(entry)
        out.append(row)
    return out


def start(pid: str) -> dict[str, Any]:
    if pid not in WEB_APPS:
        raise CreatorError("Ese programa no se abre dentro de la web.")
    sup = _supervisor()
    svc = sup.get(pid)
    outcome = sup.start(svc, wait=90.0)
    return {"id": pid, "outcome": outcome, "running": sup.running(svc)}


def install(pid: str, where: str = "") -> dict[str, Any]:
    if pid not in BY_ID:
        raise CreatorError("Programa desconocido.")
    if pid == "kronos":
        return kronos.install_in_background()
    if pid in WEB_APPS and where != "windows":
        if _installing.get(pid) == "installing":
            return {"id": pid, "installing": True}
        _installing[pid] = "installing"

        def work() -> None:
            script = ROOT / "scripts" / "instalar-programas.sh"
            done = subprocess.run(
                ["bash", str(script), pid],
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
            if done.returncode == 0:
                _installing.pop(pid, None)
            else:
                _installing[pid] = (done.stderr or done.stdout or "falló")[
                    -300:
                ].strip()

        threading.Thread(target=work, daemon=True).start()
        return {"id": pid, "installing": True}
    _cache["windows"] = None
    return {"id": pid, "message": _desktop({"action": "install", "app": pid})}


def open_in_windows(pid: str, name: str = "", data: bytes | None = None) -> str:
    if pid not in WINDOWS_APPS:
        raise CreatorError("Ese programa no se abre en Windows.")
    args: dict[str, Any] = {"action": "open", "app": pid}
    if data is not None:
        args.update(name=name, data=base64.b64encode(data).decode())
    return str(_desktop(args))


__all__ = [
    "BY_ID",
    "OPENS",
    "PROGRAMS",
    "install",
    "open_in_windows",
    "start",
    "status",
]
