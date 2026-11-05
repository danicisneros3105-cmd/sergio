"""Sergio on Windows: a cursor companion you talk to. No app window.

* A small orb follows the mouse pointer and shows what Sergio is doing.
* Say "Sergio, ..." (wake word) or press Ctrl+Space and speak.
* Sergio can read the screen and use the mouse and keyboard like you.
* Ctrl+Alt+End pauses / resumes that control at once.
* A tray icon (next to the clock) holds the few settings and "Quit".
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

HOME = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SergioEscritorio"
CONFIG = HOME / "config.json"

HOTKEY_TALK = "<ctrl>+<space>"
HOTKEY_STOP = "<ctrl>+<alt>+<end>"
HOTKEY_CAMERA = "<ctrl>+<alt>+c"

# What the companion says while Sergio uses the screen (by result prefix).
ACTIVITY = {
    "click": "Haciendo clic",
    "double_click": "Doble clic",
    "right_click": "Clic derecho",
    "move": "Moviendo el puntero",
    "typed": "Escribiendo",
    "pressed": "Pulsando teclas",
    "scrolled": "Desplazando",
}


def load_config() -> dict[str, Any]:
    """The settings; a missing or broken file never stops Sergio from opening
    (owner, 29 Oct 2026: «la app no abre»): it starts with the defaults and
    keeps the broken file aside to look at."""
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))  # PowerShell adds a BOM
        if not isinstance(data, dict):
            raise ValueError("config is not an object")
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError) as exc:
        logging.warning("config.json no se pudo leer (%s); uso los valores por defecto", exc)
        try:
            CONFIG.replace(CONFIG.with_suffix(".roto.json"))
        except OSError:
            pass
        data = {}
    data.setdefault("server_url", "http://localhost:8000")
    data.setdefault("port", 8765)
    data["wake_word"] = False
    data.setdefault("show_companion", True)
    data.setdefault("show_notch", True)
    data.setdefault("theme", "Océano")
    data.setdefault("eyes", True)
    data.setdefault("cursor_size", 9.0)
    # Set a first-install default without migrating an existing voice identity.
    if data.get("voice") is None:
        data["voice"] = "gemini:Algenib"  # male, deep, relaxed and a bit husky
    # Muse-style personalisation and the brain's effort.
    # Sergio is not personalised any more (only agents are): one name, one
    # look, one way of being, whatever an older config says.
    data.update(
        name="Sergio",
        theme="Océano",
        style="orbe",
        body="#f3e9d2",
        eye_style="ovalos",
        mouth="ninguna",
        accessory="ninguno",
        personality="Caballero británico",
    )
    if data.get("voice_rate") in (None, "+5%"):  # the old default sounded rushed
        data["voice_rate"] = "+0%"
    data.setdefault("effort", "auto")
    data.setdefault("model", "")  # «Modelo» in the control center; empty = automatic
    # Talk like a phone call (Gemini Live); "turnos" = one question at a time.
    data.setdefault("conversation", "llamada")
    # Always on: the call stays open (reconnects by itself, never hangs up on
    # silence); only Ctrl+Space (or the tile) puts it away until you call him.
    data["call_always"] = False
    data.setdefault("live_screen", True)
    data.setdefault("allow_turn_fallback", False)
    data.setdefault("reduce_motion", False)
    # Mental gym: an exercise you cannot skip every 12 minutes (real time).
    data.setdefault("gym", True)
    # ...but only as an optional add-on (owner, 2 Nov 2026): off until added,
    # here or in Settings → Complementos (``/v1/personal/complementos``).
    data.setdefault("gym_addon", False)
    data.setdefault("gym_camera", True)  # look (locally) that you are there first
    if data.get("gym_minutes") in (None, 28, 28.0):  # the old default
        data["gym_minutes"] = 12
    return data


def save_config(data: dict[str, Any]) -> None:
    CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")


def activity_caption(result: str) -> str:
    """Spanish caption for a control-server result like 'opened Spotify'."""
    head, _, rest = result.partition(" ")
    if head == "opened" and rest:
        return f"Abriendo {rest}"
    if head == "focused" and rest:
        return f"Cambiando a {rest}"
    return ACTIVITY.get(head, "")


MARK = Path(__file__).with_name("resources") / "sergio.png"  # scripts/marca_sergio.py


def make_icon(state: str = "idle") -> object:
    """Sergio's mark (blue disc, white ring) as a Pillow image, for the shortcuts' .ico.
    Paused, it is shown in grey."""
    from PIL import Image, ImageOps

    image = Image.open(MARK).convert("RGBA").resize((256, 256))
    if state == "paused":
        grey = ImageOps.grayscale(image).point(lambda v: 90 + v * 0.45)
        image = Image.merge("RGBA", (grey, grey, grey, image.getchannel("A")))
    return image


def single_instance() -> bool:
    """False if Sergio is already running (named mutex)."""
    if sys.platform != "win32":
        return True
    import ctypes

    ctypes.windll.kernel32.CreateMutexW(None, False, "SergioCompanero")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def tray_icon(colour: Any) -> Any:
    """Sergio's mark for the tray; faded when Sergio is paused."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

    from sergio_escritorio.companion import STATE_COLORS

    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    paused = QColor(colour) == QColor(STATE_COLORS.get("paused", "#8e8e93"))
    p.setOpacity(0.45 if paused else 1.0)
    p.drawPixmap(0, 0, 64, 64, QPixmap(str(MARK)))
    p.end()
    return QIcon(pix)


def companion_delay(pixels: float) -> float:
    """Seconds the companion needs to arrive before the click (0.08 to 0.3)."""
    return round(min(0.3, max(0.08, 0.08 + pixels / 4000)), 3)


def _quick_kind(kind: str, arg: str = "") -> Any:
    from sergio_escritorio.quick import Quick

    return Quick(kind, arg)


_WSL_KEEPALIVE: subprocess.Popen[bytes] | None = None
_WSL_LOCK = threading.Lock()


def stop_wsl_keepalive() -> None:
    """Close the hidden WSL keepalive process when Sergio Escritorio exits."""
    global _WSL_KEEPALIVE
    with _WSL_LOCK:
        proc, _WSL_KEEPALIVE = _WSL_KEEPALIVE, None
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass


def ensure_server_running(url: str = "http://localhost:8000") -> None:
    """Wake up the local WSL Sergio service and keep WSL alive while Sergio Escritorio runs."""
    global _WSL_KEEPALIVE
    if sys.platform != "win32":
        return
    import httpx

    # Always keep one lightweight WSL process open so Windows 11's vmIdleTimeout
    # never suspends Ubuntu or stops user@1000.service while Sergio is open.
    with _WSL_LOCK:
        if _WSL_KEEPALIVE is None or _WSL_KEEPALIVE.poll() is not None:
            try:
                _WSL_KEEPALIVE = subprocess.Popen(
                    [
                        "wsl.exe",
                        "-d",
                        "Ubuntu",
                        "-e",
                        "bash",
                        "-lc",
                        "systemctl --user start sergio.service sergio-extensiones.service && exec sleep infinity",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                )
            except Exception:  # noqa: BLE001
                pass

    probe = url.rstrip("/").replace("://localhost", "://127.0.0.1") + "/"
    try:
        if httpx.get(probe, timeout=1.5).status_code < 500:
            return
    except Exception:  # noqa: BLE001
        pass
    deadline = time.monotonic() + 18.0
    while time.monotonic() < deadline:
        try:
            if httpx.get(probe, timeout=1.5).status_code < 500:
                return
        except Exception:  # noqa: BLE001
            time.sleep(0.4)



def main() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    from sergio_escritorio.diagnose import setup_log

    setup_log(HOME / "sergio.log")
    if not single_instance():
        try:
            url = str(load_config().get("server_url") or "http://localhost:8000")
        except Exception:  # noqa: BLE001
            url = "http://localhost:8000"
        ensure_server_running(url)
        from sergio_escritorio.launch import open_app_window

        open_app_window(url, wait=True)  # this process ends right after
        return
    from sergio_escritorio.windows_backend import set_dpi_aware

    set_dpi_aware()  # before Qt creates anything
    cfg: dict[str, Any] = {}
    try:
        cfg = load_config()
        threading.Thread(
            target=ensure_server_running,
            args=(str(cfg.get("server_url") or "http://localhost:8000"),),
            daemon=True,
        ).start()
        run(cfg)
    except Exception as exc:
        logging.exception("Sergio crashed")
        _still_open(str(cfg.get("server_url") or "http://localhost:8000"), exc)
        raise


def _still_open(url: str, exc: BaseException) -> None:
    """A crash while starting never leaves the owner with nothing (owner,
    29 Oct 2026: «la app no abre»): the Sergio window opens anyway (chat,
    voice and everything on the server keep working) and a plain message
    says what failed and where the log is. The app runs with pythonw, so
    without this a crash was silent."""
    try:
        from sergio_escritorio.launch import open_app_window

        open_app_window(url, wait=True)
    except Exception:  # noqa: BLE001
        logging.exception("tampoco se pudo abrir la ventana")
    text = (
        "Sergio para el escritorio no pudo arrancar del todo, así que le abrí "
        "la ventana de Sergio. El chat y la voz funcionan ahí.\n\n"
        f"Qué falló: {str(exc)[:200]}\n\n"
        f"El detalle está en: {HOME / 'sergio.log'}\n"
        "Pulse «Actualizar» en la ventana de Sergio para repararlo."
    )
    try:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, "Sergio", 0x40)  # information
    except Exception:  # noqa: BLE001
        pass


def start_click_watch(on_click: Callable[[], None], every: float = 0.05) -> None:
    """Call *on_click* when the left mouse button goes down, by polling
    (Windows only; no hook, so the cursor never waits for Python)."""
    if sys.platform != "win32":
        return
    import ctypes

    state = ctypes.windll.user32.GetAsyncKeyState

    def loop() -> None:
        was = False
        while True:
            down = bool(state(0x01) & 0x8000)  # VK_LBUTTON
            if down and not was:
                try:
                    on_click()
                except Exception:  # noqa: BLE001 — a hop is never worth a crash
                    pass
            was = down
            time.sleep(every)

    threading.Thread(target=loop, name="click-watch", daemon=True).start()


def run(config: dict[str, Any]) -> None:
    config.update(wake_word=False, call_always=False)
    # Hand the interpreter over every 2 ms instead of 5: the audio callbacks,
    # the notch and the control server get their turn sooner while the eyes
    # or a capture are busy (voice and cursor without stutter).
    sys.setswitchinterval(0.002)
    from pynput import keyboard
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

    from sergio_escritorio.companion import STATE_COLORS, Companion
    from sergio_escritorio.control import Controller, make_server
    from sergio_escritorio.notch import Notch
    from sergio_escritorio.voice import Assistant, Ears, SergioClient, api_base
    from sergio_escritorio.windows_backend import (
        WindowsBackend,
        foreground_is_fullscreen,
    )

    from sergio_escritorio import taskbar

    taskbar.claim_process()  # one taskbar identity: Sergio, not Python
    # Exact scaling (125 %, 150 %…) instead of rounding: sharp text and shapes.
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        _Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    from PySide6.QtGui import QIcon

    app.setWindowIcon(QIcon(str(MARK)))  # the mark on every window and the taskbar
    from sergio_escritorio import estilo as _estilo

    _estilo.load_fonts()  # the house typeface for every window
    app.setQuitOnLastWindowClosed(False)
    from sergio_escritorio import companion as companion_mod
    from sergio_escritorio.camera import CameraFeed, CameraWindow
    from sergio_escritorio.character import PERSONALITIES, apply_config
    from sergio_escritorio.launch import open_app_window
    from sergio_escritorio.listen import set_wake_name
    from sergio_escritorio.panel import ControlCenter, PanelActions, Toggle

    apply_config(config)
    set_wake_name(config["name"])
    companion_mod.ORB = float(config["cursor_size"])
    show_notch = bool(config["show_notch"])
    companion = Companion(captions=not show_notch)
    feed = CameraFeed()
    camera_window = CameraWindow(feed)
    # Sergio sees in the background; the window only on request (owner,
    # 29 Oct 2026). The one thing asked is the camera, once.
    camera_window.show_window = bool(config.get("vista_visible", False))
    # Hidden while it fails (owner, 2 Nov 2026); «sergio_ve» brings it back.
    camera_window.vista_off = config.get("sergio_ve") is not True
    VISTA_OFF = "La vista de la cámara está escondida por ahora; Sergio sigue reconociéndole por detrás."

    def camera_allowed() -> bool:
        if config.get("camera_ok") is True:
            return True
        if config.get("camera_ok") is False:
            return False
        from PySide6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            None,
            "Sergio",
            "¿Puedo usar la cámara para verle y reconocerle?\n\n"
            "No se abre ninguna ventana: Sergio mira por detrás y lo que ve se "
            "queda en este equipo. Puede cambiarlo cuando quiera en Ajustes.",
        )
        config["camera_ok"] = answer == QMessageBox.StandardButton.Yes
        try:
            save_config(config)
        except OSError:
            pass
        return config["camera_ok"]

    camera_window.allow = camera_allowed
    notch = Notch(fullscreen_app=foreground_is_fullscreen)
    # Live Activities: every long job in the notch (the dúo shows two).
    from sergio_escritorio.activities import Activities

    activities = Activities()
    notch.activities = activities
    notch.name = config["name"]

    panels: list[ControlCenter] = []  # created once the tray actions exist

    def show_state(name: str) -> None:
        # Hidden by the user? Like Clicky, he still shows up while he listens,
        # thinks or talks, and leaves when done.
        if not config.get("show_companion", True):
            companion.setVisible(name != "idle" or companion.pointing)
        companion.set_state(name)
        notch.set_state(name)
        for panel in panels:
            panel.set_state(name)

    def show_text(text: str, seconds: float = 0.0) -> None:
        companion.say(text, seconds)
        notch.say(text, seconds)
        for panel in panels:
            panel.show_answer(text)
        if camera_window.isVisible():
            camera_window.show_overlay(text)

    class Bridge(QObject):
        """Thread-safe hop from worker threads to the Qt (UI) thread."""

        state = Signal(str)
        caption = Signal(str)
        level = Signal(float)
        talk = Signal()
        toggle = Signal()
        camera = Signal()
        peek = Signal()  # open the camera window (Sergio is looking)
        point = Signal(int, int, str)  # fly the orb to a spot (screen help)
        guide = Signal(object, str)  # arrows, circles and a ghost cursor (guia.py)
        fold = Signal()  # the iPhone Duo blur while windows go side by side
        pressed = Signal()  # the companion presses (a click is happening)
        clicked = Signal()  # a mouse click anywhere: he hops
        camera_off = Signal()
        call_on = Signal(bool)  # a live call started / ended
        screen_on = Signal(bool)
        ptt = Signal()  # push-to-talk (when a call could not start)
        run = Signal(object)  # run a function on the Qt thread

    bridge = Bridge()
    bridge.run.connect(lambda job: job())
    current_call: list[Any] = [None]  # the live call with Sergio, if any

    def call_active() -> bool:
        session = current_call[0]
        return session is not None and session.active

    def on_ui(fn: Any, timeout: float = 15.0) -> Any:
        """Run *fn* on the Qt thread (widgets live there) and return its result."""
        if threading.current_thread() is threading.main_thread():
            return fn()
        done = threading.Event()
        box: dict[str, Any] = {}

        def job() -> None:
            try:
                box["value"] = fn()
            except Exception as exc:  # noqa: BLE001 — re-raised in the caller
                box["error"] = exc
            finally:
                done.set()

        bridge.run.emit(job)
        if not done.wait(timeout):
            raise TimeoutError("La interfaz no respondió a tiempo")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    bridge.state.connect(show_state)
    bridge.level.connect(notch.set_level)
    bridge.level.connect(companion.set_level)
    bridge.clicked.connect(companion.bounce)
    bridge.caption.connect(lambda text: show_text(text))

    # Drawings over the real screen that show the way and vanish on the next
    # click (owner, 28 Oct 2026). The click watcher already runs for the hop.
    from sergio_escritorio.guia import make_overlay, marks_from

    guide_overlay = make_overlay()

    def show_guide(marks: Any, caption: str) -> None:
        cleaned = marks_from(marks)
        if cleaned:
            steps = any(isinstance(m, dict) and m.get("step") for m in marks or [])
            guide_overlay.show_marks(cleaned, caption, steps=steps)

    bridge.guide.connect(show_guide)

    # Two programs side by side open with the iPhone Duo fold (blur, glide,
    # focus), like the web's split screen (owner, 29 Oct 2026).
    from sergio_escritorio.duo_veil import make_veil

    duo_veil = make_veil()
    bridge.fold.connect(lambda: duo_veil.fold())
    bridge.clicked.connect(guide_overlay.clicked)

    class UIAdapter:
        def state(self, name: str) -> None:
            bridge.state.emit(name)

        def say(self, text: str) -> None:
            bridge.caption.emit(text)

    def on_activity(result: str) -> None:
        logging.info("control: %s", result)
        bridge.state.emit("acting")
        caption = activity_caption(result)
        if caption:
            bridge.caption.emit(caption)

    def camera_shot() -> bytes:
        """Sergio looks through the webcam (asked by the agent's camera tool)."""
        bridge.state.emit("acting")
        bridge.caption.emit("Mirando por la cámara…")
        return feed.jpeg()

    consent_lock = threading.Lock()

    def confirm_sensitive_action(request: str) -> bool:
        from sergio_escritorio.consent import confirm_dialog

        if not consent_lock.acquire(blocking=False):
            return False
        deadline = time.monotonic() + 35.0
        try:
            def ask() -> bool:
                remaining = deadline - time.monotonic()
                return remaining > 0 and confirm_dialog(request, seconds=min(30.0, remaining))

            return on_ui(ask, timeout=36.0) is True
        except Exception:
            logging.exception("No se pudo solicitar autorización")
            return False
        finally:
            consent_lock.release()

    from sergio_escritorio.live_screen import LiveScreen

    backend = WindowsBackend(speed=str(config.get("control_speed") or "rapido"))
    backend.on_fold = bridge.fold.emit
    # The live eye: watches the screen in the background, so every look and
    # every check after an action is instant (live_screen.py).
    live = LiveScreen(backend.screenshot, lambda: getattr(backend, "shot_origin", (0, 0)))
    controller = Controller(
        backend,
        on_activity=on_activity,
        camera=camera_shot,
        approve=lambda _request: True,
        strict_permissions=bool(config.get("strict_permissions", False)),
        live=live,
    )
    _ui_warm = threading.Event()

    def _warm_loop() -> None:
        # Re-read buttons and fields shortly after the screen changes (in the
        # background), so screen_read never waits for the accessibility tree.
        while True:
            _ui_warm.wait()
            time.sleep(0.12)
            _ui_warm.clear()
            controller.warm_ui()

    # Re-read the accessibility tree only while Sergio is looking or acting:
    # during a video it was read several times a second for nothing.
    live.on_change = lambda _frame: _ui_warm.set() if live.watched else None
    threading.Thread(target=_warm_loop, name="ui-warm", daemon=True).start()
    if config.get("live_eye", True) is not False:
        live.start()
    server = make_server(controller, config["token"], int(config["port"]))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # Load Whisper on Windows in the background so the first phrase is fast.
    from sergio_escritorio.voice import local_whisper

    threading.Thread(target=local_whisper, daemon=True).start()
    client = SergioClient(config["server_url"], api_key=str(config.get("server_api_key") or ""))
    client.voice = config["voice"]

    def apply_brain(cfg: dict) -> None:
        """Voice, personality and effort chosen in the notch."""
        client.voice = cfg["voice"]
        client.voice_rate = cfg["voice_rate"]
        client.allow_voice_fallback = bool(cfg.get("allow_voice_fallback", False))
        client.effort = cfg["effort"]
        # A model chosen in the control center («Modelo»): used for both
        # quick and deep answers; empty = Sergio picks Flash or Pro.
        from sergio_escritorio.voice import DEEP_MODEL, FAST_MODEL

        chosen = str(cfg.get("model") or "")
        client.fast_model = chosen or FAST_MODEL
        client.deep_model = chosen or DEEP_MODEL
        name = cfg["name"]
        persona = PERSONALITIES.get(cfg["personality"], "")
        client.personality = (
            f"Tu nombre es {name}. {persona}" if name != "Sergio" else persona
        )
        # International: his language and the user's country.
        from sergio_escritorio import idioma
        from sergio_escritorio import voice as _voice

        lang = cfg.get("language") or idioma.system_language()
        where = idioma.country(cfg.get("country") or idioma.system_country() or "EC")
        _voice.set_language(lang)
        client.country_name = where.name
        client.personality = (client.personality + idioma.speak_rule(lang)).strip()

    apply_brain(config)

    from sergio_escritorio.messaging import Contacts, call_plan, message_plan, platform_of
    from sergio_escritorio.operador import Operator

    contacts = Contacts(CONFIG.parent / "contactos.json")
    operator = Operator(
        controller,
        client.act_step,
        on_say=lambda t: bridge.caption.emit(t),
        on_state=lambda s: bridge.state.emit(s),
    )
    controller.film = operator.film  # the chat shows each step (GET /film)

    def _open_plan_target(target: str) -> None:
        if not target:
            return
        try:
            if "://" in target or target.startswith(("mailto:", "tel:", "sms:", "www.")):
                controller.act({"action": "open", "target": target})
            else:
                controller.act({"action": "open_app", "target": target})
            time.sleep(1.5)
        except Exception:  # noqa: BLE001
            pass

    def send_message_task(
        platform: str, to: str, text: str, subject: str = "", confirmed: bool = True
    ) -> str:
        plat = platform_of(platform or "whatsapp")
        addr = contacts.address(to, plat) or to
        plan = message_plan(plat, addr, text, subject)
        _open_plan_target(plan.open)
        return operator.run(plan.goal, confirmed=confirmed)

    def call_person_task(
        to: str, how: str = "telefono", confirmed: bool = True
    ) -> str:
        plat = platform_of(how) if how not in ("telefono", "phone", "celular") else "whatsapp"
        addr = contacts.address(to, plat) or to
        plan = call_plan(addr, how)
        _open_plan_target(plan.open)
        return operator.run(plan.goal, confirmed=confirmed)

    def run_task(kind: str, action: dict) -> str:
        confirmed = action.get("confirmed") is not False
        if kind == "operate":
            reply = str(action.get("answer") or "").strip()
            if reply and operator.pending is not None:
                return operator.answer(reply, confirmed=confirmed)
            goal = str(action.get("goal") or action.get("text") or action.get("target") or "").strip()
            return operator.run(goal, confirmed=confirmed)
        if kind == "message":
            return send_message_task(
                str(action.get("platform") or "whatsapp"),
                str(action.get("to") or action.get("target") or ""),
                str(action.get("text") or ""),
                str(action.get("subject") or ""),
                confirmed=confirmed,
            )
        if kind == "phone_call":
            return call_person_task(
                str(action.get("to") or action.get("target") or ""),
                str(action.get("platform") or "telefono"),
                confirmed=confirmed,
            )
        if kind == "contact":
            return contacts.remember(
                str(action.get("to") or action.get("target") or ""),
                str(action.get("platform") or "telefono"),
                str(action.get("text") or ""),
            )
        return "unknown task"

    controller.on_task = run_task

    def eyes() -> bytes:
        """Direct look for "¿qué tengo en la mano?": show the window too."""
        bridge.peek.emit()
        return camera_shot()

    def screen() -> tuple[bytes, list[dict], float]:
        """Screen help: what Sergio sees when you ask about your screen."""
        bridge.caption.emit("Mirando tu pantalla…")
        return controller.snapshot()

    assistant = Assistant(
        client,
        ui=UIAdapter(),
        eyes=eyes,
        screen=screen,
        point=lambda x, y, label: bridge.point.emit(x, y, label),
    )
    assistant.guide = lambda marks, caption: bridge.guide.emit(marks, caption)
    assistant.guide_showing = lambda: guide_overlay.showing
    assistant.guide_dismiss = lambda: bridge.run.emit(guide_overlay.dismiss)
    assistant.type_text = backend.type_text  # «dicta: …» writes where the cursor is
    _level_gate = [0.0, 0.0]  # [last_emit_monotonic, last_level]

    def emit_level_throttled(lvl: float) -> None:
        now = time.monotonic()
        if now - _level_gate[0] < 0.045 and abs(lvl - _level_gate[1]) < 0.025:
            return
        _level_gate[0], _level_gate[1] = now, lvl
        bridge.level.emit(lvl)

    ears = Ears(
        assistant, wake_word=bool(config["wake_word"]), on_level=emit_level_throttled
    )

    def hands_status() -> str:
        try:
            import mediapipe  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return f"no instalado ({exc}); vuelve a ejecutar sergio escritorio instalar"
        mode = getattr(camera_window.hands, "mode", "off")
        return f"ok (modo {mode})"

    def diag() -> dict:
        """For `sergio revisar`: microphone, levels, ear, brain, last error."""
        from sergio_escritorio.diagnose import recent_errors
        from sergio_escritorio.voice import _LOCAL

        ear = getattr(_LOCAL[0], "name", "") if _LOCAL and _LOCAL[0] else ""
        return {
            "microphone": ears.device_name,
            "peak_level": ears.peak(),
            "threshold": round(ears.segmenter.threshold()),
            "wake_word": ears.wake_word,
            "whisper": ear or "del servidor (Whisper local no cargado)",
            "brain": client.last_brain,
            "last_heard": assistant.last_heard,
            "wake": "instantáneo (Vosk)" if ears.spotter is not None else "Whisper por frase",
            "voice_timeline": list(ears.timeline),
            "last_error": assistant.last_error,
            "recent_errors": recent_errors(HOME / "sergio.log"),
            "voice_used": client.last_voice,
            "log": str(HOME / "sergio.log"),
            "hands": hands_status(),
            "call": call_status(),
            "vision": vision_status(),
            "holograms": holo_status(),
            "location": (
                {"lat": location.fix.lat, "lon": location.fix.lon, "source": location.fix.describe()}
                if location.fix is not None
                else None
            ),
            "gym": (
                f"cada {int(schedule.interval // 60)} min, el próximo en "
                f"{schedule.minutes_left()} min"
                if schedule.enabled
                else "apagado"
            ),
            "reminders": len(reminders.pending()),
            "voices": voices_status(),
            "minutes": minutes_status(),
        }

    def voices_status() -> str:
        try:
            import torch  # noqa: F401
        except Exception:  # noqa: BLE001
            return "sin PyTorch (vuelve a ejecutar sergio escritorio instalar)"
        known = [p["name"] for p in voice_book.people()]
        if not known:
            return "listas, aún ninguna voz aprendida (di «aprende mi voz»)"
        return f"listas, conozco {len(known)}: " + ", ".join(known[:4])

    def minutes_status() -> str:
        if recorder.active:
            return f"tomando notas ({int(recorder.seconds // 60)} min)"
        try:
            import pyaudiowpatch  # noqa: F401

            return "micrófono + audio de la computadora"
        except Exception:  # noqa: BLE001
            return "solo micrófono (falta el audio de la computadora)"

    def call_status() -> str:
        session = current_call[0]
        if session is not None and session.active:
            return f"en llamada ({session.model}, eco: {session.echo.kind})"
        mode = config.get("conversation", "llamada")
        if mode != "llamada":
            return "por turnos (llamada desactivada)"
        return f"lista{'; último error: ' + call_error[0] if call_error[0] else ''}"

    def vision_status() -> str:
        try:
            import mediapipe  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return f"sin MediaPipe ({exc})"
        return vision_engine.error or "ok"

    def holo_status() -> str:
        scene = camera_window.holo
        return (
            f"{len(scene.objects)} hologramas, modo {scene.mode}"
            f"{', gravedad' if scene.gravity else ''}; manos {hand_control.mode}"
        )

    controller.diag = diag
    try:
        ears.start()
    except Exception as exc:  # noqa: BLE001 — no microphone
        logging.exception("microphone unavailable")
        show_text(f"No encuentro el micrófono: {exc}", 10)

    # -- tray --------------------------------------------------------------
    tray = QSystemTrayIcon(tray_icon(STATE_COLORS["idle"]))
    tray.setToolTip(
        "Sergio: pulsa Ctrl+Espacio o mantén Ctrl+Alt para "
        "preguntarle por tu pantalla"
    )
    menu = QMenu()

    def remember(key: str, value: bool) -> None:
        config[key] = value
        save_config(config)

    talk_action = QAction("Hablar / llamar  (Ctrl+Espacio)", menu)
    talk_action.triggered.connect(ears.talk)
    menu.addAction(talk_action)
    gym_action = QAction("Gimnasio mental ahora", menu)
    gym_action.triggered.connect(lambda: open_gym())
    menu.addAction(gym_action)
    results_action = QAction("Mis resultados del gimnasio", menu)
    results_action.triggered.connect(lambda: open_results())
    menu.addAction(results_action)
    gym_menu = [gym_action, results_action]
    for item in gym_menu:
        item.setVisible(bool(config.get("gym_addon")))
    consult_action = QAction("Consulta (hablar con Sergio)", menu)
    consult_action.triggered.connect(lambda: open_consult())
    menu.addAction(consult_action)
    health_action = QAction("Mi salud", menu)
    health_action.triggered.connect(lambda: open_health())
    menu.addAction(health_action)
    history_action = QAction("Historial médico", menu)
    history_action.triggered.connect(lambda: open_health("history"))
    menu.addAction(history_action)
    goals_action = QAction("Mis metas (coach)", menu)
    goals_action.triggered.connect(lambda: open_goals())
    menu.addAction(goals_action)
    organizer_action = QAction("Organizador: alarmas, notas, recordatorios", menu)
    organizer_action.triggered.connect(lambda: open_organizer())
    menu.addAction(organizer_action)
    menu.addSeparator()


    live_screen_action = QAction("Compartir pantalla con Gemini en la llamada", menu, checkable=True)
    live_screen_action.setChecked(bool(config.get("live_screen", True)))
    live_screen_action.toggled.connect(lambda on: share_screen(on))
    menu.addAction(live_screen_action)
    reduced_action = QAction("Reducir movimiento del notch", menu, checkable=True)
    reduced_action.setChecked(bool(config.get("reduce_motion", False)))
    reduced_action.toggled.connect(lambda on: (notch.set_reduce_motion(on), remember("reduce_motion", on)))
    menu.addAction(reduced_action)

    control_action = QAction(
        "Puede usar mouse y teclado  (Ctrl+Alt+Fin)", menu, checkable=True
    )
    control_action.setChecked(controller.enabled)

    def set_control(enabled: bool) -> None:
        if controller.enabled == enabled and control_action.isChecked() == enabled:
            return
        controller.enabled = enabled
        control_action.setChecked(enabled)
        tray.setIcon(tray_icon(STATE_COLORS["idle" if enabled else "paused"]))
        show_state("idle" if enabled else "paused")
        show_text(
            "Puedo usar tu mouse y teclado otra vez."
            if enabled
            else "Listo, no tocaré el mouse ni el teclado.",
            4,
        )

    control_action.toggled.connect(set_control)
    menu.addAction(control_action)

    show_action = QAction("Mostrar junto al cursor", menu, checkable=True)
    show_action.setChecked(bool(config["show_companion"]))

    def set_visible(on: bool) -> None:
        companion.setVisible(on)
        remember("show_companion", on)

    show_action.toggled.connect(set_visible)
    menu.addAction(show_action)

    notch_action = QAction("Mostrar el notch arriba", menu, checkable=True)
    notch_action.setChecked(show_notch)

    def set_notch(on: bool) -> None:
        # Hidden: it falls into a black hole and rises away; shown: backwards.
        notch.show_notch() if on else notch.hide_notch()
        companion.captions = not on  # texts live in the notch when it is shown
        remember("show_notch", on)
        if notch_action.isChecked() != on:
            notch_action.setChecked(on)

    notch_action.toggled.connect(set_notch)
    # The cursor at the top edge brings it back as a drop: keep the menu in step.
    notch.on_shown = lambda: on_ui(lambda: notch_action.setChecked(True))
    menu.addAction(notch_action)
    menu.addSeparator()

    camera_action = QAction("Cámara  (Ctrl+Alt+C)", menu)
    camera_action.triggered.connect(camera_window.toggle)
    menu.addAction(camera_action)

    def save_settings(new: dict) -> None:
        apply_config(new)
        companion_mod.ORB = float(new["cursor_size"])
        apply_brain(new)
        set_wake_name(new["name"])
        notch.name = new["name"]
        save_config(config)
        tray.setIcon(tray_icon(STATE_COLORS["idle"]))

    # -- every part of Sergio, one tap away («Todo» tab) ------------------
    # Filled at the end of start-up, once every window exists.
    section_openers: dict[str, Any] = {}
    quick_handlers: list[Any] = []

    def open_section(key: str, arg: str = "") -> None:
        opener = section_openers.get(key)
        if opener is None:
            return

        def run() -> None:
            try:
                said = opener(arg)
            except Exception as exc:  # noqa: BLE001 — said, never a crash
                logging.exception("section %s failed", key)
                said = f"No pude abrir eso: {exc}"
            if said:
                tell(said)

        threading.Thread(target=run, daemon=True).start()

    # -- control center (click the notch) ---------------------------------
    def status() -> str:
        brain = getattr(client, "_model", "") or "el modelo de Sergio"
        ear = "te escucha" if ears.wake_word else "Ctrl+Espacio para hablar"
        return f"Piensa con {brain} · {ear}"

    def set_camera(on: bool) -> None:
        camera_window.open() if on else camera_window.close_camera()

    from sergio_escritorio.deshacer import journal as undo_journal

    def night_warm() -> bool:
        try:
            return bool(night_settings().warmth)
        except NameError:  # Night Shift starts later in start-up; asked again on opening
            return False

    def split_app_window(on: bool) -> bool:
        from sergio_escritorio.launch import split_window

        return split_window(on)

    panel = ControlCenter(
        PanelActions(
            talk=ears.talk,
            send=lambda text: threading.Thread(
                target=assistant.on_text, args=(text,), daemon=True
            ).start(),
            toggles=[
                Toggle(
                    "Usar el PC",
                    "hand",
                    lambda: controller.enabled,
                    control_action.setChecked,
                ),
                Toggle(
                    "Conversación",
                    "phone",
                    call_active,
                    lambda on: set_call_tile(on),
                ),
            ],
            config=config,
            save_config=save_settings,
            open_url=open_app_window,
            server_url=config["server_url"],
            status=status,
            open_section=open_section,
            swarm=activities.lines,
            multitasking=lambda: notch.multitasking,
            set_multitasking=lambda on: (notch.set_multitasking(on), remember("multitasking", on)),
            hide_notch=lambda: set_notch(False),
            split_screen=split_app_window,
            undo=lambda: undo_journal().undo_last(),
            undo_label=lambda: (step.what if (step := undo_journal().last()) else ""),
            display=[
                # Night Shift's own settings come later in start-up: looked up when tapped.
                Toggle("Night Shift", "moon", night_warm, lambda on: set_night_warmth(on)),
                Toggle("Junto al cursor", "pointer", companion.isVisible, show_action.setChecked),
                # Sergio sees in the background; this shows his camera window too.
                *([] if camera_window.vista_off else [
                    Toggle("Ver la cámara", "camera", camera_window.isVisible,
                           lambda on: camera_window.open(show=True) if on else camera_window.hide()),
                ]),
                Toggle("Gimnasio Mental", "brain",
                       lambda: bool(config.get("gym_addon") and config.get("gym", True)),
                       lambda on: set_gym(on)),
            ],
        )
    )
    panels.append(panel)
    bridge.level.connect(panel.set_level)
    panel_action = QAction("Centro de control  (clic en el notch)", menu)
    panel_action.triggered.connect(panel.open)
    menu.insertAction(talk_action, panel_action)
    menu.addSeparator()

    chat_action = QAction("Abrir la app de Sergio", menu)
    chat_action.triggered.connect(lambda: open_app_window(config["server_url"]))
    menu.addAction(chat_action)

    def update_sergio() -> None:
        # The owner's universal update, without opening PowerShell.
        def run() -> None:
            import httpx

            try:
                resp = httpx.post(
                    api_base(config["server_url"]) + "/v1/sistema/actualizar",
                    timeout=10,
                )
                text = (
                    "Actualizando Sergio; se reinicia solo en unos minutos."
                    if resp.status_code == 200
                    else f"No se pudo actualizar ({resp.status_code})."
                )
            except Exception as exc:  # noqa: BLE001 — server off
                text = f"No pude hablar con Sergio: {exc}"
            bridge.caption.emit(text)

        threading.Thread(target=run, daemon=True).start()

    update_action = QAction("Actualizar Sergio", menu)
    update_action.triggered.connect(update_sergio)
    menu.addAction(update_action)
    quit_action = QAction("Salir", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (
            open_app_window(config["server_url"])
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else (
                ears.talk()
                if reason == QSystemTrayIcon.ActivationReason.Trigger
                else None
            )
        )
    )
    tray.show()

    # -- global hotkeys (pynput thread -> Qt thread via signals) ------------
    bridge.talk.connect(ears.talk)
    bridge.camera.connect(camera_window.toggle)
    bridge.peek.connect(camera_window.open)

    def point_at(x: int, y: int, label: str) -> None:
        companion.show()  # even if hidden: pointing is the whole point
        companion.point_at(x, y, label)

    bridge.point.connect(point_at)
    controller.on_point = lambda x, y, label: bridge.point.emit(x, y, label)
    controller.on_guide = lambda marks, caption: bridge.guide.emit(marks, caption)

    def arrival_delay(x: int, y: int) -> float:
        from PySide6.QtGui import QCursor

        here = QCursor.pos()
        return companion_delay(((here.x() - x) ** 2 + (here.y() - y) ** 2) ** 0.5)

    def companion_click(x: int, y: int, kind: str) -> None:
        """The companion flies to the spot, then the click happens there."""
        if not config.get("companero_hace_clic", True):
            return
        label = {"double_click": "Doble clic", "right_click": "Clic derecho"}.get(kind, "Clic")
        bridge.point.emit(x, y, label)
        time.sleep(arrival_delay(x, y))  # long flights wait a bit, short hops almost none
        bridge.pressed.emit()

    controller.on_click = companion_click
    bridge.pressed.connect(companion.press)

    # -- hands: holograms you grab, turn, sculpt and draw in Sergio ve -------
    from sergio_escritorio.hands import ALIASES, MODES, REMOVED, HandControl

    hand_control = HandControl(frames=feed.frame)
    camera_window.hands = hand_control

    def set_hands(mode: str) -> str:
        """For Sergio (desktop_action hands, the call's "manos")."""
        mode = (mode or "off").strip().lower()
        if mode in REMOVED:
            return (
                "El control por gestos y el mouse en el aire ya no existen: tus "
                "manos ahora mueven y modelan hologramas en Vista (modo holo)."
            )
        mode = ALIASES.get(mode, mode)
        if mode not in MODES:
            return f"unknown hands mode {mode!r}; use one of {', '.join(MODES)}"

        def go() -> str:
            if mode == "off":
                return camera_window.set_holo(False)
            if not camera_window.active:
                camera_window.open()
            return camera_window.set_holo(True)

        return on_ui(go)

    controller.on_hands = set_hands
    bridge.camera_off.connect(camera_window.close_camera)

    def play_video(request: str) -> str:
        """YouTube, like a person: search, find the right video, click it.

        The server picks the video (Gemini checks the thumbnails when you
        describe what must be seen); the companion opens the results and
        moves the cursor to that video and clicks it, so you watch it happen.
        """
        resp = client.http.post(
            f"{client.base}/v1/vision/youtube", json={"request": request}, timeout=60
        )
        resp.raise_for_status()
        video = resp.json()
        title = str(video.get("title") or "")
        controller.act({"action": "open", "target": video["search_url"]})
        wanted = re.sub(r"\W+", " ", title.lower()).strip()[:28]
        deadline = time.monotonic() + 8
        while wanted and time.monotonic() < deadline:
            time.sleep(0.8)
            try:
                elements = controller.ui().get("elements", [])
            except Exception:  # noqa: BLE001
                continue
            match = next(
                (
                    el
                    for el in elements
                    if wanted in re.sub(r"\W+", " ", str(el.get("name") or "").lower())
                ),
                None,
            )
            if match is not None:
                controller.act({"action": "click", "element": match["id"]})  # the human cursor
                return f"Reproduciendo «{title}»."
        controller.act({"action": "open", "target": video["url"]})  # not visible: go straight
        return f"Reproduciendo «{title}»."

    # -- instant voice commands (no AI): "abre Spotify", "sube el volumen" ---
    def run_quick(q: Any) -> str:
        import datetime

        from sergio_escritorio.control import ActionError
        from sergio_escritorio.quick import spoken_date, spoken_time

        now = datetime.datetime.now()
        if q.kind == "stop":
            assistant.stop_speaking()
            return ""
        if q.kind in ("multitask_on", "multitask_off"):
            on = q.kind == "multitask_on"
            on_ui(lambda: notch.set_multitasking(on))
            remember("multitasking", on)
            # The open Sergio window splits (or joins) too, with the Duo fold.
            from sergio_escritorio.launch import split_window

            threading.Thread(target=split_window, args=(on,), daemon=True).start()
            return q.say
        if q.kind == "undo":
            from sergio_escritorio.deshacer import journal

            return journal().undo_last()
        if q.kind in ("notch_hide", "notch_show"):
            on_ui(lambda: set_notch(q.kind == "notch_show"))
            return "" if q.kind == "notch_hide" else "Aquí estoy."
        jarvis = run_jarvis(q, now)
        if jarvis is not None:
            return jarvis
        if q.kind == "time":
            return spoken_time(now)
        if q.kind == "date":
            return spoken_date(now)
        if q.kind == "camera":
            (bridge.peek if q.arg == "on" else bridge.camera_off).emit()
            return q.say
        if q.kind == "analyze":
            on_ui(lambda: camera_window.open() if not camera_window.active else None)
            analyze()  # it speaks the result itself
            return ""
        if q.kind == "photo":
            if not camera_window.active:
                on_ui(camera_window.open)
                time.sleep(1.6)  # the camera settles its exposure
            path = on_ui(camera_window.save_photo)
            return "Foto guardada en Imágenes, carpeta Sergio." if path else "No pude tomar la foto."
        if q.kind == "vision_detail":
            camera_window.detail = q.arg == "on"
            return q.say
        if q.kind == "vision_data":
            if not camera_window.active:
                return "Abre la cámara («abre la cámara») y te digo lo que mido."
            return (body_now().strip() or "Aún no tengo medidas; mírame unos segundos.")
        if q.kind == "mirror":
            camera_window.mirror = not camera_window.mirror
            return "Modo espejo." if camera_window.mirror else "Sin espejo."
        if q.kind == "blender_holo":
            return holograms_to_blender()
        if q.kind == "video_pro":
            return video_task(q.arg, q.say)
        if q.kind == "video_style_learn":
            return video_style_learn(q.arg)
        if q.kind == "video_styles":
            return video_styles()
        if q.kind == "video_upload":
            return upload_video()
        if q.kind == "holo_model":
            return holo_model(q.arg)
        if q.kind == "face_scan":
            return face_scan(q.arg)
        if q.kind == "voice_enroll":
            return voice_enroll(q.arg)
        if q.kind == "voice_who":
            return voice_who()
        if q.kind == "voice_forget":
            return voice_forget(q.arg)
        if q.kind == "meeting_start":
            return meeting_start(q.arg or "reunión")
        if q.kind == "meeting_stop":
            return meeting_stop()
        if q.kind == "meeting_last":
            return meeting_last()
        if q.kind == "holo_maybe":
            if getattr(hand_control, "mode", "off") != "holo" and not camera_window.holo.objects:
                raise LookupError("no hay hologramas: que responda el asistente")
            return holo_model(q.arg)
        if q.kind == "blender_task":
            return blender_task(q.arg)
        if q.kind == "blender_image":
            return blender_image(q.arg)
        if q.kind == "blender_edit":
            return blender_edit_task(q.arg)
        if q.kind == "blender_addons":
            return blender_addons_install(q.arg)
        if q.kind == "tripo":
            return tripo_model(q.arg)
        if q.kind == "sculptmate":
            return image_model(q.arg, "SculptMate")
        if q.kind == "img2mesh":
            return image_model(q.arg, "Image to Mesh")
        if q.kind == "rife_install":
            return rife_install()
        if q.kind == "feedback":
            return give_feedback(q.arg)
        if q.kind == "crew":
            return crew_task(q.arg)
        if q.kind == "cad_image":
            return cad_image(q.arg)
        if q.kind == "cad_model":
            return cad_model()
        if q.kind == "blender_object":
            return object_to_blender(q.arg)
        if q.kind == "hands":
            set_hands(q.arg)
            return q.say
        if q.kind == "globe":
            return (
                "God's Eye View ya no se muestra: ahora trabaja por dentro. "
                "Pregúnteme por el clima, un vuelo o cualquier lugar del planeta."
            )
        if q.kind == "video":
            try:
                return play_video(q.arg)
            except PermissionError:
                return "El control está en pausa. Pulsa Ctrl+Alt+Fin para reanudarlo."
        if q.kind == "device":
            from sergio_escritorio.device import run_device

            try:
                return run_device(q.step, controller.act)
            except PermissionError:
                return "El control está en pausa. Pulsa Ctrl+Alt+Fin para reanudarlo."
        if q.kind == "screenshot":
            folder = Path.home() / "Pictures" / "Sergio"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"captura-{now:%Y%m%d-%H%M%S}.png"
            controller.backend.screenshot().save(path)
            return q.say
        try:
            if q.kind == "open_url":
                controller.act({"action": "open", "target": q.arg})
            elif q.kind == "open_app":
                try:
                    done = controller.act({"action": "open_app", "target": q.arg})
                except LookupError as exc:
                    from sergio_escritorio.quick import SITES

                    if q.arg in SITES:  # not installed: its web instead
                        controller.act({"action": "open", "target": SITES[q.arg]})
                        return f"Abrí {q.arg.title()} en el navegador."
                    return str(exc)
                if "still starting" in done:
                    return f"Abriendo {q.arg.title()}; tarda un poco en arrancar."
            elif q.kind == "split_apps":
                try:
                    controller.act({"action": "split", "target": q.arg})
                except ActionError as exc:
                    return f"No pude ponerlas lado a lado: {exc}"
            elif q.kind == "close_app":
                try:
                    controller.act({"action": "close_app", "target": q.arg})
                except ActionError:
                    return f"No veo {q.arg.title()} abierto."
            elif q.kind == "key":
                controller.act({"action": "key", "keys": q.arg})
            elif q.kind == "volume":
                key = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}
                controller.act({"action": "key", "keys": key[q.arg], "repeat": 1 if q.arg == "mute" else 5})
        except PermissionError:
            return "El control está en pausa. Pulsa Ctrl+Alt+Fin para reanudarlo."
        return q.say

    assistant.quick = run_quick

    # -- your profile: learnt, updated 2.5+ times a week, applied everywhere ----
    from sergio_escritorio.perfil import Profile
    from sergio_escritorio.perfil import idle_seconds as input_idle

    profile = Profile(HOME / "perfil.json")
    assistant.on_request = profile.note_topic
    profile_state: dict[str, Any] = {"running": False, "error": ""}

    def apply_profile() -> None:
        apply_brain(config)
        line = profile.voice_line()
        if line:
            client.personality = (client.personality + " " + line).strip()
        try:
            gym_stats.prefs = profile.gym_prefs()
        except NameError:  # the gym is set up later at start-up
            pass

    def profile_context() -> dict:
        from sergio_escritorio import brain as gym_brain

        extra: dict[str, Any] = {
            "gimnasio": gym_analysis[0] if gym_analysis else {},
            "habilidades_validas": list(gym_brain.TRAINS),
            "ejercicios_validos": [k for k in gym_brain.BY_KIND if k not in ("pausa", "prueba")],
            "alarmas": [a.describe() for a in alarms.items][:10],
            "notas": [n.text[:80] for n in notes.items][:10],
        }
        extra["salud"] = health.summary_for_profile()
        extra["aprendizaje"] = coach.summary_for_profile()
        return extra

    def update_profile_now() -> str:
        from sergio_escritorio.voice import explain

        if profile_state["running"]:
            return "Ya estoy actualizando su perfil."
        profile_state["running"] = True
        try:
            def think(context: dict, previous: dict) -> dict:
                resp = client.http.post(
                    f"{client.base}/v1/coach/profile", json={"context": context, "previous": previous}, timeout=180
                )
                resp.raise_for_status()
                return resp.json()

            new = profile.update(think, profile_context())
            on_ui(apply_profile)
            profile_state["error"] = ""
            changes = new.get("cambios") or []
            return "Perfil actualizado. " + (f"Lo nuevo: {changes[0]}" if changes else str(new.get("resumen", ""))[:200])
        except Exception as exc:  # noqa: BLE001
            profile_state["error"] = explain(exc)
            logging.exception("profile update failed")
            return f"No pude actualizar su perfil: {explain(exc)}"
        finally:
            profile_state["running"] = False

    def profile_loop() -> None:
        """Every minute: were you here? Every 10 min: is the key update due?"""
        ticks = 0
        while True:
            time.sleep(60)
            ticks += 1
            try:
                if input_idle() < 120:
                    profile.seen_active()
                if ticks % 10 == 0:
                    profile.save()
                    first = profile.usage.last_decay
                    enough = profile.updates or (first and time.time() - first > 86400)
                    if profile.due() and enough and not call_active():
                        update_profile_now()
            except Exception:  # noqa: BLE001 — never kill the loop
                logging.exception("profile loop failed")

    threading.Thread(target=profile_loop, daemon=True).start()

    # -- the coach: what you are learning, at your pace ------------------------
    from sergio_escritorio.coach import (
        Coach,
        annotate_video,
        record_video,
        school_reminders,
    )

    coach = Coach(HOME / "coach.json")
    coach_windows: dict[str, Any] = {}
    coach_shown: set[str] = set()

    def coach_post(path: str, payload: dict, timeout: float = 240) -> dict:
        resp = client.http.post(f"{client.base}/v1/coach/{path}", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def learn(goal_text: str) -> str:
        """Research the skill and plan it around your free time (in the background)."""
        from sergio_escritorio.coach import goal_kind
        from sergio_escritorio.voice import explain

        def work() -> None:
            try:
                plan = coach_post("plan", {
                    "goal": goal_text, "kind": goal_kind(goal_text), "profile": profile.data,
                    "free_slots": profile.usage.free_windows(),
                }, timeout=300)  # fmt: skip
                goal = coach.add_goal(goal_text, plan, lambda after, minutes: profile.usage.next_good_time(after, minutes))
                first = coach.next_session(goal)
                when = datetime.datetime.fromtimestamp(first["due"]).strftime("%A a las %H:%M") if first else ""
                said = f"Listo, señor: plan de {len(goal['sesiones'])} sesiones para {goal_text}. {plan.get('resumen', '')}"
                tell(said + (f" La primera, el {when}." if when else ""))
            except Exception as exc:  # noqa: BLE001
                logging.exception("coach plan failed")
                tell(f"No pude preparar el plan: {explain(exc)}")

        import datetime

        threading.Thread(target=work, daemon=True).start()
        return f"Investigo cómo se aprende {goal_text} y le preparo un plan a su medida. Tardo un minuto."

    def practice_video(goal: dict, session: dict) -> dict:
        """Record 20 s, the coach reviews it, a copy with green/red circles opens."""
        import re as _re

        folder = Path.home() / "Videos" / "Sergio" / "Práctica"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        slug = _re.sub(r"[^\w-]+", "-", goal["meta"].lower()).strip("-")[:40] or "practica"
        raw = HOME / "practica" / f"{slug}-{stamp}.mp4"
        feed.start()
        feed.keep_on = True
        try:
            for i in (3, 2, 1):
                bridge.caption.emit(f"Grabo en {i}…")
                time.sleep(1)
            bridge.caption.emit("Grabando 20 segundos…")
            record_video(feed.frame, raw, seconds=20)
        finally:
            feed.keep_on = camera_window.active
        bridge.caption.emit("Revisando su práctica fotograma a fotograma…")
        with raw.open("rb") as fh:
            resp = client.http.post(
                f"{client.base}/v1/coach/review_video",
                files={"video": (raw.name, fh, "video/mp4")},
                data={"goal": goal["meta"], "focus": session.get("objetivo", "")},
                timeout=300,
            )
        resp.raise_for_status()
        review = resp.json()
        out = annotate_video(raw, review.get("marcas") or [], folder / f"{slug}-{stamp}.mp4")
        try:
            raw.unlink()  # only the annotated copy is kept
        except OSError:
            pass
        try:
            os.startfile(str(out))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — not Windows
            pass
        review["video"] = str(out)
        return review

    def start_session(goal_id: str) -> str:
        from sergio_escritorio.coach_ui import SessionWindow

        goal = coach.get(goal_id)
        session = coach.next_session(goal) if goal else None
        if goal is None or session is None:
            return "Esa meta no tiene sesiones pendientes."

        def done(result: dict) -> None:
            coach.finish(goal, session, result)
            coach_shown.discard(f"{goal['id']}:{session['n']}")
            if result.get("feedback"):
                threading.Thread(target=lambda: tell(str(result["feedback"])), daemon=True).start()

        def show() -> None:
            window = SessionWindow(
                goal,
                session,
                lambda: coach_post("lesson", {"goal": coach.for_lesson(goal), "profile": profile.data}),
                (lambda: practice_video(goal, session)) if session.get("video") else None,
                lambda text: coach_post("assess", {"goal": coach.for_lesson(goal), "results": text}),
                done,
            )
            coach_windows["session"] = window
            window.show()
            window.raise_()

        on_ui(show)
        return f"Sesión {session['n']} de {goal['meta']}: {session['objetivo']}"

    def open_goals() -> str:
        from sergio_escritorio.coach_ui import CoachWindow

        def show() -> None:
            if "goals" not in coach_windows:
                coach_windows["goals"] = CoachWindow(coach, lambda gid: start_session(gid))
            coach_windows["goals"].open()

        on_ui(show)
        return coach.describe()

    def coach_loop() -> None:
        """Every minute: a practice due while you are at the PC pops up."""
        from sergio_escritorio.coach_ui import PracticeCard

        while True:
            time.sleep(60)
            try:
                if call_active() or input_idle() > 300:
                    continue
                for goal, session in coach.due_sessions():
                    key = f"{goal['id']}:{session['n']}"
                    if key in coach_shown:
                        continue
                    coach_shown.add(key)

                    def show(g=goal, s=session, k=key) -> None:
                        card = PracticeCard(
                            g, s,
                            lambda: start_session(g["id"]),
                            lambda: (coach.snooze(g, s), coach_shown.discard(k)),
                            lambda: (coach.finish(g, s, {"feedback": "saltada"}), None),
                        )  # fmt: skip
                        coach_windows[f"card:{k}"] = card
                        card.show()

                    on_ui(show)
                    tell(f"Señor, toca practicar {goal['meta']}: {session['minutos']} minutos.")
                    break  # one invitation at a time
            except Exception:  # noqa: BLE001 — never kill the loop
                logging.exception("coach loop failed")

    threading.Thread(target=coach_loop, daemon=True).start()

    def check_school() -> str:
        from sergio_escritorio.voice import explain

        url = str(config.get("plataforma_escolar") or "").strip()
        if not url:
            return "Dígame la dirección de su plataforma: «mi plataforma escolar es aula punto colegio punto edu…»."

        def work() -> None:
            import datetime

            try:
                controller.act({"action": "open", "target": url})
                time.sleep(8)  # the page loads (and you are already logged in)
                png = controller.snapshot()[0]
                resp = client.http.post(
                    f"{client.base}/v1/coach/school", files={"image": ("plataforma.png", png, "image/png")}, timeout=180
                )
                resp.raise_for_status()
                data = resp.json()
                (HOME / "escuela.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                for due, text in school_reminders(data, datetime.datetime.now()):
                    reminders.add(due, text)
                tasks, exams = data.get("tareas") or [], data.get("examenes") or []
                said = f"Encontré {len(tasks)} tareas y {len(exams)} exámenes; los puse en el organizador con recordatorios."
                if exams:
                    said += f" Para estudiar, diga «prepárame para el examen de {exams[0].get('materia', '…')}»."
                tell(said)
            except Exception as exc:  # noqa: BLE001
                logging.exception("school check failed")
                tell(f"No pude leer la plataforma: {explain(exc)}. ¿Ya inició sesión en ella?")

        threading.Thread(target=work, daemon=True).start()
        return "Reviso su plataforma escolar."

    def run_coach(q: Any) -> str | None:
        if q.kind == "learn":
            return learn(q.arg)
        if q.kind == "goals":
            found = coach.find(q.arg) if q.arg else None
            if found is not None:
                p = coach.progress(found)
                errs = ", ".join(k for k, _ in p["errores"])
                return f"{found['meta']}: {p['hechas']} de {p['total']} sesiones" + (f"; nivel {p['nivel']}" if p["nivel"] else "") + (f"; a corregir: {errs}" if errs else "") + "."
            return open_goals()
        if q.kind == "practice":
            goal = coach.find(q.arg) if q.arg else next((g for g in coach.goals if g.get("activo", True)), None)
            if goal is None:
                return "No tengo esa meta. Dígame «estoy aprendiendo…»."
            return start_session(goal["id"])
        if q.kind == "school":
            return check_school()
        if q.kind == "school_set":
            config["plataforma_escolar"] = q.arg
            save_config(config)
            return "Guardada su plataforma escolar. Diga «revisa mi plataforma escolar» cuando quiera."
        return None

    # -- health: questionnaire, watch data, daily log, the report -------------
    from sergio_escritorio.salud import Health, daily_time, parse_health_log

    health = Health(HOME / "salud.json")
    health_windows: dict[str, Any] = {}
    health_asked: dict[str, str] = {"day": ""}

    def health_folder() -> str:
        return str(config.get("salud_carpeta") or "")

    def set_health_folder(folder: str) -> None:
        config["salud_carpeta"] = folder
        save_config(config)
        threading.Thread(target=lambda: health.sync_folder(Path(folder)), daemon=True).start()

    def analyze_health() -> dict:
        report = coach_post("health", {"data": health.overview(facts=profile.facts)}, timeout=300)
        health.report = report
        health.save()
        return report

    def open_health(tab: int | str = 0) -> str:
        from sergio_escritorio.salud_ui import HealthWindow

        def show() -> None:
            if "main" not in health_windows:
                health_windows["main"] = HealthWindow(health, analyze_health, health_folder, set_health_folder)
            health_windows["main"].open(tab)

        on_ui(show)
        if tab == "history":
            return ""
        if not health.answers:
            return "Empecemos por el cuestionario, señor: con eso calculo todo y lo analizo."
        return health.describe() or "Su salud, señor."

    def health_loop() -> None:
        """Imports the watch's exports and asks the day's questions at your time."""
        import datetime

        from sergio_escritorio.salud_ui import DailyCard

        last_sync = 0.0
        while True:
            try:
                if health_folder() and time.time() - last_sync > 6 * 3600:
                    last_sync = time.time()
                    health.sync_folder(Path(health_folder()))
                now = datetime.datetime.now()
                hour, minute = daily_time(config.get("salud_hora"), profile.usage.free_windows())
                today = now.date().isoformat()
                due = (now.hour, now.minute) >= (hour, minute)
                if (due and health_asked["day"] != today and (health.answers or health.days)
                        and health.to_ask_today(today) and input_idle() < 300 and not call_active()):  # fmt: skip
                    health_asked["day"] = today

                    def show() -> None:
                        card = DailyCard(health, lambda: None)
                        health_windows["daily"] = card
                        card.show()

                    on_ui(show)
                    tell("Señor, ¿cómo fue su día? Le dejé unas preguntas rápidas de salud.")
            except Exception:  # noqa: BLE001 — never kill the loop
                logging.exception("health loop failed")
            time.sleep(60)

    threading.Thread(target=health_loop, daemon=True).start()

    def run_health(q: Any) -> str | None:
        import datetime

        if q.kind == "health":
            return open_health({"hoy": 1, "cuestionario": 2, "reloj": 3}.get(q.arg, 0))
        if q.kind == "health_analyze":
            def work() -> None:
                from sergio_escritorio.voice import explain

                try:
                    rep = analyze_health()
                    first = (rep.get("recomendaciones") or [{}])[0].get("accion", "")
                    tell(f"{rep.get('resumen', '')} Lo primero: {first}".strip())
                except Exception as exc:  # noqa: BLE001
                    tell(f"No pude analizar su salud: {explain(exc)}")

            threading.Thread(target=work, daemon=True).start()
            return "Analizo todos sus datos de salud en conjunto."
        if q.kind == "health_log":
            values = parse_health_log(q.arg)
            if not values:
                return None
            health.log(datetime.date.today().isoformat(), values)
            return "Anotado en su salud de hoy."
        return None

    # -- the consulting room (support, notes, questionnaires) ----------------
    from sergio_escritorio import idioma
    from sergio_escritorio.psicologo import Consult

    def here() -> tuple[str, str]:
        """(country code, language) chosen in the settings (or Windows')."""
        lang = config.get("language") or idioma.system_language()
        return (config.get("country") or idioma.system_country() or "EC"), lang

    consult = Consult(HOME / "psicologo.json")
    consult_windows: dict[str, Any] = {}

    def consult_open() -> bool:
        window = consult_windows.get("main")
        return window is not None and window.isVisible()

    def open_consult() -> str:
        from sergio_escritorio.psicologo_ui import ConsultWindow

        def ask(messages: list, notes: list) -> dict:
            code, lang = here()
            return coach_post(
                "therapy",
                {"messages": messages, "notes": notes, "profile": profile.data,
                 "crisis": idioma.crisis_text(code, lang), "language": lang},
                timeout=120,
            )

        def show() -> None:
            if "main" not in consult_windows:
                consult_windows["main"] = ConsultWindow(
                    consult, ask, lambda text: tell(text), ears.talk, crisis=idioma.crisis_line(here()[0])
                )
            consult_windows["main"].open()

        on_ui(show)
        return "Aquí estoy, señor. Póngase cómodo; puede escribirme o hablarme."

    def consult_redirect(text: str) -> bool:
        """While the consultation is open, what you say goes to it."""
        if not consult_open():
            return False
        if re.search(r"\b(termina|cierra|salir de|acaba)\w* (la )?(consulta|sesion|sesión)\b", text.lower()):
            on_ui(consult_windows["main"].close)
            tell("Cuando quiera, aquí estaré.")
            return True
        on_ui(lambda: consult_windows["main"].hear(text))
        return True

    assistant.redirect = consult_redirect

    def watch_risk(text: str) -> None:
        if not consult_open():  # what is said in the consultation stays there
            profile.note_topic(text)
        if idioma.at_risk(text) and not consult_open():
            crisis = idioma.crisis_text(*here())
            threading.Thread(target=lambda: (tell(crisis), open_consult()), daemon=True).start()

    assistant.on_request = watch_risk

    def run_profile(q: Any) -> str | None:
        if q.kind == "consult":
            return open_consult()
        handled = run_health(q)
        if handled is not None:
            return handled
        handled = run_coach(q)
        if handled is not None:
            return handled
        if q.kind == "profile_show":
            return profile.summary()
        if q.kind == "profile_update":
            threading.Thread(target=lambda: tell(update_profile_now()), daemon=True).start()
            return "Actualizando su perfil con todo lo que sé; le aviso en un momento."
        if q.kind == "profile_fact":
            profile.remember(q.arg)
            return "Anotado, señor. Lo tendré en cuenta."
        return None
    if config.get("confirm_aloud"):  # the user wants every order confirmed out loud
        assistant.silent_quick = set()

    def live_speaker() -> Any:
        from sergio_escritorio.call import Speaker

        return Speaker()

    if sys.platform == "win32":
        assistant.speaker_factory = live_speaker  # Gemini Live's voice, streamed

    # -- Sergio speaks on his own (reminders, results, greetings) -----------
    def tell(text: str, *, to_call: str = "") -> None:
        """Say *text*: into the live call if one is on, else out loud."""
        bridge.caption.emit(text)
        if call_active():
            current_call[0].send_text(to_call or f"(Dile al usuario ahora: {text})")
            return

        def run() -> None:
            deadline = time.monotonic() + 20
            while assistant.busy and time.monotonic() < deadline:
                time.sleep(0.3)
            assistant.busy = True
            try:
                assistant.say_aloud(text)
            except Exception:  # noqa: BLE001 — the caption is there anyway
                logging.exception("could not speak")
            finally:
                assistant.busy = False

        threading.Thread(target=run, daemon=True).start()

    # -- camera vision: people, species, objects, face mesh ------------------
    from sergio_escritorio.camera import FaceWatcher
    from sergio_escritorio.vision import VisionEngine, scene_sentence
    from sergio_escritorio.vision import summary as vision_summary

    def head_gesture(said: str) -> None:
        """Nodding = sí, shaking the head = no (with the camera on)."""
        answer = "Sí" if said == "si" else "No"
        if call_active():
            current_call[0].send_text(f"(El usuario {'asintió' if said == 'si' else 'negó'} con la cabeza: {answer})")

    def hand_boxes() -> list:
        from sergio_escritorio.vision import hand_box

        return [hand_box(h.landmarks) for h in list(getattr(hand_control, "hands", []) or [])]

    vision_engine = VisionEngine(feed.frame, on_head=head_gesture, hands=hand_boxes)
    camera_window.vision = vision_engine

    def identify(jpeg: bytes) -> list[dict]:
        resp = client.http.post(
            f"{client.base}/v1/faces/identify",
            files={"image": ("cara.jpg", jpeg, "image/jpeg")},
            # It keeps learning the faces it is very sure of, from new angles.
            data={"learn": "true" if config.get("aprender_caras", True) else "false"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if camera_window.watcher is not None:
            camera_window.watcher.owner = str(data.get("owner") or "")
        return list(data.get("faces") or [])

    def faces_seen(found: list[dict]) -> None:
        vision_engine.tracker.add_faces(
            [
                {
                    "name": f["name"],
                    "guest": f.get("guest") or 0,
                    "quality": f.get("quality") or "ok",
                    "score": f["score"],
                    "box": f["nbox"],
                    "strong": f.get("strong", False),
                    "owner": f.get("owner", False),
                }
                for f in found
            ],
            time.monotonic(),
        )

    greeted_today: dict[str, str] = {}

    def greet(name: str) -> None:
        if not config.get("greet_faces", True):
            return
        if call_active():
            current_call[0].send_text(
                f"(Acaba de aparecer {name} frente a la cámara: salúdalo en una frase.)"
            )
            return
        if assistant.busy:
            return
        import datetime as _dt

        from sergio_escritorio.jarvis import briefing, system_status

        today = time.strftime("%Y-%m-%d")
        first_today = greeted_today.get(name) != today
        greeted_today[name] = today
        now = _dt.datetime.now()
        watcher = camera_window.watcher
        boss = watcher is not None and watcher.owner and watcher.owner.lower() == name.lower()
        who = "señor" if boss else name  # the owner is «señor»
        if first_today and now.hour < 12:  # the morning report
            text = briefing(now, system_status(), reminders.pending(), who)
        else:
            text = f"Bienvenido de vuelta, {who}." if boss else f"Hola, {name}."
        tell(text)

    camera_window.watcher = FaceWatcher(
        feed.frame, identify, on_person=greet, on_faces=faces_seen
    )

    def face_scan(name: str = "") -> str:
        """Face ID-style scan: turn your head in a circle and Sergio learns
        your face from every angle, with a 3D map of it in millimetres."""
        from sergio_escritorio.facescan import Scanner, measures_text

        if not camera_window.active:
            on_ui(camera_window.open)
            time.sleep(1.5)  # the camera settles and the face mesh starts
        who = name.strip()
        boss = (camera_window.watcher.owner if camera_window.watcher else "") or ""
        if not who:
            seen = [
                t for t in vision_engine.tracker.visible(time.monotonic())
                if t.kind == "persona" and t.name
            ]
            who = seen[0].name if len(seen) == 1 else boss
        if not who:
            return "¿Cómo se llama la persona? Diga: «escanea mi cara, soy …»."
        scanner = Scanner(feed.frame, lambda: list(vision_engine.faces or []))
        camera_window.scan_text = []
        camera_window.scanner = scanner
        hint = "Gire la cabeza despacio, en círculo, como con Face ID."
        bridge.caption.emit(hint)
        if not call_active():  # said while it scans (the scan takes ~10 s)
            threading.Thread(target=lambda: assistant.say_aloud(hint), daemon=True).start()
        jpegs, mesh = scanner.run()
        if len(jpegs) < 3:
            camera_window.scanner = None
            return "No vi bien la cara durante el escaneo. Con más luz y la cara entera en la cámara, otra vez."
        try:
            out = client.face_scan(who, jpegs, mesh)
        except Exception as exc:  # noqa: BLE001
            camera_window.scanner = None
            return f"No pude guardar el escaneo: {str(exc)[:200]}"
        angles = len(out.get("angles") or [])
        sizes = measures_text((mesh or {}).get("measures") or {})
        camera_window.scan_text = [
            f"{out.get('name') or who} · {angles} ángulos" + (" · mapa 3D de 478 puntos" if mesh else ""),
            sizes,
        ]
        pupils = ((mesh or {}).get("measures") or {}).get("entre pupilas")
        extra = f" Mide {pupils:.0f} milímetros entre pupilas, aproximadamente." if pupils else ""
        if boss and who.lower() == boss.lower():
            return (
                f"Listo, señor. Su cara quedó guardada desde {angles} ángulos"
                + (", con un mapa 3D de 478 puntos" if mesh else "")
                + f".{extra} Ahora le reconozco hasta de perfil."
            )
        return f"Listo: ya conozco la cara de {who} desde {angles} ángulos.{extra}"

    # A new face in view: look at once instead of waiting for the next look.
    vision_engine.on_new_face = camera_window.watcher.poke

    def analyze() -> None:
        """Camera "Analizar": Gemini looks at everything in view."""

        def run() -> None:
            try:
                jpeg = feed.jpeg()
                resp = client.http.post(
                    f"{client.base}/v1/vision/scene",
                    files={"image": ("camara.jpg", jpeg, "image/jpeg")},
                    timeout=90,
                )
                resp.raise_for_status()
                data = resp.json()
                items = list(data.get("items") or [])
                vision_engine.tracker.add_scene(items, time.monotonic())
                text = scene_sentence(items)
                if data.get("distances"):
                    text += " " + data["distances"]
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                text = f"No pude analizar la imagen: {explain(exc)}"
            on_ui(lambda: camera_window.show_overlay(text, 12))
            tell(text, to_call=f"(Análisis de la cámara: {text} Cuéntaselo al usuario.)")

        threading.Thread(target=run, daemon=True).start()

    camera_window.on_analyze = analyze

    # New things in view get a proper name from Gemini by themselves (the
    # detector only knows 80 kinds); rate-limited to protect the free quota.
    from PySide6.QtCore import QTimer as _QTimer

    from sergio_escritorio.vision import AutoNamer

    namer = AutoNamer()
    namer.enabled = bool(config.get("auto_objetos", True))

    def close_up(box: tuple) -> bytes | None:
        """A JPEG crop around one thing in view (what Gemini looks at)."""
        import cv2

        from sergio_escritorio.vision import crop_box

        frame = feed.frame()
        if frame is None:
            return None
        h, w = frame.shape[:2]
        x, y, bw, bh = crop_box(box)
        crop = frame[int(y * h) : int((y + bh) * h), int(x * w) : int((x + bw) * w)]
        if crop.size == 0:
            return None
        ok, data = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return data.tobytes() if ok else None

    def auto_name() -> None:
        """Name a new or unsure object from a close-up (a lipstick is not a
        "control remoto": the detector only knows 80 kinds of things)."""
        if not camera_window.active:
            return
        now = time.monotonic()
        tracks = vision_engine.tracker.visible(now)
        if not namer.due(tracks, now, day=time.strftime("%Y-%m-%d")):
            return
        target = namer.pick(tracks, now)
        if target is None:
            return
        namer.asked(tracks, now)
        namer.tried(target)
        image = close_up(target.box)
        if image is None:
            return

        def run() -> None:
            try:
                resp = client.http.post(
                    f"{client.base}/v1/vision/name",
                    files={"image": ("objeto.jpg", image, "image/jpeg")},
                    timeout=30,
                )
                resp.raise_for_status()
                got = resp.json()
                label = str(got.get("label") or "")
                if got.get("unsure") and label:
                    label += "?"  # the looks disagreed: shown as a doubt, never as a fact
                vision_engine.tracker.name_track(target.id, label, str(got.get("detail") or ""))
            except Exception:  # noqa: BLE001 — naming is a bonus
                logging.info("auto naming failed", exc_info=True)

        threading.Thread(target=run, daemon=True).start()

    namer_timer = _QTimer()
    namer_timer.timeout.connect(auto_name)
    namer_timer.start(2000)

    # Looking after you while the camera is on: posture, tired eyes, too close.
    care_said: dict[str, float] = {}
    care_since: dict[str, float] = {}

    def care() -> None:
        if not camera_window.active:
            care_since.clear()
            return
        now = time.monotonic()
        checks = {
            "postura": (bool(vision_engine.posture.last.get("slouch")),
                        "Señor, lleva un rato encorvado: enderece la espalda y relaje los hombros."),
            "ojos": (bool(vision_engine.face_stats.last.get("tired")),
                     "Sus ojos se ven cansados. Mire algo lejano veinte segundos; le hará bien."),
            "cerca": (bool(vision_engine.distance_cm and vision_engine.distance_cm < 35),
                      "Está muy cerca de la pantalla; un brazo de distancia es lo ideal."),
        }
        for key, (bad, advice) in checks.items():
            if not bad:
                care_since.pop(key, None)
                continue
            start = care_since.setdefault(key, now)
            if now - start > 60 and now - care_said.get(key, -1e9) > 20 * 60:
                care_said[key] = now
                tell(advice)

    care_timer = _QTimer()
    care_timer.timeout.connect(care)
    care_timer.start(5000)

    def face_photos(box: tuple, count: int = 3) -> list[bytes]:
        """A few crops of one face from the live camera (for enrolling)."""
        import cv2

        shots = []
        for i in range(count):
            frame = feed.frame()
            if frame is None:
                continue
            h, w = frame.shape[:2]
            x, y, bw, bh = box
            cx, cy = (x + bw / 2) * w, (y + bh / 2) * h
            side = max(bw * w, bh * h) * 2.0
            x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
            x1, y1 = int(min(w, cx + side / 2)), int(min(h, cy + side / 2))
            ok, jpeg = cv2.imencode(".jpg", frame[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 92])
            if ok:
                shots.append(jpeg.tobytes())
            if i + 1 < count:
                time.sleep(0.4)
        return shots

    def enroll_face(name: str, box: tuple) -> str:
        saved = 0
        last_error = ""
        from sergio_escritorio.vision import face_points

        for jpeg in face_photos(box):
            resp = client.http.post(
                f"{client.base}/v1/faces/enroll",
                data={"name": name, "consent": "true", "faces": json.dumps(face_points(jpeg))},
                files={"image": ("cara.jpg", jpeg, "image/jpeg")},
                timeout=30,
            )
            if resp.status_code == 200:
                saved += 1
            else:
                last_error = str(resp.json().get("detail", ""))[:120]
        if not saved:
            return f"No pude guardar su cara ({last_error or 'no la vi bien'})."
        return f"Encantado, {name}. Desde ahora le reconozco."

    def name_face(box: tuple) -> None:
        """Click on a stranger's frame: ask the name, then learn the face."""
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            camera_window,
            "¿Quién es?",
            "Nombre de esta persona (guárdalo solo con su permiso):",
        )
        name = name.strip()
        if ok and name:
            camera_window.show_overlay(f"Aprendiendo la cara de {name}…", 8)
            threading.Thread(
                target=lambda: tell(enroll_face(name, box)), daemon=True
            ).start()

    camera_window.on_name_face = name_face

    def name_from_voice(name: str) -> str:
        if not camera_window.active:
            on_ui(camera_window.open)
            time.sleep(4.0)  # let the camera and the recognition look first
        now = time.monotonic()
        strangers = [
            t
            for t in vision_engine.tracker.visible(now)
            if t.kind == "persona" and not t.name and t.face_box
        ]
        if not strangers:
            return "No veo a nadie nuevo frente a la cámara."
        if len(strangers) > 1:
            return "Veo a varias personas: haz clic en su recuadro y dime su nombre."
        return enroll_face(name, strangers[0].face_box)

    # -- reminders, system status, protocols ------------------------
    from sergio_escritorio.jarvis import (
        PROTOCOLS,
        Reminders,
        briefing,
        parse_reminder,
        status_sentence,
        system_status,
        when_phrase,
    )

    def reminder_due(item: Any) -> None:
        from sergio_escritorio.voice import beep

        beep(988)
        text = f"Le recuerdo: {item.text}." if item.text else "Se acabó el temporizador."
        tell(text, to_call=f"[Recordatorio que pidió el usuario: {item.text or 'temporizador terminado'}] Díselo ahora.")

    reminders = Reminders(HOME / "recordatorios.json", reminder_due)
    reminders.start()

    # -- organizer: alarms and sticky notes ------------------------------------
    from sergio_escritorio.organizer import Alarms, Notes, parse_alarm, parse_note

    organizer_windows: list[Any] = []
    alarm_cards: list[Any] = []

    def alarm_rings(alarm: Any) -> None:
        from sergio_escritorio.organizer_ui import AlarmCard, ring_sound

        def show() -> None:
            ring_sound()
            card = AlarmCard(alarm, lambda: alarms.snooze(alarm.id), lambda: None)
            alarm_cards[:] = [card]
            card.show()
            card.raise_()

        try:
            on_ui(show)
        except Exception:  # noqa: BLE001 — the voice still says it
            logging.exception("alarm card failed")
        what = f": {alarm.label}" if alarm.label else ""
        tell(f"Señor, son las {alarm.hour:02d}:{alarm.minute:02d}{what}.", to_call=f"[Alarma de las {alarm.hour:02d}:{alarm.minute:02d}{what}] Avísale ahora.")

    alarms = Alarms(HOME / "alarmas.json", alarm_rings)
    notes = Notes(HOME / "notas.json")
    note_board: list[Any] = []

    def alarm_loop() -> None:
        while True:
            try:
                alarms.check()
            except Exception:  # noqa: BLE001 — never kill the alarms
                logging.exception("alarms failed")
            time.sleep(1.0)

    threading.Thread(target=alarm_loop, daemon=True).start()

    def board() -> Any:
        from sergio_escritorio.organizer_ui import NotesBoard

        if not note_board:
            note_board.append(NotesBoard(notes))
        return note_board[0]

    def homework_items() -> list[dict]:
        try:
            data = json.loads((HOME / "escuela.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = [{"tipo": "tarea", **t} for t in data.get("tareas", [])]
        items += [{"tipo": "examen", "titulo": ", ".join(e.get("temas", [])[:3]), **e} for e in data.get("examenes", [])]
        return sorted(items, key=lambda i: i.get("fecha") or "9999")

    def open_organizer(tab: int = 0) -> str:
        from sergio_escritorio.organizer_ui import OrganizerWindow

        def show() -> None:
            if not organizer_windows:
                organizer_windows.append(OrganizerWindow(alarms, notes, board(), reminders, homework_items))
            organizer_windows[0].open(tab)

        on_ui(show)
        return "Su organizador, señor."

    def run_organizer(q: Any, now: Any) -> str | None:
        if q.kind == "alarm":
            parsed = parse_alarm(q.arg, now)
            if parsed is None:
                return "¿A qué hora pongo la alarma?"
            hour, minute, days, label = parsed
            alarm = alarms.add(hour, minute, days, label)
            if organizer_windows:
                on_ui(organizer_windows[0].refresh)
            return f"Alarma puesta: {alarm.describe()}."
        if q.kind == "alarm_remove":
            from sergio_escritorio.jarvis import parse_clock

            when = parse_clock(q.arg, now)
            gone = alarms.remove_at(when.hour, when.minute) if when else 0
            if not gone and when is None and alarms.items:
                gone = len(alarms.items)
                for a in list(alarms.items):
                    alarms.remove(a.id)
            return f"Quité {gone} alarma{'s' if gone != 1 else ''}." if gone else "No encontré esa alarma."
        if q.kind == "alarms_list":
            items = alarms.upcoming()
            if not items:
                return "No tiene alarmas activas."
            return "Sus alarmas: " + "; ".join(a.describe() for _w, a in items[:5]) + "."
        if q.kind == "note":
            parsed = parse_note(q.arg)
            if parsed is None:
                return "¿Qué escribo en la nota?"
            # No Post-its on the desktop any more (owner, Oct. 2026): the note
            # goes to the organizer's list.
            text, colour = parsed
            notes.add(text, colour)
            if organizer_windows:
                on_ui(organizer_windows[0].refresh)
            return "Anotado, señor."
        if q.kind == "notes_show":
            if not notes.items:
                return "No tiene notas. Diga «nota: …» para crear una."
            return open_organizer(1)
        if q.kind == "notes_hide":
            if note_board:
                on_ui(lambda: board().hide_all())
            return "Listo."
        if q.kind == "note_remove":
            found = notes.find(q.arg)
            for n in found:
                on_ui(lambda nid=n.id: board().remove(nid))
            return f"Borré {len(found)} nota{'s' if len(found) != 1 else ''}." if found else "No encontré esa nota."
        if q.kind == "organizer":
            return open_organizer({"alarmas": 0, "notas": 1, "recordatorios": 2, "tareas": 3}.get(q.arg, 0))
        return None

    protocols = dict(PROTOCOLS)
    protocols.update(config.get("protocolos") or {})

    def run_protocol(name: str) -> str:
        plan = protocols.get(name)
        if plan is None:
            return f"No conozco el protocolo {name}."
        for action in plan.get("actions", []):
            controller.act(dict(action))
            time.sleep(0.4)
        return str(plan.get("say") or f"Protocolo {name} listo.")

    def run_jarvis(q: Any, now: Any) -> str | None:
        """The quick commands; None = not one of them."""
        for extra in quick_handlers:  # world, blocking, language (set up at the end)
            handled = extra(q)
            if handled is not None:
                return handled
        handled = run_organizer(q, now)
        if handled is None:
            handled = run_profile(q)
        if handled is not None:
            return handled
        if q.kind == "reminder":
            parsed = parse_reminder(q.arg, now)
            if parsed is None:
                return "¿Para cuándo? Dime en cuántos minutos o a qué hora."
            when, what = parsed
            reminders.add(when.timestamp(), what)
            return f"Le avisaré {when_phrase(when, now)}" + (f": {what}." if what else ".")
        if q.kind == "reminders_list":
            items = reminders.pending()
            if not items:
                return "No tiene recordatorios pendientes."
            import datetime as _dt

            return "Tiene " + "; ".join(
                f"{r.text or 'un temporizador'} {when_phrase(_dt.datetime.fromtimestamp(r.due), now)}"
                for r in items[:5]
            ) + "."
        if q.kind == "reminders_clear":
            n = reminders.cancel_all()
            return f"Cancelé {n} recordatorios." if n else "No había recordatorios."
        if q.kind == "status":
            return status_sentence(system_status())
        if q.kind == "briefing":
            return briefing(now, system_status(), reminders.pending())
        if q.kind == "protocol":
            return run_protocol(q.arg)
        if q.kind == "gym_report":
            return gym_report()
        if q.kind == "gym_results":
            return open_results()
        if q.kind == "photo_who":
            return photo_who(q.arg)
        if q.kind == "kinship":
            return kinship(q.arg)
        if q.kind == "overhead":
            bridge.caption.emit("Mirando el cielo sobre usted…")
            return overhead_now()
        if q.kind == "globe_goto":
            return globe_tool(q.arg)
        if q.kind == "call":
            ok = start_call(force=True)
            return "" if ok else "No pude abrir la llamada ahora."
        if q.kind == "gym":
            return on_ui(open_gym)
        if q.kind == "holo":
            return run_holo(q.arg)
        if q.kind == "name_face":
            return name_from_voice(q.arg)
        return None

    def run_holo(order: str) -> str:
        """Holograms by voice: "crea un cubo rojo", "esculpir", "gravedad"."""

        def go() -> str:
            if not camera_window.active:
                camera_window.open()
            return camera_window.hologram(order)

        return on_ui(go)

    # -- Blender: your holograms, or the real object in your hands -------------
    def blender_file(name: str) -> str:
        import re as _re

        folder = Path.home() / "Documents" / "Sergio" / "Blender"
        folder.mkdir(parents=True, exist_ok=True)
        slug = _re.sub(r"[^\w-]+", "-", name.lower()).strip("-") or "modelo"
        return str(folder / f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}.blend")

    holo_sync: dict[str, Any] = {"path": "", "last": ""}

    def write_holo_sync() -> None:
        """Every 0.25 s while Blender follows the holograms: their state."""
        if not holo_sync["path"]:
            return
        from sergio_escritorio.holo import blender_state

        try:
            data = json.dumps(blender_state(list(camera_window.holo.objects)))
        except Exception:  # noqa: BLE001 — a frame mid-change: next tick
            return
        if data == holo_sync["last"]:
            return
        holo_sync["last"] = data
        target = Path(holo_sync["path"])
        tmp = target.with_suffix(".tmp")
        try:
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, target)  # Blender never reads half a file
        except OSError:
            pass

    holo_sync_timer = _QTimer()
    holo_sync_timer.timeout.connect(write_holo_sync)
    holo_sync_timer.start(250)

    def holograms_to_blender() -> str:
        from sergio_escritorio.holo import recipe_request, to_bpy

        objects = list(camera_window.holo.objects)
        if not objects:
            return "No hay hologramas que pasar a Blender. Pídeme uno: «haz un holograma de un teléfono»."
        path = blender_file("hologramas")
        sync = path[:-6] + ".sync.json"
        holo_sync["path"], holo_sync["last"] = sync, ""
        write_holo_sync()
        controller.act({"action": "blender", "script": to_bpy(objects, path, sync)})
        answer = (
            f"Abrí Blender con tus {len(objects)} hologramas a tamaño real; lo que hagas con "
            "las manos se ve allí al instante."
        )
        designed = [o for o in objects if o.recipe]
        if designed and config.get("blender_pro", True):
            for obj in designed[:2]:  # the detailed, professional version
                blender_task(recipe_request(obj))
            answer += " Y Blender Pro ya está haciendo la versión detallada; le aviso al terminar."
        return answer

    def holo_model(request: str) -> str:
        """A hologram of anything: Gemini designs its real parts.

        In the background: before, the voice waited up to two minutes for the
        designer (it "did not answer") and, if the designer failed, only the
        stray starter cube was left on screen."""
        what = request.strip() or "un objeto"
        bridge.caption.emit(f"Diseñando {what}, pieza por pieza…")

        def show(recipe: dict) -> str:
            if not camera_window.active:
                camera_window.open()
            set_hands("holo")
            obj = camera_window.holo.add_model(recipe)
            return f"{obj.name}: {len(recipe['parts'])} piezas, {obj.size_cm()} cm."

        def run() -> None:
            try:
                resp = client.http.post(
                    f"{client.base}/v1/vision/holo_model", json={"request": what}, timeout=150
                )
                if resp.status_code != 200:
                    try:
                        why = resp.json().get("detail") or resp.text
                    except ValueError:
                        why = resp.text
                    raise RuntimeError(str(why)[:220])
                recipe = resp.json()
                made = on_ui(lambda: show(recipe))
                answer = f"Listo, {made} Pellízcalo para moverlo, y «pásalo a Blender» para trabajarlo allí."
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                answer = f"No pude diseñar el holograma: {explain(exc)}"
            tell(answer, to_call=f"[Holograma] {answer} Cuéntaselo en una frase.")

        threading.Thread(target=run, daemon=True).start()
        return f"Diseñando {what} pieza por pieza; aparece en unos segundos."

    def blender_pro(request: str, reference: bytes = b"", rounds: int = 3) -> str:
        """Blender Pro: blueprint, model, render four views, look, fix — like a pro.

        Runs in the background; Sergio tells you when the project is ready.
        """
        path = blender_file("pro")
        preview = path[:-6] + "-vista.png"
        live = activities.start(f"Blender Pro: {request[:40]}", "blender", "planos")
        try:
            said = _blender_pro(request, reference, rounds, path, preview, live)
        except Exception:
            activities.finish(live, False)
            raise
        activities.finish(live, "Listo" in said, said[:80])
        return said

    last_blender: dict[str, Any] = {}  # the last finished project (for surgical edits)
    last_result: list[str] = []  # what the user's next feedback is about

    def blender_verify(request: str, shot: bytes, reference: bytes = b"", sheet: bytes = b"") -> dict | None:
        """The vision check of a build (None if it could not run)."""
        if not shot:
            return None
        files = {"preview": ("vista.png", shot, "image/png")}
        if reference:
            files["reference"] = ("referencia.jpg", reference, "image/jpeg")
        if sheet:
            files["sheet"] = ("planos.png", sheet, "image/png")
        try:
            resp = client.http.post(f"{client.base}/v1/vision/blender/verify", data={"request": request},
                                    files=files, timeout=180)
            return resp.json() if resp.status_code == 200 else None
        except Exception:  # noqa: BLE001 — the check is a bonus, never a blocker
            return None

    def _blender_pro(request: str, reference: bytes, rounds: int, path: str, preview: str, live: int) -> str:
        import base64

        from sergio_escritorio import media

        bridge.caption.emit("Blender Pro: dibujando los planos del objeto…")
        version = media.blender_version()
        if reference:
            resp = client.http.post(
                f"{client.base}/v1/vision/blender",
                files={"image": ("objeto.jpg", reference, "image/jpeg")},
                data={"save_path": path, "note": request, "preview_path": preview, "pro": "true",
                      "blender_version": version},
                timeout=600,
            )
        else:
            resp = client.http.post(
                f"{client.base}/v1/vision/blender/text",
                json={"request": request, "save_path": path, "preview_path": preview, "blender_version": version},
                timeout=600,
            )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            raise RuntimeError(str(why)[:300])
        model = resp.json()
        sheet = base64.b64decode(model.get("reference_b64") or "")
        if sheet:  # the blueprint, next to the project, for the user too
            try:
                Path(path[:-6] + "-planos.png").write_bytes(sheet)
            except OSError:
                pass
        target = json.dumps(model.get("dimensions_cm") or [])
        best = blender_review(request, model, reference, sheet, target, rounds, path, preview, live)
        from sergio_escritorio import limpieza

        model, log, verdict = best["model"], best["log"], best.get("verdict")
        if "SERGIO_SAVED" not in log:
            limpieza.forget_attempt(path)  # no half-made versions left behind
            return f"Blender Pro no logró una versión que funcione: {media.review_log(log)[-200:]}"
        limpieza.clean_blender(Path(path).parent, media.HOME / "blender")
        last_blender.clear()
        last_blender.update({"request": request, "model": model, "log": log, "path": path, "preview": preview,
                             "shot": best.get("shot") or b"", "reference": reference, "sheet": sheet})
        try:  # a clean build becomes a worked example; its verdict goes to long-term memory
            client.http.post(f"{client.base}/v1/vision/blender/learn", timeout=20, json={
                "request": request, "script": model.get("raw_script") or "" if (verdict or {}).get("score", 7) >= 7 else "",
                "log": log[-6000:], "verdict": verdict})
        except Exception:  # noqa: BLE001 — learning is a bonus
            pass
        last_result[:] = [f"el modelo de Blender «{request[:80]}»"]
        media.open_in_blender(path)
        name = model.get("name") or "el modelo"
        return (
            f"Listo: {name}, revisado {best['reviews']} veces mirando cuatro vistas"
            + (" contra los planos" if sheet else "")
            + media.vision_sentence(verdict)
            + ". Abrí el proyecto en Blender; está en Documentos, Sergio, Blender."
        )

    def blender_review(request: str, model: dict, reference: bytes, sheet: bytes, target: str, rounds: int,
                       path: str, preview: str, live: int) -> dict:
        """Build, render four views, have the vision model judge them, fix —
        until the vision check passes (8/10) or the rounds run out. The best
        version wins (vision score first, then what Blender measured)."""
        from sergio_escritorio import media

        reviews = 0
        best: dict[str, Any] = {}
        built = None  # the model the .blend on disk comes from
        for step in range(rounds + 4):  # visual reviews + a few error fixes
            bridge.caption.emit(f"Blender Pro: construyendo y revisando 4 vistas (paso {step + 1})…")
            activities.update(live, progress=min(0.95, step / (rounds + 1)), detail=f"revisión {step + 1}")
            Path(preview).unlink(missing_ok=True)
            log = media.run_blender_background(model["script"])
            built = model
            try:
                shot = Path(preview).read_bytes()
            except OSError:
                shot = b""
            verdict = blender_verify(request, shot, reference, sheet) if "SERGIO_SAVED" in log else None
            if verdict:
                bridge.caption.emit(
                    f"Blender Pro: la revisión visual le da {verdict.get('score')}/10 "
                    f"(parece «{verdict.get('looks_like', '')}»)."
                )
            rank = media.build_rank(media.blender_score(log), verdict)
            if best and media.worse_build(rank, best["rank"]):
                # The rewrite broke more than it fixed: back to the best
                # version, and the reviewer learns what went wrong.
                failed = [ln for ln in log.splitlines() if ln.startswith("SERGIO_STEP_ERROR")][:6]
                model, shot = best["model"], best["shot"]
                log = best["log"] + (
                    "\nSERGIO_NOTE your last rewrite was DISCARDED because it built much less or looked worse "
                    "(errors: " + " | ".join(failed or ["it looked worse to the vision check"]) + "). This is "
                    "the earlier, better version: make careful, targeted fixes and keep every part."
                )
                verdict = best.get("verdict")
            elif not best or rank >= best["rank"]:
                best = {"rank": rank, "model": model, "log": log, "shot": shot, "verdict": verdict}
            broken = "SERGIO_SAVED" not in log
            errors = any(ln.startswith("SERGIO_STEP_ERROR") for ln in log.splitlines())
            if not broken:
                if verdict and verdict.get("score", 0) >= 8 and not errors and reviews >= 1:
                    break  # the vision check passed: no quota spent on more rounds
                if reviews >= rounds:
                    break
                reviews += 1
            elif step >= rounds + 3:
                break
            if not shot and not broken:
                break  # no render to look at: keep what works
            files = {"preview": ("vista.png", shot or b"\x89PNG", "image/png")}
            if reference:
                files["reference"] = ("objeto.jpg", reference, "image/jpeg")
            if sheet:
                files["sheet"] = ("planos.png", sheet, "image/png")
            fixed = client.http.post(
                f"{client.base}/v1/vision/blender/refine",
                data={
                    "request": request,
                    "raw_script": model.get("raw_script") or model["script"],
                    "save_path": path,
                    "log": (media.vision_lines(verdict) + "\n" + media.review_log(log))[-3500:],
                    "preview_path": preview,
                    "target_cm": target,
                },
                files=files,
                timeout=600,
            )
            if fixed.status_code != 200:
                break  # the last good version stays
            model = fixed.json()
        if best and built is not best["model"]:
            best["log"] = media.run_blender_background(best["model"]["script"])  # save the best one
        best = best or {"model": model, "log": "", "shot": b"", "verdict": None, "rank": -1.0}
        best["reviews"] = reviews
        return best

    def blender_edit(instruction: str) -> str:
        """Surgical edit of the last Blender Pro model: only what is asked
        changes; Blender measures every part before and after to prove it."""
        if not last_blender:
            return "Primero hagamos un modelo en Blender Pro; luego lo edito pieza por pieza."
        live = activities.start(f"Edición: {instruction[:40]}", "blender", "editando")
        try:
            said = _blender_edit(instruction)
        except Exception:
            activities.finish(live, False)
            raise
        activities.finish(live, "Listo" in said, said[:80])
        return said

    def _blender_edit(instruction: str) -> str:
        from sergio_escritorio import media

        job = last_blender
        before_log, model = job["log"], job["model"]
        request = job["request"]
        path = blender_file("editado")
        preview = path[:-6] + "-vista.png"
        collateral: list[str] = []
        attempt: dict[str, Any] = {}
        for _ in range(2):  # one retry if the edit touched parts it should not
            bridge.caption.emit("Blender Pro: editando solo lo que pidió…")
            files = {"preview": ("vista.png", job.get("shot") or b"\x89PNG", "image/png")}
            if job.get("reference"):
                files["reference"] = ("referencia.jpg", job["reference"], "image/jpeg")
            resp = client.http.post(
                f"{client.base}/v1/vision/blender/edit",
                data={"request": request, "raw_script": model.get("raw_script") or "", "instruction": instruction,
                      "save_path": path, "preview_path": preview, "collateral": json.dumps(collateral)},
                files=files,
                timeout=600,
            )
            if resp.status_code != 200:
                try:
                    why = resp.json().get("detail") or resp.text
                except ValueError:
                    why = resp.text
                raise RuntimeError(str(why)[:300])
            edited = resp.json()
            Path(preview).unlink(missing_ok=True)
            log = media.run_blender_background(edited["script"])
            report = media.surgical_report(before_log, log, edited.get("changed") or [])
            if not attempt or len(report["collateral"]) < len(attempt["report"]["collateral"]):
                attempt = {"model": edited, "log": log, "report": report}
            if "SERGIO_SAVED" in log and not report["collateral"]:
                break
            collateral = report["collateral"]
        model, log, report = attempt["model"], attempt["log"], attempt["report"]
        if "SERGIO_SAVED" not in attempt["log"]:
            return f"No pude aplicar la edición: {media.review_log(log)[-200:]}"
        try:
            shot = Path(preview).read_bytes()
        except OSError:
            shot = b""
        verdict = blender_verify(f"{request}. Con este cambio: {instruction}", shot, job.get("reference") or b"")
        job.update({"model": model, "log": log, "path": path, "shot": shot,
                    "request": f"{request}. {instruction}"})
        media.open_in_blender(path)
        touched = ", ".join(report["edited"][:6]) or "lo pedido"
        extra = (f" Ojo: también cambió {', '.join(report['collateral'][:4])}." if report["collateral"] else "")
        return (
            f"Listo: cambié solo {touched}; las otras {report['kept']} piezas quedaron idénticas "
            f"(medidas antes y después).{extra}{media.vision_sentence(verdict)} Abrí la versión editada."
        )

    def blender_image(text: str) -> str:
        """An image (copied, a file or the newest download) rebuilt in Blender
        in full detail, then edited surgically with the prompt, if any."""
        from sergio_escritorio import media
        from sergio_escritorio.quick import image_edit_parts

        path_hint, instruction = image_edit_parts(text)
        image, where = media.find_image(path_hint)
        if not image:
            return ("No encuentro la imagen: cópiela (Ctrl+C) o guárdela en Descargas y vuelva a pedírmelo, "
                    "o dígame su ruta.")

        def run() -> None:
            try:
                answer = blender_pro(
                    "Recrea en Blender, con todo lujo de detalle, EXACTAMENTE lo que muestra esta imagen: "
                    "las mismas formas, proporciones, colores, materiales y cada detalle visible.",
                    image,
                )
                if instruction and last_blender:
                    answer = answer.split(". Abrí")[0] + ". " + blender_edit(instruction)
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                answer = f"Blender Pro falló con la imagen: {explain(exc)}"
            tell(answer, to_call=f"[Blender terminado] {answer} Cuéntaselo en una frase.")

        threading.Thread(target=run, daemon=True).start()
        return (f"Tengo la imagen ({where}). La reconstruyo en Blender con todo detalle"
                + (f" y luego aplico: «{instruction}»" if instruction else "") + ". Le aviso al terminar.")

    # Video Pro: learn a style, edit, upload (video_skills.py).
    from sergio_escritorio.video_skills import VideoSkills

    videos = VideoSkills(
        client=client,
        activities=activities,
        caption=bridge.caption.emit,
        tell=tell,
        controller=controller,
        last_result=last_result,
    )
    video_style_learn, video_styles = videos.learn_style, videos.styles
    video_task, upload_video = videos.task, videos.upload

    def blender_task(request: str) -> str:
        """Start Blender Pro in the background (it takes a few minutes)."""
        def run() -> None:
            try:
                answer = blender_pro(request)
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                answer = f"Blender Pro falló: {explain(exc)}"
            tell(answer, to_call=f"[Blender terminado] {answer} Cuéntaselo en una frase.")

        threading.Thread(target=run, daemon=True).start()
        return "Blender Pro está en ello: modela, renderiza, revisa y corrige. Le aviso al terminar."

    def _cad_save(done: dict, name: str) -> str:
        import base64

        from sergio_escritorio import media

        folder = media.cad_folder()
        stem = re.sub(r"[^\w\-]+", "-", name.lower()).strip("-")[:40] or "plano"
        path = folder / f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}.dxf"
        path.write_bytes(base64.b64decode(done["dxf_b64"]))
        path.with_suffix(".png").write_bytes(base64.b64decode(done["preview_b64"]))
        if hasattr(os, "startfile"):
            os.startfile(str(path.with_suffix(".png")))  # noqa: S606 — the user's own drawing
        return str(path)

    def cad_image(text: str) -> str:
        """An image vectorised into a DXF (OpenCV + ezdxf), at the width asked."""
        from sergio_escritorio import media
        from sergio_escritorio.quick import image_edit_parts

        hint, _ = image_edit_parts(text)
        image, where = media.find_image(hint)
        if not image:
            return "No encuentro la imagen: cópiela (Ctrl+C) o guárdela en Descargas y vuelva a pedírmelo."
        found = re.search(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b", text.lower())
        width = 100.0
        if found:
            value = float(found.group(1).replace(",", "."))
            width = value * {"mm": 1, "cm": 10, "m": 1000}[found.group(2)]
        resp = client.http.post(f"{client.base}/v1/vision/cad/image", files={"image": ("imagen.png", image, "image/png")},
                                data={"width_mm": str(width)}, timeout=120)
        if resp.status_code != 200:
            return f"No pude vectorizarla: {resp.json().get('detail', resp.text)[:200]}"
        done = resp.json()
        path = _cad_save(done, "imagen")
        return (f"Listo: la imagen ({where}) ahora es un DXF de {done['width_mm']} x {done['height_mm']} mm con "
                f"{done['shapes']} contornos y {done['holes']} huecos, en {path}. Le abrí la vista previa.")

    def cad_model() -> str:
        """The last Blender Pro model as a three-view DXF drawing with dimensions."""
        from sergio_escritorio import media

        if not last_blender:
            return "Primero hagamos un modelo en Blender Pro; luego le saco los planos CAD."
        log = media.blender_edges(last_blender["path"])
        name = last_blender["model"].get("name") or "Modelo"
        resp = client.http.post(f"{client.base}/v1/vision/cad/model", json={"log": log, "name": name}, timeout=120)
        if resp.status_code != 200:
            return f"No pude hacer los planos: {resp.json().get('detail', resp.text)[:200]}"
        done = resp.json()
        path = _cad_save(done, name)
        w, d, h = done["size_mm"]
        return (f"Planos listos: {name}, vistas frontal, lateral y superior con cotas ({w} x {d} x {h} mm), en {path}. "
                "Se abren en AutoCAD, FreeCAD o LibreCAD.")

    def give_feedback(text: str) -> str:
        """The user's opinion of the last result: long-term memory, so the
        next similar job starts from it."""
        from sergio_escritorio.quick import feedback_rating

        rating = feedback_rating(text)
        about = last_result[0] if last_result else ""
        client.http.post(f"{client.base}/v1/evolve/feedback", json={"text": text, "rating": rating, "about": about},
                         timeout=30).raise_for_status()
        return ("Anotado" + (f" sobre {about}" if about else "") + ": lo tendré en cuenta la próxima vez."
                if rating >= 0 else "Anotado. La próxima vez lo hago distinto; ya está en mi memoria.")

    def crew_task(task: str) -> str:
        """A long written job for the crewAI team (specialist + quality supervisor)."""
        def run() -> None:
            try:
                resp = client.http.post(f"{client.base}/v1/evolve/crew", json={"task": task}, timeout=1800)
                if resp.status_code != 200:
                    raise RuntimeError(str(resp.json().get("detail") or resp.text)[:300])
                result = resp.json()["result"]
                folder = Path.home() / "Documents" / "Sergio" / "Equipo"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"equipo-{time.strftime('%Y%m%d-%H%M%S')}.md"
                path.write_text(f"# {task}\n\n{result}\n", encoding="utf-8")
                if hasattr(os, "startfile"):
                    os.startfile(str(path))  # noqa: S606 — the user's own document
                answer = "El equipo terminó y el supervisor de calidad lo aprobó. Le abrí el documento."
                last_result[:] = [f"el trabajo del equipo: {task[:80]}"]
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                answer = f"El equipo de agentes no pudo: {explain(exc)}"
            tell(answer, to_call=f"[Equipo] {answer} Cuéntaselo en una frase.")

        threading.Thread(target=run, daemon=True).start()
        return "El equipo de agentes está en ello: un especialista lo hace y un supervisor de calidad lo revisa."

    def background(job: Callable[[], str], label: str) -> None:
        """Run *job* in the background and tell its answer when it ends."""
        def run() -> None:
            try:
                answer = job()
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                answer = f"{label} falló: {explain(exc)}"
            tell(answer, to_call=f"[{label}] {answer} Cuéntaselo en una frase.")

        threading.Thread(target=run, daemon=True).start()

    def blender_addons_install(which: str = "") -> str:
        """MeshGen, Tripo, SculptMate and Image-to-Mesh into the user's Blender."""
        from sergio_escritorio import blender_addons, media

        def job() -> str:
            version = media.blender_version()
            key = ""
            try:
                key = client.http.get(f"{client.base}/v1/vision/meshgen_key", timeout=10).json().get("key", "")
            except Exception:  # noqa: BLE001 — MeshGen can be set up by hand
                pass
            names = [which] if which in blender_addons.ADDONS else list(blender_addons.ADDONS)
            lines = []
            for name in names:
                try:
                    lines.append(blender_addons.install(name, version))
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"{name}: {str(exc)[:120]}")
            if key and any(ln.startswith("meshgen: instalado") for ln in lines):
                log = media.run_blender_background(blender_addons.meshgen_config_script(key))
                lines.append("MeshGen piensa con su Gemini." if "SERGIO_MESHGEN_OK" in log else "MeshGen: elija el modelo en sus preferencias.")
            return "Complementos de Blender: " + " ".join(lines)

        background(job, "La instalación de complementos")
        return "Instalo los complementos de Blender desde GitHub (MeshGen, Tripo, SculptMate, Image to Mesh); le aviso al terminar."

    def generated_model(glb: Path, request: str, reference: bytes = b"", engine: str = "") -> str:
        """A model made by Tripo / SculptMate / Image-to-Mesh through Sergio's
        ending: Blender project, four views, vision check."""
        from sergio_escritorio import media

        path = blender_file(engine.lower() or "modelo")
        preview = path[:-6] + "-vista.png"
        resp = client.http.post(f"{client.base}/v1/vision/blender/import", timeout=60, json={
            "glb_path": str(glb), "save_path": path, "preview_path": preview, "name": request[:60]})
        resp.raise_for_status()
        model = resp.json()
        log = media.run_blender_background(model["script"])
        if "SERGIO_SAVED" not in log:
            return f"{engine} hizo el modelo pero Blender no pudo abrirlo: {media.review_log(log)[-160:]}"
        try:
            shot = Path(preview).read_bytes()
        except OSError:
            shot = b""
        verdict = blender_verify(request, shot, reference)
        last_blender.clear()
        last_blender.update({"request": request, "model": model, "log": log, "path": path, "preview": preview,
                             "shot": shot, "reference": reference, "sheet": b""})
        last_result[:] = [f"el modelo de {engine} «{request[:60]}»"]
        media.open_in_blender(path)
        return f"Listo: {engine} hizo «{request[:60]}»{media.vision_sentence(verdict)}. Lo abrí en Blender."

    def tripo_model(text: str) -> str:
        """Tripo 3D: text (or the copied image) -> textured PBR model."""
        import base64

        from sergio_escritorio import media

        prompt = re.sub(r"(?i)\b(con|usando|en) tripo( 3d)?\b", " ", text)
        prompt = re.sub(r"(?i)^(hazme|haz|crea|creame|genera|modela)\s+(en 3d\s+)?", "", prompt).strip(" ,.")
        image = b""
        if re.search(r"(?i)\b(imagen|foto)\b", text):
            image, _ = media.find_image()

        def job() -> str:
            files = {"image": ("ref.png", image, "image/png")} if image else None
            resp = client.http.post(f"{client.base}/v1/vision/tripo", data={"prompt": prompt}, files=files, timeout=1200)
            if resp.status_code != 200:
                raise RuntimeError(str(resp.json().get("detail") or resp.text)[:300])
            glb = media.HOME / "blender" / f"tripo-{time.strftime('%Y%m%d-%H%M%S')}.glb"
            glb.parent.mkdir(parents=True, exist_ok=True)
            glb.write_bytes(base64.b64decode(resp.json()["glb_b64"]))
            return generated_model(glb, prompt or "imagen", image, "Tripo")

        background(job, "Tripo")
        return "Tripo está generando el modelo con textura en la nube (uno o dos minutos); le aviso al terminar."

    def image_model(text: str, engine: str) -> str:
        """The copied / latest image as 3D: organic (SculptMate) or technical (Image-to-Mesh)."""
        from sergio_escritorio import blender_addons, media
        from sergio_escritorio.quick import image_edit_parts

        hint, _ = image_edit_parts(text)
        image, where = media.find_image(hint)
        if not image:
            return "No encuentro la imagen: cópiela (Ctrl+C) o guárdela en Descargas y vuelva a pedírmelo."

        def job() -> str:
            if engine == "SculptMate":
                glb = blender_addons.sculptmate(image)
            else:
                glb = blender_addons.image_to_mesh(image, extrude=0.08)
            return generated_model(glb, f"la imagen ({where})", image, engine)

        background(job, engine)
        what = "orgánico y con textura" if engine == "SculptMate" else "técnico extruido"
        return f"Paso la imagen ({where}) a 3D {what} con {engine}; le aviso al terminar."

    def rife_install() -> str:
        from sergio_escritorio import video_master

        background(lambda: f"RIFE instalado en {video_master.install_rife().parent}. Ya puedo interpolar a 60 fps "
                            "y hacer cámara lenta con IA.", "La instalación de RIFE")
        return "Descargo RIFE (interpolación de fotogramas con IA, unos 400 MB); le aviso al terminar."

    def blender_edit_task(instruction: str) -> str:
        """A surgical edit in the background (it takes a minute or two)."""
        if not last_blender:
            return "Primero hagamos un modelo en Blender Pro; luego lo edito pieza por pieza."

        def run() -> None:
            try:
                answer = blender_edit(instruction)
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                answer = f"La edición en Blender falló: {explain(exc)}"
            tell(answer, to_call=f"[Blender editado] {answer} Cuéntaselo en una frase.")

        threading.Thread(target=run, daemon=True).start()
        return f"Edito solo eso: «{instruction}». El resto del modelo no se toca; le aviso al terminar."

    def object_to_blender(note: str = "") -> str:
        """The object in your hands: Gemini studies it, Blender models it."""
        if not camera_window.active:
            on_ui(camera_window.open)
            time.sleep(1.6)
        bridge.caption.emit("Estudiando el objeto que tienes en las manos…")
        jpeg = feed.jpeg()
        if config.get("blender_pro", True):
            def run() -> None:
                try:
                    answer = blender_pro(note or "el objeto que tengo en la mano, ultra detallado", jpeg)
                except Exception as exc:  # noqa: BLE001
                    from sergio_escritorio.voice import explain

                    answer = f"Blender Pro falló: {explain(exc)}"
                tell(answer, to_call=f"[Blender terminado] {answer} Cuéntaselo en una frase.")

            threading.Thread(target=run, daemon=True).start()
            return "Lo tengo. Blender Pro lo está modelando y revisando contra la foto; le aviso al terminar."
        path = blender_file("objeto")
        resp = client.http.post(
            f"{client.base}/v1/vision/blender",
            files={"image": ("objeto.jpg", jpeg, "image/jpeg")},
            data={"save_path": path, "note": note},
            timeout=300,
        )
        if resp.status_code != 200:
            try:
                why = resp.json().get("detail") or resp.text
            except ValueError:
                why = resp.text
            return f"No pude modelarlo: {str(why)[:200]}"
        model = resp.json()
        controller.act({"action": "blender", "script": model["script"]})
        dims = model.get("dimensions_cm") or []
        size = " × ".join(f"{d:g}" for d in dims) + " cm" if len(dims) == 3 else ""
        parts = f", {model['parts']} piezas" if model.get("parts") else ""
        return (
            f"Es {model['name']}" + (f" (unos {size}{parts})" if size else "")
            + f". {model.get('description', '')} Lo modelé en Blender y guardé el "
            f"proyecto en Documentos, Sergio, Blender."
        ).replace("..", ".")

    # -- faces in photos (old ones too) and family resemblance ------------------
    PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

    def find_photo(name: str) -> Path:
        path = Path(name.strip().strip('"'))
        if path.is_file():
            return path
        wanted = name.strip().lower()
        home = Path.home()
        places = [home / "Pictures", home / "Downloads", home / "Desktop", home / "Documents",
                  home / "OneDrive" / "Pictures", home / "OneDrive" / "Imágenes"]
        found = [
            f
            for place in places
            if place.is_dir()
            for f in place.rglob("*")
            if f.suffix.lower() in PHOTO_TYPES and wanted in f.name.lower()
        ]
        if not found:
            raise FileNotFoundError(f"No encuentro una foto llamada «{name}».")
        return max(found, key=lambda f: f.stat().st_mtime)

    def photo_bytes(source: str, path: str = "") -> bytes:
        source = (source or "camara").lower()
        if path or source.startswith("arch"):
            return find_photo(path).read_bytes()
        if source.startswith("pant"):
            return jpeg_of(controller.backend.screenshot(), 1920)
        if not camera_window.active:
            bridge.peek.emit()  # open the camera: hold the photo in front of it
            time.sleep(1.5)
        return feed.jpeg()

    def photo_who(source: str, path: str = "") -> str:
        bridge.caption.emit("Mirando la foto…")
        return client.photo_who(photo_bytes(source, path))

    def kinship(source: str, path: str = "") -> str:
        bridge.caption.emit("Comparando rasgos y proporciones…")
        return client.kinship(photo_bytes(source, path))

    # -- where we are and the plane overhead (God's Eye View's data) ----------
    from sergio_escritorio.location import Location

    location = Location(config.get("ubicacion"))
    location.keep_fresh()  # always fresh: the plane question never waits for it
    last_globe = [""]

    def overhead_now() -> str:
        fix = location.get()
        if fix is None:
            return f"No sé dónde estamos: {location.problem or 'sin ubicación'}."
        report = client.overhead(fix.lat, fix.lon, fix.alt)
        last_globe[0] = report.get("globe_url") or last_globe[0]
        note = "" if fix.source == "windows" else f" (Usé la {fix.describe()}.)"
        return str(report.get("text") or "No hay datos.") + note

    def globe_tool(place: str) -> str:
        """God's Eye View, hidden: where a place is, its time and its weather."""
        if not place.strip():
            return "¿De qué lugar quiere saber?"
        return client.place(place.strip())

    # -- the call: talk with Sergio like on the phone (Gemini Live) -----------
    from sergio_escritorio.call import CallSession
    from sergio_escritorio.call_tools import Abilities, call_context, call_tools

    call_failed_at = [-1e9]
    call_error = [""]
    call_paused = [False]  # you hung up yourself: no automatic reconnect
    call_backoff = [20.0]
    call_busy = [False]  # an app window has the voice (server said «busy»)

    def jpeg_of(image: Any, width: int) -> bytes:
        import io

        image = image.convert("RGB")
        if image.width > width:
            image = image.resize((width, int(image.height * width / image.width)))
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=80)
        return buf.getvalue()

    sent_frame = [0, 0.0]  # last screen frame sent to the call, and when

    def cursor_now() -> tuple[int, int] | None:
        # real pixels, like the frame (the app is DPI aware; Qt's are scaled)
        try:
            import ctypes
            from ctypes import wintypes

            point = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                return point.x, point.y
        except Exception:  # noqa: BLE001 — not Windows
            pass
        return None

    # The live video's sizes, lightest last: it steps down while the server
    # says frames are not reaching Gemini on time, and back up after.
    video_steps = ((1024, 62), (896, 56), (768, 50), (640, 45))
    video_level = [0, 0.0, 0.0]  # step, last change, last «slow» seen
    sharp_at = [0.0]

    def screen_for_call() -> tuple[bytes, str] | None:
        # Gemini on the screen: a steady 32-frame-a-second video with the
        # mouse pointer drawn in. Each frame is light (shrunk first, then
        # encoded, cached); once a second, while the screen is still, the
        # frame is a sharp one, so small text can be read.
        from sergio_escritorio.live_screen import video_jpeg

        session = current_call[0]
        live.streaming = bool(session is not None and session.active and session.share_screen)
        frame = live.latest(look=False)
        now = time.monotonic()
        if session is not None:
            if session.video_slow:
                video_level[2] = now
                if now - video_level[1] > 2.0 and video_level[0] < len(video_steps) - 1:
                    video_level[0] += 1
                    video_level[1] = now
            elif now - video_level[2] > 6.0 and now - video_level[1] > 6.0 and video_level[0] > 0:
                video_level[0] -= 1
                video_level[1] = now
        cursor = cursor_now()
        if frame.id != sent_frame[0]:
            sent_frame[0], sent_frame[1] = frame.id, now
        elif now - sent_frame[1] >= 0.5 and now - sharp_at[0] >= 1.0 and video_level[0] == 0:
            sharp_at[0] = now
            return video_jpeg(frame, cursor, 1600, 80), "pantalla"
        width, quality = video_steps[video_level[0]]
        return video_jpeg(frame, cursor, width, quality), "pantalla"

    def call_video() -> tuple[bytes, str] | None:
        session = current_call[0]
        if session is not None and session.share_screen and (
            not camera_window.active or int(time.monotonic()) % 2 == 0
        ):
            return screen_for_call()
        if camera_window.active:
            frame = feed.frame()
            if frame is not None:
                import cv2

                h, w = frame.shape[:2]
                small = cv2.resize(frame, (768, int(h * 768 / w)))
                ok, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    return jpeg.tobytes(), "cámara"
        if session is not None and session.share_screen:
            return screen_for_call()
        return None

    def look_screen(question: str) -> str:
        session = current_call[0]
        if session is None:
            return "No hay llamada."
        session.send_image(live.latest().encode("JPEG", 1280, 80), "pantalla")
        return "Te envié una captura de la pantalla: mírala y responde."

    def share_screen(on: bool) -> str:
        session = current_call[0]
        if session is not None:
            session.share_screen = on
            if on:
                session._told_screen = False  # tell Gemini again it is watching
        config["live_screen"] = on
        save_config(config)
        bridge.screen_on.emit(on and session is not None)
        bridge.run.emit(lambda: live_screen_action.setChecked(on))
        return "Ahora veo tu pantalla en vivo." if on else "Dejé de ver tu pantalla."

    def background_task(description: str) -> str:
        def run() -> None:
            try:
                answer = client.ask(description)
            except Exception as exc:  # noqa: BLE001
                answer = f"La tarea falló: {exc}"
            tell(
                answer[:600],
                to_call=f"[Tarea terminada: «{description[:200]}»] Resultado: {answer[:1500]} "
                "Cuéntaselo al usuario en una o dos frases.",
            )

        threading.Thread(target=run, daemon=True).start()
        return "Empecé la tarea en segundo plano; le aviso cuando termine."

    def save_screenshot() -> str:
        folder = Path.home() / "Pictures" / "Sergio"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"captura-{time.strftime('%Y%m%d-%H%M%S')}.png"
        controller.backend.screenshot().save(path)
        return f"Captura guardada en Imágenes\\Sergio\\{path.name}."

    def camera_tool(on: bool) -> str:
        on_ui(camera_window.open if on else camera_window.close_camera)
        return "Cámara abierta: ya recibes sus imágenes." if on else "Cámara cerrada."

    def hands_tool(mode: str) -> str:
        if mode == "fisica":  # the old physics: holograms with gravity
            return run_holo("activa la gravedad")
        return set_hands(mode)

    def people_tool() -> str:
        if not camera_window.active:
            return "La cámara está cerrada; ábrela con camara para ver."
        return vision_summary(vision_engine.tracker.visible(time.monotonic()), time.monotonic()) + body_now()

    def body_now() -> str:
        """Hands, eyes, posture and distance, for Sergio to talk about."""
        from sergio_escritorio.body import hand_summary

        parts = []
        if vision_engine.distance_cm:
            parts.append(f"Distancia a la pantalla: {vision_engine.distance_cm:.0f} cm.")
        if vision_engine.face_stats.summary():
            parts.append(f"Ojos: {vision_engine.face_stats.summary()}.")
        if vision_engine.posture.summary():
            parts.append(f"Cuerpo: {vision_engine.posture.summary()}.")
        for hand in list(getattr(hand_control, "hands", []) or [])[:2]:
            parts.append(f"Mano: {hand_summary(hand.landmarks, hand.side)}.")
        return (" " + " ".join(parts)) if parts else ""

    def hang_up_tool() -> str:
        session = current_call[0]
        if session is not None:
            session.hang_up_after_goodbye()
        return "Colgaré cuando termines de despedirte."

    def quick_order(text: str) -> str:
        from sergio_escritorio.quick import parse_quick

        q = parse_quick(text)
        if q is None:
            return f"«{text}» no es una orden directa; usa otra herramienta."
        return run_quick(q) or "Hecho."

    abilities = Abilities(
        act=controller.act,
        snapshot=controller.snapshot,
        screen_help=client.screen_help,
        screen_box=lambda: (*live.latest(look=False).origin, *live.latest(look=False).size),
        point=lambda x, y, label: bridge.point.emit(x, y, label),
        guide=lambda marks, caption: bridge.guide.emit(marks, caption),
        camera=camera_tool,
        hands=hands_tool,
        holo=run_holo,
        holo_model=holo_model,
        blender_holo=holograms_to_blender,
        blender_object=object_to_blender,
        people=people_tool,
        remind=lambda due, text: (reminders.add(due, text), "ok")[1],
        reminders=reminders.pending,
        status=system_status,
        protocol=run_protocol,
        task=background_task,
        look_screen=look_screen,
        share_screen=share_screen,
        hang_up=hang_up_tool,
        gym=lambda: on_ui(open_gym),
        gym_report=lambda: gym_report(),
        overhead=overhead_now,
        globe=globe_tool,
        photo_who=photo_who,
        kinship=kinship,
        operate=lambda goal, confirmed=True: operator.run(goal, confirmed=True if confirmed is None else bool(confirmed)),
        operate_answer=lambda reply, confirmed=True: operator.answer(reply, confirmed=True if confirmed is None else bool(confirmed)),
        message=send_message_task,
        call_person=call_person_task,
        remember_contact=contacts.remember,
        screenshot=save_screenshot,
        quick=quick_order,
        video=play_video,
        blender_task=blender_task,
        edit_video=lambda req, src="": video_task(req, src),
        upload_video=upload_video,
        face_scan=face_scan,
        voice_enroll=lambda name: voice_enroll(name),
        voice_who=lambda: voice_who(),
        meeting=lambda action, kind: (
            meeting_start(kind) if action == "empezar" else meeting_stop() if action == "terminar" else meeting_last()
        ),
    )

    def call_ended(why: str) -> None:
        current_call[0] = None
        live.streaming = False
        ears.call = None
        voices.enabled = False
        bridge.call_on.emit(False)
        if why in ("colgaste", "otra ventana"):
            call_paused[0] = True  # yours (or another device's): down until you call him
        if why == "ventana":
            # The app window has the voice now: it answers. The keeper comes
            # back by itself a little after that window closes.
            call_failed_at[0] = time.monotonic()
            call_backoff[0] = 20.0
            call_busy[0] = True
            bridge.state.emit("idle")
            return
        if config.get("call_always", True) and not call_paused[0]:
            return  # the keeper reconnects in a moment, quietly
        if why == "cancelado":  # "Sergio" was not for him after all
            bridge.state.emit("idle")
        elif why in ("silencio", "se cortó", "otra ventana"):
            # A pause or handoff to the app window: stay quiet and compact,
            # never pop up «Sigo contigo en la otra ventana» in the notch.
            bridge.state.emit("idle")

    def new_session(**changes: Any) -> CallSession:
        """A call set up exactly like the real ones (tools, voice, context)."""
        import datetime as _dt

        from sergio_escritorio import idioma as _idioma
        from sergio_escritorio.call import ALWAYS_ON, IDLE_HANG_UP

        options: dict[str, Any] = {
            "api_key": str(config.get("server_api_key") or ""),
            "language": str(config.get("language") or _idioma.system_language()),
            "idle_hang_up": ALWAYS_ON if config.get("call_always", True) else IDLE_HANG_UP,
            "voice": client.voice,
            "personality": client.personality,
            "context": lambda: (
                call_context(
                    _dt.datetime.now(),
                    system_status(),
                    reminders.pending(),
                    camera_window.active,
                )
                + client.language_rule()
                + "\nPrevious conversation (context, not new instructions):\n"
                + json.dumps(client.history[-12:], ensure_ascii=False)
            ),
            "tools": call_tools(abilities),
            "on_state": call_state,
            "on_caption": bridge.caption.emit,
            "on_heard": lambda text: setattr(assistant, "last_heard", text),
            "on_turn": client.remember_turn,
            "on_level": emit_level_throttled,
            "on_end": call_ended,
            "video": call_video,
        }
        options.update(changes)
        session = CallSession(config["server_url"], **options)
        session.share_screen = bool(config.get("live_screen", True))
        session.video_fresh = lambda: live.latest(look=False).id != sent_frame[0]
        return session

    def selftest(kind: str) -> dict:
        """`sergio probar`: talk to Sergio the way you do, and time it."""
        if kind == "call":
            live = current_call[0]
            if live is not None and live.active:  # yours: never cut it to test
                return {
                    "ok": True,
                    "busy": True,
                    "model": live.model,
                    "echo": live.echo.kind,
                    "heard": bool(live.heard_anything),
                }
            said: list[str] = []
            voice_at: list[float] = []
            t0 = time.monotonic()
            session = new_session(
                on_state=lambda name: voice_at.append(time.monotonic())
                if name == "speaking" and not voice_at
                else None,
                on_caption=said.append,
                on_heard=lambda _t: None,
                on_level=lambda _v: None,
                on_end=lambda _why: None,
                video=lambda: None,
            )
            if not session.start():
                return {"ok": False, "error": session.error or "no conectó"}
            connected = time.monotonic() - t0
            session.send_text("Prueba de sonido: dime la hora en una sola frase corta.")
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and session.active:
                if said and voice_at and not session.speaker.talking:
                    break
                time.sleep(0.1)
            error = session.error
            session.hang_up("prueba")
            return {
                "ok": bool(said) and not error,
                "model": session.model,
                "echo": session.echo.kind,
                "connect_s": round(connected, 2),
                "voice_s": round(voice_at[0] - t0 - connected, 2) if voice_at else None,
                "said": (said[-1] if said else "")[:200],
                "error": error or ("" if said else "Sergio no contestó en 15 s"),
            }
        if kind == "turn":
            t0 = time.monotonic()
            try:
                answer = client.ask("Prueba: dime la hora en una sola frase corta.")
                thought = time.monotonic() - t0
                if client.live_voice:  # what you hear: the first sound of the stream
                    for _chunk in client.speak_stream(answer[:200]):
                        break
                    client.last_voice = f"streaming ({client.voice})"
                else:
                    client.speak(answer[:200])
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                return {"ok": False, "error": explain(exc), "voice": client.last_voice}
            return {
                "ok": True,
                "answer": answer[:200],
                "think_s": round(thought, 2),
                "voice_s": round(time.monotonic() - t0 - thought, 2),
                "voice": client.last_voice,
                "brain": client.last_brain,
            }
        if kind == "open":
            from sergio_escritorio.quick import parse_quick

            # Only checks that the order is understood and the app is found:
            # nothing opens (it used to open the Calculator and close it a
            # second later, as if Sergio acted on his own).
            said = "abre la calculadora"
            t0 = time.monotonic()
            try:
                q = parse_quick(said)
                if q is None or q.kind != "open_app":
                    return {"ok": False, "said": said, "error": f"no entendí «{said}»"}
                launcher = getattr(controller.backend, "launcher", None)
                found = launcher.resolve(q.arg) if launcher is not None else q.arg
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "said": said, "error": f"{type(exc).__name__}: {exc}"}
            took = round(time.monotonic() - t0, 2)
            return {"ok": True, "said": said, "answer": f"abriría {found} (sin abrirla)",
                    "took_s": took, "error": ""}
        return {"ok": False, "error": f"prueba desconocida: {kind}"}

    controller.selftest = selftest
    controller.skills["face_scan"] = lambda args: face_scan(str(args.get("name") or ""))

    # -- who is talking: voiceprints of the people Sergio knows ---------------
    from sergio_escritorio.speakers import (
        Encoder,
        LiveVoices,
        VoiceBook,
        pcm_to_float,
        voiced,
    )

    voice_book = VoiceBook()
    owner_cache = [str(config.get("owner") or "")]

    def owner_name() -> str:
        watcher = camera_window.watcher
        return (watcher.owner if watcher is not None and watcher.owner else "") or owner_cache[0]

    def fetch_owner() -> None:
        try:
            owner_cache[0] = client.owner() or owner_cache[0]
        except Exception:  # noqa: BLE001 — the server may be starting
            pass

    threading.Thread(target=fetch_owner, daemon=True).start()

    def make_encoder() -> Any:
        from sergio_escritorio.vision import cuda_works

        return Encoder(device="cuda" if cuda_works() else "cpu")

    def owner_looking_away() -> bool:
        """The owner's face is turned well away from the screen (talking to
        someone else in the room, probably)."""
        if not camera_window.active:
            return False
        faces = list(getattr(vision_engine, "faces", []) or [])
        return len(faces) >= 1 and all(abs(f.yaw) > 32 for f in faces[:1]) and len(
            [t for t in vision_engine.tracker.visible(time.monotonic()) if t.kind == "persona"]
        ) >= 2

    def voice_changed(new: Any, _old: Any) -> None:
        """Tell the live conversation who is talking now (it may stay quiet
        when people talk to each other)."""
        if not call_active():
            return
        who = voices.describe(new)
        note = f"(Ahora habla {who}.)"
        if new.owner and owner_looking_away():
            note = f"(Ahora habla {who}, pero mira hacia otra persona: quizá no te habla a ti.)"
        current_call[0].send_note(note)
        bridge.caption.emit(f"Habla: {who}")

    def sergio_talking() -> bool:
        session = current_call[0]
        return assistant.busy or bool(session is not None and session.active and session.speaker.talking)

    voices = LiveVoices(make_encoder, voice_book, owner=owner_name, on_change=voice_changed, mute=sergio_talking)
    voices.enabled = False  # on during calls (and while learning a voice)
    ears.voices = voices

    def who_spoke(wav: bytes) -> str:
        """A note for the brain about who gave this order ("" = the owner)."""
        if not voice_book.people():
            return ""
        from sergio_escritorio.voice import wav_pcm

        voice = voices.identify_pcm(wav_pcm(wav))
        voices.note(voice)
        if voice.owner:
            return ""
        if voice.name:
            return f"Te lo pide {voice.name}, no el señor"
        return "Te lo pide una voz que no conozco; no es el señor"

    assistant.who_spoke = who_spoke

    def ask_passcode(reason: str) -> bool:
        """Face ID's backup, as on the iPhone: the owner's passcode."""
        from PySide6.QtWidgets import QInputDialog, QLineEdit

        code, ok = on_ui(
            lambda: QInputDialog.getText(
                None, "Código de Sergio", reason, QLineEdit.EchoMode.Password
            ),
            timeout=120.0,
        ) or ("", False)
        if not ok or not code.strip():
            return False
        return code_ok(code)

    def code_ok(code: str) -> bool:
        try:
            out = client.http.post(
                f"{client.base}/v1/faces/faceid/passcode/check",
                data={"code": code.strip()},
                timeout=10,
            ).json()
        except Exception:  # noqa: BLE001
            return False
        if out.get("wait"):
            bridge.caption.emit(f"Demasiados intentos: espere {out['wait']} s.")
        return out.get("ok") is True

    def owner_approves(request: str, seconds: float = 10.0) -> bool:
        """Explicit action consent with Sergio's own Visage (owner, 26 Oct
        2026: no Windows Hello); its backup code when Face ID asks for it."""
        if not bool(config.get("strict_permissions", False)):
            return True
        if not request.strip():
            return False
        from sergio_escritorio import faceid_verify
        from sergio_escritorio.facegate import ConsentDialog

        def look(_hwnd, _request, cancel, say=lambda _t: None):  # noqa: ANN001
            return faceid_verify.verify(client.http, client.base, feed, cancel=cancel, say=say)

        def ask() -> bool:
            # The island shows Face ID too, as on the iPhone.
            try:
                notch.faceid("scan")
            except Exception:  # noqa: BLE001 — the notch is a bonus
                pass
            dialog = ConsentDialog(request, verifier=look, check_code=code_ok)
            dialog.exec()
            ok = dialog.verified and not dialog.cancelled.is_set()
            try:
                notch.faceid("success" if ok else "fail")
            except Exception:  # noqa: BLE001
                pass
            return ok

        try:
            return on_ui(ask, timeout=70.0) is True
        except Exception:  # noqa: BLE001 — fail closed if the OS is unavailable
            logging.exception("Visage verification unavailable")
            bridge.caption.emit("No aprobado: confirme con Visage en este equipo.")
            return False

    assistant.approve = owner_approves
    # The control API uses the same verifier, so direct desktop actions
    # cannot bypass the identity check by skipping the face_approval tool.
    controller.approve = owner_approves

    def owner_approval(args: dict) -> dict:
        what = str(args.get("what") or "").strip()
        return {"what": what, "approved": bool(what) and owner_approves(what),
                "method": "faceid"}

    controller.skills["owner_approval"] = owner_approval
    controller.skills["voice_enroll"] = lambda args: voice_enroll(str(args.get("name") or ""))
    controller.skills["voice_who"] = lambda _args: voice_who()

    PHRASES = (
        "El veloz murciélago hindú comía feliz cardillo y kiwi, mientras la cigüeña tocaba el saxofón detrás del palenque de paja.",
        "Quiero que me reconozcas por mi voz, hable fuerte o bajito, cansado o contento, aquí o en cualquier rincón de la casa.",
        "Los volcanes del Ecuador, del Cotopaxi al Chimborazo, se ven mejor al amanecer, con café caliente y sin prisa.",
    )

    def voice_enroll(name: str = "") -> str:
        """«Aprende mi voz»: read a sentence aloud; Sergio keeps its voiceprints."""
        import random

        import numpy as np

        who = name.strip() or owner_name()
        if not who:
            return "¿De quién es la voz? Diga: «aprende mi voz, soy …»."
        phrase = random.choice(PHRASES)
        bridge.caption.emit(f"Lea en voz alta: «{phrase}»")
        assistant.say_aloud("Lea en voz alta la frase de la pantalla, con su voz de siempre.")
        frames: list[bytes] = []
        remove = voices.tap(frames.append)
        try:
            started = time.monotonic()
            while time.monotonic() - started < 14:
                time.sleep(0.25)
                speech = voiced(pcm_to_float(b"".join(frames)))
                if speech.size >= 9 * 16000:
                    break
        finally:
            remove()
        speech = voiced(pcm_to_float(b"".join(frames)))
        if speech.size < 4 * 16000:
            return "No oí suficiente voz. Otra vez, más cerca del micrófono y leyendo la frase completa."
        try:
            encoder = voices.encoder()
            step = 3 * 16000
            prints = [encoder.embed(speech[i : i + step]) for i in range(0, speech.size - step + 1, step)]
            prints = prints or [encoder.embed(speech)]
            count = voice_book.enroll(who, [np.asarray(p) for p in prints])
        except Exception as exc:  # noqa: BLE001
            return f"No pude aprender la voz: {str(exc)[:200]}"
        if who.lower() == owner_name().lower():
            return f"Listo, señor. Ya reconozco su voz ({count} huellas). Si alguien más habla, lo sabré."
        return f"Listo: ya reconozco la voz de {who} ({count} huellas)."

    def voice_who() -> str:
        if not voice_book.people():
            return "Aún no conozco ninguna voz. Diga «aprende mi voz» y lea una frase."
        wav = assistant.last_wav
        if wav:
            from sergio_escritorio.voice import wav_pcm

            try:
                voice = voices.identify_pcm(wav_pcm(wav))
            except Exception as exc:  # noqa: BLE001
                return f"No pude analizar la voz: {str(exc)[:160]}"
            sure = f" ({voice.score * 100:.0f}% de parecido)" if voice.name else ""
            if voice.owner:
                return f"Es usted, señor{sure}."
            if voice.name:
                return f"Es {voice.name}{sure}."
            return "Esa voz no la conozco."
        return f"Lo último que oí era {voices.describe()}."

    # -- meetings, video calls, conversations: Sergio takes the minutes --------
    from sergio_escritorio.meeting import (
        MeetingRecorder,
        diarize,
        encode,
        mix,
        read_wav,
        spoken_summary,
        timeline_text,
    )
    from sergio_escritorio.speakers import HOME as SERGIO_HOME

    recorder = MeetingRecorder(voices.tap, SERGIO_HOME / "reuniones")
    meeting_kind = ["reunión"]
    last_minutes: list[dict] = []
    reminded_consent = [""]

    def meeting_start(kind: str = "reunión") -> str:
        if recorder.active:
            return "Ya estoy tomando notas, señor."
        recorder.start(kind)
        meeting_kind[0] = kind
        bridge.caption.emit(f"● Tomando notas de la {kind}… («Sergio, termina la reunión»)")
        parts = [f"Tomando notas de la {kind}"]
        if recorder.loopback_error:
            parts.append("(solo el micrófono: no pude grabar el sonido de la computadora)")
        else:
            parts.append("con el micrófono y el sonido de la computadora")
        text = " ".join(parts) + "."
        # Every meeting, not once a day: grabar a otros sin su consentimiento
        # puede ser delito (COIP art. 178 en Ecuador; docs/LEGAL.md).
        reminded_consent[0] = time.strftime("%Y-%m-%d")
        text += (
            " Avise a todos de que estoy grabando y tomando notas, y pare si"
            " alguien no está de acuerdo."
        )
        return text

    def finish_meeting(rec: Any) -> None:
        import datetime as _dt
        import json as _json

        try:
            tracks = {"sala": read_wav(rec.room)}
            if rec.call is not None:
                tracks["llamada"] = read_wav(rec.call)
            turns = []
            try:
                encoder = voices.encoder()
                boss = owner_name()
                turns = diarize(
                    tracks,
                    encoder.embed,
                    lambda p: voice_book.identify(p, boss, 3.0),
                )
            except Exception:  # noqa: BLE001 — no voiceprints: Gemini tells voices apart
                logging.info("diarization unavailable", exc_info=True)
            audio = mix(tracks)
            path, mime = encode(audio, rec.folder)
            when = _dt.datetime.fromtimestamp(rec.started).strftime("%d/%m/%Y %H:%M")
            speakers = list(dict.fromkeys(t.speaker for t in turns))
            data = client.meeting_summary(
                path.read_bytes(), mime, timeline_text(turns), kind=meeting_kind[0],
                when=when, seconds=rec.seconds, speakers=speakers,
            )
            folder = Path.home() / "Documents" / "Sergio" / "Reuniones"
            folder.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w áéíóúñÁÉÍÓÚÑ-]", "", str(data.get("titulo") or "Reunión"))[:60].strip() or "Reunión"
            notes = folder / f"{_dt.datetime.fromtimestamp(rec.started):%Y-%m-%d %H%M} {safe}.md"
            notes.write_text(str(data.get("markdown") or ""), encoding="utf-8")
            (rec.folder / "acta.json").write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")
            for raw in (rec.room, rec.call):  # the minutes stay; the raw tracks go
                if raw is not None:
                    Path(raw).unlink(missing_ok=True)
            last_minutes[:] = [dict(data, path=str(notes))]
            tell(f"El acta está lista, señor. {spoken_summary(data)}")
            bridge.caption.emit(f"Acta guardada en Documentos › Sergio › Reuniones: {notes.name}")
        except Exception as exc:  # noqa: BLE001
            logging.exception("meeting minutes failed")
            tell(f"No pude escribir el acta: {str(exc)[:160]}. El audio quedó en {rec.folder}.")

    def meeting_stop() -> str:
        rec = recorder.stop()
        if rec is None:
            if last_minutes:
                return meeting_last()
            return "No estaba tomando notas. Para empezar diga «Sergio, toma notas de la reunión»."
        minutes = max(1, round(rec.seconds / 60))
        threading.Thread(target=finish_meeting, args=(rec,), daemon=True).start()
        return f"Listo. Escribo el acta de {minutes} minuto{'s' if minutes != 1 else ''} y le aviso."

    def meeting_last() -> str:
        if not last_minutes:
            folder = Path.home() / "Documents" / "Sergio" / "Reuniones"
            files = sorted(folder.glob("*.md")) if folder.exists() else []
            if not files:
                return "Aún no tengo actas. Diga «toma notas de la reunión» la próxima vez."
            text = files[-1].read_text(encoding="utf-8")
            summary = text.split("## Resumen", 1)[-1].split("##", 1)[0].strip()
            return f"Del acta «{files[-1].stem}»: {summary[:600]}"
        return spoken_summary(last_minutes[0])

    controller.skills["meeting_start"] = lambda args: meeting_start(str(args.get("kind") or "reunión"))
    controller.skills["meeting_stop"] = lambda _args: meeting_stop()

    def voice_forget(name: str = "") -> str:
        who = name.strip() or owner_name()
        if who and voice_book.forget(who):
            return f"Olvidé la voz de {who}."
        return f"No tenía guardada la voz de {who or 'esa persona'}."

    call_start_lock = threading.Lock()

    def sergio_window_in_front() -> bool:
        """The Sergio app window is the one in front: it hears the owner, so
        the desktop does not take the voice from it."""
        if sys.platform != "win32":
            return False
        from sergio_escritorio.windows_backend import foreground_title

        title = foreground_title()
        return title == "Sergio" or title.startswith("Sergio ")

    def start_call(prefill: bytes = b"", force: bool = False, quiet: bool = False) -> bool:
        with call_start_lock:
            return _start_call(prefill, force, quiet)

    def _start_call(prefill: bytes = b"", force: bool = False, quiet: bool = False) -> bool:
        """Open a live call (from a worker thread). False = use turns."""
        if not client.voice.lower().startswith("gemini:"):
            return False  # retain ElevenLabs/Edge identity through the turn route
        if not force and config.get("conversation", "llamada") != "llamada":
            return False
        if not quiet:
            call_paused[0] = False  # you called him: always-on again
        if call_active():
            return True
        if not force and time.monotonic() - call_failed_at[0] < 20:
            return False  # it failed a moment ago: don't make you wait again
        from sergio_escritorio.voice import wav_pcm

        session = new_session()
        # Called on purpose (wake word, shortcut): the voice comes back here
        # even if an app window had it. The quiet keeper never takes it.
        session.force = not quiet and not sergio_window_in_front()
        current_call[0] = session
        ears.call = session
        if not session.start(wav_pcm(prefill) if prefill else b""):
            current_call[0] = None
            ears.call = None
            call_failed_at[0] = time.monotonic()
            call_busy[0] = bool(getattr(session, "busy", False))
            if call_busy[0]:
                # Not a failure: the app window already hears the owner and
                # answers. Quiet, and try again in a little while.
                call_backoff[0] = 20.0
                call_error[0] = ""
                ears.mark("la ventana de Sergio tiene la voz")
                return False
            call_error[0] = session.error
            logging.warning("live call unavailable: %s", session.error)
            ears.mark(f"la llamada falló: {session.error[:80]}")
            if not quiet:
                bridge.caption.emit(f"Voz en vivo no disponible: {session.error[:240]}")
            return False
        call_error[0] = ""
        call_backoff[0] = 20.0
        call_busy[0] = False
        ears.mark(f"llamada lista ({session.model})")
        bridge.call_on.emit(True)
        bridge.screen_on.emit(session.share_screen)
        voices.enabled = bool(voice_book.people())  # who is talking, live
        return True

    first_voice = [False]

    def call_state(name: str) -> None:
        if name == "speaking" and not first_voice[0]:
            first_voice[0] = True
            ears.mark("primera palabra de Sergio")
        elif name == "listening":
            first_voice[0] = False
        bridge.state.emit(name)

    wake_cancelled = [False]

    def on_wake(event: str) -> None:
        """Instant wake word: connect while you are still talking."""
        if event == "maybe":
            wake_cancelled[0] = False
            bridge.state.emit("listening")  # he heard his name

            def connect() -> None:
                if not start_call():
                    if call_busy[0]:
                        ears.wake_elsewhere()  # the window answers it
                        bridge.state.emit("idle")
                    else:
                        ears.wake_failed()
                elif wake_cancelled[0]:
                    end_call("cancelado")

            threading.Thread(target=connect, daemon=True).start()
        elif event == "no":
            wake_cancelled[0] = True
            session = current_call[0]
            if session is not None and session.active and not session.heard_anything:
                end_call("cancelado")
            else:
                bridge.state.emit("idle")

    ears.on_wake = on_wake

    def load_wake_word() -> None:
        from sergio_escritorio.listen import WAKE_NAMES
        from sergio_escritorio.wake import load_spotter

        spotter = load_spotter(HOME, list(WAKE_NAMES))
        if spotter is not None:
            ears.spotter = spotter
            logging.info("instant wake word on")

    if ears.wake_word:
        threading.Thread(target=load_wake_word, daemon=True).start()

    def end_call(why: str = "colgaste") -> None:
        session = current_call[0]
        if session is not None:
            session.hang_up(why)

    def keep_call() -> None:
        """Always on: open the call at start-up and whenever it drops (a
        network cut, Google rotating the session), with a growing pause after
        failures (20 s, 40 s… up to 5 min). Silence costs nothing: the
        microphone only streams while someone talks."""
        time.sleep(8)  # let the rest of Sergio start first
        while True:
            try:
                wanted = (
                    config.get("call_always", True)
                    and config.get("conversation", "llamada") == "llamada"
                    and not call_paused[0]
                )
                if wanted and not call_active() and time.monotonic() - call_failed_at[0] > call_backoff[0]:
                    if not start_call(force=True, quiet=True) and not call_busy[0]:
                        call_backoff[0] = min(300.0, call_backoff[0] * 2)
            except Exception:  # noqa: BLE001 — the keeper never dies
                logging.exception("always-on call keeper")
            time.sleep(3)

    if config["call_always"]:
        threading.Thread(target=keep_call, daemon=True, name="call-keeper").start()

    def talk_hotkey() -> bool:
        """Ctrl+Space: start or end the call (else push-to-talk)."""
        if call_active():
            end_call()
            return True
        if config.get("conversation", "llamada") != "llamada":
            return False
        bridge.state.emit("thinking")
        bridge.caption.emit("Llamando a Sergio…")

        def run() -> None:
            if not start_call(force=True):
                if call_busy[0]:
                    bridge.state.emit("idle")
                    return
                bridge.caption.emit(f"Voz en vivo no disponible: {call_error[0][:240]}")
                if config.get("allow_turn_fallback", False):
                    bridge.ptt.emit()

        threading.Thread(target=run, daemon=True).start()
        return True

    assistant.start_call = start_call
    assistant.allow_turn_fallback = (config.get("conversation", "llamada") != "llamada"
                                     or bool(config.get("allow_turn_fallback", False)))
    ears.on_talk = talk_hotkey
    bridge.ptt.connect(ears.ptt)

    def call_changed(on: bool) -> None:
        notch.set_call(on)
        for panel in panels:
            for tile in panel.tiles:
                tile.sync()

    bridge.call_on.connect(call_changed)
    bridge.screen_on.connect(notch.set_screen_sharing)
    notch.set_reduce_motion(bool(config.get("reduce_motion", False)))

    # Gemini on the screen: while he watches it live, a soft light breathes
    # along the edges of the monitor he sees (brighter while he talks).
    from sergio_escritorio.screen_glow import ScreenGlow

    glow = ScreenGlow(reduce_motion=bool(config.get("reduce_motion", False)))

    def glow_box() -> tuple[int, int, int, int] | None:
        # the shared frame is in real pixels; the glow needs the Qt screen
        try:
            from PySide6.QtCore import QPoint
            from PySide6.QtGui import QGuiApplication

            from sergio_escritorio.companion import to_logical

            origin = to_logical(*live.latest(look=False).origin).toPoint()
            screen = QGuiApplication.screenAt(origin + QPoint(4, 4))
            if screen is None:
                return None
            g = screen.geometry()
            return (g.x(), g.y(), g.width(), g.height())
        except Exception:  # noqa: BLE001 — then the monitor under the mouse
            return None

    bridge.screen_on.connect(lambda on: glow.set_on(on, glow_box() if on else None))
    bridge.level.connect(glow.set_level)
    bridge.state.connect(lambda name: glow.set_level(glow.level, speaking=name == "speaking"))
    reduced_action.toggled.connect(lambda on: setattr(glow, "reduce_motion", bool(on)))

    # -- mental gym: an exercise you cannot skip every 12 minutes -------------
    from PySide6.QtCore import QTimer

    from sergio_escritorio.gym import (
        GymSchedule,
        GymStats,
        GymWindow,
        idle_seconds,
        screen_locked,
        word_validator,
    )

    gym_stats = GymStats.load(HOME / "gimnasio.json")
    gym_stats.prefs = profile.gym_prefs()
    apply_profile()

    def remember_due(due: float) -> None:
        gym_stats.next_due = due
        gym_stats.save()

    schedule = GymSchedule(
        float(config.get("gym_minutes", 12)),
        away=idle_seconds,
        locked=screen_locked,
        busy=lambda: call_active() or recorder.active or foreground_is_fullscreen(),
        due=gym_stats.next_due,
        on_change=remember_due,
    )
    schedule.enabled = bool(config.get("gym_addon") and config.get("gym", True))

    def apply_gym_addon(on: bool) -> None:
        config["gym_addon"] = bool(on)
        save_config(config)
        schedule.enabled = bool(on and config.get("gym", True))
        for item in gym_menu:
            item.setVisible(bool(on))

    def sync_gym_addon() -> None:
        """The add-on as the server has it (also changed from the web)."""
        import httpx

        try:
            data = httpx.get(api_base(config["server_url"]) + "/v1/personal/complementos", timeout=5).json()
        except Exception:  # noqa: BLE001 — server off: what this PC last knew
            return
        on = any(a.get("clave") == "gimnasio" and a.get("activo") for a in data.get("complementos") or [])
        if on != bool(config.get("gym_addon")):
            on_ui(lambda: apply_gym_addon(on))

    def push_gym_addon(on: bool) -> None:
        import httpx

        try:
            httpx.put(api_base(config["server_url"]) + "/v1/personal/complementos/gimnasio",
                      json={"activa": bool(on)}, timeout=5)
        except Exception:  # noqa: BLE001 — server off: this PC keeps it
            pass

    threading.Thread(target=sync_gym_addon, daemon=True).start()
    gym_sync = QTimer()
    gym_sync.timeout.connect(lambda: threading.Thread(target=sync_gym_addon, daemon=True).start())
    gym_sync.start(5 * 60 * 1000)
    gym_windows: list[Any] = []
    snoozed_once = [False]

    def gym_speak(text: str) -> None:
        threading.Thread(
            target=lambda: assistant.say_aloud(text) if not assistant.busy else None,
            daemon=True,
        ).start()

    def open_gym() -> str:
        if not config.get("gym_addon"):
            return ("El Gimnasio Mental es un complemento opcional. El cerebro humano está frito por "
                    "las redes sociales; el tuyo puede volverse un genio. Actívelo en Ajustes, Complementos.")
        if gym_windows:
            return "Ya hay un ejercicio en curso."
        if call_active():
            current_call[0].hang_up("gimnasio")
        assistant.stop_speaking()
        exercise = gym_stats.take_next()
        window = GymWindow(
            exercise,
            stats=gym_stats,
            speak=gym_speak,
            validate_word=word_validator(client.chat_fast),
        )
        window.can_snooze = not snoozed_once[0]  # «Ahora no» once per exercise
        gym_windows.append(window)
        if not schedule.running:
            schedule.started()  # opened by hand or by voice

        def done(session: Any) -> None:
            gym_windows.clear()
            if window.snoozed:
                snoozed_once[0] = True
                schedule.snooze()
                bridge.caption.emit("Gimnasio mental en 10 minutos.")
                return
            snoozed_once[0] = False
            schedule.done()
            if session.absent:
                bridge.caption.emit("Gimnasio mental: no estabas; vuelve en unos minutos.")
                return
            bridge.caption.emit(
                f"Gimnasio mental, {exercise.title}: {session.summary()} {session.verdict()}"
            )
            threading.Thread(target=analyse_gym, daemon=True).start()  # in the background

        window.finished.connect(done)
        window.start()
        return f"Empieza el gimnasio mental: {exercise.title}."

    gym_analysis: list[dict] = []
    results_windows: list[Any] = []

    def analyse_gym() -> dict:
        """Everything worth knowing from the answers (after each session,
        in the background), kept for «Tus resultados»."""
        from sergio_escritorio.brain import analysis

        try:
            found = analysis(list(gym_stats.history))
            (HOME / "gimnasio_analisis.json").write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
            gym_analysis[:] = [found]
            return found
        except Exception:  # noqa: BLE001 — never break the gym
            logging.exception("gym analysis failed")
            return {}

    def open_results() -> str:
        from sergio_escritorio.gym_results import GymResults

        found = gym_analysis[0] if gym_analysis else analyse_gym()

        def show() -> None:
            window = GymResults(gym_stats.history, found)
            results_windows[:] = [window]
            window.open()

        on_ui(show)
        return "Aquí están sus resultados, señor."

    def gym_report() -> str:
        from sergio_escritorio.gym_results import results_sentence

        found = gym_analysis[0] if gym_analysis else analyse_gym()
        return f"{gym_stats.report()} {results_sentence(found)}".strip()

    threading.Thread(target=analyse_gym, daemon=True).start()
    absent_said = [False]

    def start_if_here() -> None:
        """Worker thread: a quick look through the webcam (local, nothing
        saved) before an exercise; nobody there = it waits for you."""
        from sergio_escritorio.camera import someone_there

        try:
            here = someone_there(feed)
        except Exception:  # noqa: BLE001 — no camera: the keyboard decides
            here = None

        def decide() -> None:
            if here is False:
                schedule.not_here()
                if not absent_said[0]:
                    absent_said[0] = True
                    bridge.caption.emit("Gimnasio mental: no te veo en la cámara; empiezo cuando vuelvas.")
                return
            absent_said[0] = False
            open_gym()

        try:
            on_ui(decide)
        except Exception:  # noqa: BLE001
            logging.exception("mental gym failed to start")
            on_ui(schedule.done)

    # -- Night Shift: the evening wound down, from sleep research ----------------
    import datetime as _dt

    from sergio_escritorio import nocturno
    from sergio_escritorio.nocturno_ui import NightScreen, NightSheet, VeilTint

    night_diary = nocturno.Diary.load(SERGIO_HOME / "sueno.json")
    night_screen = NightScreen()
    # The screen is tinted on its own thread: Windows' colour matrix first, a
    # verified gamma ramp next, the veil only as a last resort.
    night_engine = nocturno.NightEngine(nocturno.ChainTint([*nocturno.windows_tints(), VeilTint(night_screen)]))
    night_engine.start()
    night_state: dict[str, Any] = {"look": None, "said": set(), "preview_until": 0.0}

    def night_settings() -> nocturno.Settings:
        return nocturno.load_settings(config.get("night"))

    def night_dusk(s: nocturno.Settings | None = None) -> _dt.time | None:
        s = s or night_settings()
        lat, lon = s.lat, s.lon
        if lat is None and location.fix is not None:
            lat, lon = location.fix.lat, location.fix.lon
        if lat is None or lon is None:
            return None
        offset = (time.localtime().tm_gmtoff or 0) / 3600
        return nocturno.sunset(_dt.date.today(), float(lat), float(lon), offset)

    def night_now() -> nocturno.Moment:
        s = night_settings()
        return nocturno.moment(_dt.datetime.now(), s, night_dusk(s))

    def night_quiet() -> bool:
        try:
            return night_now().quiet
        except Exception:  # noqa: BLE001
            return False

    def night_look(s: nocturno.Settings) -> tuple[float, float]:
        m = nocturno.moment(_dt.datetime.now(), s, night_dusk(s))
        return (m.kelvin, m.brightness) if s.warmth else (nocturno.DAY_K, 1.0)

    def save_night(s: nocturno.Settings, fade_s: float = 1.2) -> None:
        config["night"] = nocturno.dump_settings(s)
        save_config(config)
        night_state["preview_until"] = 0.0
        night_engine.go(*night_look(s), fade_s=fade_s)  # changes are seen right away, faded

    def set_night_warmth(on: bool) -> None:
        """The control center's «Pantalla» switch: Night Shift on or off."""
        import dataclasses

        save_night(dataclasses.replace(night_settings(), warmth=bool(on)))

    def night_preview(kelvin: float, brightness: float) -> None:
        night_state["preview_until"] = time.monotonic() + 4
        night_engine.go(kelvin, brightness, fade_s=0.25)

    night_sheet: dict[str, Any] = {"w": None}

    def open_night_sheet() -> None:
        if night_sheet["w"] is None:
            night_sheet["w"] = NightSheet(night_settings, save_night, night_preview, night_dusk)
        night_sheet["w"].open()

    def night_tick() -> None:
        try:
            s = night_settings()
            m = nocturno.moment(_dt.datetime.now(), s, night_dusk(s))
            if time.monotonic() >= night_state["preview_until"]:
                # Every 15 s a tiny step, faded over 15 s: the evening flows.
                night_engine.go(*night_look(s), fade_s=15.0)
            today = _dt.date.today().isoformat()
            key = f"{today}:{m.phase}"
            if s.on and m.phase in nocturno.TIPS and key not in night_state["said"]:
                night_state["said"].add(key)
                if m.phase == "relajacion":
                    tell(nocturno.TIPS[m.phase])
                else:
                    bridge.caption.emit(nocturno.TIPS[m.phase])
            cut = nocturno.caffeine_cutoff(s)
            coffee = f"{today}:cafe"
            now = _dt.datetime.now().time()
            if s.on and coffee not in night_state["said"] and cut <= now < (
                    _dt.datetime.combine(_dt.date.today(), cut) + _dt.timedelta(minutes=30)).time():
                night_state["said"].add(coffee)
                bridge.caption.emit(nocturno.caffeine_note(s))
        except Exception:  # noqa: BLE001 — the evening never breaks Sergio
            logging.exception("night shift tick failed")

    night_timer = QTimer()
    night_timer.timeout.connect(night_tick)
    night_timer.start(15_000)
    QTimer.singleShot(1500, night_tick)

    def run_night(q: Any) -> str | None:
        if not q.kind.startswith("night_"):
            return None
        s = night_settings()
        if q.kind == "night_on":
            s.on = s.warmth = True
            save_night(s, fade_s=2.5)
            return nocturno.describe(s, dusk=night_dusk(s)) + " Diga «night shift más fuerte» o «al 60 %» para ajustarlo."
        if q.kind == "night_off":
            s.on = False
            s.force_until = ""
            save_night(s, fade_s=2.5)
            return "Night Shift apagado; la pantalla vuelve a la normalidad."
        if q.kind in ("night_more", "night_less", "night_level"):
            value = float(q.arg) if q.kind == "night_level" else s.intensity + (0.15 if q.kind == "night_more" else -0.15)
            nocturno.set_intensity(s, value)
            s.on = s.warmth = True
            save_night(s)
            k, b = nocturno.looks(s)["night"]
            return (f"Night Shift al {round(s.intensity * 100)} %: a la hora de dormir, {round(k)} K y "
                    f"{round(b * 100)} % de luz.")
        if q.kind == "night_now":
            nocturno.force_now(s)
            save_night(s, fade_s=3.0)
            return f"Modo noche ya, hasta las {s.wake}. Diga «night shift normal» para volver al horario."
        if q.kind == "night_auto":
            s.force_until = ""
            save_night(s, fade_s=3.0)
            return "Vuelvo al horario: " + nocturno.describe(s, dusk=night_dusk(s))
        if q.kind == "night_settings":
            on_ui(open_night_sheet)
            return "Le abro el Night Shift."
        if q.kind == "night_status":
            return nocturno.describe(s, dusk=night_dusk(s))
        if q.kind == "night_wake":
            s.wake = q.arg
            save_night(s)
            return (f"Anotado: se levanta a las {s.wake}, todos los días. A la cama a las "
                    f"{nocturno.bedtime(s).strftime('%H:%M')}; último café a las "
                    f"{nocturno.caffeine_cutoff(s).strftime('%H:%M')}.")
        if q.kind == "night_need":
            s.need_h = max(6.0, min(10.0, float(q.arg)))
            save_night(s)
            extra = " Menos de 7 h no es lo recomendado para adultos." if s.need_h < 7 else ""
            return f"Planifico {s.need_h:g} h: a la cama a las {nocturno.bedtime(s).strftime('%H:%M')}.{extra}"
        if q.kind == "night_bedtime":
            times = nocturno.bedtimes_for(q.arg, s.need_h)
            return (f"Para levantarse a las {q.arg}: a la cama a las {times[0]} ({s.need_h:g} h de sueño). "
                    f"Por ciclos de unos 90 min, también {' o '.join(times[1:])} (es una estimación).")
        if q.kind == "night_diary":
            bed, wake = q.arg.split("-")
            night_diary.add(bed, wake)
            st = nocturno.stats(night_diary.nights)
            return (f"Anotado: de {bed} a {wake}. Media de {st['noches']} noches: {st['horas']} h, "
                    f"regularidad {st['regularidad']}/100." if st else "Anotado.")
        if q.kind == "night_report":
            return nocturno.report(night_diary.nights, s)
        if q.kind == "night_insomnia":
            return nocturno.INSOMNIA
        if q.kind == "night_caffeine":
            return nocturno.caffeine_note(s)
        return None

    quick_handlers.append(run_night)
    section_openers["night"] = lambda _a="": on_ui(open_night_sheet)  # the tile: the sheet
    app.aboutToQuit.connect(night_engine.stop)  # back to normal colours on the way out

    def gym_check() -> None:
        if night_quiet():  # no pop-ups in the hour before bed or at night
            return
        try:
            if schedule.check():
                if config.get("gym_camera", True):
                    threading.Thread(target=start_if_here, daemon=True).start()
                else:
                    open_gym()
        except Exception:  # noqa: BLE001 — never kill the timer
            logging.exception("mental gym failed to start")
            schedule.done()

    gym_timer = QTimer()
    gym_timer.timeout.connect(gym_check)
    gym_timer.start(10_000)

    def set_gym(on: bool) -> None:
        config["gym"] = on
        apply_gym_addon(on)  # the toggle adds or removes the add-on itself
        threading.Thread(target=push_gym_addon, args=(on,), daemon=True).start()
        if on:
            schedule.postpone_from_now()
        bridge.caption.emit(
            f"Gimnasio mental cada {int(schedule.interval // 60)} minutos."
            if on
            else "Gimnasio mental apagado."
        )

    def set_call_tile(on: bool) -> None:
        if on and not call_active():
            talk_hotkey()
        elif not on and call_active():
            end_call()

    bridge.toggle.connect(lambda: set_control(not controller.enabled))
    # One keyboard hook for the shortcuts and Ctrl+Alt (each pynput listener
    # is a system-wide hook that every key press waits on).
    hotkeys = [
        keyboard.HotKey(keyboard.HotKey.parse(combo), action)
        for combo, action in (
            (HOTKEY_TALK, bridge.talk.emit),
            (HOTKEY_STOP, bridge.toggle.emit),
            (HOTKEY_CAMERA, bridge.camera.emit),
        )
    ]

    # Clicky: hold Ctrl+Alt, talk while holding, release to send. Sergio looks
    # at your screen with the question and points at what you need.
    from sergio_escritorio.hold import HoldDetector

    def hold_start() -> None:
        if call_active():  # in a call: he looks at your screen right away
            threading.Thread(target=look_screen, args=("",), daemon=True).start()
            bridge.caption.emit("Mirando tu pantalla…")
        else:
            ears.hold_start()

    detector = HoldDetector(hold_start, ears.hold_end, ears.hold_cancel)

    def notch_hold_start() -> None:
        # Do not make the Qt event loop wait for playback to stop.
        if assistant.busy and not call_active():
            assistant.stop_speaking()
        else:
            hold_start()

    notch.on_hold_start = notch_hold_start
    notch.on_hold_end = ears.hold_end
    notch.on_hold_cancel = ears.hold_cancel
    keys: Any = None

    def key_down(key: Any) -> None:
        if key == keyboard.Key.esc and guide_overlay.showing:
            bridge.run.emit(guide_overlay.dismiss)  # Esc: the drawings go
        detector.press(key)
        for hotkey in hotkeys:
            hotkey.press(keys.canonical(key))

    def key_up(key: Any) -> None:
        detector.release(key)
        for hotkey in hotkeys:
            hotkey.release(keys.canonical(key))

    keys = keyboard.Listener(on_press=key_down, on_release=key_up)
    keys.start()
    # The companion's hop on a click: the button state is read 20 times a
    # second instead of a system-wide mouse hook, which made the cursor
    # stutter whenever Python was busy (owner, 26 Oct 2026: «realentiza el cursor»).
    start_click_watch(bridge.clicked.emit)

    # -- extra windows (blocking, agents) and the language ---------------------
    from sergio_escritorio import bloqueo
    from sergio_escritorio import idioma as _idioma

    world_windows: dict[str, Any] = {}
    last_plane = [""]

    def lang_now() -> str:
        return str(config.get("language") or _idioma.system_language())

    def follow_flight(number: str) -> str:
        number = number or last_plane[0]
        fix = location.get() if not number else None
        if fix is not None:  # «este vuelo»: the plane above us now
            number = str(client.overhead(fix.lat, fix.lon, fix.alt).get("callsign") or "")
            last_plane[0] = number
        if not number:
            return "¿Qué vuelo? Dígame el número, por ejemplo «sigue el vuelo AV 123»."

        return client.flight(number)  # said in words: no flight window

    blocks = bloqueo.Store(HOME / "bloqueo.json")
    guard = bloqueo.Guard(
        blocks,
        title=lambda: getattr(controller.backend, "active_window", lambda: "")(),
        close_tab=lambda: controller.act({"action": "key", "keys": "ctrl+w"}),
        told=lambda text: bridge.caption.emit(text),
    )
    guard.start()

    def block_on() -> str:
        return bloqueo.switch_on(blocks)

    def block_off() -> str:
        if not blocks.list.on:
            return "El bloqueo ya está apagado."
        return bloqueo.switch_off(blocks, owner_approves("quitar el bloqueo"))

    def show_blocks() -> str:
        from sergio_escritorio.bloqueo_ui import BlockWindow

        def show() -> None:
            if "block" not in world_windows:
                world_windows["block"] = BlockWindow(blocks, block_on, block_off)
            world_windows["block"].open()

        on_ui(show)
        return "Aquí está su lista de bloqueo."

    def set_language(code: str) -> str:
        config["language"] = code
        save_config(config)
        apply_brain(config)
        names = {"es": "Listo, sigo en español.", "en": "Done, sir: English from now on.",
                 "pt": "Pronto, senhor: agora em português.", "fr": "C'est fait, monsieur : en français.",
                 "de": "Erledigt: ab jetzt auf Deutsch.", "it": "Fatto, signore: ora in italiano."}
        return names.get(code, "Listo.") + " (El panel cambia de idioma al reiniciar a Sergio.)"

    def set_country(code: str) -> str:
        config["country"] = code
        save_config(config)
        apply_brain(config)
        where = _idioma.country(code)
        return f"Anotado: {where.name}. Emergencias {where.emergency}; apoyo: {where.crisis}."

    def run_world(q: Any) -> str | None:
        if q.kind == "distance":
            from sergio_escritorio.vision import distance_answer

            if not camera_window.active:
                on_ui(camera_window.open)
                time.sleep(1.5)
            resp = client.http.post(
                f"{client.base}/v1/vision/scene",
                files={"image": ("camara.jpg", feed.jpeg(), "image/jpeg")},
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
            return distance_answer(q.arg, data.get("items") or [], data.get("relations") or [])
        if q.kind == "flight_follow":
            return follow_flight(q.arg)
        if q.kind == "block_add":
            kind, _, what = q.arg.partition(":")
            added = blocks.list.add(kind, what)
            blocks.save()
            if not added:
                return "Eso ya estaba en la lista (o no se puede bloquear)."
            if blocks.list.on and kind == "sites":
                bloqueo.write_policies(blocks.list.sites)
            label = {"apps": "la app", "sites": "la web", "words": "las búsquedas de"}[kind]
            return f"Añadí {label} {added} al bloqueo." + ("" if blocks.list.on else " Diga «activa el bloqueo» cuando quiera.")
        if q.kind == "block_on":
            return block_on()
        if q.kind == "block_off":
            return block_off()
        if q.kind == "block_show":
            return show_blocks()
        if q.kind == "language":
            return set_language(q.arg)
        if q.kind == "country":
            return set_country(q.arg)
        return None

    quick_handlers.append(run_world)

    # -- useless apps out with one «sí», throwaway files without asking ---------
    import sergio_escritorio.apps_limpieza as apps_limpieza

    def clean_apps() -> None:
        live = activities.start("Limpieza de apps", "task", "revisando lo instalado")
        try:
            found = apps_limpieza.audit(apps_limpieza.installed())
            freed = apps_limpieza.clean_temp()
            config["temp_clean"] = time.time()
            save_config(config)
            note = f" Además liberé {freed / 1e6:.0f} MB de archivos temporales." if freed > 5e6 else ""
            if not found:
                activities.finish(live, True, "nada que quitar")
                tell("No encontré apps inútiles ni duplicadas." + note)
                return
            bridge.caption.emit(apps_limpieza.describe(found))
            tell(f"Encontré {len(found)} apps que sobran; están en pantalla. Mire a la cámara para quitarlas todas.")
            time.sleep(8)  # time to read the list before the approval prompt replaces it
            if not owner_approves(f"desinstalar {len(found)} apps", 20.0):
                activities.finish(live, False, "sin su aprobación")
                tell("Las dejo como están." + note)
                return
            activities.update(live, detail=f"quitando {len(found)} apps")
            done = apps_limpieza.remove([a for a, _ in found])
            ok = [n for n, worked in done if worked]
            failed = [n for n, worked in done if not worked]
            activities.finish(live, not failed, f"{len(ok)} quitadas")
            tell(f"Quité {len(ok)} apps." + (f" No pude con: {', '.join(failed[:5])}." if failed else "") + note)
        except Exception as exc:  # noqa: BLE001
            activities.finish(live, False, "falló")
            tell(f"No pude revisar las apps: {exc}")

    def weekly_temp_clean() -> None:
        if time.time() - float(config.get("temp_clean") or 0) > 7 * 86400:
            config["temp_clean"] = time.time()
            save_config(config)
            apps_limpieza.clean_temp()

    threading.Thread(target=weekly_temp_clean, daemon=True).start()

    def learn_skill(source: str) -> str:
        import base64

        from sergio_escritorio.media import resolve

        path = resolve(source) if source else None
        if path is None or not path.is_file():
            return "Dígame qué PDF: «aprende el manual C:\\ruta\\manual.pdf» (o su nombre en Descargas)."
        data = path.read_bytes()
        body = ({"name": path.stem, "pdf_b64": base64.b64encode(data).decode()} if path.suffix.lower() == ".pdf"
                else {"name": path.stem, "text": data.decode("utf-8", "ignore")})

        def work() -> None:
            live = activities.start(f"Aprendiendo {path.stem[:30]}", "search", "leyendo el manual")
            try:
                resp = client.http.post(f"{client.base}/v1/skills/learn", json=body, timeout=300)
                resp.raise_for_status()
                skill = resp.json()
                activities.finish(live, True, f"{skill['reglas']} reglas")
                tell(f"Aprendido: «{skill['nombre']}», {skill['reglas']} reglas. Las aplico solo cuando "
                     f"pida algo de {', '.join(skill['claves'][:4])}.")
            except Exception as exc:  # noqa: BLE001
                activities.finish(live, False, "no pude")
                tell(f"No pude aprender ese documento: {exc}")

        threading.Thread(target=work, daemon=True).start()
        return f"Leo «{path.name}» y saco sus reglas; le aviso al terminar."

    def run_cleanup_and_skills(q: Any) -> str | None:
        if q.kind == "apps_clean":
            threading.Thread(target=clean_apps, daemon=True).start()
            return "Reviso sus apps; nada se quita sin su cara."
        if q.kind == "skill_learn":
            return learn_skill(q.arg)
        if q.kind == "skills_show":
            resp = client.http.get(f"{client.base}/v1/skills", timeout=20)
            resp.raise_for_status()
            names = [s["nombre"] for s in resp.json().get("skills", [])]
            return "Mis skills permanentes: " + ", ".join(names) + "." if names else "Aún no tengo skills."
        return None

    quick_handlers.append(run_cleanup_and_skills)

    # -- multitasking: complex tasks in the foreground and the background --------
    from sergio_escritorio.tareas import Orchestrator

    def plan_task(request: str, agent: dict | None = None) -> dict:
        body: dict[str, Any] = {"request": request}
        if agent:  # the agent's role and its own toolbox
            body.update(tools=agent.get("herramientas"), role=f"{agent['nombre']}: {agent.get('instrucciones', '')}")
        resp = client.http.post(f"{client.base}/v1/tasks/plan", json=body, timeout=90)
        resp.raise_for_status()
        return resp.json()

    def new_asker() -> Any:
        """Each task thinks in its own conversation (tasks never mix up)."""
        worker = SergioClient(config["server_url"], api_key=str(config.get("server_api_key") or ""))
        worker.personality, worker.effort = client.personality, client.effort
        worker.country_name = client.country_name
        return lambda text: worker.ask(text, force_agent=True)

    from sergio_escritorio.tareas import plan_line

    def file_exists(path: str) -> bool | None:
        """Windows paths are checked here; Ubuntu ones through \\wsl$ when possible."""
        expanded = os.path.expanduser(path)
        if re.match(r"^[A-Za-z]:\\", expanded) or path.startswith("~"):
            return Path(expanded).exists()
        wsl = Path(r"\\wsl$\Ubuntu" + path.replace("/", "\\"))
        try:
            return wsl.exists() if path.startswith(("/home/", "/mnt/")) and os.name == "nt" else None
        except OSError:
            return None

    def task_done(task: Any) -> None:
        if task.agent and task.status == "done":
            agents.remember(task.agent["nombre"], task.result)

    orchestrator = Orchestrator(
        plan_task, new_asker, activities, approve=owner_approves, told=lambda text: tell(text),
        on_plan=lambda task: bridge.caption.emit(plan_line(task)),  # the plan, seen before the work
        on_done=lambda task: task_done(task),
        plan_grace=6.0,
        exists=file_exists,
        review=True,
    )
    panel.actions.swarm_details = orchestrator.snapshot
    panel.actions.swarm_cancel = orchestrator.cancel_task
    panel.actions.swarm_task = orchestrator.task_details

    def run_tasks(q: Any) -> str | None:
        if q.kind == "task_bg":
            task = orchestrator.submit(q.arg)
            return f"En marcha en segundo plano: «{task.request[:60]}». Siga con lo suyo; le aviso al terminar."
        if q.kind == "tasks_together":
            started = [orchestrator.submit(part) for part in q.arg.split("\n") if part.strip()]
            return f"Arranco {len(started)} tareas a la vez; las ve en el notch."
        if q.kind == "tasks_status":
            return activities.describe()
        if q.kind == "task_cancel":
            return orchestrator.cancel_last()
        return None

    quick_handlers.append(run_tasks)

    # -- agents: the pro ones and the ones the user creates ---------------------
    from sergio_escritorio.agentes import Agents, describe

    agents = Agents(HOME / "agentes.json")

    def agent_job(agent: dict, job: str) -> str:
        orchestrator.submit(job, agent=agents.with_memory(agent))
        return f"{agent['nombre']} se pone con ello en segundo plano. Le aviso al terminar."

    def create_agent(description: str) -> str:
        def run() -> None:
            try:
                resp = client.http.post(f"{client.base}/v1/tasks/agent", json={"description": description}, timeout=90)
                resp.raise_for_status()
                spec = agents.add(resp.json())
                tell(f"Agente listo. {describe(spec)}")
                if "agents" in world_windows:
                    on_ui(world_windows["agents"].refresh)
            except Exception as exc:  # noqa: BLE001
                tell(f"No pude crear el agente: {exc}")

        threading.Thread(target=run, daemon=True).start()
        return "Diseñando el agente; le aviso en unos segundos."

    def show_agents() -> str:
        from sergio_escritorio.agentes_ui import AgentsWindow

        def show() -> None:
            if "agents" not in world_windows:
                world_windows["agents"] = AgentsWindow(agents, agent_job, create_agent)
            world_windows["agents"].open()

        on_ui(show)
        return ""

    def run_agents(q: Any) -> str | None:
        if q.kind != "agent":
            return None
        what, name, job = (q.arg.split("\n") + ["", ""])[:3]
        if what == "show":
            return show_agents() or "Aquí tiene sus agentes."
        if what == "create":
            return create_agent(name)
        if what == "remove":
            return "Agente borrado." if agents.remove(name) else "No encuentro ese agente (los Pro no se borran)."
        agent = agents.find(name)
        if agent is None:
            return f"No conozco un agente «{name}». Diga «mis agentes» para verlos."
        return agent_job(agent, job)

    quick_handlers.append(run_agents)
    section_openers["agents"] = lambda _a="": show_agents()

    def scheduled_agents() -> None:
        import datetime as _dt

        now = _dt.datetime.now()
        for agent in agents.due(now):
            agents.ran(agent, now)
            orchestrator.submit(agent["tarea"], agent=agents.with_memory(agent))

    agents_timer = _QTimer()
    agents_timer.timeout.connect(lambda: threading.Thread(target=scheduled_agents, daemon=True).start())
    agents_timer.start(30_000)

    def prefill(text: str) -> Any:
        def run(_arg: str = "") -> str:
            def show() -> None:
                panel.open()
                panel.show_tab(0)
                panel.entry.setText(text)
                panel.entry.setFocus()

            on_ui(show)
            return ""

        return run

    section_openers.update(
        organizer=lambda _a="": open_organizer(),
        goals=lambda _a="": open_goals(),
        health=lambda _a="": open_health(),
        health_history=lambda _a="": open_health("history"),
        consult=lambda _a="": open_consult(),
        gym=lambda _a="": on_ui(open_gym),
        results=lambda _a="": open_results(),
        camera=lambda _a="": VISTA_OFF if camera_window.vista_off else (on_ui(lambda: camera_window.open(show=True)), "")[1],
        holo=lambda _a="": VISTA_OFF if camera_window.vista_off else (on_ui(lambda: camera_window.open(show=True)), set_hands("holo"))[1],
        globe=lambda _a="": globe_tool(_a) if _a else run_quick(_quick_kind("globe")),
        blender=prefill("en Blender haz "),
        video=prefill("edita un video con la carpeta "),
        meeting=lambda _a="": run_quick(_quick_kind("meeting_last")),
        profile=lambda _a="": run_quick(_quick_kind("profile_show")),
        faces=lambda _a="": (on_ui(lambda: camera_window.open(show=True)), "Mírenme a la cámara; diga «recuerda mi cara» para guardarla.")[1],
        blocking=lambda _a="": show_blocks(),
        lock=lambda _a="": run_quick(_quick_kind("key", "win+l")),
    )

    # -- what the web app's Health and Profile pages read (via the server) -----
    def health_summary(_args: dict) -> dict:
        from datetime import date

        from sergio_escritorio.salud import body_metrics, trends

        return {
            "text": health.describe(),
            "metrics": body_metrics(health.answers) if health.answers else {},
            "trends": trends(health.days, date.today()) if health.days else {},
            "report": health.summary_for_profile(),
        }

    def profile_summary(_args: dict) -> dict:
        data = profile.data or {}

        def lines(key: str) -> list[str]:
            return [str(x) for x in (data.get(key) or []) if str(x).strip()][:10]

        return {
            "text": profile.summary(),
            "updates": len(profile.updates),
            "last": profile.updates[-1] if profile.updates else 0,
            "traits": lines("rasgos"),
            "interests": lines("intereses"),
            "goals": lines("objetivos"),
            "adjustments": lines("ajustes"),
            "hours": profile.usage.free_windows(),
            "facts": [str(f) for f in profile.facts[-10:]],
            "talk": (data.get("comunicacion") or {}),
        }

    def open_from_web(args: dict) -> str:
        key = str(args.get("section") or "")
        if key not in section_openers:
            raise LookupError(f"unknown section {key}")
        open_section(key)
        return "ok"

    controller.skills["health_summary"] = health_summary
    controller.skills["profile_summary"] = profile_summary
    controller.skills["open_section"] = open_from_web
    # Creator's real programs (ArtCraft, Kdenlive, FreeCAD, LibreCAD,
    # Blender + Bonsai, VSCodium): status, install and open, from the web.
    from sergio_escritorio import creator_apps

    controller.skills["creator_apps"] = creator_apps.skill

    controller.skills["video_pro"] = videos.pro_skill

    # A click on the notch opens the quick bar (small tasks); the control
    # center is one chip away.
    from sergio_escritorio.notch_bar import NotchBar

    bar = NotchBar(
        on_submit=lambda text: threading.Thread(
            target=assistant.on_text, args=(text,), daemon=True
        ).start(),
        on_talk=ears.talk,
        on_panel=panel.toggle,
        reduced_motion=lambda: notch.reduced_motion or bool(config.get("reduce_motion", False)),
    )
    notch.on_click = bar.toggle
    companion.setVisible(bool(config["show_companion"]))
    notch.setVisible(show_notch)
    if not show_notch:
        notch.hide_notch(instant=True)
    notch.set_multitasking(bool(config.get("multitasking", False)))

    def _wake_and_open_app() -> None:
        ensure_server_running(config["server_url"])
        if "--background" not in sys.argv and bool(config.get("open_app_on_start", True)):
            on_ui(lambda: open_app_window(config["server_url"]))

    threading.Thread(target=_wake_and_open_app, daemon=True).start()
    show_text(
        f"Hola, soy {config['name']}. Mantén Ctrl+Alt o el notch para hablar. "
        "Suelta para enviar.",
        7,
    )
    app.aboutToQuit.connect(orchestrator.close)
    app.aboutToQuit.connect(server.shutdown)
    app.aboutToQuit.connect(stop_wsl_keepalive)
    app.exec()


if __name__ == "__main__":
    main()
