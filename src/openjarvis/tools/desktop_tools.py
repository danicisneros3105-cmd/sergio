"""Tools: see and use the Windows desktop through Sergio Escritorio.

Sergio's brain runs in WSL; Sergio Escritorio (``windows/``) runs in Windows
and exposes a token-protected control server on 127.0.0.1. These tools are
how the agent reads the screen and moves the mouse/keyboard like the user.

The user can pause all control at any time with Ctrl+Alt+End.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

DEFAULT_URL = "http://127.0.0.1:8765"
MAX_LISTED = 120
_SETUP_HINT = (
    "Sergio Escritorio is not reachable. Install it with `sergio escritorio "
    "instalar` (in Ubuntu) and make sure it is running in Windows."
)

_VISION_PROMPT = (
    "Describe this screenshot of a Windows desktop for an assistant that must "
    "act on it: which app and page are open, the main content, visible buttons, "
    "fields and messages. Be concise and literal. Answer in Spanish."
)


def _endpoint() -> tuple[str, dict[str, str]]:
    url = os.environ.get("SERGIO_DESKTOP_URL", DEFAULT_URL).rstrip("/")
    token = os.environ.get("SERGIO_DESKTOP_TOKEN", "")
    return url, {"Authorization": f"Bearer {token}"}


class _DesktopTool(BaseTool):
    def __init__(self, *, http: httpx.Client | None = None) -> None:
        self._http = http

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=httpx.Timeout(60, connect=3))
        return self._http

    def _call(self, method: str, path: str, **kwargs: Any) -> dict:
        url, headers = _endpoint()
        if not headers["Authorization"].removeprefix("Bearer "):
            raise RuntimeError(_SETUP_HINT)
        try:
            resp = self._client().request(method, url + path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise RuntimeError(_SETUP_HINT) from exc
        data = resp.json()
        if resp.status_code != 200 or not data.get("ok", True):
            raise RuntimeError(data.get("error") or f"HTTP {resp.status_code}")
        return data

    def _ok(self, content: str, **meta: Any) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=content, metadata=meta)

    def _fail(self, content: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=content, success=False)


def _describe_image(png_b64: str, http: httpx.Client) -> str:
    """Ask a local vision model (if configured) what the screenshot shows."""
    model = os.environ.get("SERGIO_VISION_MODEL", "").strip()
    if not model:
        return ""
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if "://" not in host:
        host = "http://" + host
    try:
        resp = http.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "user", "content": _VISION_PROMPT, "images": [png_b64]}
                ],
            },
            timeout=180,
        )
        resp.raise_for_status()
        return str(resp.json()["message"]["content"]).strip()
    except Exception as exc:  # noqa: BLE001 — vision is a bonus, never fatal
        return f"(vision model {model} failed: {exc})"


@ToolRegistry.register("screen_read")
class ScreenReadTool(_DesktopTool):
    tool_id = "screen_read"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="screen_read",
            description=(
                "See the user's Windows screen: the active window, the other open "
                "windows, and a numbered list of the buttons, fields, links and "
                "menu items you can act on (use the number as 'element' in "
                "desktop_action). Call it before acting and again after each step "
                "to check the result. Set look=true for a visual description too."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "look": {
                        "type": "boolean",
                        "description": "Also describe the screenshot (slower).",
                    }
                },
            },
            category="desktop",
            timeout_seconds=200,
        )

    def execute(self, **params: Any) -> ToolResult:
        try:
            ui = self._call("GET", "/ui")
        except RuntimeError as exc:
            return self._fail(str(exc))
        lines = [f"Active window: {ui.get('window') or '(none)'}"]
        others = [w for w in ui.get("windows", []) if w != ui.get("window")]
        if others:
            lines.append("Other open windows: " + " | ".join(others[:15]))
        elements = ui.get("elements", [])
        if elements:
            lines.append("Elements (id. type 'name' @x,y):")
            for el in elements[:MAX_LISTED]:
                name = el["name"] or "(no label)"
                lines.append(f"{el['id']}. {el['type']} '{name}' @{el['x']},{el['y']}")
        else:
            lines.append("No accessible elements found; use look=true.")
        if params.get("look"):
            try:
                shot = self._call("GET", "/screen")
                described = _describe_image(shot["image_png_b64"], self._client())
                lines.append(
                    "Screen: "
                    + (
                        described
                        or "no vision model configured (set SERGIO_VISION_MODEL)."
                    )
                )
            except RuntimeError as exc:
                lines.append(f"Screenshot failed: {exc}")
        return self._ok("\n".join(lines), elements=len(elements))


@ToolRegistry.register("desktop_action")
class DesktopActionTool(_DesktopTool):
    tool_id = "desktop_action"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_action",
            description=(
                "Use the user's Windows computer like they would. Actions: click, "
                "double_click, right_click, move (element id from screen_read, or "
                "x,y); type (text into the focused field); key ('enter', 'ctrl+s', "
                "'alt+tab'); scroll (amount, negative = down); open_app (target = "
                "app name, via the Start menu); open (target = web address, file or "
                "folder); focus (target = part of a window title); wait (seconds). "
                "One action per call; check with screen_read afterwards. Never "
                "buy, pay, delete, or send messages/emails on the user's behalf "
                "unless they clearly asked for that exact thing."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "element": {
                        "type": "integer",
                        "description": "id from screen_read",
                    },
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "text": {"type": "string"},
                    "keys": {"type": "string"},
                    "amount": {"type": "integer"},
                    "target": {"type": "string"},
                    "seconds": {"type": "number"},
                },
                "required": ["action"],
            },
            category="desktop",
            timeout_seconds=60,
        )

    def execute(self, **params: Any) -> ToolResult:
        action = {k: v for k, v in params.items() if v not in (None, "")}
        try:
            data = self._call("POST", "/act", json=action)
        except RuntimeError as exc:
            return self._fail(str(exc))
        return self._ok(str(data.get("result", "done")))


@ToolRegistry.register("camera_look")
class CameraLookTool(_DesktopTool):
    tool_id = "camera_look"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="camera_look",
            description=(
                "Look through the user's webcam and answer a question about it: "
                "the object in their hand, a gesture (thumbs up, pointing, "
                "counting fingers), their expression, or what is in front of the "
                "camera. Also says who is there if the face was enrolled. Use it "
                "whenever the user says 'mira', 'qué tengo', 'qué ves', or "
                "guides you with gestures."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "What to find out, in Spanish.",
                    }
                },
                "required": ["question"],
            },
            category="desktop",
            timeout_seconds=150,
        )

    def execute(self, **params: Any) -> ToolResult:
        import base64

        from openjarvis.tools.vision_look import ask_vision

        try:
            shot = self._call("GET", "/camera")
        except RuntimeError as exc:
            return self._fail(f"No pude ver por la cámara: {exc}")
        jpeg = base64.b64decode(shot["image_jpeg_b64"])
        people = ""
        try:
            from openjarvis.faces import FaceBook

            names = [m.name for m in FaceBook().identify(jpeg) if m.name]
            if names:
                people = "Personas reconocidas: " + ", ".join(sorted(set(names))) + ". "
        except Exception:  # noqa: BLE001 — face recognition is optional
            pass
        try:
            seen = ask_vision(jpeg, str(params.get("question") or ""), self._client())
        except RuntimeError as exc:
            return self._fail(people + str(exc))
        return self._ok(people + seen)


__all__ = ["CameraLookTool", "DesktopActionTool", "ScreenReadTool"]
