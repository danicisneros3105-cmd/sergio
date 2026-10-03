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
)


class Backend(Protocol):
    def screenshot(self) -> Any: ...  # PIL.Image of the whole screen

    def ui(self) -> dict: ...

    def click(self, x: int, y: int, button: str, clicks: int) -> None: ...

    def move(self, x: int, y: int) -> None: ...

    def type_text(self, text: str) -> None: ...

    def hotkey(self, keys: list[str]) -> None: ...

    def scroll(self, amount: int, x: int | None, y: int | None) -> None: ...

    def open_app(self, name: str) -> None: ...

    def open_target(self, target: str) -> None: ...

    def focus(self, title: str) -> bool: ...


class ActionError(ValueError):
    pass


class Controller:
    """Turns validated requests into backend calls. Thread-safe."""

    def __init__(
        self,
        backend: Backend,
        *,
        on_activity: Callable[[str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.backend = backend
        self.enabled = True
        self._elements: dict[int, tuple[int, int]] = {}
        self._lock = threading.Lock()
        self._on_activity = on_activity or (lambda _msg: None)
        self._sleep = sleep

    # -- reading -----------------------------------------------------------
    def screen(self) -> dict:
        image = self.backend.screenshot()
        width, height = image.size
        scale = 1.0
        if width > MAX_SHOT_WIDTH:
            scale = width / MAX_SHOT_WIDTH
            image = image.resize((MAX_SHOT_WIDTH, round(height / scale)))
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG", optimize=True)
        return {
            "image_png_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
            "width": width,
            "height": height,
            "scale": scale,
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
            b.hotkey(keys)
            result = "pressed " + "+".join(keys)
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
            b.open_app(name)
            result = f"opened {name}"
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
        else:  # wait
            seconds = min(max(float(action.get("seconds") or 1), 0.1), 10)
            self._sleep(seconds)
            result = f"waited {seconds:g}s"
        self._on_activity(result)
        return result


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
                else:
                    self._send(404, {"ok": False, "error": "not found"})
            except Exception as exc:  # noqa: BLE001
                self._send(500, {"ok": False, "error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorised():
                return
            if self.path != "/act":
                self._send(404, {"ok": False, "error": "not found"})
                return
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 64_000)
                action = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(action, dict):
                    raise ActionError("Send a JSON object.")
                self._send(200, {"ok": True, "result": controller.act(action)})
            except PermissionError as exc:
                self._send(423, {"ok": False, "error": str(exc)})
            except (ActionError, ValueError) as exc:
                self._send(400, {"ok": False, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 — incl. pyautogui fail-safe
                self._send(500, {"ok": False, "error": str(exc)})

    return ThreadingHTTPServer((host, port), Handler)


__all__ = ["ACTIONS", "ActionError", "Backend", "Controller", "make_server"]
