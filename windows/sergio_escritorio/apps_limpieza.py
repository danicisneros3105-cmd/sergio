"""Useless and duplicated apps: found by Sergio, removed with one «sí».

Uninstalling cannot be undone, so the closest thing to doing it alone is:
Sergio finds the candidates by himself (older versions of the same app,
trial software that came with the PC, apps nobody opened in months), shows
the list, and ONE approval with the owner's face removes all of them, quietly
and in the background. Throwaway files (the Windows temp folder, more than a
week old) are cleaned without asking, since nothing there is anyone's work.

Runtimes and drivers are never touched: several Visual C++ or .NET versions
side by side are normal and other programs need them.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PROTECTED = re.compile(
    r"visual c\+\+|\.net|dotnet|directx|driver|controlador|nvidia|intel|amd |amd$|realtek|microsoft windows|"
    r"windows sdk|webview2|redistributable|runtime|update for|security|defender|bios|firmware|chipset|"
    r"python launcher|sergio|openjarvis|blender|ffmpeg|git$|^git |wsl|ubuntu",
    re.I,
)
TRIALWARE = re.compile(
    r"mcafee|wildtangent|candy crush|bubble witch|march of empires|norton security (trial|ultra)|"
    r"booking\.com|dropbox promotion|amazon assistant|ask toolbar|hp jumpstart|cyberlink.*trial",
    re.I,
)
UNUSED_DAYS = 120


@dataclass
class App:
    name: str
    version: str = ""
    publisher: str = ""
    uninstall: str = ""
    quiet: str = ""
    last_used: float = 0.0  # epoch seconds; 0 = unknown


def family(name: str) -> str:
    """«Zoom 5.17.1 (64-bit)» and «Zoom 6.0» -> «zoom»."""
    text = re.sub(r"\(.*?\)|\bv?\d+([.\-_]\d+)*\b|x64|x86|64-bit|32-bit|\bversion\b", " ", name.lower())
    return " ".join(text.split())


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:4]) or (0,)


def audit(apps: list[App], now: float | None = None) -> list[tuple[App, str]]:
    """(app, why) for each candidate; never a protected one."""
    now = now or time.time()
    out: list[tuple[App, str]] = []
    groups: dict[str, list[App]] = {}
    for app in apps:
        if not app.name or PROTECTED.search(app.name):
            continue
        groups.setdefault(family(app.name), []).append(app)
    for same in groups.values():
        if len(same) > 1:
            newest = max(same, key=lambda a: _version(a.version or a.name))
            out += [(a, f"duplicada: hay una versión más nueva ({newest.version or newest.name})")
                    for a in same if a is not newest]
    seen = {id(a) for a, _ in out}
    for app in apps:
        if id(app) in seen or not app.name or PROTECTED.search(app.name):
            continue
        if TRIALWARE.search(app.name):
            out.append((app, "de prueba o preinstalada (bloatware)"))
        elif app.last_used and now - app.last_used > UNUSED_DAYS * 86400:
            days = int((now - app.last_used) / 86400)
            out.append((app, f"sin abrir desde hace {days} días"))
    return out


def uninstall_command(app: App) -> str:
    """Silent uninstall: the app's own quiet command, MSI /X /qn, or winget."""
    if app.quiet:
        return app.quiet
    msi = re.search(r"msiexec(\.exe)?\s+/[ix]\s*(\{[0-9A-F\-]+\})", app.uninstall, re.I)
    if msi:
        return f"MsiExec.exe /X{msi.group(2)} /qn /norestart"
    return f'winget uninstall --name "{app.name}" --exact --silent --accept-source-agreements'


def installed() -> list[App]:  # pragma: no cover — Windows registry
    import winreg

    apps, seen = [], set()
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, path in roots:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                key = winreg.OpenKey(root, winreg.EnumKey(root, i))
            except OSError:
                continue

            def get(name: str, key: Any = key) -> str:
                try:
                    return str(winreg.QueryValueEx(key, name)[0])
                except OSError:
                    return ""

            name = get("DisplayName")
            if not name or get("SystemComponent") == "1" or get("ParentKeyName") or name in seen:
                continue
            seen.add(name)
            apps.append(App(name, get("DisplayVersion"), get("Publisher"), get("UninstallString"),
                            get("QuietUninstallString"), _last_used(get("DisplayIcon"), get("InstallLocation"))))
    return apps


def _last_used(icon: str, folder: str) -> float:  # pragma: no cover — Windows
    """When the app's program was last opened (Windows prefetch), 0 if unknown."""
    exe = Path(icon.split(",")[0].strip('"')).name.upper() if icon else ""
    if not exe.endswith(".EXE"):
        return 0.0
    prefetch = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Prefetch"
    try:
        hits = [p.stat().st_mtime for p in prefetch.glob(f"{exe}-*.pf")]
    except OSError:
        return 0.0
    return max(hits) if hits else 0.0


def remove(apps: list[App], run: Callable[..., Any] = subprocess.run) -> list[tuple[str, bool]]:
    """Uninstall each one quietly; (name, worked)."""
    done = []
    for app in apps:
        try:
            result = run(uninstall_command(app), shell=True, capture_output=True, timeout=900)
            done.append((app.name, getattr(result, "returncode", 1) in (0, 1605, 3010)))
        except Exception:  # noqa: BLE001 — one stubborn app never stops the rest
            done.append((app.name, False))
    return done


def clean_temp(folder: Path | None = None, days: int = 7, now: float | None = None) -> int:
    """Throwaway files older than *days* in the temp folder (no approval needed:
    nothing there is anyone's work; files in use are skipped). Bytes freed."""
    folder = folder or Path(os.environ.get("TEMP") or "/tmp")
    limit = (now or time.time()) - days * 86400
    freed = 0
    try:
        entries = list(folder.iterdir())
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.is_symlink() or entry.stat().st_mtime > limit:
                continue
            size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file()) if entry.is_dir() else entry.stat().st_size
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
            freed += size
        except OSError:
            continue
    return freed


def describe(found: list[tuple[App, str]], limit: int = 12) -> str:
    if not found:
        return "No encontré apps inútiles ni duplicadas."
    lines = [f"• {a.name} — {why}" for a, why in found[:limit]]
    more = f"\n… y {len(found) - limit} más." if len(found) > limit else ""
    return f"Encontré {len(found)} apps para quitar:\n" + "\n".join(lines) + more


__all__ = ["App", "audit", "clean_temp", "describe", "family", "installed", "remove", "uninstall_command"]
