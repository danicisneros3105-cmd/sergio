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
                "Use the user's Windows computer like they would. FASTEST: click_name "
                "(target = the visible name of a button, link, tab or menu, e.g. "
                "'Suscribirse'; button = left | right | double): finds it in the "
                "window in front and clicks it at once, no screen_read needed. "
                "Other actions: click, "
                "double_click, right_click, move (element id from screen_read, or "
                "x,y); type (text into the focused field); key ('enter', 'ctrl+s', "
                "'alt+tab'); scroll (amount, negative = down); open_app (target = "
                "app name, via the Start menu); close_app (target = app or window "
                "name; closes it like its X button, so it can ask to save); point "
                "(element or x,y, text = short label: the companion flies there to "
                "SHOW the user something, without clicking); hands (target = "
                "holo | off: the user's hands grab, turn, scale, sculpt and draw 3D "
                "holograms in the camera window, which can then go to Blender); open "
                "(target = web address, file or folder); focus (target = part of a "
                "window title); wait (seconds); operate (target = a whole task on "
                "screen, done step by step like a person with mouse and keyboard); "
                "message (target = whatsapp | instagram | messenger | telegram | "
                "gmail | outlook | sms | x..., to = contact/@user/number/email, text, "
                "subject); phone_call (to, by = telefono | whatsapp); contact (to = "
                "name, field = telefono | instagram | correo..., text = value). For "
                "message/phone_call/operate set confirmed=true ONLY after the user "
                "said yes to exactly what will be sent (otherwise it stops and asks). "
                "One action per call; the result says which window is now in "
                "front, so check it worked (and screen_read when unsure). Never "
                "buy, pay, delete, or send messages/emails on the user's behalf "
                "unless they clearly asked for that exact thing."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "click_name",
                            "click",
                            "double_click",
                            "right_click",
                            "move",
                            "type",
                            "key",
                            "scroll",
                            "open_app",
                            "close_app",
                            "point",
                            "hands",
                            "open",
                            "focus",
                            "wait",
                            "operate",
                            "message",
                            "phone_call",
                            "contact",
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
                    "button": {"type": "string", "enum": ["left", "right", "double"]},
                    "amount": {"type": "integer"},
                    "target": {"type": "string"},
                    "seconds": {"type": "number"},
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "by": {"type": "string"},
                    "field": {"type": "string"},
                    "confirmed": {"type": "boolean"},
                },
                "required": ["action"],
            },
            category="desktop",
            timeout_seconds=330,
        )

    def execute(self, **params: Any) -> ToolResult:
        action = {k: v for k, v in params.items() if v not in (None, "")}
        slow = action.get("action") in ("operate", "message", "phone_call")
        try:
            data = self._call("POST", "/act", json=action, timeout=300 if slow else 60)
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


def _config_owner() -> str:
    try:
        from openjarvis.core.config import load_config

        return (load_config().phone.owner_name or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _owner_name(people: list[str]) -> str:
    """Who may approve: SERGIO_OWNER_NAME, else phone.owner_name, else the
    only enrolled person."""
    name = os.environ.get("SERGIO_OWNER_NAME", "").strip() or _config_owner()
    if not name and len(people) == 1:
        name = people[0]
    return name


@ToolRegistry.register("video_edit")
class VideoEditTool(_DesktopTool):
    tool_id = "video_edit"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="video_edit",
            description=(
                "Edit a video on the user's Windows laptop from their clips: cuts "
                "each clip, joins them in name order, reframes to 16:9 (YouTube), "
                "9:16 (Shorts/TikTok/Reels) or 1:1, adds an opening title and "
                "background music, then OPENS the result so the user can review "
                "it (saved in Videos\\Sergio). 'source' can be a full path or "
                "just the folder/file name the user said (searched in Videos, "
                "Escritorio, Descargas, Documentos, OneDrive). To imitate a "
                "channel's style, first research it with web_search (format, "
                "clip length, pacing, titles) and choose the options from that."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Folder or file."},
                    "aspect": {"type": "string", "enum": ["16:9", "9:16", "1:1"]},
                    "clip_seconds": {
                        "type": "number",
                        "description": "Seconds kept from each clip (0 = all).",
                    },
                    "max_seconds": {
                        "type": "number",
                        "description": "Max total length (0 = no limit).",
                    },
                    "title": {"type": "string", "description": "Opening title."},
                    "music": {"type": "string", "description": "Music file."},
                    "name": {"type": "string", "description": "Output name."},
                },
                "required": ["source"],
            },
            category="desktop",
            timeout_seconds=1800,
        )

    def execute(self, **params: Any) -> ToolResult:
        action = {k: v for k, v in params.items() if v not in (None, "")}
        action["action"] = "make_video"
        try:
            data = self._call("POST", "/act", json=action, timeout=1800)
        except RuntimeError as exc:
            return self._fail(f"No pude editar el video: {exc}")
        return self._ok(
            str(data.get("result", "listo"))
            + ". Ya lo abrí para que el usuario lo revise; no lo publiques sin "
            "su aprobación con face_approval."
        )


@ToolRegistry.register("blender_create")
class BlenderCreateTool(_DesktopTool):
    tool_id = "blender_create"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="blender_create",
            description=(
                "Build a 3D model or scene in Blender on the user's laptop. Write "
                "a complete Blender Python script (import bpy) that creates the "
                "objects, materials (Principled BSDF), lights and camera; Blender "
                "opens running it so the user sees the result and can keep "
                "editing. For big models use loops, modifiers (array, mirror, "
                "subdivision) and geometry instead of thousands of manual lines. "
                "Start by clearing the default scene. Set hands=true to also open "
                "the holograms so the user can shape things with their hands."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "bpy code."},
                    "hands": {
                        "type": "boolean",
                        "description": "Live hand control of the model.",
                    },
                },
                "required": ["script"],
            },
            category="desktop",
            timeout_seconds=120,
        )

    def execute(self, **params: Any) -> ToolResult:
        script = str(params.get("script") or "")
        try:
            data = self._call(
                "POST",
                "/act",
                json={
                    "action": "blender",
                    "script": script,
                    "hands": bool(params.get("hands")),
                },
            )
        except RuntimeError as exc:
            return self._fail(f"No pude abrir Blender: {exc}")
        return self._ok(str(data.get("result", "Blender abierto")))


def _camera_faces(tool: _DesktopTool) -> tuple[bytes, list[str], list[str]]:
    """(jpeg, names seen, enrolled names)."""
    import base64

    from openjarvis.faces import FaceBook

    shot = tool._call("GET", "/camera")
    jpeg = base64.b64decode(shot["image_jpeg_b64"])
    book = FaceBook()
    seen = [m.name for m in book.identify(jpeg)]
    enrolled = [p["name"] for p in book.people()]
    return jpeg, seen, enrolled


@ToolRegistry.register("face_approval")
class FaceApprovalTool(_DesktopTool):
    tool_id = "face_approval"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="face_approval",
            description=(
                "Confirm with face recognition that the OWNER (not someone else) "
                "approves something. REQUIRED before publishing/uploading, "
                "sending, buying, paying or deleting. Ask the user to look at "
                "the camera, then call it; only go ahead if it says APROBADO."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "what": {"type": "string", "description": "What is approved."},
                },
                "required": ["what"],
            },
            category="desktop",
            timeout_seconds=120,
        )

    def execute(self, **params: Any) -> ToolResult:
        what = str(params.get("what") or "la acción")
        try:
            _jpeg, seen, enrolled = _camera_faces(self)
        except RuntimeError as exc:
            return self._fail(f"NO APROBADO: no pude ver por la cámara ({exc}).")
        except Exception as exc:  # noqa: BLE001 — models missing, etc.
            return self._fail(
                f"NO APROBADO: reconocimiento facial no disponible ({exc})."
            )
        owner = _owner_name(enrolled)
        lookup = {n.lower(): n for n in enrolled}
        owner = lookup.get(owner.lower(), "")
        if not owner:
            return self._fail(
                "NO APROBADO: todavía no conozco la cara del dueño. Pídele que "
                "diga 'Sergio, aprende mi cara' mirando a la cámara."
            )
        if not seen:
            return self._fail("NO APROBADO: no veo ninguna cara; que mire a la cámara.")
        if owner in seen:
            return self._ok(
                f"APROBADO: {owner} aprobó {what} (cara reconocida).", approved=True
            )
        others = ", ".join(n or "desconocido" for n in seen)
        return self._fail(f"NO APROBADO: veo a {others}, no a {owner}.")


@ToolRegistry.register("face_enroll")
class FaceEnrollTool(_DesktopTool):
    tool_id = "face_enroll"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="face_enroll",
            description=(
                "Learn a person's face from the webcam (only when asked, e.g. "
                "'aprende mi cara', 'escanea mi cara' or 'aprende la cara de "
                "Ana', and with that person's consent). 'name' is REQUIRED: the "
                "name of the person in front of the camera right now (the "
                "owner's own name only if it is the owner). If you do not know "
                "the name, ask first. A Face ID-style scan: the person turns "
                "their head slowly in a circle for ~10 s while a ring fills on "
                "the camera; Sergio keeps the sharpest photo of each angle and a "
                "3D map of the face. Only one face may be visible."
            ),
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            category="desktop",
            timeout_seconds=120,
        )

    def execute(self, **params: Any) -> ToolResult:
        import base64
        import time

        name = str(params.get("name") or "").strip()
        if not name:  # never guess: a guessed name saved strangers as the owner
            return self._fail("¿Cómo se llama la persona que está frente a la cámara?")
        try:  # the Face ID-style scan on the companion (all angles + 3D map)
            done = self._call(
                "POST",
                "/skill",
                json={"name": "face_scan", "args": {"name": name}},
                timeout=90,
            )
            return self._ok(
                str(done.get("result") or f"Listo, ya conozco la cara de {name}.")
            )
        except RuntimeError as exc:
            if "unknown skill" not in str(exc) and "not found" not in str(exc):
                return self._fail(f"No pude escanear la cara: {exc}")
        try:  # an older companion: five photos a moment apart
            from openjarvis.faces import FaceBook

            book = FaceBook()
            saved, problem = 0, ""
            for _ in range(5):  # a few angles recognise you better later
                shot = self._call("GET", "/camera")
                try:
                    saved = book.enroll(
                        name, base64.b64decode(shot["image_jpeg_b64"]), consent=True
                    )
                except ValueError as exc:  # no clear face here; try again
                    problem = str(exc)
                time.sleep(0.6)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"No pude aprender la cara: {exc}")
        if not saved:
            return self._fail(
                "No vi una cara clara; que mire de frente con buena luz. " + problem
            )
        return self._ok(f"Listo, ya conozco la cara de {name}.")


@ToolRegistry.register("files_organize")
class FilesOrganizeTool(_DesktopTool):
    tool_id = "files_organize"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="files_organize",
            description=(
                "Tidy a folder on the user's Windows laptop: moves its loose "
                "files into subfolders by kind (Imágenes, Videos, Documentos, "
                "Música, Instaladores...) or by month. 'target' can be a path or "
                "a folder name said out loud (Descargas, Escritorio, Documentos). "
                "ALWAYS call first with apply=false to get the preview, tell the "
                "user what will happen, and only call again with apply=true "
                "after they agree. Nothing is deleted or overwritten, and "
                "undo=true puts the last tidy-up back."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Folder."},
                    "by": {"type": "string", "enum": ["type", "month"]},
                    "apply": {"type": "boolean"},
                    "undo": {"type": "boolean"},
                },
            },
            category="desktop",
            timeout_seconds=300,
        )

    def execute(self, **params: Any) -> ToolResult:
        if params.get("undo"):
            action: dict[str, Any] = {"action": "undo_organize"}
        else:
            action = {
                "action": "organize",
                "target": str(params.get("target") or ""),
                "by": params.get("by") or "type",
                "apply": bool(params.get("apply")),
            }
        try:
            data = self._call("POST", "/act", json=action, timeout=300)
        except RuntimeError as exc:
            return self._fail(f"No pude ordenar la carpeta: {exc}")
        return self._ok(str(data.get("result", "listo")))


@ToolRegistry.register("python_run")
class PythonRunTool(_DesktopTool):
    tool_id = "python_run"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="python_run",
            description=(
                "Run a Python program on the user's Windows laptop and get what "
                "it printed (numpy, Pillow and OpenCV are available; the "
                "working folder is Documents\\Sergio). Use it for calculations, "
                "converting or resizing images, renaming many files, reading "
                "CSVs, making charts... print() the results. Ask the user "
                "before code that deletes or overwrites their files."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code."},
                    "seconds": {"type": "number", "description": "Time limit."},
                },
                "required": ["code"],
            },
            category="desktop",
            timeout_seconds=960,
        )

    def execute(self, **params: Any) -> ToolResult:
        action = {
            "action": "python",
            "code": str(params.get("code") or ""),
            "seconds": params.get("seconds") or 120,
        }
        try:
            data = self._call("POST", "/act", json=action, timeout=960)
        except RuntimeError as exc:
            return self._fail(f"No pude ejecutar Python: {exc}")
        result = str(data.get("result", ""))
        return ToolResult(
            tool_name=self.tool_id,
            content=result,
            success=result.startswith("exit code 0"),
        )


@ToolRegistry.register("terminal_run")
class TerminalRunTool(_DesktopTool):
    tool_id = "terminal_run"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="terminal_run",
            description=(
                "Run a PowerShell command on the user's Windows laptop (in their "
                "home folder) and get its output: list or find files, check disk "
                "space, see running apps (Get-Process), install apps with "
                "winget, git, pip, npm, change settings... Prefer one clear "
                "command at a time and read the output. Before anything that "
                "deletes files, uninstalls, changes system settings or shuts "
                "down, tell the user exactly what will happen and get their "
                "OK (face_approval for deleting)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell."},
                    "seconds": {"type": "number", "description": "Time limit."},
                },
                "required": ["command"],
            },
            category="desktop",
            timeout_seconds=960,
        )

    def execute(self, **params: Any) -> ToolResult:
        action = {
            "action": "terminal",
            "command": str(params.get("command") or ""),
            "seconds": params.get("seconds") or 120,
        }
        try:
            data = self._call("POST", "/act", json=action, timeout=960)
        except RuntimeError as exc:
            return self._fail(f"No pude usar la terminal: {exc}")
        result = str(data.get("result", ""))
        return ToolResult(
            tool_name=self.tool_id,
            content=result,
            success=result.startswith("exit code 0"),
        )


__all__ = [
    "BlenderCreateTool",
    "CameraLookTool",
    "DesktopActionTool",
    "FaceApprovalTool",
    "FaceEnrollTool",
    "FilesOrganizeTool",
    "PythonRunTool",
    "ScreenReadTool",
    "TerminalRunTool",
    "VideoEditTool",
]
