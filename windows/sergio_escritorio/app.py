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

    bridge = Bridge()
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
        }

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

    talk_action = QAction("Hablar  (Ctrl+Espacio)", menu)
    talk_action.triggered.connect(ears.talk)
    menu.addAction(talk_action)
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
        if name == "open":  # ✋ stop talking
            assistant.stop_speaking()
            bridge.caption.emit("✋ Me callo.")
        elif name in ("thumbs_up", "victory"):
            said = "Sí" if name == "thumbs_up" else "¿Qué ves?"
            bridge.caption.emit("👍 Sí" if name == "thumbs_up" else "✌️ ¿Qué ves?")
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

    detector = HoldDetector(ears.hold_start, ears.hold_end, ears.hold_cancel)
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
