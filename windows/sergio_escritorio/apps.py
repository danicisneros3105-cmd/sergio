"""Open and close apps in a fraction of a second, on the screen you are using.

Before, "abre Spotify" pressed Win, typed the name into the Start menu and
pressed Enter: slow, and the Start menu sometimes picked a web result or the
wrong app, and the window could appear on another monitor behind everything.

Now:

* ``AppIndex`` knows every app of the Start menu (its shortcuts, the Store
  apps from ``Get-StartApps`` and the registered programs), so the name is
  matched at once — also the Spanish way people say it ("bloc de notas",
  "la calculadora", "el Word").
* ``Launcher.open`` starts it directly, waits for its window, moves it to the
  monitor where your mouse is and brings it to the front.
* ``Launcher.close`` finds the app's windows by title *or by program* (the
  Spotify window is titled with the song) and closes them like their X.

Pure logic with the Windows calls behind ``Desktop`` (fake in the tests).
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

log = logging.getLogger(__name__)

# What people say -> other names the app goes by (Start menu name or .exe).
ALIASES: dict[str, list[str]] = {
    "calculadora": ["calculator", "calc"],
    "bloc de notas": ["notepad", "bloc de notas"],
    "notas": ["notepad", "bloc de notas", "sticky notes", "notas rapidas"],
    "explorador": ["explorer", "explorador de archivos", "file explorer"],
    "explorador de archivos": ["explorer", "file explorer"],
    "archivos": ["explorer", "explorador de archivos"],
    "configuracion": ["settings", "configuracion"],
    "ajustes": ["settings", "configuracion"],
    "word": ["winword", "microsoft word"],
    "excel": ["excel", "microsoft excel"],
    "powerpoint": ["powerpnt", "microsoft powerpoint"],
    "outlook": ["outlook", "microsoft outlook", "olk"],
    "correo": ["outlook", "mail", "correo"],
    "teams": ["ms-teams", "microsoft teams", "teams"],
    "edge": ["msedge", "microsoft edge"],
    "navegador": ["chrome", "msedge", "firefox", "brave"],
    "chrome": ["chrome", "google chrome"],
    "google chrome": ["chrome"],
    "firefox": ["firefox", "mozilla firefox"],
    "visual studio code": ["code", "visual studio code"],
    "vs code": ["code", "visual studio code"],
    "vscode": ["code", "visual studio code"],
    "terminal": ["windowsterminal", "terminal", "wt"],
    "simbolo del sistema": ["cmd", "command prompt", "simbolo del sistema"],
    "powershell": ["powershell", "windows powershell", "pwsh"],
    "paint": ["mspaint", "paint"],
    "fotos": ["photos", "fotos", "microsoft photos"],
    "camara": ["windowscamera", "camara", "camera"],
    "reloj": ["clock", "reloj", "alarmas y reloj"],
    "alarmas": ["clock", "reloj", "alarmas y reloj"],
    "tienda": ["microsoft store", "store"],
    "administrador de tareas": ["taskmgr", "task manager", "administrador de tareas"],
    "panel de control": ["control", "control panel", "panel de control"],
    "recortes": ["snippingtool", "snipping tool", "recortes", "herramienta recortes"],
    "enlace movil": ["phone link", "enlace movil", "phoneexperiencehost"],
    "phone link": ["phone link", "enlace movil", "phoneexperiencehost"],
    "whatsapp": ["whatsapp", "whatsapp desktop"],
    "spotify": ["spotify"],
    "discord": ["discord"],
    "telegram": ["telegram", "telegram desktop"],
    "blender": ["blender"],
    "steam": ["steam"],
    "obs": ["obs64", "obs studio"],
    "zoom": ["zoom", "zoom workplace"],
    "capcut": ["capcut"],
    "davinci": ["resolve", "davinci resolve"],
    "davinci resolve": ["resolve", "davinci resolve"],
    "premiere": ["adobe premiere pro", "premiere pro"],
    "photoshop": ["photoshop", "adobe photoshop"],
}
# Apps Windows opens by a link ("ms-settings:") when no shortcut matched.
URI_APPS: dict[str, str] = {
    "configuracion": "ms-settings:",
    "ajustes": "ms-settings:",
    "calculadora": "calculator:",
    "camara": "microsoft.windows.camera:",
    "reloj": "ms-clock:",
    "alarmas": "ms-clock:",
    "tienda": "ms-windows-store:",
    "fotos": "ms-photos:",
    "spotify": "spotify:",
    "whatsapp": "whatsapp:",
    "correo": "outlookmail:",
    "calendario": "outlookcal:",
    "mapas": "bingmaps:",
    "teams": "msteams:",
    "enlace movil": "ms-phone:",
    "phone link": "ms-phone:",
    "recortes": "ms-screenclip:",
    "explorador": "explorer.exe",
    "explorador de archivos": "explorer.exe",
    "archivos": "explorer.exe",
    "bloc de notas": "notepad.exe",
    "paint": "mspaint.exe",
    "administrador de tareas": "taskmgr.exe",
    "panel de control": "control.exe",
    "simbolo del sistema": "cmd.exe",
    "powershell": "powershell.exe",
}
# Shortcuts that are not the app itself.
_NOT_APPS = re.compile(
    r"\b(uninstall|desinstalar|desinstalacion|readme|leeme|help|ayuda|manual|"
    r"license|licencia|release notes|documentation|documentacion|website|"
    r"sitio web|web site|changelog|what s new)\b"
)
_NOISE = {
    "el",
    "la",
    "los",
    "las",
    "app",
    "aplicacion",
    "programa",
    "de",
    "mi",
    "microsoft",
}


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\.(exe|lnk)$", "", text.strip())
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", text).split())


def _core(text: str) -> str:
    words = [w for w in normalise(text).split() if w not in _NOISE]
    return " ".join(words) or normalise(text)


@dataclass(frozen=True)
class App:
    name: str  # as Windows shows it ("Spotify", "Calculadora")
    kind: str  # "lnk" (shortcut path) | "appid" (Store/Start id) | "exe"
    target: str

    @property
    def key(self) -> str:
        return _core(self.name)


def lookup(table: dict[str, Any], spoken: str) -> Any:
    """table[...] by how the name was said: "bloc de notas", "la calculadora"."""
    plain = normalise(spoken)
    words = plain.split()
    while words and words[0] in ("el", "la", "los", "las", "mi", "app", "aplicacion"):
        words = words[1:]
    for key in (plain, " ".join(words), _core(spoken)):
        if key in table:
            return table[key]
    return None


def score(query: str, name: str) -> float:
    """How well a spoken app name matches an app's name (0..100)."""
    q, n = _core(query), _core(name)
    if not q or not n:
        return 0.0
    if q == n:
        return 100.0
    q_words, n_words = q.split(), n.split()
    if n.startswith(q + " ") or (len(q) >= 3 and n.startswith(q)):
        return 90.0 - min(20, len(n) - len(q)) / 2
    if q.startswith(n + " ") and len(n) >= 4:
        return 80.0
    if all(w in n_words for w in q_words):
        return 75.0 - min(15, len(n_words) - len(q_words))
    ratio = difflib.SequenceMatcher(None, q, n).ratio()
    return ratio * 70.0 if ratio >= 0.8 else 0.0


class AppIndex:
    """Every app the user can open, found by the name they say."""

    def __init__(self, apps: Iterable[App] = ()) -> None:
        self.apps: list[App] = []
        self.add(apps)

    def add(self, apps: Iterable[App]) -> None:
        seen = {(a.key, a.kind) for a in self.apps}
        for app in apps:
            if _NOT_APPS.search(normalise(app.name)) or (app.key, app.kind) in seen:
                continue
            seen.add((app.key, app.kind))
            self.apps.append(app)

    def find(self, spoken: str) -> App | None:
        names = [spoken] + (lookup(ALIASES, spoken) or [])
        best: tuple[float, int, App] | None = None
        order = {"appid": 0, "lnk": 1, "exe": 2}
        for app in self.apps:
            points = max(score(n, app.name) for n in names)
            if points < 60:
                continue
            rank = (points, -order.get(app.kind, 3))
            if best is None or rank > best[:2]:
                best = (*rank, app)
        return best[2] if best else None

    # -- persistence (the scan takes a second or two: done once, cached) ----
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [{"name": a.name, "kind": a.kind, "target": a.target} for a in self.apps]
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> AppIndex:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(App(d["name"], d["kind"], d["target"]) for d in data)
        except Exception:  # noqa: BLE001 — no cache yet
            return cls()


def scan_shortcuts(folders: Iterable[Path]) -> list[App]:
    """Start menu shortcuts (.lnk): their file name is the app's name."""
    found = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for lnk in folder.rglob("*.lnk"):
            found.append(App(lnk.stem, "lnk", str(lnk)))
    return found


def start_menu_folders() -> list[Path]:
    roots = [
        os.environ.get("ProgramData", r"C:\ProgramData"),
        os.environ.get("APPDATA", ""),
    ]
    return [
        Path(r) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        for r in roots
        if r
    ]


# The same list through the Start menu's own folder (when Get-StartApps
# is missing or prints nothing).
SHELL_APPS = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
    "(New-Object -ComObject Shell.Application).NameSpace('shell:AppsFolder').Items() | "
    "ForEach-Object { [pscustomobject]@{Name=$_.Name; AppID=$_.Path} } | "
    "ConvertTo-Json -Compress"
)


def scan_start_apps(run: Callable[[list[str]], str] | None = None) -> list[App]:
    """Store and Start apps with their ids (PowerShell's Get-StartApps)."""
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress",
    ]
    if run is None:

        def run(cmd: list[str]) -> str:
            done = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return done.stdout.decode("utf-8", "replace")

    data: Any = []
    for cmd in (command, command[:-1] + [SHELL_APPS]):
        try:
            data = json.loads(run(cmd) or "[]")
        except Exception:  # noqa: BLE001 — try the other way
            log.warning("app scan failed: %s", cmd[-1][:60], exc_info=True)
            data = []
        if data:
            break
    if isinstance(data, dict):
        data = [data]
    return [
        App(str(d.get("Name") or ""), "appid", str(d.get("AppID") or ""))
        for d in data
        if d.get("Name") and d.get("AppID")
    ]


def scan_app_paths() -> list[App]:
    """Programs registered under App Paths (chrome.exe, winword.exe...)."""
    if sys.platform != "win32":
        return []
    import winreg  # type: ignore[import-not-found]

    found = []
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            root = winreg.OpenKey(hive, key_path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                exe = winreg.EnumKey(root, i)
                path = winreg.QueryValue(root, exe)
            except OSError:
                continue
            if path:
                found.append(App(Path(exe).stem, "exe", path.strip('"')))
    return found


def build_index() -> AppIndex:
    index = AppIndex(scan_start_apps())
    index.add(scan_shortcuts(start_menu_folders()))
    index.add(scan_app_paths())
    return index


# -- windows on screen --------------------------------------------------------
@dataclass(frozen=True)
class Window:
    hwnd: int
    title: str
    exe: str  # program file name without .exe, lower case ("spotify")


class Desktop:
    """The few Windows calls the launcher needs (ctypes)."""

    def windows(self) -> list[Window]:
        if sys.platform != "win32":
            return []
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        found: list[Window] = []

        def exe_of(hwnd: int) -> str:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED
            if not handle:
                return ""
            try:
                size = wintypes.DWORD(520)
                buf = ctypes.create_unicode_buffer(520)
                if kernel32.QueryFullProcessImageNameW(
                    handle, 0, buf, ctypes.byref(size)
                ):
                    return Path(buf.value).stem.lower()
                return ""
            finally:
                kernel32.CloseHandle(handle)

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # owned
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if title and title != "Program Manager":
                found.append(Window(int(hwnd), title, exe_of(hwnd)))
            return True

        user32.EnumWindows(collect, 0)
        return found

    def launch(self, app: App) -> None:
        if app.kind == "appid":
            subprocess.Popen(  # noqa: S603 — explorer opens Store/Start apps
                ["explorer.exe", f"shell:AppsFolder\\{app.target}"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.startfile(app.target)  # type: ignore[attr-defined]  # Windows only

    def open_uri(self, uri: str) -> None:
        os.startfile(uri)  # type: ignore[attr-defined]  # Windows only

    def find_program(self, names: Iterable[str]) -> str:
        """A program of that name on the PATH (notepad.exe), or ""."""
        import shutil

        for name in names:
            exe = shutil.which(normalise(name).replace(" ", "") + ".exe") if sys.platform == "win32" else None
            if exe:
                return exe
        return ""

    def start_program(self, names: Iterable[str]) -> bool:
        """Last resort: a program of that name on the PATH (notepad.exe)."""
        exe = self.find_program(names)
        if exe:
            subprocess.Popen([exe], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # noqa: S603
            return True
        return False

    def to_front_here(self, hwnd: int) -> None:
        """Move the window to the monitor with the mouse and focus it."""
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        here = user32.MonitorFromPoint(point, 2)
        there = user32.MonitorFromWindow(hwnd, 2)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        if here and there and here != there:
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            user32.GetMonitorInfoW(here, ctypes.byref(info))
            work = info.rcWork
            zoomed = bool(user32.IsZoomed(hwnd))
            if zoomed:
                user32.ShowWindow(hwnd, 9)
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = min(rect.right - rect.left, work.right - work.left)
            height = min(rect.bottom - rect.top, work.bottom - work.top)
            left = work.left + (work.right - work.left - width) // 2
            top = work.top + (work.bottom - work.top - height) // 2
            user32.SetWindowPos(hwnd, 0, left, top, width, height, 0x0004 | 0x0010)
            if zoomed:
                user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        front = user32.GetForegroundWindow()
        theirs = user32.GetWindowThreadProcessId(front, None)
        mine = kernel32.GetCurrentThreadId()
        user32.keybd_event(0x12, 0, 0, 0)  # a tap of Alt lets us take the focus
        user32.keybd_event(0x12, 0, 2, 0)
        user32.AttachThreadInput(theirs, mine, True)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(theirs, mine, False)

    def close(self, hwnd: int) -> None:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE


def exe_matches(window: Window, names: Iterable[str]) -> bool:
    """The window belongs to the app's program (spotify.exe, winword.exe)."""
    if not window.exe:
        return False
    for name in names:
        core = _core(name).replace(" ", "")
        if core and (
            window.exe == core or (len(core) >= 4 and score(core, window.exe) >= 85)
        ):
            return True
    return False


def title_matches(window: Window, names: Iterable[str]) -> bool:
    title = normalise(window.title)
    for name in names:
        core = _core(name)
        if len(core) >= 3 and re.search(rf"(^| ){re.escape(core)}( |$)", title):
            return True
    return False


def window_matches(window: Window, names: Iterable[str]) -> bool:
    names = list(names)
    return exe_matches(window, names) or title_matches(window, names)


class Launcher:
    """open/close by name, fast, on the screen you are looking at."""

    OWN = ("sergio",)

    def __init__(
        self,
        index: AppIndex | None = None,
        desktop: Desktop | None = None,
        *,
        cache: Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rescan: Callable[[], AppIndex] = build_index,
    ) -> None:
        self.cache = cache
        self.index = (
            index
            if index is not None
            else (AppIndex.load(cache) if cache else AppIndex())
        )
        self.desktop = desktop or Desktop()
        self.sleep = sleep
        self.clock = clock
        self._rescan = rescan
        self._scanned = False
        self._lock = threading.Lock()

    def refresh(self) -> None:
        """Scan the Start menu again (in the background at start-up)."""
        try:
            fresh = self._rescan()
        except Exception:  # noqa: BLE001
            log.warning("app scan failed", exc_info=True)
            return
        with self._lock:
            if fresh.apps:
                self.index = fresh
            self._scanned = True
        if self.cache is not None and fresh.apps:
            try:
                fresh.save(self.cache)
            except OSError:
                pass

    def _names(self, spoken: str, app: App | None) -> list[str]:
        names = [spoken, *(lookup(ALIASES, spoken) or [])]
        if app is not None:
            names.append(app.name)
        return names

    def _ours(self, window: Window) -> bool:
        return normalise(window.title).startswith(self.OWN)

    def resolve(self, spoken: str) -> str:
        """What "abre <spoken>" would open, without opening anything (for
        ``sergio probar``: the test used to open the Calculator and close it
        a second later, which looked like Sergio acting on his own)."""
        app = self.index.find(spoken)
        if app is None and not self._scanned:
            self.refresh()
            app = self.index.find(spoken)
        if app is not None:
            return app.name
        uri = lookup(URI_APPS, spoken)
        if uri:
            return uri
        if self.desktop.find_program(self._names(spoken, None)):
            return spoken
        raise LookupError(f"No encuentro una app llamada «{spoken}» en esta computadora.")

    def open(self, spoken: str, wait: float = 3.0) -> str:
        app = self.index.find(spoken)
        if app is None and not self._scanned:
            self.refresh()  # a new app since the last scan
            app = self.index.find(spoken)
        before = {w.hwnd for w in self.desktop.windows()}
        names = self._names(spoken, app)
        if app is not None:
            self.desktop.launch(app)
            label = app.name
        elif lookup(URI_APPS, spoken):
            self.desktop.open_uri(lookup(URI_APPS, spoken))
            label = spoken
        elif self.desktop.start_program(names):
            label = spoken  # found as a program on the PATH (notepad.exe...)
        else:
            raise LookupError(
                f"No encuentro una app llamada «{spoken}» en esta computadora."
            )
        window = self._wait_window(names, before, wait)
        if window is None:
            # Slow starter (Word, Blender): keep watching in the background
            # and bring it here when it appears.
            threading.Thread(
                target=lambda: self._bring_later(names, before), daemon=True
            ).start()
            return f"opened {label} (still starting)"
        self.desktop.to_front_here(window.hwnd)
        return f"opened {label}"

    def _wait_window(
        self, names: list[str], before: set[int], wait: float
    ) -> Window | None:
        deadline = self.clock() + wait
        existing: Window | None = None
        while True:
            for window in self.desktop.windows():
                if self._ours(window) or not window_matches(window, names):
                    continue
                if window.hwnd not in before:
                    return window  # its new window
                existing = existing or window
            if self.clock() >= deadline:
                return existing  # it was open already: Windows reused it
            self.sleep(0.1)

    def _bring_later(self, names: list[str], before: set[int]) -> None:
        window = self._wait_window(names, before, 25.0)
        if window is not None:
            try:
                self.desktop.to_front_here(window.hwnd)
            except Exception:  # noqa: BLE001
                pass

    def close(self, spoken: str) -> list[str]:
        app = self.index.find(spoken)
        names = self._names(spoken, app)
        windows = [w for w in self.desktop.windows() if not self._ours(w)]
        # By program first: "cierra Word" must not close a browser tab that
        # is titled "how to use word".
        chosen = [w for w in windows if exe_matches(w, names)]
        if not chosen:
            chosen = [w for w in windows if title_matches(w, names)]
        for window in chosen:
            self.desktop.close(window.hwnd)
        return [w.title for w in chosen]


__all__ = [
    "ALIASES",
    "App",
    "AppIndex",
    "Desktop",
    "Launcher",
    "URI_APPS",
    "Window",
    "build_index",
    "exe_matches",
    "normalise",
    "scan_shortcuts",
    "scan_start_apps",
    "score",
    "title_matches",
    "window_matches",
]
