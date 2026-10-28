"""Real Windows implementation of the control backend.

* Screen: ``mss`` (fast, all monitors' primary).
* Mouse/keyboard: ``pyautogui`` (fail-safe on: top-left corner aborts).
* Text: pasted through the clipboard so accents and ñ work, then the user's
  clipboard is restored.
* What is on screen: Windows UI Automation via ``pywinauto`` — the names of
  buttons, fields, links… of the window the user is looking at. Local models
  act far more reliably on that list than on raw pixels.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
from typing import Any

INTERACTIVE = {
    "Button",
    "CheckBox",
    "ComboBox",
    "DataItem",
    "Edit",
    "Hyperlink",
    "ListItem",
    "MenuItem",
    "RadioButton",
    "SplitButton",
    "TabItem",
    "TreeItem",
    "Document",
}
MAX_ELEMENTS = 150
MAX_DEPTH = 25
TIME_BUDGET = 2.0  # seconds (a look must never feel slow)
OWN_TITLES = ("Sergio",)  # never treat our own (overlay) windows as the target


def _visible_windows(minimized: bool = False) -> list[tuple[int, str]]:
    """Top-level windows in z-order (front first): (handle, title)."""
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    def collect(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.IsIconic(hwnd) and not minimized:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title and title not in ("Program Manager",):
            found.append((hwnd, title))
        return True

    user32.EnumWindows(collect, 0)
    return found


def no_captureblt() -> None:
    """Grab the screen without CAPTUREBLT: with it every grab makes Windows
    recompose the layered windows and the mouse cursor flickers and drags
    (owner, 26 Oct 2026: «realentiza el cursor»). Sergio's own notch and
    companion are left out of the picture, which is right."""
    import importlib

    for name in ("mss.windows.gdi", "mss.windows"):  # mss 10 and mss 9
        try:
            module = importlib.import_module(name)
        except Exception:  # noqa: BLE001 — not Windows, or another layout
            continue
        if hasattr(module, "CAPTUREBLT"):
            module.CAPTUREBLT = 0


def set_dpi_aware() -> None:
    """Use real pixels everywhere.

    Laptops usually run at 125-150 % scaling. Without this, UI Automation
    reports physical pixels while the mouse works in scaled ones, and clicks
    land in the wrong place.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — older Windows / already set
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def foreground_title() -> str:
    """Title of the window in front ('' off Windows or on error)."""
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()
    except Exception:  # noqa: BLE001
        return ""


def foreground_is_fullscreen() -> bool:
    """True when the active window covers its whole monitor (video, game)."""
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    hwnd = user32.GetForegroundWindow()
    if not hwnd or hwnd in (user32.GetDesktopWindow(), user32.GetShellWindow()):
        return False
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    m = info.rcMonitor
    return (rect.left, rect.top, rect.right, rect.bottom) == (
        m.left,
        m.top,
        m.right,
        m.bottom,
    )


class WindowsBackend:
    def __init__(self, speed: str = "rapido") -> None:
        set_dpi_aware()
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.0  # no built-in wait after every key
        self._gui = pyautogui
        import threading
        from pathlib import Path

        from sergio_escritorio.apps import Launcher

        home = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SergioEscritorio"
        # Every app of the Start menu, by name: opening one is instant.
        self.launcher = Launcher(cache=home / "apps.json")
        threading.Thread(target=self.launcher.refresh, daemon=True).start()
        from sergio_escritorio.human import WindowsHands

        # Mouse and keyboard like a person: curved, eased moves and typing
        # key by key, so the user can follow (and it never looks like a bot).
        self.hands = WindowsHands(speed=speed)

    # -- seeing ------------------------------------------------------------
    def screenshot(self) -> Any:
        import mss
        from PIL import Image

        # One capture context per thread, kept open: opening it costs more
        # than the capture itself (the live eye grabs 15 times a second).
        local = getattr(self, "_mss_local", None)
        if local is None:
            local = self._mss_local = threading.local()
        if getattr(local, "shot", None) is None:
            no_captureblt()
            local.shot = mss.mss()
        shot = local.shot
        if True:
            # The monitor you are using (where the mouse is), not always the
            # main one: Sergio sees and acts on the screen in front of you.
            x, y = self._gui.position()
            monitor = next(
                (
                    m
                    for m in shot.monitors[1:]
                    if m["left"] <= x < m["left"] + m["width"]
                    and m["top"] <= y < m["top"] + m["height"]
                ),
                shot.monitors[1],
            )
            self.shot_origin = (monitor["left"], monitor["top"])
            raw = shot.grab(monitor)
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    def _target_window(self) -> tuple[int, str] | None:
        """The window the user is working in (not Sergio's own window)."""
        for hwnd, title in _visible_windows():
            if not title.startswith(OWN_TITLES):
                return hwnd, title
        return None

    def ui(self) -> dict:
        windows = [title for _, title in _visible_windows()]
        target = self._target_window()
        if target is None:
            return {"window": "", "windows": windows, "elements": []}
        hwnd, title = target
        elements = []
        try:
            from pywinauto.uia_element_info import UIAElementInfo

            # Lazy walk with depth and time limits: big pages (Chrome) have
            # thousands of nodes and must not freeze Sergio.
            deadline = time.monotonic() + TIME_BUDGET
            root = UIAElementInfo(hwnd)
            for info in root.iter_descendants(depth=MAX_DEPTH):
                if time.monotonic() > deadline:
                    break
                kind = info.control_type
                if kind not in INTERACTIVE:
                    continue
                rect = info.rectangle
                if rect.width() <= 2 or rect.height() <= 2:
                    continue
                name = (info.name or "").strip()
                if not name and kind not in ("Edit", "Document"):
                    continue
                elements.append(
                    {
                        "name": name,
                        "type": kind,
                        "rect": (rect.left, rect.top, rect.right, rect.bottom),
                    }
                )
                if len(elements) >= MAX_ELEMENTS:
                    break
        except Exception:  # noqa: BLE001 — some apps expose no UIA tree
            pass
        return {"window": title, "windows": windows, "elements": elements}

    def find_elements(self, query: str, budget: float = 1.5) -> list[dict]:
        """Named elements of the window in front, for clicking one by name.
        Stops as soon as an exact match turns up (usually well under a
        second), screen coordinates."""
        from sergio_escritorio.control import _plain

        target = self._target_window()
        if target is None:
            return []
        want = _plain(query)
        found: list[dict] = []
        try:
            from pywinauto.uia_element_info import UIAElementInfo

            deadline = time.monotonic() + budget
            for info in UIAElementInfo(target[0]).iter_descendants(depth=MAX_DEPTH):
                if time.monotonic() > deadline or len(found) >= 800:
                    break
                name = (info.name or "").strip()
                if not name or len(name) > 120:
                    continue
                rect = info.rectangle
                if rect.width() <= 2 or rect.height() <= 2:
                    continue
                found.append(
                    {
                        "name": name,
                        "type": info.control_type,
                        "x": (rect.left + rect.right) // 2,
                        "y": (rect.top + rect.bottom) // 2,
                        "w": rect.width(),
                        "h": rect.height(),
                    }
                )
                if _plain(name) == want and info.control_type in INTERACTIVE:
                    break  # exact: no need to look further
        except Exception:  # noqa: BLE001 — some apps expose no UIA tree
            pass
        return found

    # -- acting ------------------------------------------------------------
    def click(self, x: int, y: int, button: str, clicks: int) -> None:
        self.hands.click(x, y, button, clicks)

    def move(self, x: int, y: int) -> None:
        self.hands.move(x, y)

    def type_text(self, text: str) -> None:
        if len(text) <= 1500 or self.hands.speed == "rapido":
            self.hands.type_text(text)  # key by key, at a human rhythm
            return
        import pyperclip  # a whole document: paste it

        try:
            previous = pyperclip.paste()
        except Exception:  # noqa: BLE001
            previous = None
        pyperclip.copy(text)
        self._gui.hotkey("ctrl", "v")
        time.sleep(0.15)
        if previous is not None:
            pyperclip.copy(previous)

    def user_took_over(self) -> bool:
        return self.hands.user_took_over()

    def hotkey(self, keys: list[str]) -> None:
        aliases = {
            "windows": "win",
            "control": "ctrl",
            "escape": "esc",
            "return": "enter",
        }
        self._gui.hotkey(*[aliases.get(k, k) for k in keys])

    def scroll(self, amount: int, x: int | None, y: int | None) -> None:
        self._gui.scroll(amount * 120, x=x, y=y)

    def open_app(self, name: str) -> str:
        """Straight from the Start menu's list (no typing), on your screen."""
        try:
            return self.launcher.open(name)
        except LookupError:
            from sergio_escritorio.apps import normalise
            from sergio_escritorio.quick import SITES

            site = SITES.get(normalise(name))
            if site:  # not installed as an app: its website
                self.open_target(site)
                return f"opened {site} (web: no app installed)"
            raise

    def open_target(self, target: str) -> None:
        from sergio_escritorio.launch import is_app_page, open_app_window

        if is_app_page(target):  # the 3D globe: its own window, no browser bars
            open_app_window(target)
            return
        if "://" in target or os.path.exists(target):
            os.startfile(target)  # type: ignore[attr-defined]  # Windows only
        else:
            subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)

    def focus(self, title: str) -> bool:
        needle = title.lower()
        for hwnd, window_title in _visible_windows():
            if needle in window_title.lower():
                user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                return True
        return False

    def active_window(self) -> str:
        """Title of the window in front (to verify what an action did)."""
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()

    def close_app(self, name: str) -> list[str]:
        """Close the app's windows like their X (so it can ask to save):
        found by program (Spotify's title is the song) or by title."""
        closed = self.launcher.close(name)
        if not closed:
            from sergio_escritorio.apps import ALIASES, lookup, normalise

            for exe in [
                normalise(name).replace(" ", ""),
                *(lookup(ALIASES, name) or []),
            ]:
                done = subprocess.run(
                    ["taskkill", "/im", f"{exe.replace(' ', '')}.exe"],
                    capture_output=True,
                    text=True,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if done.returncode == 0:
                    closed.append(f"{exe}.exe")
                    break
        return closed

    def shell(self, command: str, timeout: float) -> dict:
        from sergio_escritorio import files

        return files.run_shell(command, timeout=timeout)

    def make_video(self, options: dict) -> str:
        from sergio_escritorio import media

        source = options.pop("source")
        return media.make_video(
            source,
            aspect=str(options.get("aspect") or "16:9"),
            clip_seconds=float(options.get("clip_seconds") or 0),
            max_seconds=float(options.get("max_seconds") or 0),
            title=str(options.get("title") or ""),
            music=str(options.get("music") or ""),
            name=str(options.get("name") or ""),
        )

    def blender(self, script: str) -> str:
        from sergio_escritorio import media

        return media.run_blender(script)

    def organize(self, folder: str, by: str, apply: bool) -> dict:
        from sergio_escritorio import files

        return files.organize(folder, by=by, apply=apply)

    def undo_organize(self) -> int:
        from sergio_escritorio import files

        return files.undo()

    def python(self, code: str, timeout: float) -> dict:
        from sergio_escritorio import files

        return files.run_python(code, timeout=timeout)


__all__ = ["WindowsBackend"]
