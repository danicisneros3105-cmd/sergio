"""Local control server: lets Sergio (in WSL) see and use the Windows desktop.

Only listens on 127.0.0.1 and every request needs the shared token. The user
can cut it off at any time with Ctrl+Alt+End (``Controller.enabled``) or by
slamming the mouse into the top-left corner (pyautogui fail-safe).

Protocol (JSON):
  GET  /health -> {"ok": true, "enabled": bool}
  GET  /screen -> {"image_png_b64", "width", "height", "scale"}
  GET  /ui     -> {"window", "windows", "elements": [{"id","name","type","x","y"}]}
  POST /act    -> {"ok": bool, "result": str}

Coordinates are real screen pixels; ``x``/``y`` of an element are its centre.
"""

from __future__ import annotations

import base64
import hmac
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Protocol

MAX_SHOT_WIDTH = 1280
MAX_TEXT = 4000
ACTIONS = (
    "click",
    "double_click",
    "right_click",
    "move",
    "type",
    "key",
    "scroll",
    "open_app",
    "open",
    "focus",
    "wait",
    "make_video",
    "blender",
    "organize",
    "undo_organize",
    "python",
    "close_app",
    "terminal",
    "point",
    "hands",
    "operate",
    "message",
    "phone_call",
    "contact",
)
MEDIA_KEYS = {"volumeup", "volumedown", "volumemute", "playpause", "nexttrack", "prevtrack"}
TASKS = ("operate", "message", "phone_call", "contact")  # done by the operator


class Backend(Protocol):
    def screenshot(self) -> Any: ...  # PIL.Image of the whole screen

    def ui(self) -> dict: ...

    def click(self, x: int, y: int, button: str, clicks: int) -> None: ...

    def move(self, x: int, y: int) -> None: ...

    def type_text(self, text: str) -> None: ...

    def hotkey(self, keys: list[str]) -> None: ...

    def scroll(self, amount: int, x: int | None, y: int | None) -> None: ...

    def open_app(self, name: str) -> str | None: ...  # "opened Spotify"

    def open_target(self, target: str) -> None: ...

    def focus(self, title: str) -> bool: ...

    def make_video(self, options: dict) -> str: ...  # path of the new video

    def blender(self, script: str) -> str: ...  # path of the saved script

    def organize(self, folder: str, by: str, apply: bool) -> dict: ...

    def undo_organize(self) -> int: ...  # files put back

    def python(self, code: str, timeout: float) -> dict: ...

    def close_app(self, name: str) -> list[str]: ...  # titles closed

    def shell(self, command: str, timeout: float) -> dict: ...


class ActionError(ValueError):
    pass


class ShotScale(float):
    """Screenshot pixels -> screen pixels: a scale plus where the shot's
    monitor starts (the screen in use may be the second monitor)."""

    origin: tuple[int, int] = (0, 0)

    def __new__(cls, scale: float, origin: tuple[int, int] = (0, 0)) -> "ShotScale":
        obj = super().__new__(cls, scale)
        obj.origin = (int(origin[0]), int(origin[1]))
        return obj

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        return round(x * self + self.origin[0]), round(y * self + self.origin[1])


class Controller:
    """Turns validated requests into backend calls. Thread-safe."""

    def __init__(
        self,
        backend: Backend,
        *,
        on_activity: Callable[[str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        camera: Callable[[], bytes] | None = None,
        diag: Callable[[], dict] | None = None,
    ) -> None:
        self.backend = backend
        self.camera = camera  # returns a JPEG of the webcam, or None
        self.diag = diag or (lambda: {})  # what the ear is doing (revisar)
        # The companion flies to a spot to show the user something.
        self.on_point: Callable[[int, int, str], None] = lambda _x, _y, _l: None
        # Hands for the holograms in Sergio ve ("holo" / "off"); returns a status.
        self.on_hands: Callable[[str], str] = lambda _mode: "hands unavailable"
        # `sergio probar`: talk to Sergio like the user does ("call"/"turn").
        self.selftest: Callable[[str], dict] | None = None
        # Tasks done like a person (operate, message, phone_call, contact).
        self.on_task: Callable[[str, dict], str] = lambda _k, _a: "operator unavailable"
        self.enabled = True
        self._elements: dict[int, tuple[int, int]] = {}
        self._lock = threading.Lock()
        self._on_activity = on_activity or (lambda _msg: None)
        self._sleep = sleep

    # -- reading -----------------------------------------------------------
    def camera_shot(self) -> dict:
        if self.camera is None:
            raise ActionError("No camera available.")
        jpeg = self.camera()
        return {"image_jpeg_b64": base64.b64encode(jpeg).decode("ascii")}

    def screen(self) -> dict:
        image = self.backend.screenshot()
        width, height = image.size
        scale = 1.0
        if width > MAX_SHOT_WIDTH:
            scale = width / MAX_SHOT_WIDTH
            image = image.resize((MAX_SHOT_WIDTH, round(height / scale)))
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG", optimize=True)
        left, top = getattr(self.backend, "shot_origin", (0, 0))
        return {
            "image_png_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
            "width": width,
            "height": height,
            "scale": scale,
            "left": left,
            "top": top,
        }

    def ui(self) -> dict:
        info = self.backend.ui()
        elements = []
        mapping: dict[int, tuple[int, int]] = {}
        for number, el in enumerate(info.get("elements", []), start=1):
            left, top, right, bottom = el["rect"]
            centre = ((left + right) // 2, (top + bottom) // 2)
            mapping[number] = centre
            elements.append(
                {
                    "id": number,
                    "name": str(el.get("name") or "")[:80],
                    "type": el.get("type", ""),
                    "x": centre[0],
                    "y": centre[1],
                }
            )
        with self._lock:
            self._elements = mapping
        return {
            "window": info.get("window", ""),
            "windows": info.get("windows", []),
            "elements": elements,
        }

    def snapshot(self) -> tuple[bytes, list[dict], float]:
        """Screenshot (PNG) + elements in screenshot pixels + scale to screen.

        Used by the companion's screen help: the vision model sees the same
        picture the element coordinates refer to.
        """
        shot = self.screen()
        left, top = shot.get("left", 0), shot.get("top", 0)
        scale = ShotScale(float(shot["scale"]) or 1.0, (left, top))
        try:
            elements = self.ui()["elements"]
        except Exception:  # noqa: BLE001 — accessibility is a bonus
            elements = []
        in_shot = []
        for el in elements:
            x, y = (el["x"] - left) / scale, (el["y"] - top) / scale
            if 0 <= x <= shot["width"] / scale and 0 <= y <= shot["height"] / scale:
                in_shot.append({**el, "x": round(x), "y": round(y)})
        return base64.b64decode(shot["image_png_b64"]), in_shot, scale

    # -- acting ------------------------------------------------------------
    def _point(self, action: dict) -> tuple[int, int]:
        if action.get("element") not in (None, ""):
            try:
                number = int(action["element"])
            except (TypeError, ValueError) as exc:
                raise ActionError(
                    "'element' must be a number from screen_read"
                ) from exc
            with self._lock:
                point = self._elements.get(number)
            if point is None:
                raise ActionError(
                    f"Element {number} is unknown: call screen_read again first."
                )
            return point
        try:
            return int(action["x"]), int(action["y"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ActionError("Give 'element' or both 'x' and 'y'.") from exc

    def act(self, action: dict) -> str:
        if not self.enabled:
            raise PermissionError(
                "Screen control is paused by the user (Ctrl+Alt+End to resume)."
            )
        kind = str(action.get("action") or "")
        if kind not in ACTIONS:
            raise ActionError(
                f"Unknown action {kind!r}. Use one of: {', '.join(ACTIONS)}"
            )
        b = self.backend
        if kind in ("click", "double_click", "right_click", "move"):
            x, y = self._point(action)
            if kind == "move":
                b.move(x, y)
            else:
                button = "right" if kind == "right_click" else "left"
                b.click(x, y, button, 2 if kind == "double_click" else 1)
            result = f"{kind} at ({x}, {y})"
        elif kind == "type":
            text = str(action.get("text") or "")
            if not text or len(text) > MAX_TEXT:
                raise ActionError(f"'text' must have 1-{MAX_TEXT} characters.")
            b.type_text(text)
            result = f"typed {len(text)} characters"
        elif kind == "key":
            keys = [k.strip().lower() for k in str(action.get("keys") or "").split("+")]
            if not all(keys):
                raise ActionError("'keys' looks like 'enter', 'ctrl+s' or 'alt+tab'.")
            repeat = min(max(int(action.get("repeat") or 1), 1), 60)
            for _ in range(repeat):  # "volume to 30%": 50 presses in a blink
                b.hotkey(keys)
            result = "pressed " + "+".join(keys) + (f" x{repeat}" if repeat > 1 else "")
        elif kind == "scroll":
            amount = int(action.get("amount") or -5)
            point = (
                self._point(action)
                if ("element" in action or "x" in action)
                else (None, None)
            )
            b.scroll(amount, *point)
            result = f"scrolled {amount}"
        elif kind == "open_app":
            name = str(action.get("target") or "").strip()
            if not name:
                raise ActionError("'target' is the app name, e.g. 'Spotify'.")
            opened = b.open_app(name)
            result = opened if isinstance(opened, str) and opened else f"opened {name}"
        elif kind == "open":
            target = str(action.get("target") or "").strip()
            if not target:
                raise ActionError("'target' is a web address, file or folder.")
            b.open_target(target)
            result = f"opened {target}"
        elif kind == "focus":
            title = str(action.get("target") or "").strip()
            if not title or not b.focus(title):
                raise ActionError(f"No open window matches {title!r}.")
            result = f"focused {title}"
        elif kind == "make_video":
            source = str(action.get("source") or "").strip()
            if not source:
                raise ActionError("'source' is the folder or file with the clips.")
            options = {
                k: action[k]
                for k in (
                    "source",
                    "aspect",
                    "clip_seconds",
                    "max_seconds",
                    "title",
                    "music",
                    "name",
                )
                if action.get(k) not in (None, "")
            }
            result = "video ready: " + b.make_video(options)
        elif kind == "blender":
            script = str(action.get("script") or "")
            if not script.strip() or len(script) > 60_000:
                raise ActionError("'script' is Blender Python (bpy) code.")
            if action.get("hands"):  # shape it with your hands first: holograms
                self.on_hands("holo")
            result = "Blender opened with script " + b.blender(script)
        elif kind == "organize":
            folder = str(action.get("target") or "").strip()
            if not folder:
                raise ActionError("'target' is the folder to organise.")
            by = "month" if action.get("by") == "month" else "type"
            plan = b.organize(folder, by, bool(action.get("apply")))
            groups = ", ".join(f"{k}: {v}" for k, v in plan["groups"].items())
            verb = "moved" if plan["applied"] else "would move (preview, nothing moved)"
            result = (
                f"{verb} {plan['files']} files in {plan['folder']} -> {groups or '-'}"
            )
        elif kind == "undo_organize":
            result = f"put back {b.undo_organize()} files"
        elif kind == "python":
            code = str(action.get("code") or "")
            if not code.strip() or len(code) > 60_000:
                raise ActionError("'code' is the Python program to run.")
            timeout = min(max(float(action.get("seconds") or 120), 5), 900)
            ran = b.python(code, timeout)
            result = (
                f"exit code {ran['exit_code']} (script {ran['script']})\n"
                f"stdout:\n{ran['stdout']}\nstderr:\n{ran['stderr']}"
            )
        elif kind == "hands":
            mode = str(action.get("target") or "off").strip().lower()
            result = self.on_hands(mode)
        elif kind in TASKS:
            result = self.on_task(kind, action)
        elif kind == "point":
            x, y = self._point(action)
            label = str(action.get("text") or action.get("target") or "")[:40]
            self.on_point(x, y, label)
            result = f"pointed at ({x}, {y})"
        elif kind == "close_app":
            name = str(action.get("target") or "").strip()
            if len(name) < 2:
                raise ActionError("'target' is the app or window name to close.")
            closed = b.close_app(name)
            if not closed:
                raise ActionError(f"No open app matches {name!r}.")
            result = "asked to close: " + " | ".join(closed)
        elif kind == "terminal":
            command = str(action.get("command") or "")
            if not command.strip() or len(command) > 20_000:
                raise ActionError("'command' is the PowerShell command to run.")
            timeout = min(max(float(action.get("seconds") or 120), 5), 900)
            ran = b.shell(command, timeout)
            result = (
                f"exit code {ran['exit_code']}\n"
                f"output:\n{ran['stdout']}\nerrors:\n{ran['stderr']}"
            )
        else:  # wait
            seconds = min(max(float(action.get("seconds") or 1), 0.1), 10)
            self._sleep(seconds)
            result = f"waited {seconds:g}s"
        self._on_activity(result)
        if kind == "key" and set(result.split()[1].split("+")) <= MEDIA_KEYS:
            return result  # the window in front does not change
        return result + self._verify(kind)

    VERIFY = {
        "click",
        "double_click",
        "right_click",
        "key",
        "type",
        "open_app",
        "open",
        "close_app",
        "focus",
    }

    def _verify(self, kind: str) -> str:
        """What is in front after the action, so Sergio can check it worked."""
        active = getattr(self.backend, "active_window", None)
        if kind not in self.VERIFY or active is None:
            return ""
        self._sleep({"open_app": 0.15, "open": 0.6, "close_app": 0.4}.get(kind, 0.25))
        try:
            title = active() or "(escritorio)"
        except Exception:  # noqa: BLE001 — a check must never break the action
            return ""
        return f" | now in front: {title[:80]}"


def make_server(
    controller: Controller, token: str, port: int = 8765, host: str = "127.0.0.1"
) -> ThreadingHTTPServer:
    expected = f"Bearer {token}".encode()

    class Handler(BaseHTTPRequestHandler):
        server_version = "SergioEscritorio"

        def log_message(self, *_args: Any) -> None:  # keep the console quiet
            pass

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self) -> bool:
            got = self.headers.get("Authorization", "").encode()
            if token and hmac.compare_digest(got, expected):
                return True
            self._send(401, {"ok": False, "error": "bad token"})
            return False

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorised():
                return
            try:
                if self.path == "/health":
                    self._send(200, {"ok": True, "enabled": controller.enabled})
                elif self.path == "/screen":
                    self._send(200, controller.screen())
                elif self.path == "/ui":
                    self._send(200, controller.ui())
                elif self.path == "/camera":
                    self._send(200, controller.camera_shot())
                elif self.path == "/diag":
                    self._send(200, {"ok": True, **controller.diag()})
                else:
                    self._send(404, {"ok": False, "error": "not found"})
            except Exception as exc:  # noqa: BLE001
                self._send(500, {"ok": False, "error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorised():
                return
            if self.path == "/selftest":
                try:
                    length = min(int(self.headers.get("Content-Length") or 0), 4_000)
                    body = json.loads(self.rfile.read(length) or b"{}")
                    test = controller.selftest
                    if test is None:
                        self._send(404, {"ok": False, "error": "no self-test"})
                    else:
                        self._send(200, test(str(body.get("kind") or "")))
                except Exception as exc:  # noqa: BLE001
                    self._send(500, {"ok": False, "error": str(exc)})
                return
            if self.path != "/act":
                self._send(404, {"ok": False, "error": "not found"})
                return
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 128_000)
                action = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(action, dict):
                    raise ActionError("Send a JSON object.")
                self._send(200, {"ok": True, "result": controller.act(action)})
            except PermissionError as exc:
                self._send(423, {"ok": False, "error": str(exc)})
            except (ActionError, ValueError, LookupError) as exc:
                self._send(400, {"ok": False, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 — incl. pyautogui fail-safe
                self._send(500, {"ok": False, "error": str(exc)})

    return ThreadingHTTPServer((host, port), Handler)


__all__ = ["ACTIONS", "ActionError", "Backend", "Controller", "ShotScale", "make_server"]
