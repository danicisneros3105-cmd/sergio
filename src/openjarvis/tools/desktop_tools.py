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
        if (
            os.environ.get("SERGIO_EXECUTION_MODE", "local") == "container"
            and method != "GET"
        ):
            owner_consent = (
                path == "/skill"
                and kwargs.get("json", {}).get("name") == "owner_approval"
            )
            if not owner_consent:
                raise RuntimeError(
                    "Desktop mutations are disabled in project container mode. "
                    "Use shell_exec or code_interpreter inside the configured project."
                )
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
                try:  # the live eye answers a JPEG at once
                    shot = self._call("GET", "/screen?format=jpeg")
                except RuntimeError:  # an older Sergio Escritorio
                    shot = self._call("GET", "/screen")
                image = shot.get("image_jpeg_b64") or shot["image_png_b64"]
                described = _describe_image(image, self._client())
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
                "SHOW the user something, without clicking); guide (marks = up to "
                "6 drawings over the real screen, in order: each {element | target "
                "= visible name | x,y, shape = arrow | circle | box | underline | "
                "line, text = 1-4 words}; 3D arrows, hand-drawn circles and a ghost "
                "cursor that walks the route; they vanish on the user's next click: "
                "use it to TEACH where things are instead of describing them; with "
                "steps = true it is a step-by-step tour: one mark at a time, «Paso 2 "
                "de 4», each click shows the next; use it for anything that takes "
                "several clicks); hands (target = "
                "holo | off: the user's hands grab, turn, scale, sculpt and draw 3D "
                "holograms in the camera window, which can then go to Blender); open "
                "(target = web address, file or folder); focus (target = part of a "
                "window title); split (target = two programs, 'Chrome | Word': "
                "side by side, each on half of the screen, opened if needed); "
                "wait (seconds); operate (target = a whole task on "
                "screen, done step by step like a person with mouse and keyboard: "
                "ordering food by delivery or Uber, online shopping, ordering clothes, "
                "finding products and adding them to the cart, publishing sales listings "
                "with title/price/description across multiple platforms, sending emails "
                "or messages, or controlling any web/desktop app); "
                "message (target = whatsapp | instagram | messenger | telegram | "
                "gmail | outlook | sms | x..., to = contact/@user/number/email, text, "
                "subject); phone_call (to, by = telefono | whatsapp); contact (to = "
                "name, field = telefono | instagram | correo..., text = value). "
                "Pass confirmed=true by default to execute the user's request end-to-end "
                "without asking for extra permissions. One action per call; the result "
                "says which window is now in front, so check it worked (and screen_read "
                "when unsure)."
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
                            "guide",
                            "hands",
                            "open",
                            "focus",
                            "split",
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
                    "steps": {
                        "type": "boolean",
                        "description": "guide: one mark at a time, each click the next",
                    },
                    "marks": {
                        "type": "array",
                        "description": "guide: the drawings, in order",
                        "items": {
                            "type": "object",
                            "properties": {
                                "element": {"type": "integer"},
                                "target": {"type": "string"},
                                "x": {"type": "integer"},
                                "y": {"type": "integer"},
                                "shape": {
                                    "type": "string",
                                    "enum": [
                                        "arrow",
                                        "circle",
                                        "box",
                                        "underline",
                                        "line",
                                    ],
                                },
                                "text": {"type": "string"},
                            },
                        },
                    },
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
        kind = action.get("action")
        if kind in ("operate", "message", "phone_call"):
            action.setdefault("confirmed", True)
        if kind == "operate" and "goal" not in action and "target" in action:
            action["goal"] = action["target"]
        if kind == "message" and "platform" not in action and "target" in action:
            action["platform"] = action["target"]
        if kind == "phone_call" and "platform" not in action and "by" in action:
            action["platform"] = action["by"]
        if kind == "contact" and "platform" not in action and "field" in action:
            action["platform"] = action["field"]
        slow = kind in ("operate", "message", "phone_call")
        try:
            data = self._call("POST", "/act", json=action, timeout=300 if slow else 110)
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


@ToolRegistry.register("video_pro")
class VideoProTool(_DesktopTool):
    """The professional edit on the owner's laptop (video_master.pipeline)."""

    tool_id = "video_pro"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="video_pro",
            description=(
                "Professional video edit on the user's Windows laptop, for anything "
                "beyond a quick montage. Gemini watches every clip (contact sheets), "
                "picks the best moments and plans the cut in the requested style; "
                "then: cross fades, captions, opening title, music under the voices, "
                "loudness at -14 LUFS, HDR tone-mapped and tagged Rec.709. Optional "
                "finishing: remove silences from talking clips, photos as Ken Burns "
                "clips, AI frame interpolation (RIFE) to 60 fps or slow motion, and a "
                "10-bit master (ProRes 422 HQ, ProRes 4444, DNxHR HQX or HEVC 10-bit) "
                "with a colour chain (3D LUT .cube, denoise, contrast curve, "
                "sharpening). 'request' is the creative brief: audience, platform, "
                "length, pacing, mood, a channel to imitate (research it first with "
                "web_search). It opens the result for review; never publish without "
                "face_approval. Takes minutes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Folder or file."},
                    "request": {"type": "string", "description": "Creative brief."},
                    "aspect": {"type": "string", "enum": ["16:9", "9:16", "1:1"]},
                    "silences": {"type": "boolean", "description": "Cut dead air."},
                    "fps": {"type": "integer", "description": "Interpolate to fps."},
                    "slow": {"type": "number", "description": "Slow motion factor."},
                    "master": {
                        "type": "string",
                        "enum": ["prores", "prores4444", "dnxhr", "hevc10"],
                    },
                    "lut": {"type": "string", "description": ".cube LUT path."},
                    "denoise": {"type": "boolean"},
                    "sharpen": {"type": "boolean"},
                    "contrast_curve": {"type": "boolean"},
                    "music": {"type": "string", "description": "Music file."},
                },
                "required": ["source", "request"],
            },
            category="desktop",
            timeout_seconds=3600,
        )

    def execute(self, **params: Any) -> ToolResult:
        args = {k: v for k, v in params.items() if v not in (None, "")}
        try:
            data = self._call(
                "POST", "/skill", json={"name": "video_pro", "args": args}, timeout=3600
            )
        except RuntimeError as exc:
            return self._fail(f"No pude editar el video: {exc}")
        out = data.get("result") or {}
        lines = [f"Video listo: {out.get('path', '')}"]
        if out.get("title"):
            lines.append(
                f"Título: «{out['title']}» ({out.get('segments', 0)} momentos, "
                f"{out.get('aspect', '')})."
            )
        if out.get("master"):
            lines.append(f"Máster {out.get('master_label', '')}: {out['master']}")
        if out.get("interpolated"):
            lines.append(f"Interpolado: {out['interpolated']}")
        if out.get("steps"):
            lines.append("Pasos: " + "; ".join(out["steps"][:12]))
        lines.append(
            "Ya lo abrí para que el usuario lo revise; no lo publiques sin su "
            "aprobación con face_approval."
        )
        return self._ok("\n".join(lines), **out)


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
                "Confirm with Sergio's own Face ID that the OWNER "
                "approves something. REQUIRED before publishing/uploading, "
                "sending, buying, paying or deleting. Display the exact action "
                "and request system verification; only proceed on APROBADO."
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
            data = self._call(
                "POST",
                "/skill",
                json={"name": "owner_approval", "args": {"what": what}},
                timeout=100,
            )
        except RuntimeError as exc:
            return self._fail(f"NO APROBADO: Face ID no disponible ({exc}).")
        except Exception as exc:  # noqa: BLE001 — models missing, etc.
            return self._fail(
                f"NO APROBADO: verificación del sistema no disponible ({exc})."
            )
        decision = data.get("result")
        if (
            isinstance(decision, dict)
            and decision.get("approved") is True
            and decision.get("what") == what
            and decision.get("method") in ("faceid", "windows_hello")
        ):
            return self._ok(
                f"APROBADO: el dueño confirmó {what} y su identidad.", approved=True
            )
        return self._fail(
            "NO APROBADO: falta consentimiento explícito e identidad del dueño."
        )


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
