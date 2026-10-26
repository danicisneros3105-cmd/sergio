"""Run the companion app for a few seconds with Windows-only pieces faked.

Used by test_app_starts.py in a separate process; prints one JSON line with
what /diag answered.
"""

import json
import os
import sys
import threading
import types
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HOME = Path(sys.argv[1])
PORT = int(sys.argv[2])
os.environ["LOCALAPPDATA"] = str(HOME)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "windows"))


def fake(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class Quiet:
    def __init__(self, *a, **k):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


class HotKey(Quiet):
    @staticmethod
    def parse(combo):
        return [combo]


keyboard = fake(
    "pynput.keyboard",
    GlobalHotKeys=Quiet,
    HotKey=HotKey,
    Listener=Quiet,
    Key=mock.MagicMock(),
)
fake("pynput", keyboard=keyboard, mouse=fake("pynput.mouse", Listener=Quiet))
fake(
    "sounddevice",
    RawInputStream=Quiet,
    RawOutputStream=Quiet,
    query_devices=lambda kind=None: {"name": "Micrófono de prueba"},
)
fake("pyautogui", size=lambda: (1920, 1080), moveTo=lambda *a, **k: None)
fake("faster_whisper", WhisperModel=mock.MagicMock())

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from sergio_escritorio import app, voice, windows_backend  # noqa: E402


class Backend:
    def __init__(self, speed="rapido"):
        self.speed = speed

    def screenshot(self):
        from PIL import Image

        return Image.new("RGB", (1280, 720))

    def __getattr__(self, _name):
        return lambda *a, **k: None


windows_backend.WindowsBackend = Backend
windows_backend.foreground_is_fullscreen = lambda: False
windows_backend.set_dpi_aware = lambda: None
voice.local_whisper = lambda: None
real_exec = QApplication.exec


probed = threading.Event()


def probe() -> None:
    import time
    import urllib.request

    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/diag", headers={"Authorization": "Bearer t"}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # On a busy machine the control server can take a while to come up:
    # retry for up to 40 s instead of guessing a fixed start-up time.
    deadline = time.monotonic() + 40
    error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            print(
                "DIAG " + opener.open(request, timeout=10).read().decode(), flush=True
            )
            break
        except Exception as exc:  # noqa: BLE001
            error = exc
            time.sleep(0.3)
    else:
        print(f"DIAG-ERROR {error!r}", flush=True)
    probed.set()


def exec_briefly() -> int:
    threading.Thread(target=probe, daemon=True).start()
    # Quit once the probe has its answer (checked from the Qt thread).
    timer = QTimer()
    timer.timeout.connect(lambda: probed.is_set() and QApplication.instance().quit())
    timer.start(100)
    QTimer.singleShot(60_000, QApplication.instance().quit)
    return real_exec()


QApplication.exec = staticmethod(exec_briefly)
HOME.mkdir(parents=True, exist_ok=True)
app.HOME = HOME
app.CONFIG = HOME / "config.json"
app.CONFIG.write_text(
    json.dumps({"token": "t", "port": PORT, "server_url": "http://127.0.0.1:1"})
)
app.run(app.load_config())
print("STARTED-AND-QUIT", flush=True)
