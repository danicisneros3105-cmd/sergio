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
TIME_BUDGET = 4.0  # seconds
OWN_TITLES = ("Sergio",)  # never treat our own (overlay) windows as the target


def _visible_windows() -> list[tuple[int, str]]:
    """Top-level windows in z-order (front first): (handle, title)."""
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    def collect(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
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
    def __init__(self) -> None:
        set_dpi_aware()
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        self._gui = pyautogui

    # -- seeing ------------------------------------------------------------
    def screenshot(self) -> Any:
        import mss
        from PIL import Image

        with mss.mss() as shot:
            raw = shot.grab(shot.monitors[1])
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

    # -- acting ------------------------------------------------------------
    def _glide(self, x: int, y: int) -> None:
        # Travel visibly (the companion orb rides along) so the user always
        # sees where Sergio is about to click.
        self._gui.moveTo(x, y, duration=0.35, tween=self._gui.easeOutQuad)

    def click(self, x: int, y: int, button: str, clicks: int) -> None:
        self._glide(x, y)
        self._gui.click(x, y, clicks=clicks, interval=0.08, button=button)

    def move(self, x: int, y: int) -> None:
        self._glide(x, y)

    def type_text(self, text: str) -> None:
        import pyperclip

        try:
            previous = pyperclip.paste()
        except Exception:  # noqa: BLE001
            previous = None
        pyperclip.copy(text)
        self._gui.hotkey("ctrl", "v")
        time.sleep(0.15)
        if previous is not None:
            pyperclip.copy(previous)

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

    def open_app(self, name: str) -> None:
        # Exactly what a person does: Start menu, type the name, Enter.
        self._gui.press("win")
        time.sleep(0.6)
        self.type_text(name)
        time.sleep(0.8)
        self._gui.press("enter")

    def open_target(self, target: str) -> None:
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


__all__ = ["WindowsBackend"]
