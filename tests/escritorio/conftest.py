"""Make the Windows package (windows/sergio_escritorio) importable in tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "windows"))


class FakeDesktop:
    """Records what Sergio would do to the Windows desktop."""

    def __init__(self):
        self.calls = []

    def screenshot(self):
        from PIL import Image

        return Image.new("RGB", (2560, 1440), (10, 20, 30))

    def ui(self):
        return {
            "window": "WhatsApp",
            "windows": ["WhatsApp", "Spotify"],
            "elements": [
                {"name": "Buscar", "type": "Edit", "rect": (100, 100, 300, 140)},
                {"name": "Enviar", "type": "Button", "rect": (900, 1000, 960, 1040)},
            ],
        }

    def click(self, x, y, button, clicks):
        self.calls.append(("click", x, y, button, clicks))

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def type_text(self, text):
        self.calls.append(("type", text))

    def hotkey(self, keys):
        self.calls.append(("hotkey", keys))

    def scroll(self, amount, x, y):
        self.calls.append(("scroll", amount, x, y))

    def open_app(self, name):
        self.calls.append(("open_app", name))

    def open_target(self, target):
        self.calls.append(("open", target))

    def focus(self, title):
        self.calls.append(("focus", title))
        return title.lower() in "whatsapp"


@pytest.fixture
def desktop():
    return FakeDesktop()


@pytest.fixture
def control_server(desktop):
    """A real control server on a free port, backed by the fake desktop."""
    import threading

    from sergio_escritorio.control import Controller, make_server

    controller = Controller(desktop, sleep=lambda _s: None)
    server = make_server(controller, "secreto", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield controller, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
