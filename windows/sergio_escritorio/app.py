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
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

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
    data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))  # PowerShell adds a BOM
    data.setdefault("server_url", "http://localhost:8000")
    data.setdefault("port", 8765)
    data.setdefault("wake_word", True)
    data.setdefault("show_companion", True)
    data.setdefault("show_notch", True)
    data.setdefault("theme", "Océano")
    data.setdefault("eyes", True)
    data.setdefault("cursor_size", 9.0)
    # Sergio's own voice: the British gentleman (Gemini). The old default
    # neural voice is upgraded; a voice the user picked is kept.
    if data.get("voice") in (None, "es-EC-LuisNeural"):
        data["voice"] = "gemini:Algieba"
    # Muse-style personalisation and the brain's effort.
    data["name"] = "Sergio"  # his name is fixed
    data.setdefault("style", "orbe")
    data.setdefault("body", "#f3e9d2")
    data.setdefault("eye_style", "ovalos")
    data.setdefault("mouth", "ninguna")
    data.setdefault("accessory", "ninguno")
    data.setdefault("personality", "Caballero británico")
    data.setdefault("voice_rate", "+5%")
    data.setdefault("effort", "auto")
    # Talk like a phone call (Gemini Live); "turnos" = one question at a time.
    data.setdefault("conversation", "llamada")
    # Mental gym: an exercise you cannot skip every 28 minutes.
    data.setdefault("gym", True)
    data.setdefault("gym_minutes", 28)
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


def make_icon(state: str = "idle") -> object:
    """Sergio's mark as a Pillow image (used for the .ico of the shortcuts)."""
    from PIL import Image, ImageDraw

    colours = {"idle": (10, 108, 255), "paused": (142, 142, 147)}
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 248, 248), fill=colours.get(state, colours["idle"]))
    draw.ellipse((80, 80, 176, 176), outline=(255, 255, 255), width=26)
    return image


def single_instance() -> bool:
    """False if Sergio is already running (named mutex)."""
    if sys.platform != "win32":
        return True
    import ctypes

    ctypes.windll.kernel32.CreateMutexW(None, False, "SergioCompanero")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def tray_icon(colour: Any) -> Any:
    """The Sergio mark (filled circle + white ring) as a tray icon."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap

    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(colour)
    p.drawEllipse(QPointF(32, 32), 29, 29)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(Qt.GlobalColor.white, 7))
    p.drawEllipse(QPointF(32, 32), 12, 12)
    p.end()
    return QIcon(pix)


def main() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=HOME / "sergio.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not single_instance():
        return
    from sergio_escritorio.windows_backend import set_dpi_aware

    set_dpi_aware()  # before Qt creates anything
    try:
        run(load_config())
    except Exception:
        logging.exception("Sergio crashed")
        raise


def run(config: dict[str, Any]) -> None:
    from pynput import keyboard
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

    from sergio_escritorio.companion import STATE_COLORS, Companion
    from sergio_escritorio.control import Controller, make_server
    from sergio_escritorio.notch import Notch
    from sergio_escritorio.voice import Assistant, Ears, SergioClient
    from sergio_escritorio.windows_backend import (
        WindowsBackend,
        foreground_is_fullscreen,
    )

    app = QApplication(sys.argv)
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
    camera_window = CameraWindow(
        feed,
        # "¿Qué ves?" button: same as asking out loud (assistant made below).
        on_ask=lambda: threading.Thread(
            target=lambda: assistant.on_text("¿Qué ves?"), daemon=True
        ).start(),
    )
    notch = Notch(fullscreen_app=foreground_is_fullscreen)
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
        clicked = Signal()  # a mouse click anywhere: he hops
        camera_off = Signal()
        call_on = Signal(bool)  # a live call started / ended
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

    controller = Controller(
        WindowsBackend(), on_activity=on_activity, camera=camera_shot
    )
    server = make_server(controller, config["token"], int(config["port"]))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # Load Whisper on Windows in the background so the first phrase is fast.
    from sergio_escritorio.voice import local_whisper

    threading.Thread(target=local_whisper, daemon=True).start()
    client = SergioClient(config["server_url"])
    client.voice = config["voice"]

    def apply_brain(cfg: dict) -> None:
        """Voice, personality and effort chosen in the notch."""
        client.voice = cfg["voice"]
        client.voice_rate = cfg["voice_rate"]
        client.effort = cfg["effort"]
        name = cfg["name"]
        persona = PERSONALITIES.get(cfg["personality"], "")
        client.personality = (
            f"Tu nombre es {name}. {persona}" if name != "Sergio" else persona
        )

    apply_brain(config)

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
    ears = Ears(
        assistant, wake_word=bool(config["wake_word"]), on_level=bridge.level.emit
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
            "last_error": assistant.last_error,
            "log": str(HOME / "sergio.log"),
            "hands": hands_status(),
            "call": call_status(),
            "vision": vision_status(),
            "physics": physics_status(),
            "gym": (
                f"cada {int(schedule.interval // 60)} min, el próximo en "
                f"{schedule.minutes_left()} min"
                if schedule.enabled
                else "apagado"
            ),
            "reminders": len(reminders.pending()),
        }

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

    def physics_status() -> str:
        try:
            import pymunk

            return f"ok (pymunk {pymunk.version})"
        except Exception as exc:  # noqa: BLE001
            return f"no instalado ({exc})"

    controller.diag = diag
    try:
        ears.start()
    except Exception as exc:  # noqa: BLE001 — no microphone
        logging.exception("microphone unavailable")
        show_text(f"No encuentro el micrófono: {exc}", 10)

    # -- tray --------------------------------------------------------------
    tray = QSystemTrayIcon(tray_icon(STATE_COLORS["idle"]))
    tray.setToolTip(
        "Sergio: di «Sergio…», pulsa Ctrl+Espacio, o mantén Ctrl+Alt para "
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
    menu.addSeparator()

    wake_action = QAction("Escuchar cuando digo «Sergio»", menu, checkable=True)
    wake_action.setChecked(bool(config["wake_word"]))

    def set_wake(on: bool) -> None:
        ears.wake_word = on
        remember("wake_word", on)

    wake_action.toggled.connect(set_wake)
    menu.addAction(wake_action)

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
        notch.setVisible(on)
        companion.captions = not on  # texts live in the notch when it is shown
        remember("show_notch", on)

    notch_action.toggled.connect(set_notch)
    menu.addAction(notch_action)
    menu.addSeparator()

    camera_action = QAction("Cámara  (Ctrl+Alt+C)", menu)
    camera_action.triggered.connect(camera_window.toggle)
    menu.addAction(camera_action)

    def save_personalization(new: dict) -> None:
        apply_config(new)
        companion_mod.ORB = float(new["cursor_size"])
        apply_brain(new)
        set_wake_name(new["name"])
        notch.name = new["name"]
        save_config(config)
        tray.setIcon(tray_icon(STATE_COLORS["idle"]))

    personalize_action = QAction("Personalizar a Sergio…", menu)
    menu.addAction(personalize_action)

    # -- control center (click the notch) ---------------------------------
    def status() -> str:
        brain = getattr(client, "_model", "") or "el modelo de Sergio"
        ear = "te escucha" if ears.wake_word else "Ctrl+Espacio para hablar"
        return f"Piensa con {brain} · {ear}"

    def set_camera(on: bool) -> None:
        camera_window.open() if on else camera_window.close_camera()

    panel = ControlCenter(
        PanelActions(
            talk=ears.talk,
            send=lambda text: threading.Thread(
                target=assistant.on_text, args=(text,), daemon=True
            ).start(),
            toggles=[
                Toggle(
                    "Escuchar «Sergio»",
                    "wave",
                    lambda: ears.wake_word,
                    wake_action.setChecked,
                ),
                Toggle(
                    "Control de pantalla",
                    "hand",
                    lambda: controller.enabled,
                    control_action.setChecked,
                ),
                Toggle("Cámara", "camera", camera_window.isVisible, set_camera),
                Toggle(
                    "Junto al cursor",
                    "pointer",
                    companion.isVisible,
                    show_action.setChecked,
                ),
                Toggle(
                    "Llamada",
                    "phone",
                    call_active,
                    lambda on: set_call_tile(on),
                ),
                Toggle(
                    "Gimnasio mental",
                    "brain",
                    lambda: bool(config.get("gym", True)),
                    lambda on: set_gym(on),
                ),
            ],
            config=config,
            save_config=save_personalization,
            open_url=open_app_window,
            server_url=config["server_url"],
            status=status,
        )
    )
    panels.append(panel)
    personalize_action.triggered.connect(lambda: (panel.open(), panel.show_tab(1)))
    bridge.level.connect(panel.set_level)
    panel_action = QAction("Centro de control  (clic en el notch)", menu)
    panel_action.triggered.connect(panel.open)
    menu.insertAction(talk_action, panel_action)
    menu.addSeparator()

    chat_action = QAction("Abrir el chat en el navegador", menu)
    chat_action.triggered.connect(lambda: webbrowser.open(config["server_url"]))
    menu.addAction(chat_action)
    quit_action = QAction("Salir", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (
            ears.talk() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
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

    # -- hands: gestures, air mouse, 3D in Blender ---------------------------
    from sergio_escritorio.hands import MODES, HandControl

    def hand_gesture(name: str) -> None:
        swipes = {
            "swipe_right": ("right", "Siguiente."),
            "swipe_left": ("left", "Anterior."),
            "swipe_up": ("volumeup", "Más volumen."),
            "swipe_down": ("volumedown", "Menos volumen."),
        }
        if name in swipes:  # an open hand swept: next/previous, volume
            key, said = swipes[name]
            try:
                for _ in range(3 if key.startswith("volume") else 1):
                    controller.act({"action": "key", "keys": key})
                bridge.caption.emit(said)
            except PermissionError:
                bridge.caption.emit("El control está en pausa (Ctrl+Alt+Fin).")
            return
        if name == "open":  # open palm: stop talking
            if call_active():
                current_call[0].interrupt()
            assistant.stop_speaking()
            bridge.caption.emit("Me callo.")
        elif name in ("thumbs_up", "victory") and call_active():
            said = "Sí" if name == "thumbs_up" else "¿Qué ves?"
            current_call[0].send_text(f"(El usuario hizo un gesto con la mano: {said})")
        elif name in ("thumbs_up", "victory"):
            said = "Sí" if name == "thumbs_up" else "¿Qué ves?"
            bridge.caption.emit(said)
            threading.Thread(
                target=assistant.on_text, args=(said,), daemon=True
            ).start()

    def hand_mouse(events: list) -> None:
        if not controller.enabled:  # Ctrl+Alt+Fin pauses the hands too
            return
        import pyautogui

        for kind, x, y in events:
            if kind == "move":
                pyautogui.moveTo(x, y, _pause=False)
            elif kind == "click":
                pyautogui.click(x, y, _pause=False)
            elif kind == "down":
                pyautogui.mouseDown(x, y, _pause=False)
            elif kind == "up":
                pyautogui.mouseUp(x, y, _pause=False)
            elif kind == "right":
                pyautogui.rightClick(x, y, _pause=False)
            elif kind == "scroll":
                pyautogui.scroll(x * 40, _pause=False)  # x carries the amount
            elif kind == "zoom":  # both hands pinching: Ctrl + wheel
                pyautogui.keyDown("ctrl", _pause=False)
                try:
                    pyautogui.scroll(x * 120, _pause=False)
                finally:
                    pyautogui.keyUp("ctrl", _pause=False)

    def screen_size() -> tuple[int, int]:
        try:
            import pyautogui

            width, height = pyautogui.size()
            return int(width), int(height)
        except Exception:  # noqa: BLE001
            return 1920, 1080

    hand_control = HandControl(
        frames=feed.frame,
        on_gesture=hand_gesture,
        mouse_events=hand_mouse,
        screen=screen_size(),
    )
    camera_window.hands = hand_control

    def set_hands(mode: str) -> str:
        """For Sergio (desktop_action hands / blender with hands)."""
        if mode not in MODES:
            return f"unknown hands mode {mode!r}; use one of {', '.join(MODES)}"
        hand_control.set_mode(mode)
        feed.keep_on = mode != "off"
        if mode != "off":
            feed.start()
            bridge.peek.emit()  # show the camera so you see your hands
        return f"hands mode: {MODES[mode]}"

    controller.on_hands = set_hands
    bridge.camera_off.connect(camera_window.close_camera)

    # -- instant voice commands (no AI): "abre Spotify", "sube el volumen" ---
    def run_quick(q: Any) -> str:
        import datetime

        from sergio_escritorio.control import ActionError
        from sergio_escritorio.quick import spoken_date, spoken_time

        now = datetime.datetime.now()
        if q.kind == "stop":
            assistant.stop_speaking()
            return ""
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
        if q.kind == "hands":
            set_hands(q.arg)
            return q.say
        if q.kind == "globe":
            resp = client.http.post(f"{client.base}/v1/world/open", timeout=240)
            resp.raise_for_status()
            open_app_window(resp.json()["url"])
            return q.say
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
                controller.act({"action": "open_app", "target": q.arg})
            elif q.kind == "close_app":
                try:
                    controller.act({"action": "close_app", "target": q.arg})
                except ActionError:
                    return f"No veo {q.arg.title()} abierto."
            elif q.kind == "key":
                controller.act({"action": "key", "keys": q.arg})
            elif q.kind == "volume":
                key = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}
                for _ in range(1 if q.arg == "mute" else 5):
                    controller.act({"action": "key", "keys": key[q.arg]})
        except PermissionError:
            return "El control está en pausa. Pulsa Ctrl+Alt+Fin para reanudarlo."
        return q.say

    assistant.quick = run_quick

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
        elif hand_control.mode == "gestos" and not assistant.busy:
            bridge.caption.emit(answer)
            threading.Thread(target=assistant.on_text, args=(answer,), daemon=True).start()

    vision_engine = VisionEngine(feed.frame, on_head=head_gesture)
    camera_window.vision = vision_engine

    def identify(jpeg: bytes) -> list[dict]:
        resp = client.http.post(
            f"{client.base}/v1/faces/identify",
            files={"image": ("cara.jpg", jpeg, "image/jpeg")},
            timeout=10,
        )
        resp.raise_for_status()
        return list(resp.json().get("faces") or [])

    def faces_seen(found: list[dict]) -> None:
        vision_engine.tracker.add_faces(
            [
                {
                    "name": f["name"],
                    "guest": f.get("guest") or 0,
                    "score": f["score"],
                    "box": f["nbox"],
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
        if first_today and now.hour < 12:  # the morning report, JARVIS-style
            text = briefing(now, system_status(), reminders.pending(), name)
        else:
            text = f"Hola, {name}."
        tell(text)

    camera_window.watcher = FaceWatcher(
        feed.frame, identify, on_person=greet, on_faces=faces_seen
    )

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
                items = list(resp.json().get("items") or [])
                vision_engine.tracker.add_scene(items, time.monotonic())
                text = scene_sentence(items)
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                text = f"No pude analizar la imagen: {explain(exc)}"
            on_ui(lambda: camera_window.show_overlay(text, 12))
            tell(text, to_call=f"(Análisis de la cámara: {text} Cuéntaselo al usuario.)")

        threading.Thread(target=run, daemon=True).start()

    camera_window.on_analyze = analyze

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
        for jpeg in face_photos(box):
            resp = client.http.post(
                f"{client.base}/v1/faces/enroll",
                data={"name": name, "consent": "true"},
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
        if not camera_window.isVisible():
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

    # -- reminders, system status, protocols (JARVIS) ------------------------
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
        """The JARVIS quick commands; None = not one of them."""
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
        if q.kind == "call":
            ok = start_call(force=True)
            return "" if ok else "No pude abrir la llamada ahora."
        if q.kind == "gym":
            return on_ui(open_gym)
        if q.kind == "physics":
            return run_physics(q.arg)
        if q.kind == "name_face":
            return name_from_voice(q.arg)
        return None

    def run_physics(order: str) -> str:
        def go() -> str:
            if not camera_window.isVisible():
                camera_window.open()
            if hand_control.mode != "fisica":
                camera_window.set_physics(True)
            world = camera_window.sandbox
            return world.command(order) if world is not None else "No hay motor de física."

        return on_ui(go)

    # -- the call: talk with Sergio like on the phone (Gemini Live) -----------
    from sergio_escritorio.call import CallSession
    from sergio_escritorio.call_tools import Abilities, call_context, call_tools

    call_failed_at = [-1e9]
    call_error = [""]

    def jpeg_of(image: Any, width: int) -> bytes:
        import io

        image = image.convert("RGB")
        if image.width > width:
            image = image.resize((width, int(image.height * width / image.width)))
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=80)
        return buf.getvalue()

    def call_video() -> tuple[bytes, str] | None:
        session = current_call[0]
        if camera_window.isVisible():
            frame = feed.frame()
            if frame is not None:
                import cv2

                h, w = frame.shape[:2]
                small = cv2.resize(frame, (768, int(h * 768 / w)))
                ok, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    return jpeg.tobytes(), "cámara"
        if session is not None and session.share_screen:
            return jpeg_of(controller.backend.screenshot(), 1280), "pantalla"
        return None

    def look_screen(question: str) -> str:
        session = current_call[0]
        if session is None:
            return "No hay llamada."
        session.send_image(jpeg_of(controller.backend.screenshot(), 1280), "pantalla")
        return "Te envié una captura de la pantalla: mírala y responde."

    def share_screen(on: bool) -> str:
        session = current_call[0]
        if session is not None:
            session.share_screen = on
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
        if mode == "fisica":
            return on_ui(lambda: (camera_window.open(), camera_window.set_physics(True))[1])
        return set_hands(mode)

    def people_tool() -> str:
        if not camera_window.isVisible():
            return "La cámara está cerrada; ábrela con camara para ver."
        return vision_summary(vision_engine.tracker.visible(time.monotonic()), time.monotonic())

    def hang_up_tool() -> str:
        session = current_call[0]
        if session is not None:
            session.hang_up_after_goodbye()
        return "Colgaré cuando termines de despedirte."

    abilities = Abilities(
        act=controller.act,
        snapshot=controller.snapshot,
        screen_help=client.screen_help,
        point=lambda x, y, label: bridge.point.emit(x, y, label),
        camera=camera_tool,
        hands=hands_tool,
        physics=run_physics,
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
        screenshot=save_screenshot,
    )

    def call_ended(why: str) -> None:
        current_call[0] = None
        ears.call = None
        bridge.call_on.emit(False)
        if why == "silencio":
            bridge.caption.emit("Quedo atento. Di «Sergio» cuando me necesites.")
        elif why == "se cortó":
            bridge.caption.emit("Se cortó la llamada. Di «Sergio» para volver.")

    def start_call(prefill: bytes = b"", force: bool = False) -> bool:
        """Open a live call (from a worker thread). False = use turns."""
        import datetime as _dt

        if not force and config.get("conversation", "llamada") != "llamada":
            return False
        if call_active():
            return True
        if not force and time.monotonic() - call_failed_at[0] < 600:
            return False  # it failed a moment ago: don't make you wait again
        from sergio_escritorio.voice import wav_pcm

        session = CallSession(
            config["server_url"],
            voice=client.voice,
            personality=client.personality,
            context=lambda: call_context(
                _dt.datetime.now(),
                system_status(),
                reminders.pending(),
                camera_window.isVisible(),
            ),
            tools=call_tools(abilities),
            on_state=bridge.state.emit,
            on_caption=bridge.caption.emit,
            on_heard=lambda text: setattr(assistant, "last_heard", text),
            on_level=bridge.level.emit,
            on_end=call_ended,
            video=call_video,
        )
        current_call[0] = session
        ears.call = session
        if not session.start(wav_pcm(prefill) if prefill else b""):
            current_call[0] = None
            ears.call = None
            call_failed_at[0] = time.monotonic()
            call_error[0] = session.error
            logging.warning("live call unavailable: %s", session.error)
            return False
        call_error[0] = ""
        bridge.call_on.emit(True)
        return True

    def end_call() -> None:
        session = current_call[0]
        if session is not None:
            session.hang_up()

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
                bridge.caption.emit("No pude abrir la llamada; te escucho por turnos.")
                bridge.ptt.emit()

        threading.Thread(target=run, daemon=True).start()
        return True

    assistant.start_call = start_call
    ears.on_talk = talk_hotkey
    bridge.ptt.connect(ears.ptt)

    def call_changed(on: bool) -> None:
        notch.set_call(on)
        for panel in panels:
            for tile in panel.tiles:
                tile.sync()

    bridge.call_on.connect(call_changed)

    # -- mental gym: an exercise you cannot skip every 28 minutes -------------
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
    schedule = GymSchedule(
        float(config.get("gym_minutes", 28)), away=idle_seconds, locked=screen_locked
    )
    schedule.enabled = bool(config.get("gym", True))
    gym_windows: list[Any] = []

    def gym_speak(text: str) -> None:
        threading.Thread(
            target=lambda: assistant.say_aloud(text) if not assistant.busy else None,
            daemon=True,
        ).start()

    def open_gym() -> str:
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
        gym_windows.append(window)
        schedule.running = True

        def done(session: Any) -> None:
            gym_windows.clear()
            schedule.done()
            bridge.caption.emit(
                f"Gimnasio mental, {exercise.title}: {session.summary()} {session.verdict()}"
            )

        window.finished.connect(done)
        window.start()
        return f"Empieza el gimnasio mental: {exercise.title}."

    def gym_check() -> None:
        try:
            if schedule.check():
                schedule.running = False  # open_gym marks it again
                open_gym()
        except Exception:  # noqa: BLE001 — never kill the timer
            logging.exception("mental gym failed to start")
            schedule.done()

    gym_timer = QTimer()
    gym_timer.timeout.connect(gym_check)
    gym_timer.start(10_000)

    def set_gym(on: bool) -> None:
        schedule.enabled = on
        if on:
            schedule.postpone_from_now()
        config["gym"] = on
        save_config(config)
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
    hotkeys = keyboard.GlobalHotKeys(
        {
            HOTKEY_TALK: bridge.talk.emit,
            HOTKEY_STOP: bridge.toggle.emit,
            HOTKEY_CAMERA: bridge.camera.emit,
        }
    )
    hotkeys.start()

    # Clicky: hold Ctrl+Alt, talk while holding, release to send. Sergio looks
    # at your screen with the question and points at what you need.
    from pynput import mouse

    from sergio_escritorio.hold import HoldDetector

    def hold_start() -> None:
        if call_active():  # in a call: he looks at your screen right away
            threading.Thread(target=look_screen, args=("",), daemon=True).start()
            bridge.caption.emit("Mirando tu pantalla…")
        else:
            ears.hold_start()

    detector = HoldDetector(hold_start, ears.hold_end, ears.hold_cancel)
    keyboard.Listener(on_press=detector.press, on_release=detector.release).start()
    mouse.Listener(
        on_click=lambda _x, _y, _b, pressed: bridge.clicked.emit() if pressed else None
    ).start()

    notch.on_click = panel.toggle
    companion.setVisible(bool(config["show_companion"]))
    notch.setVisible(show_notch)
    show_text(
        f"Hola, soy {config['name']}. Di «Sergio…», o mantén Ctrl+Alt y "
        "pregúntame por lo que ves en pantalla.",
        7,
    )
    app.aboutToQuit.connect(server.shutdown)
    app.exec()


if __name__ == "__main__":
    main()
