"""Sergio on Windows: a cursor companion you talk to. No app window.

* A small orb follows the mouse pointer and shows what Sergio is doing.
* Say "Sergio, ..." (wake word) or press Ctrl+Space and speak.
* Sergio can read the screen and use the mouse and keyboard like you.
* Ctrl+Alt+End pauses / resumes that control at once.
* A tray icon (next to the clock) holds the few settings and "Quit".
"""

from __future__ import annotations

import json
import re
import logging
import os
import subprocess
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
    # Gemini Live's default voice everywhere (calls and spoken answers): the
    # user asked for it, and one voice sounds like one Sergio.
    if data.get("voice") in (None, "es-EC-LuisNeural", "gemini:Algieba", "gemini:Predeterminada") and not data.get("voice_chosen"):
        data["voice"] = "gemini:Algenib"  # male, deep, relaxed and a bit husky
    # Muse-style personalisation and the brain's effort.
    data["name"] = "Sergio"  # his name is fixed
    data.setdefault("style", "orbe")
    data.setdefault("body", "#f3e9d2")
    data.setdefault("eye_style", "ovalos")
    data.setdefault("mouth", "ninguna")
    data.setdefault("accessory", "ninguno")
    data.setdefault("personality", "Caballero británico")
    if data.get("voice_rate") in (None, "+5%"):  # the old default sounded rushed
        data["voice_rate"] = "+0%"
    data.setdefault("effort", "auto")
    # Talk like a phone call (Gemini Live); "turnos" = one question at a time.
    data.setdefault("conversation", "llamada")
    # Mental gym: an exercise you cannot skip every 12 minutes (real time).
    data.setdefault("gym", True)
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
    from sergio_escritorio.diagnose import setup_log

    setup_log(HOME / "sergio.log")
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
    camera_window = CameraWindow(feed)
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
        WindowsBackend(speed=str(config.get("control_speed") or "rapido")),
        on_activity=on_activity,
        camera=camera_shot,
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
    results_action = QAction("Mis resultados del gimnasio", menu)
    results_action.triggered.connect(lambda: open_results())
    menu.addAction(results_action)
    health_action = QAction("Mi salud", menu)
    health_action.triggered.connect(lambda: open_health())
    menu.addAction(health_action)
    goals_action = QAction("Mis metas (coach)", menu)
    goals_action.triggered.connect(lambda: open_goals())
    menu.addAction(goals_action)
    organizer_action = QAction("Organizador: alarmas, notas, recordatorios", menu)
    organizer_action.triggered.connect(lambda: open_organizer())
    menu.addAction(organizer_action)
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
                "manos ahora mueven y modelan hologramas en Sergio ve (modo holo)."
            )
        mode = ALIASES.get(mode, mode)
        if mode not in MODES:
            return f"unknown hands mode {mode!r}; use one of {', '.join(MODES)}"

        def go() -> str:
            if mode == "off":
                return camera_window.set_holo(False)
            if not camera_window.isVisible():
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
            on_ui(lambda: camera_window.open() if not camera_window.isVisible() else None)
            analyze()  # it speaks the result itself
            return ""
        if q.kind == "photo":
            if not camera_window.isVisible():
                on_ui(camera_window.open)
                time.sleep(1.6)  # the camera settles its exposure
            path = on_ui(camera_window.save_photo)
            return "Foto guardada en Imágenes, carpeta Sergio." if path else "No pude tomar la foto."
        if q.kind == "vision_detail":
            camera_window.detail = q.arg == "on"
            return q.say
        if q.kind == "vision_data":
            if not camera_window.isVisible():
                return "Abre la cámara («abre la cámara») y te digo lo que mido."
            return (body_now().strip() or "Aún no tengo medidas; mírame unos segundos.")
        if q.kind == "mirror":
            camera_window.mirror = not camera_window.mirror
            return "Modo espejo." if camera_window.mirror else "Sin espejo."
        if q.kind == "blender_holo":
            return holograms_to_blender()
        if q.kind == "video_pro":
            return video_task(q.arg, q.say)
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
        if q.kind == "blender_object":
            return object_to_blender(q.arg)
        if q.kind == "hands":
            set_hands(q.arg)
            return q.say
        if q.kind == "globe":
            resp = client.http.post(f"{client.base}/v1/world/open", timeout=240)
            resp.raise_for_status()
            open_app_window(resp.json()["url"])
            return q.say
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
    from sergio_escritorio.coach import Coach, annotate_video, record_video, school_reminders

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
            feed.keep_on = camera_window.isVisible()
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

    def open_health(tab: int = 0) -> str:
        from sergio_escritorio.salud_ui import HealthWindow

        def show() -> None:
            if "main" not in health_windows:
                health_windows["main"] = HealthWindow(health, analyze_health, health_folder, set_health_folder)
            health_windows["main"].open(tab)

        on_ui(show)
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

    def run_profile(q: Any) -> str | None:
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
        who = "señor" if boss else name  # JARVIS: the owner is «señor»
        if first_today and now.hour < 12:  # the morning report, JARVIS-style
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

        if not camera_window.isVisible():
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
        if not camera_window.isVisible():
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
                vision_engine.tracker.name_track(
                    target.id, str(got.get("label") or ""), str(got.get("detail") or "")
                )
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
        if not camera_window.isVisible():
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
            text, colour = parsed
            note = notes.add(text, colour)
            on_ui(lambda: board().show(note))
            return "Nota pegada en el escritorio."
        if q.kind == "notes_show":
            count = on_ui(lambda: board().show_all())
            return f"Aquí están sus {count} notas." if count else "No tiene notas. Diga «nota: …» para crear una."
        if q.kind == "notes_hide":
            on_ui(lambda: board().hide_all())
            return "Notas guardadas."
        if q.kind == "note_remove":
            found = notes.find(q.arg)
            for n in found:
                on_ui(lambda nid=n.id: board().remove(nid))
            return f"Borré {len(found)} nota{'s' if len(found) != 1 else ''}." if found else "No encontré esa nota."
        if q.kind == "organizer":
            return open_organizer({"alarmas": 0, "notas": 1, "recordatorios": 2, "tareas": 3}.get(q.arg, 0))
        return None

    if notes.items and config.get("notas_al_iniciar", True):
        _QTimer.singleShot(2500, lambda: board().show_all())
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
        if q.kind == "globe_last":
            if not last_globe[0]:
                raise RuntimeError("nothing shown on the globe yet")  # the agent decides
            return globe_tool("")
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
            if not camera_window.isVisible():
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
        """A hologram of anything: Gemini designs its real parts."""
        what = request.strip() or "un objeto"
        bridge.caption.emit(f"Diseñando {what}, pieza por pieza…")
        resp = client.http.post(
            f"{client.base}/v1/vision/holo_model", json={"request": what}, timeout=120
        )
        resp.raise_for_status()
        recipe = resp.json()

        def show() -> str:
            if not camera_window.isVisible():
                camera_window.open()
            set_hands("holo")
            obj = camera_window.holo.add_model(recipe)
            return f"{obj.name}: {len(recipe['parts'])} piezas, {obj.size_cm()} cm."

        made = on_ui(show)
        return f"Listo, {made} Pellízcalo para moverlo, y «pásalo a Blender» para trabajarlo allí."

    def blender_pro(request: str, reference: bytes = b"", rounds: int = 2) -> str:
        """Blender Pro: model, render, look at the render, fix — like a pro.

        Runs in the background; Sergio tells you when the project is ready.
        """
        from sergio_escritorio import media

        path = blender_file("pro")
        preview = path[:-6] + "-vista.png"
        if reference:
            resp = client.http.post(
                f"{client.base}/v1/vision/blender",
                files={"image": ("objeto.jpg", reference, "image/jpeg")},
                data={"save_path": path, "note": request, "preview_path": preview},
                timeout=600,
            )
        else:
            resp = client.http.post(
                f"{client.base}/v1/vision/blender/text",
                json={"request": request, "save_path": path, "preview_path": preview},
                timeout=600,
            )
        resp.raise_for_status()
        model = resp.json()
        log = ""
        reviews = 0
        for step in range(rounds + 4):  # visual reviews + a few error fixes
            bridge.caption.emit(f"Blender Pro: construyendo y revisando (paso {step + 1})…")
            Path(preview).unlink(missing_ok=True)
            log = media.run_blender_background(model["script"])
            broken = "SERGIO_SAVED" not in log
            if not broken:
                if reviews >= rounds:
                    break
                reviews += 1
            elif step >= rounds + 3:
                break
            try:
                shot = Path(preview).read_bytes()
            except OSError:
                shot = b""
            if not shot and not broken:
                break  # no render to look at (no Cycles?): keep what works
            files = {"preview": ("vista.png", shot or b"\x89PNG", "image/png")}
            if reference:
                files["reference"] = ("objeto.jpg", reference, "image/jpeg")
            fixed = client.http.post(
                f"{client.base}/v1/vision/blender/refine",
                data={
                    "request": request,
                    "raw_script": model.get("raw_script") or model["script"],
                    "save_path": path,
                    "log": log[-3000:],
                    "preview_path": preview,
                },
                files=files,
                timeout=600,
            )
            if fixed.status_code != 200:
                break  # the last good version stays
            model = fixed.json()
        if "SERGIO_SAVED" not in log:
            return f"Blender Pro no logró una versión que funcione: {log[-200:]}"
        media.open_in_blender(path)
        name = model.get("name") or "el modelo"
        return (
            f"Listo: {name}, revisado {rounds} veces mirando el render. Abrí el proyecto "
            "en Blender; está en Documentos, Sergio, Blender."
        )

    last_video: list[dict] = []

    def video_task(request: str, source: str = "") -> str:
        """Video Pro in the background: Gemini watches, plans, ffmpeg renders."""
        import json as _json

        from sergio_escritorio import video_pro

        def planner(req: str, sheets: list, lengths: list) -> dict:
            resp = client.http.post(
                f"{client.base}/v1/vision/video_plan",
                data={"request": req, "lengths": _json.dumps(lengths)},
                files=[("sheets", (f"clip{i}.jpg", s, "image/jpeg")) for i, s in enumerate(sheets)],
                timeout=600,
            )
            resp.raise_for_status()
            return resp.json()

        def run() -> None:
            try:
                bridge.caption.emit("Video Pro: mirando tus clips…")
                done = video_pro.edit(source or "Videos", request, planner)
                last_video[:] = [done]
                os.startfile(done["path"]) if hasattr(os, "startfile") else None  # noqa: B018
                title = done["plan"]["youtube"]["title"]
                answer = (
                    f"Video listo: «{title}». Lo abrí para que lo veas; está en Videos, Sergio, "
                    "con el título, la descripción y las etiquetas al lado. Si le gusta, diga "
                    "«súbelo a YouTube»."
                )
            except Exception as exc:  # noqa: BLE001
                from sergio_escritorio.voice import explain

                answer = f"Video Pro falló: {explain(exc)}"
            tell(answer, to_call=f"[Video terminado] {answer} Cuéntaselo en una frase.")

        threading.Thread(target=run, daemon=True).start()
        return "Video Pro en marcha: mira tus clips, elige los mejores momentos y lo monta. Le aviso al terminar."

    def upload_video() -> str:
        """YouTube Studio's upload, ready; publishing stays your click."""
        if not last_video:
            return "Primero hagamos un video: «edita un video con la carpeta…»."
        video = last_video[0]
        yt = video["plan"]["youtube"]
        try:
            import pyperclip

            pyperclip.copy(f"{yt['title']}\n\n{yt['description']}\n\n{', '.join(yt['tags'])}")
        except Exception:  # noqa: BLE001
            pass
        controller.act({"action": "open", "target": "https://studio.youtube.com/channel/UC/videos/upload?d=ud"})
        subprocess.Popen(["explorer", "/select,", video["path"]])  # noqa: S603,S607
        return (
            "Abrí YouTube Studio para subirlo y le marqué el video en la carpeta: "
            "arrástrelo a la ventana de subida. El título, la descripción y las etiquetas "
            "están copiados: péguelos con Ctrl+V. Publicar lo decide usted."
        )

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

    def object_to_blender(note: str = "") -> str:
        """The object in your hands: Gemini studies it, Blender models it."""
        if not camera_window.isVisible():
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
        if not camera_window.isVisible():
            bridge.peek.emit()  # open the camera: hold the photo in front of it
            time.sleep(1.5)
        return feed.jpeg()

    def photo_who(source: str, path: str = "") -> str:
        bridge.caption.emit("Mirando la foto…")
        return client.photo_who(photo_bytes(source, path))

    def kinship(source: str, path: str = "") -> str:
        bridge.caption.emit("Comparando rasgos y proporciones…")
        return client.kinship(photo_bytes(source, path))

    # -- where we are, the plane overhead and the 3D globe ----------------------
    from sergio_escritorio.location import Location

    location = Location(config.get("ubicacion"))
    location.keep_fresh()  # always fresh: the plane question never waits for it
    last_globe = [""]

    def show_globe(url: str) -> None:
        """God's Eye View in its own window, on your screen (old one closed)."""
        launcher = getattr(controller.backend, "launcher", None)
        before: set[int] = set()
        if launcher is not None:
            for window in launcher.desktop.windows():
                before.add(window.hwnd)
                if "god's eye view" in window.title.lower():
                    launcher.desktop.close(window.hwnd)
        open_app_window(url)
        if launcher is not None:
            threading.Thread(
                target=lambda: launcher._bring_later(["God's Eye View"], before), daemon=True
            ).start()

    def overhead_now() -> str:
        fix = location.get()
        if fix is None:
            return f"No sé dónde estamos: {location.problem or 'sin ubicación'}."
        report = client.overhead(fix.lat, fix.lon, fix.alt)
        last_globe[0] = report.get("globe_url") or last_globe[0]
        note = "" if fix.source == "windows" else f" (Usé la {fix.describe()}.)"
        return str(report.get("text") or "No hay datos.") + note

    def globe_tool(place: str) -> str:
        if place.strip():
            url = client.globe_goto(place.strip())
            label = place.strip().title()
        elif last_globe[0]:
            url, label = last_globe[0], "el avión"
        else:
            return "¿Qué lugar quiere ver en el globo?"
        last_globe[0] = url
        show_globe(url)
        return f"Mostrando {label} en God's Eye View."

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
        if mode == "fisica":  # the old physics: holograms with gravity
            return run_holo("activa la gravedad")
        return set_hands(mode)

    def people_tool() -> str:
        if not camera_window.isVisible():
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
        point=lambda x, y, label: bridge.point.emit(x, y, label),
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
        ears.call = None
        voices.enabled = False
        bridge.call_on.emit(False)
        if why == "cancelado":  # "Sergio" was not for him after all
            bridge.state.emit("idle")
        elif why == "silencio":
            bridge.caption.emit("Quedo atento. Di «Sergio» cuando me necesites.")
        elif why == "se cortó":
            bridge.caption.emit("Se cortó la llamada. Di «Sergio» para volver.")

    def new_session(**changes: Any) -> CallSession:
        """A call set up exactly like the real ones (tools, voice, context)."""
        import datetime as _dt

        options: dict[str, Any] = {
            "voice": client.voice,
            "personality": client.personality,
            "context": lambda: call_context(
                _dt.datetime.now(),
                system_status(),
                reminders.pending(),
                camera_window.isVisible(),
            ),
            "tools": call_tools(abilities),
            "on_state": call_state,
            "on_caption": bridge.caption.emit,
            "on_heard": lambda text: setattr(assistant, "last_heard", text),
            "on_level": bridge.level.emit,
            "on_end": call_ended,
            "video": call_video,
        }
        options.update(changes)
        return CallSession(config["server_url"], **options)

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
    from sergio_escritorio.speakers import Encoder, LiveVoices, VoiceBook, pcm_to_float, voiced

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
        if not camera_window.isVisible():
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
    from sergio_escritorio.meeting import MeetingRecorder, diarize, encode, mix, read_wav, spoken_summary, timeline_text
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
        today = time.strftime("%Y-%m-%d")
        if reminded_consent[0] != today:  # once a day is enough
            reminded_consent[0] = today
            text += " Recuerde avisar a los presentes de que estoy tomando notas."
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

    def start_call(prefill: bytes = b"", force: bool = False) -> bool:
        """Open a live call (from a worker thread). False = use turns."""
        if not force and config.get("conversation", "llamada") != "llamada":
            return False
        if call_active():
            return True
        if not force and time.monotonic() - call_failed_at[0] < 20:
            return False  # it failed a moment ago: don't make you wait again
        from sergio_escritorio.voice import wav_pcm

        session = new_session()
        current_call[0] = session
        ears.call = session
        if not session.start(wav_pcm(prefill) if prefill else b""):
            current_call[0] = None
            ears.call = None
            call_failed_at[0] = time.monotonic()
            call_error[0] = session.error
            logging.warning("live call unavailable: %s", session.error)
            ears.mark(f"la llamada falló: {session.error[:80]}")
            bridge.caption.emit(f"No pude abrir la llamada ({session.error[:90]}); te respondo por turnos.")
            return False
        call_error[0] = ""
        ears.mark(f"llamada lista ({session.model})")
        bridge.call_on.emit(True)
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

    threading.Thread(target=load_wake_word, daemon=True).start()

    def end_call(why: str = "colgaste") -> None:
        session = current_call[0]
        if session is not None:
            session.hang_up(why)

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
        due=gym_stats.next_due,
        on_change=remember_due,
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
        if not schedule.running:
            schedule.started()  # opened by hand or by voice

        def done(session: Any) -> None:
            gym_windows.clear()
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

    def gym_check() -> None:
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
