"""Open Sergio in one application window and external links in a browser.

One window, like an app: a page asked for from the notch, the tray or the
voice goes to the Sergio window already open (the server hands it over,
``/v1/app/open``) and that window comes to the front. Only when none is open
does a new one start, first with a loading screen (``resources/cargando.html``)
that becomes the app as soon as the server answers, so the owner never sees
an error page while Sergio starts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote, urlparse

APP_PORTS = {8000, 4173}
SERGIO_PORT = 8000  # the app itself (4173 is the globe, its own window)
LOADING = Path(__file__).resolve().parent / "resources" / "cargando.html"


def is_app_page(url: str) -> bool:
    """Recognize internal app pages, never arbitrary external sites."""
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "http"
            and parsed.hostname in ("127.0.0.1", "localhost")
            and parsed.port in APP_PORTS
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def _api_key() -> str:
    """The server key Sergio Escritorio saved (no Qt, no app import)."""
    path = (
        Path(os.environ.get("LOCALAPPDATA", Path.home()))
        / "SergioEscritorio"
        / "config.json"
    )
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return str(data.get("server_api_key") or "")
    except (OSError, ValueError):
        return ""


def show_in_open_window(url: str, post=None) -> bool:
    """True if the Sergio window already open now shows *url*'s page."""
    parsed = urlparse(url)
    if parsed.port != SERGIO_PORT:
        return False
    path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
    if parsed.fragment:
        path += f"#{parsed.fragment}"
    key = _api_key()
    try:
        if post is None:
            import httpx

            post = httpx.post
        resp = post(
            f"http://127.0.0.1:{SERGIO_PORT}/v1/app/open",
            json={"path": path},
            headers={"Authorization": f"Bearer {key}"} if key else {},
            timeout=4,
        )
        shown = resp.status_code == 200 and bool(resp.json().get("shown"))
    except Exception:  # noqa: BLE001 — server starting: open a window
        return False
    if shown:
        bring_to_front("Sergio")
    return shown


def split_window(on: bool, post=None, opener=None) -> bool:
    """Split (or join) the Sergio window, with the Duo fold. When no Sergio
    window is open, splitting opens one already split (owner, 29 Oct 2026:
    «no puede hacer split screen» — the order used to do nothing then)."""
    url = f"http://127.0.0.1:{SERGIO_PORT}/?dividir={'1' if on else '0'}"
    if show_in_open_window(url, post=post):
        return True
    if not on:
        return False
    (opener or open_app_window)(url)
    return True


def bring_to_front(title: str) -> bool:
    """Restore and raise the window whose title starts with *title*."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        from sergio_escritorio.windows_backend import _visible_windows

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        for hwnd, name in _visible_windows(minimized=True):
            if name == title or name.startswith(title + " "):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                return True
    except Exception:  # noqa: BLE001 — the page changed anyway
        pass
    return False


def _exe_of(hwnd: int) -> str:
    """The program file name behind a window (``msedge.exe``), or ''."""
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32  # type: ignore[attr-defined]
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(handle)


def is_sergio_window(title: str, exe: str) -> bool:
    """Sergio's own app window: an Edge window whose page is called Sergio."""
    return exe == "msedge.exe" and (title == "Sergio" or title.startswith("Sergio "))


def focus_open_window() -> bool:
    """Bring the Sergio window already open to the front, even if it is
    minimized and asleep (then it does not answer ``/v1/app/wait``, and a
    click on Sergio used to open a second, identical window)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        from sergio_escritorio.windows_backend import _visible_windows

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        for hwnd, name in _visible_windows(minimized=True):
            if is_sergio_window(name, _exe_of(hwnd)):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                return True
    except Exception:  # noqa: BLE001 — then a new window opens, as before
        pass
    return False


def _edge() -> str | None:
    return shutil.which("msedge") or next(
        (
            p
            for p in (
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    "Microsoft",
                    "Edge",
                    "Application",
                    "msedge.exe",
                ),
            )
            if os.path.exists(p)
        ),
        None,
    )


def server_up(timeout: float = 0.8) -> bool:
    try:
        import httpx

        return httpx.get(f"http://127.0.0.1:{SERGIO_PORT}/health", timeout=timeout).status_code < 500
    except Exception:  # noqa: BLE001
        return False


def window_url(url: str, up: bool | None = None) -> str:
    """What a new window loads: the page itself when Sergio already answers
    (the window stays on one address, no bar), else the loading screen that
    becomes the page as soon as he does."""
    if urlparse(url).port != SERGIO_PORT or not LOADING.is_file():
        return url
    if up if up is not None else server_up():
        return url
    return f"{LOADING.as_uri()}?to={quote(url, safe='')}"


def _claim_when_shown(seconds: float = 8.0) -> None:
    """The new window gets Sergio's own taskbar button (taskbar.py) as soon
    as it appears, so pinning it pins Sergio, not Edge."""
    import time

    from sergio_escritorio import taskbar

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if taskbar.claim_sergio_windows():
            return
        time.sleep(0.4)


def _launch(edge: str, url: str) -> None:
    if show_in_open_window(url):
        return
    if focus_open_window():
        # Woken up, the window asks the server again: give it the page.
        import time

        for _ in range(6):
            time.sleep(0.5)
            if show_in_open_window(url):
                break
        return
    try:
        subprocess.Popen([edge, f"--app={window_url(url)}", "--window-size=1280,800"])
        threading.Thread(target=_claim_when_shown, daemon=True).start()
    except OSError:
        import logging

        logging.getLogger(__name__).warning("could not open the Sergio window")


def open_app_window(url: str, wait: bool = False) -> None:
    """Internal pages: the one Sergio window; external links: the browser.

    The server is asked from a background thread, so a click in the tray
    never freezes the notch; *wait* runs it here (tests, second instance)."""
    if not is_app_page(url):
        webbrowser.open(url)
        return
    edge = _edge()
    if not edge:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(
            None,
            "Sergio",
            "No se pudo abrir la ventana de Sergio. "
            "Repare o instale Microsoft Edge y vuelva a intentarlo.",
        )
        return
    if wait:
        _launch(edge, url)
        return
    import threading

    threading.Thread(target=_launch, args=(edge, url), daemon=True).start()


__all__ = [
    "bring_to_front",
    "focus_open_window",
    "is_sergio_window",
    "is_app_page",
    "open_app_window",
    "server_up",
    "show_in_open_window",
    "split_window",
    "window_url",
]
