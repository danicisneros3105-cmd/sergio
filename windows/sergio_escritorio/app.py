"""Sergio Escritorio: Sergio's own window, tray icon, hotkeys, voice and hands.

Hotkeys (anywhere in Windows):
  Ctrl+Space       show / hide Sergio's window
  Ctrl+Alt+Space   talk to Sergio (press, speak, press again)
  Ctrl+Alt+End     pause / resume Sergio's control of mouse and keyboard
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

HOME = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SergioEscritorio"
CONFIG = HOME / "config.json"

HOTKEY_WINDOW = "<ctrl>+<space>"
HOTKEY_TALK = "<ctrl>+<alt>+<space>"
HOTKEY_STOP = "<ctrl>+<alt>+<end>"

COLORS = {
    "idle": (10, 108, 255),
    "listening": (220, 50, 60),
    "thinking": (240, 170, 30),
    "speaking": (60, 180, 90),
    "paused": (120, 120, 120),
}

LOADING_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>body{margin:0;height:100vh;display:grid;place-items:center;background:#0d1117;
color:#c9d1d9;font:16px system-ui}.dot{width:56px;height:56px;border-radius:50%%;
background:#2596be;margin:0 auto 18px;animation:p 1.4s infinite}
@keyframes p{50%%{transform:scale(.8);opacity:.6}}</style></head><body><div>
<div class="dot"></div>Sergio está despertando…</div><script>
const u=%(url)s;setInterval(()=>fetch(u+'/health',{mode:'no-cors'})
.then(()=>location.replace(u)).catch(()=>{}),1500);</script></body></html>"""


def load_config() -> dict[str, Any]:
    data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))  # PowerShell adds a BOM
    data.setdefault("server_url", "http://localhost:8000")
    data.setdefault("port", 8765)
    return data


def make_icon(state: str) -> Any:
    from PIL import Image, ImageDraw

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, size - 2, size - 2), fill=COLORS.get(state, COLORS["idle"]))
    draw.ellipse((18, 18, size - 18, size - 18), outline=(255, 255, 255), width=5)
    return image


def single_instance() -> bool:
    """False if Sergio Escritorio is already running (named mutex)."""
    if sys.platform != "win32":
        return True
    import ctypes

    ctypes.windll.kernel32.CreateMutexW(None, False, "SergioEscritorioUnico")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


class SergioDesktop:
    def __init__(self, config: dict[str, Any]) -> None:
        from sergio_escritorio.control import Controller, make_server
        from sergio_escritorio.voice import SergioClient, VoiceChat
        from sergio_escritorio.windows_backend import WindowsBackend

        self.config = config
        self.url = config["server_url"].rstrip("/")
        self.window: Any = None
        self.visible = True
        self.tray: Any = None
        self.state = "idle"
        self.controller = Controller(WindowsBackend(), on_activity=self._activity)
        self.server = make_server(self.controller, config["token"], int(config["port"]))
        self.voice = VoiceChat(
            SergioClient(self.url), notify=self.notify, on_state=self.set_state
        )

    # -- feedback ----------------------------------------------------------
    def notify(self, message: str) -> None:
        logging.info(message)
        if self.tray is not None:
            try:
                self.tray.notify(message[:250], "Sergio")
            except Exception:  # noqa: BLE001
                pass

    def set_state(self, state: str) -> None:
        self.state = state
        if self.tray is not None:
            shown = (
                "paused" if not self.controller.enabled and state == "idle" else state
            )
            self.tray.icon = make_icon(shown)

    def _activity(self, what: str) -> None:
        logging.info("control: %s", what)
        if self.tray is not None:
            self.tray.title = f"Sergio — {what}"

    # -- actions -----------------------------------------------------------
    def toggle_window(self) -> None:
        if self.window is None:
            return
        if self.visible:
            self.window.hide()
        else:
            self.window.show()
            self.window.restore()
        self.visible = not self.visible

    def toggle_control(self) -> None:
        self.controller.enabled = not self.controller.enabled
        self.notify(
            "Control de pantalla ACTIVADO"
            if self.controller.enabled
            else "Control de pantalla PAUSADO: Sergio no tocará el mouse ni el teclado"
        )
        self.set_state(self.state)

    def quit(self) -> None:
        self.server.shutdown()
        if self.tray is not None:
            self.tray.stop()
        if self.window is not None:
            self.window.destroy()

    # -- wiring ------------------------------------------------------------
    def _start_tray(self) -> None:
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem(
                "Mostrar / ocultar  (Ctrl+Espacio)",
                lambda: self.toggle_window(),
                default=True,
            ),
            pystray.MenuItem("Hablar  (Ctrl+Alt+Espacio)", lambda: self.voice.toggle()),
            pystray.MenuItem(
                "Sergio puede usar mouse y teclado  (Ctrl+Alt+Fin)",
                lambda: self.toggle_control(),
                checked=lambda _item: self.controller.enabled,
            ),
            pystray.MenuItem("Salir", lambda: self.quit()),
        )
        self.tray = pystray.Icon("Sergio", make_icon("idle"), "Sergio", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _start_hotkeys(self) -> None:
        from pynput import keyboard

        keyboard.GlobalHotKeys(
            {
                HOTKEY_WINDOW: self.toggle_window,
                HOTKEY_TALK: self.voice.toggle,
                HOTKEY_STOP: self.toggle_control,
            }
        ).start()

    def run(self) -> None:
        import webview

        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self._start_tray()
        self._start_hotkeys()
        self.window = webview.create_window(
            "Sergio",
            html=LOADING_HTML % {"url": json.dumps(self.url)},
            width=480,
            height=800,
            min_size=(380, 500),
            text_select=True,
        )

        def on_closing() -> bool:
            # Closing the window only hides it: Sergio keeps living in the tray.
            self.window.hide()
            self.visible = False
            return False

        self.window.events.closing += on_closing
        self.notify("Sergio está listo. Ctrl+Alt+Espacio para hablarle.")
        webview.start(private_mode=False, storage_path=str(HOME / "webview"))


def main() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=HOME / "escritorio.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not single_instance():
        return
    from sergio_escritorio.windows_backend import set_dpi_aware

    set_dpi_aware()  # before any window or screenshot exists
    try:
        SergioDesktop(load_config()).run()
    except Exception:
        logging.exception("Sergio Escritorio crashed")
        raise


if __name__ == "__main__":
    main()
