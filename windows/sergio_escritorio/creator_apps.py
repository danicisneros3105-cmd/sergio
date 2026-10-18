"""The real programs behind Creator, installed and opened by Sergio.

Creator does not reinvent what already exists (owner, 2026-10): the Adobe
side is ArtCraft (with Kdenlive for video editing), architecture is FreeCAD,
Blender with the Bonsai (BlenderBIM) add-on and LibreCAD, and code is
VSCodium. This module knows where each one lives in Windows, installs the
missing ones (winget, or the project's own GitHub release), opens them, and
opens the files Sergio makes (a plan as DXF or IFC, an image, a project) in
the right one.

Run by hand or from the installer::

    python -m sergio_escritorio.creator_apps estado
    python -m sergio_escritorio.creator_apps instalar-todo
"""

from __future__ import annotations

import base64
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

HOME = Path.home() / "Sergio"
INCOMING = HOME / "Creator"
LOG = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Sergio" / "programas.log"
)


@dataclass(frozen=True)
class Program:
    name: str
    what: str
    winget: str = ""  # winget package id
    github: str = ""  # owner/repo whose latest release has the installer
    asset: str = ""  # regex of that installer's file name
    silent: tuple[str, ...] = ()  # the installer's quiet switches
    exe: tuple[str, ...] = ()  # where the program lives (env vars and * allowed)
    opens: tuple[str, ...] = ()  # file kinds it opens (lower-case suffixes)
    needs: str = ""  # another program it lives in (Bonsai lives in Blender)


PROGRAMS: dict[str, Program] = {
    "artcraft": Program(
        "Imagen",
        "imagen y video con IA",
        github="storytold/artcraft",
        asset=r"ArtCraft_[\d.]+_x64-setup\.exe",
        silent=("/S",),
        exe=(
            r"%LOCALAPPDATA%\ArtCraft\ArtCraft.exe",
            r"%LOCALAPPDATA%\Programs\ArtCraft\ArtCraft.exe",
            r"%ProgramFiles%\ArtCraft\ArtCraft.exe",
        ),
        opens=(".png", ".jpg", ".jpeg", ".webp"),
    ),
    "kdenlive": Program(
        "Video",
        "edición de video",
        winget="KDE.Kdenlive",
        exe=(
            r"%ProgramFiles%\kdenlive\bin\kdenlive.exe",
            r"%LOCALAPPDATA%\Programs\kdenlive\bin\kdenlive.exe",
        ),
        opens=(".kdenlive", ".mp4", ".mov", ".mkv", ".webm"),
    ),
    "freecad": Program(
        "Planos",
        "arquitectura y BIM",
        winget="FreeCAD.FreeCAD",
        exe=(
            r"%ProgramFiles%\FreeCAD*\bin\freecad.exe",
            r"%LOCALAPPDATA%\Programs\FreeCAD*\bin\freecad.exe",
        ),
        opens=(".fcstd", ".ifc", ".dxf", ".step", ".stp", ".stl", ".obj"),
    ),
    "librecad": Program(
        "Plano 2D",
        "dibujo en DXF",
        winget="LibreCAD.LibreCAD",
        exe=(
            r"%ProgramFiles%\LibreCAD\librecad.exe",
            r"%ProgramFiles(x86)%\LibreCAD\librecad.exe",
        ),
        opens=(".dxf",),
    ),
    "blender": Program(
        "Estudio 3D",
        "modelado 3D",
        winget="BlenderFoundation.Blender",
        exe=(r"%ProgramFiles%\Blender Foundation\Blender*\blender.exe",),
        opens=(".blend", ".glb", ".gltf", ".obj", ".fbx", ".stl", ".py"),
    ),
    "godot": Program(
        "Motor 3D · Godot 4",
        "motor de videojuegos y simulación 3D/2D",
        winget="GodotEngine.GodotEngine",
        exe=(
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\GodotEngine.GodotEngine*\Godot_v*.exe",
            r"%ProgramFiles%\Godot*\Godot*.exe",
            r"%LOCALAPPDATA%\Programs\Godot*\Godot*.exe",
        ),
        opens=(".godot", ".tscn", ".tres", ".gd", ".glb", ".gltf"),
    ),
    "bonsai": Program(
        "BIM",
        "el edificio en IFC",
        github="IfcOpenShell/IfcOpenShell",
        asset=r"bonsai_py3\d+-[\d.]+-win(dows)?(-x64)?\.zip",
        opens=(".ifc",),
        needs="blender",
    ),
    "vscodium": Program(
        "Código",
        "editor de código",
        winget="VSCodium.VSCodium",
        exe=(
            r"%LOCALAPPDATA%\Programs\VSCodium\VSCodium.exe",
            r"%ProgramFiles%\VSCodium\VSCodium.exe",
        ),
        opens=(".py", ".js", ".ts", ".tsx", ".json", ".md", ".html", ".css", ""),
    ),
}

_state: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _log(line: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    except OSError:
        pass


def _expand(pattern: str) -> list[str]:
    path = os.path.expandvars(pattern)
    if "%" in path:  # a variable that is not set
        return []
    return sorted(glob.glob(path), reverse=True)


def find(key: str, *, expand: Callable[[str], list[str]] | None = None) -> str:
    """Where the program is ('' when it is not installed)."""
    expand = expand or _expand
    prog = PROGRAMS[key]
    if prog.needs:
        return find(prog.needs, expand=expand) if bonsai_installed() else ""
    for pattern in prog.exe:
        for hit in expand(pattern):
            if os.path.isfile(hit):
                return hit
    return ""


def bonsai_installed() -> bool:
    """Bonsai is a Blender extension: look for it in Blender's user folders."""
    roots = _expand(r"%APPDATA%\Blender Foundation\Blender\*")
    for root in roots:
        for sub in (
            "extensions\\blender_org\\bonsai",
            "extensions\\user_default\\bonsai",
            "scripts\\addons\\bonsai",
            "scripts\\addons\\blenderbim",
        ):
            if os.path.isdir(os.path.join(root, sub)):
                return True
    return False


def status() -> dict[str, dict[str, Any]]:
    out = {}
    for key, prog in PROGRAMS.items():
        state = _state.get(key, {})
        out[key] = {
            "name": prog.name,
            "what": prog.what,
            "installed": bool(find(key)),
            "installing": bool(state.get("installing")),
            "error": state.get("error", ""),
        }
    return out


# -- installing ------------------------------------------------------------------
def _run(cmd: list[str], timeout: float = 1800.0) -> subprocess.CompletedProcess:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=flags,
        check=False,
    )


def winget_command(package: str, user_scope: bool = True) -> list[str]:
    cmd = [
        "winget",
        "install",
        "--id",
        package,
        "--exact",
        "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    return cmd + (["--scope", "user"] if user_scope else [])


def latest_asset(
    repo: str, pattern: str, get: Callable[[str], Any] | None = None
) -> str:
    """Download link of the newest release asset whose name matches."""
    if get is None:
        import httpx

        def get(url: str) -> Any:
            resp = httpx.get(
                url, timeout=30, headers={"Accept": "application/vnd.github+json"}
            )
            resp.raise_for_status()
            return resp.json()

    releases = get(f"https://api.github.com/repos/{repo}/releases?per_page=30")
    for release in releases if isinstance(releases, list) else []:
        if release.get("draft"):
            continue
        for asset in release.get("assets", []):
            if re.fullmatch(pattern, asset.get("name", ""), flags=re.I):
                return asset["browser_download_url"]
    raise RuntimeError(
        f"No encontré el instalador de {repo} en sus versiones publicadas."
    )


def _download(url: str) -> Path:
    import httpx

    folder = Path(os.environ.get("TEMP", str(HOME))) / "sergio-programas"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / url.rsplit("/", 1)[-1]
    with (
        httpx.stream("GET", url, follow_redirects=True, timeout=1200) as resp,
        path.open("wb") as fh,
    ):
        resp.raise_for_status()
        for chunk in resp.iter_bytes(1 << 20):
            fh.write(chunk)
    return path


def bonsai_commands(blender: str, zip_path: str = "") -> list[list[str]]:
    """Blender's own extension manager first (extensions.blender.org), then
    the release zip when the online repository is not reachable."""
    if zip_path:
        script = (
            "import bpy\n"
            f"bpy.ops.extensions.package_install_files(filepath={zip_path!r}, "
            "repo='user_default', enable_on_install=True)\n"
            "bpy.ops.wm.save_userpref()\n"
            "print('SERGIO_BONSAI_OK')\n"
        )
        return [[blender, "--background", "--factory-startup", "--python-expr", script]]
    return [
        [
            blender,
            "--online-mode",
            "--command",
            "extension",
            "install",
            "--sync",
            "--repo",
            "blender_org",
            "--enable",
            "bonsai",
        ]
    ]


def install(key: str, run: Callable[[list[str]], Any] = _run) -> str:
    """Install one program; returns a line for the owner."""
    prog = PROGRAMS[key]
    if find(key):
        return f"{prog.name}: ya está instalado."
    with _lock:
        _state[key] = {"installing": True}
    try:
        if prog.needs:
            if not find(prog.needs):
                install(prog.needs, run)
            blender = find(prog.needs)
            if not blender:
                raise RuntimeError("Blender no se instaló.")
            done = run(bonsai_commands(blender)[0])
            if getattr(done, "returncode", 1) != 0 or not bonsai_installed():
                url = latest_asset(prog.github, prog.asset)
                zip_path = str(_download(url))
                run(bonsai_commands(blender, zip_path)[0])
        elif prog.winget:
            done = run(winget_command(prog.winget))
            if getattr(done, "returncode", 1) != 0 and not find(key):
                # Some installers only offer a machine-wide install.
                done = run(winget_command(prog.winget, user_scope=False))
            if getattr(done, "returncode", 1) != 0 and not find(key):
                tail = (getattr(done, "stdout", "") or getattr(done, "stderr", ""))[
                    -200:
                ]
                raise RuntimeError(f"winget no pudo instalarlo ({tail.strip()})")
        elif prog.github:
            installer = _download(latest_asset(prog.github, prog.asset))
            run([str(installer), *prog.silent])
        ok = bool(find(key))
        line = f"{prog.name}: {'instalado' if ok else 'instalado; ábralo una vez para terminar'}."
        _log(line)
        with _lock:
            _state[key] = {}
        return line
    except Exception as exc:  # noqa: BLE001 — told to the owner
        _log(f"{prog.name}: falló: {exc}")
        with _lock:
            _state[key] = {"error": str(exc)[:300]}
        return f"{prog.name}: no se pudo instalar ({exc})."


def install_in_background(key: str) -> str:
    if _state.get(key, {}).get("installing"):
        return f"{PROGRAMS[key].name} ya se está instalando."
    with _lock:
        _state[key] = {"installing": True}
    threading.Thread(target=install, args=(key,), daemon=True).start()
    return f"Instalando {PROGRAMS[key].name} (unos minutos)…"


def install_all(run: Callable[[list[str]], Any] = _run) -> list[str]:
    return [install(key, run) for key in PROGRAMS]


# -- opening -------------------------------------------------------------------------
_SAFE_NAME = re.compile(r"[^\w.\- ]+", re.UNICODE)


def save_incoming(name: str, data_b64: str) -> Path:
    """A file Sergio made, saved where the owner keeps his Creator work."""
    clean = _SAFE_NAME.sub("", os.path.basename(name or "")).strip(" .") or "archivo"
    INCOMING.mkdir(parents=True, exist_ok=True)
    path = INCOMING / clean
    path.write_bytes(base64.b64decode(data_b64, validate=True))
    return path


def open_command(key: str, file: str = "") -> list[str]:
    prog = PROGRAMS[key]
    exe = find(key)
    if not exe:
        raise LookupError(f"{prog.name} no está instalado.")
    if key == "bonsai" and file:
        expr = f"import bpy; bpy.ops.bim.load_project(filepath={file!r})"
        return [exe, "--python-expr", expr]
    if file and Path(file).suffix.lower() not in prog.opens and "" not in prog.opens:
        raise ValueError(f"{prog.name} no abre archivos {Path(file).suffix}.")
    return [exe, file] if file else [exe]


def open_program(
    key: str, file: str = "", popen: Callable[..., Any] | None = None
) -> str:
    cmd = open_command(key, file)
    (popen or subprocess.Popen)(cmd, cwd=str(Path(file).parent) if file else None)
    shown = f" con {Path(file).name}" if file else ""
    return f"Abriendo {PROGRAMS[key].name}{shown}."


def skill(args: dict) -> Any:
    """What the server asks for (``creator_apps``): status, install, open."""
    action = str(args.get("action") or "status")
    if action == "status":
        return status()
    key = str(args.get("app") or "")
    if key not in PROGRAMS:
        raise LookupError(f"programa desconocido: {key}")
    if action == "install":
        return install_in_background(key)
    if action == "open":
        file = ""
        if args.get("data"):
            file = str(save_incoming(str(args.get("name") or ""), str(args["data"])))
        return open_program(key, file)
    raise LookupError(f"acción desconocida: {action}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    what = argv[0] if argv else "estado"
    if what == "estado":
        print(json.dumps(status(), ensure_ascii=False, indent=1))
        return 0
    if what == "instalar-todo":
        for line in install_all():
            print(line)
        return 0
    if what == "instalar" and len(argv) > 1:
        print(install(argv[1]))
        return 0
    print(
        "Uso: python -m sergio_escritorio.creator_apps estado | instalar-todo | instalar <programa>"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
