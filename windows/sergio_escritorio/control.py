"""Local control server: lets Sergio (in WSL) see and use the Windows desktop.

Only listens on 127.0.0.1 and every request needs the shared token. The user
can cut it off at any time with Ctrl+Alt+End (``Controller.enabled``) or by
slamming the mouse into the top-left corner (pyautogui fail-safe).

Protocol (JSON):
  GET  /health -> {"ok": true, "enabled": bool}
  GET  /screen -> {"image_png_b64", "width", "height", "scale", "frame"}
  GET  /screen?format=jpeg -> the same with "image_jpeg_b64" (4–8× faster)
  GET  /screen.jpg         -> the live frame as a JPEG (no JSON, no base64)
  GET  /screen/stream      -> MJPEG: the screen live, a part per change
  GET  /screen/wait?after=<frame>&timeout=<s> -> the next changed frame
  GET  /ui     -> {"window", "windows", "elements": [{"id","name","type","x","y"}]}
  POST /act    -> {"ok": bool, "result": str}

Coordinates are real screen pixels; ``x``/``y`` of an element are its centre.
"""

from __future__ import annotations

import base64
import hmac
import io
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Protocol

MAX_SHOT_WIDTH = 1280
MAX_TEXT = 4000
ACTIONS = (
    "system",
    "click",
    "click_name",
    "double_click",
    "right_click",
    "move",
    "type",
    "key",
    "scroll",
    "open_app",
    "open",
    "focus",
    "split",
    "wait",
    "make_video",
    "blender",
    "organize",
    "undo_organize",
    "python",
    "close_app",
    "terminal",
    "point",
    "guide",
    "hands",
    "operate",
    "message",
    "phone_call",
    "contact",
)
MEDIA_KEYS = {
    "volumeup",
    "volumedown",
    "volumemute",
    "playpause",
    "nexttrack",
    "prevtrack",
}
TASKS = ("operate", "message", "phone_call", "contact")  # done by the operator
# Ordinary moves of a task: they never ask (see RISKY below).
ROUTINE = (
    "click",
    "click_name",
    "double_click",
    "right_click",
    "type",
    "key",
    "focus",
    "split",
    "open_app",
)
APPROVAL_WINDOW_S = 600.0
# Owner (29 Oct 2026): «Sergio pide demasiados permisos para hacer cualquier
# cosa y se vuelve tedioso». Ordinary moves (click, type, keys, open an app,
# a web page or a document) run at once, as when he does them himself. Only
# what cannot be taken back or reaches other people asks, and then Sergio's
# own Visage confirms by itself through the camera (no button, no PIN).
RISKY = ("python", "terminal", "close_app", "message", "phone_call", "contact")
RISKY_KEYS = ("shift+delete", "shift+del", "ctrl+shift+delete", "alt+f4")
RUNS_CODE = (".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jar", ".scr",
             ".com", ".lnk", ".reg", ".sh", ".app", ".pkg", ".dmg")  # fmt: skip
# Skills that record or learn someone (consent first); the rest just run.
RISKY_SKILLS = ("face_scan", "voice_enroll", "meeting_start")


def risky(action: dict) -> bool:
    """Does this action need the owner's Visage before it runs?"""
    kind = str(action.get("action") or "")
    if kind in RISKY:
        return True
    if kind == "organize":
        return bool(action.get("apply"))  # a preview never asks
    if kind == "key":
        keys = str(action.get("keys") or action.get("key") or "").lower().replace(" ", "")
        return any(k in keys for k in RISKY_KEYS)
    if kind == "open":
        target = str(action.get("target") or action.get("path") or "").lower().strip()
        return not target.startswith(("http://", "https://")) and target.endswith(RUNS_CODE)
    if kind == "skill":
        name = str(action.get("name") or "")
        if name == "creator_apps":
            return str((action.get("args") or {}).get("action") or "") in ("install", "instalar")
        return name in RISKY_SKILLS
    return False


_SPLIT_SEP = re.compile(r"\s*(?:\||,|;|/|\by\b|\band\b|\bcon\b|\bjunto a\b)\s*", re.I)


def split_targets(target: str) -> tuple[str, str]:
    """«Chrome | Word», «chrome y word» → ('Chrome', 'Word'); one name → (name, '')
    (that window takes the left half and the one behind it the right)."""
    parts = [p.strip() for p in _SPLIT_SEP.split(target or "") if p and p.strip()]
    if not parts:
        return "", ""
    return parts[0], (parts[1] if len(parts) > 1 else "")


def halves(area: tuple[int, int, int, int]) -> tuple[tuple[int, int, int, int], ...]:
    """The left and right halves (x, y, w, h) of a screen's work area."""
    left, top, right, bottom = area
    width = (right - left) // 2
    return (left, top, width, bottom - top), (left + width, top, right - left - width, bottom - top)


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

    def side_by_side(self, left: str, right: str) -> list[str]: ...  # titles placed

    def make_video(self, options: dict) -> str: ...  # path of the new video

    def blender(self, script: str) -> str: ...  # path of the saved script

    def organize(self, folder: str, by: str, apply: bool) -> dict: ...

    def undo_organize(self) -> int: ...  # files put back

    def python(self, code: str, timeout: float) -> dict: ...

    def close_app(self, name: str) -> list[str]: ...  # titles closed

    def shell(self, command: str, timeout: float) -> dict: ...


CLICKABLE = {"Button", "Hyperlink", "MenuItem", "TabItem", "ListItem", "CheckBox",
             "RadioButton", "SplitButton", "TreeItem", "ComboBox"}  # fmt: skip


def _plain(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def best_element(query: str, elements: list[dict]) -> dict | None:
    """The on-screen element the user named ("suscribirse", "enviar"):
    exact name first, then the start of it, whole words, then a close spelling."""
    import difflib

    want = _plain(query)
    if not want:
        return None
    words = set(want.split())
    best, best_score = None, 0.0
    for el in elements:
        name = _plain(el.get("name", ""))
        if not name:
            continue
        if name == want:
            score = 100.0
        elif name.startswith(want + " ") or (
            len(name) >= 3 and want.startswith(name + " ")
        ):
            score = 80.0
        elif f" {want} " in f" {name} ":
            score = 70.0
        elif words <= set(name.split()):
            score = 60.0
        else:
            ratio = difflib.SequenceMatcher(None, want, name[: len(want) + 6]).ratio()
            score = 55.0 * ratio if ratio >= 0.82 else 0.0
        if not score:
            continue
        score += 5.0 if el.get("type") in CLICKABLE else 0.0
        score -= min(len(name), 80) / 100  # the shorter, the more exact
        if score > best_score:
            best, best_score = el, score
    return best


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

    live: Any = None  # the live eye (set in __init__)
    _ui_cache: tuple[int, dict] | None = None

    def __init__(
        self,
        backend: Backend,
        *,
        on_activity: Callable[[str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        camera: Callable[[], bytes] | None = None,
        diag: Callable[[], dict] | None = None,
        approve: Callable[[str], bool] | None = None,
        strict_permissions: bool = True,
        live: Any = None,
    ) -> None:
        self.backend = backend
        # The live eye (live_screen.LiveScreen): every look is the frame it
        # already has, and actions are checked the moment the screen changes.
        self.live = live
        self._ui_cache: tuple[int, dict] | None = None
        self.camera = camera  # returns a JPEG of the webcam, or None
        self.diag = diag or (lambda: {})  # what the ear is doing (revisar)
        # The companion flies to a spot to show the user something.
        self.on_point: Callable[[int, int, str], None] = lambda _x, _y, _l: None
        # Arrows, circles and a ghost cursor drawn over the screen (guia.py):
        # (marks as dicts in screen pixels, caption).
        self.on_guide: Callable[[list[dict], str], None] = lambda _m, _c: None
        # The companion goes to the spot and presses it, like a hand (before
        # every click, so the user always sees who clicks where).
        self.on_click: Callable[[int, int, str], None] = lambda _x, _y, _k: None
        # Hands for the holograms in Sergio ve ("holo" / "off"); returns a status.
        self.on_hands: Callable[[str], str] = lambda _mode: "hands unavailable"
        # `sergio probar`: talk to Sergio like the user does ("call"/"turn").
        self.selftest: Callable[[str], dict] | None = None
        # Longer abilities Sergio's server asks for by name (a face scan,
        # learning a voice, a meeting): name -> run(args) -> text.
        self.skills: dict[str, Callable[[dict], str]] = {}
        # Tasks done like a person (operate, message, phone_call, contact).
        self.on_task: Callable[[str, dict], str] = lambda _k, _a: "operator unavailable"
        self.enabled = True
        self._approved_kinds: dict[str, float] = {}
        self.approve = approve
        self.strict_permissions = strict_permissions
        self._elements: dict[int, tuple[int, int]] = {}
        self._sizes: dict[int, tuple[int, int]] = {}  # element id -> (w, h)
        self._lock = threading.Lock()
        self._on_activity = on_activity or (lambda _msg: None)
        self._sleep = sleep

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if not value:
            self._approved_kinds = {}  # pausing takes the permission back
        self._enabled = bool(value)

    # -- reading -----------------------------------------------------------
    def camera_shot(self) -> dict:
        if self.camera is None:
            raise ActionError("No camera available.")
        jpeg = self.camera()
        return {"image_jpeg_b64": base64.b64encode(jpeg).decode("ascii")}

    def screen(self, fmt: str = "png") -> dict:
        if self.live is not None:
            frame = self.live.latest()
            width, height = frame.size
            scale = width / MAX_SHOT_WIDTH if width > MAX_SHOT_WIDTH else 1.0
            jpeg = fmt == "jpeg"
            data = frame.encode("JPEG" if jpeg else "PNG", MAX_SHOT_WIDTH)
            left, top = frame.origin
            return {
                ("image_jpeg_b64" if jpeg else "image_png_b64"): base64.b64encode(
                    data
                ).decode("ascii"),
                "width": width,
                "height": height,
                "scale": scale,
                "left": left,
                "top": top,
                "frame": frame.id,
                "changed": frame.changed,
            }
        image = self.backend.screenshot()
        width, height = image.size
        scale = 1.0
        if width > MAX_SHOT_WIDTH:
            scale = width / MAX_SHOT_WIDTH
            image = image.resize((MAX_SHOT_WIDTH, round(height / scale)))
        buf = io.BytesIO()
        # Fast PNG: "optimize" cost ~0.5 s per look for a few KB less.
        if fmt == "jpeg":
            image.convert("RGB").save(buf, format="JPEG", quality=78)
        else:
            image.convert("RGB").save(buf, format="PNG", compress_level=1)
        left, top = getattr(self.backend, "shot_origin", (0, 0))
        return {
            ("image_jpeg_b64" if fmt == "jpeg" else "image_png_b64"): base64.b64encode(
                buf.getvalue()
            ).decode("ascii"),
            "width": width,
            "height": height,
            "scale": scale,
            "left": left,
            "top": top,
        }

    def ui(self) -> dict:
        # The accessibility tree only changes when the screen does: while the
        # live frame is the same, the last reading is still the truth.
        frame_id = self.live.latest().id if self.live is not None else 0
        cached = self._ui_cache
        if frame_id and cached and cached[0] == frame_id:
            with self._lock:
                self._elements = cached[1]["_mapping"]
                self._sizes = cached[1]["_sizes"]
            return {
                k: v for k, v in cached[1].items() if k not in ("_mapping", "_sizes")
            }
        info = self.backend.ui()
        elements = []
        mapping: dict[int, tuple[int, int]] = {}
        sizes: dict[int, tuple[int, int]] = {}
        for number, el in enumerate(info.get("elements", []), start=1):
            left, top, right, bottom = el["rect"]
            centre = ((left + right) // 2, (top + bottom) // 2)
            mapping[number] = centre
            sizes[number] = (max(0, right - left), max(0, bottom - top))
            elements.append(
                {
                    "id": number,
                    "name": str(el.get("name") or "")[:80],
                    "type": el.get("type", ""),
                    "x": centre[0],
                    "y": centre[1],
                    "w": sizes[number][0],
                    "h": sizes[number][1],
                }
            )
        with self._lock:
            self._elements = mapping
            self._sizes = sizes
        out = {
            "window": info.get("window", ""),
            "windows": info.get("windows", []),
            "elements": elements,
        }
        if frame_id:
            self._ui_cache = (frame_id, {**out, "_mapping": mapping, "_sizes": sizes})
        return out

    def warm_ui(self, frame: Any = None) -> None:
        """Read the accessibility tree in the background after a change, so
        the next screen_read answers at once."""
        try:
            self.ui()
        except Exception:  # noqa: BLE001 — accessibility is a bonus
            pass

    def snapshot(self, fmt: str = "png") -> tuple[bytes, list[dict], float]:
        """Screenshot + elements in screenshot pixels + scale to screen.

        Used by the companion's screen help: the vision model sees the same
        picture the element coordinates refer to.
        """
        shot = self.screen(fmt)
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
                item = {**el, "x": round(x), "y": round(y)}
                if el.get("w"):
                    item["w"], item["h"] = round(el["w"] / scale), round(el["h"] / scale)
                in_shot.append(item)
        data = shot.get("image_jpeg_b64") or shot["image_png_b64"]
        return base64.b64decode(data), in_shot, scale

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

    def _marks(self, wanted: Any) -> list[dict]:
        """Each mark at its element (id from screen_read, or a visible name)
        or at x,y, with the element's size so a circle fits around it."""
        from sergio_escritorio.guia import MAX_MARKS, SHAPES

        if not isinstance(wanted, list) or not wanted:
            raise ActionError(
                "'marks' is a list: [{element | target | x,y, shape, text}]."
            )
        marks: list[dict] = []
        for item in wanted[:MAX_MARKS]:
            if not isinstance(item, dict):
                continue
            w = h = 0
            if item.get("element") not in (None, ""):
                x, y = self._point(item)
                with self._lock:
                    w, h = self._sizes.get(int(item["element"]), (0, 0))
            elif str(item.get("target") or "").strip() and item.get("x") is None:
                query = str(item["target"]).strip()
                finder = getattr(self.backend, "find_elements", None)
                found = best_element(
                    query, finder(query) if finder else self.ui()["elements"]
                )
                if found is None:
                    raise ActionError(f"No veo «{query}» en la ventana de enfrente.")
                x, y = int(found["x"]), int(found["y"])
                w, h = int(found.get("w") or 0), int(found.get("h") or 0)
            else:
                x, y = self._point(item)
            shape = str(item.get("shape") or "arrow")
            marks.append(
                {
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "shape": shape if shape in SHAPES else "arrow",
                    "text": str(item.get("text") or item.get("target") or "")[:48],
                    "depth": item.get("depth", True),
                }
            )
        if not marks:
            raise ActionError("No mark could be placed.")
        return marks

    def _confirm(self, action: dict) -> None:
        prompt = json.dumps(action, ensure_ascii=False, sort_keys=True)
        try:
            approved = self.approve is not None and self.approve(prompt) is True
        except Exception as exc:
            raise PermissionError("No se pudo solicitar autorización.") from exc
        if not approved or not self.enabled:
            raise PermissionError("Acción no autorizada o control en pausa.")

    def act(self, action: dict) -> str:
        action = dict(action)
        if not self.enabled:
            raise PermissionError(
                "Screen control is paused by the user (Ctrl+Alt+End to resume)."
            )
        kind = str(action.get("action") or "")
        if kind not in ACTIONS:
            raise ActionError(
                f"Unknown action {kind!r}. Use one of: {', '.join(ACTIONS)}"
            )
        # Only what cannot be undone or reaches other people asks (risky);
        # a sensitive action approved a moment ago does not ask again for
        # the same kind of thing while the task goes on.
        strict_confirmed = self.strict_permissions and risky(action)
        recent = getattr(self, "_approved_kinds", {})
        if strict_confirmed and kind in ("close_app", "organize") and time.monotonic() < recent.get(kind, 0.0):
            strict_confirmed = False
        if strict_confirmed:
            self._confirm(action)
            self._approved_kinds = {**recent, kind: time.monotonic() + APPROVAL_WINDOW_S}
        b = self.backend
        before = self._front() if kind in self.SETTLE else ""
        if kind in ("click", "double_click", "right_click", "move"):
            x, y = self._point(action)
            if kind == "move":
                b.move(x, y)
            else:
                button = "right" if kind == "right_click" else "left"
                self.on_click(x, y, kind)
                b.click(x, y, button, 2 if kind == "double_click" else 1)
            result = f"{kind} at ({x}, {y})"
        elif kind == "click_name":
            query = str(action.get("target") or "").strip()
            if not query:
                raise ActionError("'target' is the name of the button or link.")
            finder = getattr(b, "find_elements", None)
            elements = finder(query) if finder else self.ui()["elements"]
            found = best_element(query, elements)
            if found is None:
                raise ActionError(f"No veo «{query}» en la ventana de enfrente.")
            how = str(action.get("button") or "left")
            self.on_click(int(found["x"]), int(found["y"]), "click")
            b.click(
                int(found["x"]),
                int(found["y"]),
                "right" if how == "right" else "left",
                2 if how == "double" else 1,
            )
            result = (
                f"clicked {found.get('name', query)!r} at ({found['x']}, {found['y']})"
            )
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
        elif kind == "split":
            left, right = split_targets(str(action.get("target") or ""))
            if not left:
                raise ActionError(
                    "'target' is the two windows, e.g. 'Chrome | Word' "
                    "(open them first with open_app)."
                )
            placed = b.side_by_side(left, right)
            if not placed:
                raise ActionError(f"No open window matches {left!r}.")
            result = "split screen: " + " | ".join(placed)
        elif kind == "system":
            # the device from a fixed list (volume, brightness, windows,
            # clipboard, lock…): no free command, so no Visage (sistema.py)
            from sergio_escritorio import sistema

            def press(keys: str, times: int) -> None:
                for _ in range(min(max(times, 1), 60)):
                    b.hotkey(keys.split("+"))

            try:
                result = sistema.run(
                    str(action.get("target") or action.get("op") or ""),
                    action.get("value", action.get("text")),
                    b,
                    press,
                )
            except sistema.SistemaError as exc:
                raise ActionError(str(exc)) from exc
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
            if self.strict_permissions and not strict_confirmed:
                self._confirm(action)
            if action.get("hands"):  # shape it with your hands first: holograms
                self.on_hands("holo")
            result = "Blender opened with script " + b.blender(script)
        elif kind == "organize":
            folder = str(action.get("target") or "").strip()
            if not folder:
                raise ActionError("'target' is the folder to organise.")
            by = "month" if action.get("by") == "month" else "type"
            if action.get("apply") and self.strict_permissions and not strict_confirmed:
                self._confirm(action)
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
            if self.strict_permissions and not strict_confirmed:
                self._confirm(action)
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
        elif kind == "guide":
            marks = self._marks(action.get("marks"))
            steps = bool(action.get("steps")) and len(marks) > 1
            if steps:  # one at a time: each click shows the next
                marks = [{**m, "step": True} for m in marks]
            self.on_guide(marks, str(action.get("text") or "")[:90])
            shapes = ", ".join(m["shape"] for m in marks)
            result = (
                f"guide of {len(marks)} steps on the screen ({shapes}); each click shows the next"
                if steps
                else f"drew {len(marks)} marks on the screen ({shapes}); they vanish on the next click"
            )
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
            if self.strict_permissions and not strict_confirmed:
                self._confirm(action)
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
        self._remember_undo(kind, action, result)
        if kind == "key" and set(result.split()[1].split("+")) <= MEDIA_KEYS:
            return result  # the window in front does not change
        if kind == "system":
            return result
        return result + self._verify(kind, before)

    def _remember_undo(self, kind: str, action: dict, result: str) -> None:
        """What can be taken back goes to the journal (deshacer.py)."""
        from sergio_escritorio.deshacer import journal

        b = self.backend
        target = str(action.get("target") or "").strip()
        if kind == "open_app" and target:
            journal().add(f"Abrí {target}", lambda: b.close_app(target), f"Cerré {target}.")
        elif kind == "type":
            journal().add(
                "Escribí un texto", lambda: b.hotkey(["ctrl", "z"]), "Borré lo que escribí."
            )
        elif kind == "organize" and action.get("apply") and result.startswith("moved"):
            journal().add(
                "Ordené una carpeta",
                b.undo_organize,
                "Devolví los archivos a donde estaban.",
            )

    VERIFY = {
        "click",
        "click_name",
        "double_click",
        "right_click",
        "key",
        "type",
        "open_app",
        "open",
        "close_app",
        "focus",
        "split",
    }

    # How long a new window may take to come to the front (watched, not slept).
    SETTLE = {"open_app": 1.5, "open": 1.5, "close_app": 0.8, "focus": 0.3, "split": 0.3}

    def _verify(self, kind: str, before: str = "") -> str:
        """What is in front after the action, so Sergio can check it worked.
        No fixed wait: it looks every 30 ms and answers as soon as the
        window in front changes (or right away for clicks and keys)."""
        active = getattr(self.backend, "active_window", None)
        if kind not in self.VERIFY:
            return ""
        if self.live is not None:
            return self._verify_live(kind, before, active)
        if active is None:
            return ""
        try:
            limit = time.monotonic() + self.SETTLE.get(kind, 0.03)
            title = active()
            while title == before and time.monotonic() < limit:
                self._sleep(0.03)
                title = active()
        except Exception:  # noqa: BLE001 — a check must never break the action
            return ""
        return f" | now in front: {(title or '(escritorio)')[:80]}"

    def _verify_live(self, kind: str, before: str, active: Any) -> str:
        """With the live eye: answer the moment the screen shows the result
        (and has settled), not after a guess of how long it takes."""
        try:
            start = self.live.latest().id
            changed = self.live.wait_change(start, self.SETTLE.get(kind, 0.35))
            if changed is not None:
                self.live.wait_settled(quiet=0.08, timeout=0.6)
            title = active() if active is not None else ""
        except Exception:  # noqa: BLE001 — a check must never break the action
            return ""
        seen = (
            " | the screen changed"
            if changed is not None
            else " | the screen did not change"
        )
        front = (
            f" | now in front: {(title or '(escritorio)')[:80]}"
            if active is not None
            else ""
        )
        return front + seen

    def _front(self) -> str:
        active = getattr(self.backend, "active_window", None)
        try:
            return active() if active is not None else ""
        except Exception:  # noqa: BLE001
            return ""


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
            from urllib.parse import parse_qs, urlsplit

            parts = urlsplit(self.path)
            query = {k: v[-1] for k, v in parse_qs(parts.query).items()}
            path = parts.path
            try:
                if path == "/health":
                    self._send(200, {"ok": True, "enabled": controller.enabled})
                elif path == "/screen":
                    self._send(200, controller.screen(query.get("format", "png")))
                elif path == "/screen.jpg":
                    frame = controller.live.latest() if controller.live else None
                    data = (
                        frame.encode("JPEG", int(query.get("width", MAX_SHOT_WIDTH)))
                        if frame
                        else base64.b64decode(
                            controller.screen("jpeg")["image_jpeg_b64"]
                        )
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                elif path == "/screen/wait" and controller.live is not None:
                    after = int(query.get("after", "0") or 0)
                    timeout = min(max(float(query.get("timeout", "2") or 2), 0.0), 10.0)
                    frame = controller.live.wait_change(after, timeout)
                    if frame is None:
                        self._send(200, {"ok": True, "changed": False})
                    else:
                        self._send(
                            200,
                            {
                                "ok": True,
                                "changed": True,
                                "frame": frame.id,
                                "box": frame.changed,
                            },
                        )
                elif path == "/screen/stream" and controller.live is not None:
                    self.send_response(200)
                    self.send_header(
                        "Content-Type", "multipart/x-mixed-replace; boundary=frame"
                    )
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    fps = min(max(float(query.get("fps", "8") or 8), 1.0), 15.0)
                    try:
                        for part in controller.live.stream(fps=fps):
                            self.wfile.write(part)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                elif path == "/ui":
                    self._send(200, controller.ui())
                elif path == "/camera":
                    self._send(200, controller.camera_shot())
                elif path == "/diag":
                    self._send(200, {"ok": True, **controller.diag()})
                elif path == "/film":
                    # What the operator is doing, in pictures (pelicula.py).
                    film = getattr(controller, "film", None)
                    since = int(query.get("since", "0") or 0)
                    self._send(200, film.to_dict(since) if film else {"ok": True, "task": 0, "frames": []})
                else:
                    self._send(404, {"ok": False, "error": "not found"})
            except Exception as exc:  # noqa: BLE001
                self._send(500, {"ok": False, "error": str(exc)})

        def _read_json(self, limit: int) -> dict:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError as exc:
                raise ActionError("Invalid Content-Length") from exc
            if length < 0 or length > limit:
                raise ActionError("Request body is too large")
            self.connection.settimeout(15)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ActionError("Send a JSON object")
            return body

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorised():
                return
            if self.path == "/selftest":
                try:
                    body = self._read_json(4_000)
                    test = controller.selftest
                    if test is None:
                        self._send(404, {"ok": False, "error": "no self-test"})
                    else:
                        self._send(200, test(str(body.get("kind") or "")))
                except Exception as exc:  # noqa: BLE001
                    self._send(500, {"ok": False, "error": str(exc)})
                return
            if self.path == "/skill":
                try:
                    body = self._read_json(16_000)
                    skill = controller.skills.get(str(body.get("name") or ""))
                    if skill is None:
                        self._send(404, {"ok": False, "error": "unknown skill"})
                    else:
                        args = (
                            body.get("args")
                            if isinstance(body.get("args"), dict)
                            else {}
                        )
                        if controller.strict_permissions and risky(
                            {"action": "skill", "name": body.get("name"), "args": args}
                        ):
                            controller._confirm(
                                {
                                    "action": "skill",
                                    "name": body.get("name"),
                                    "args": args,
                                }
                            )
                        self._send(200, {"ok": True, "result": skill(args)})
                except PermissionError as exc:
                    self._send(423, {"ok": False, "error": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    self._send(500, {"ok": False, "error": str(exc)})
                return
            if self.path != "/act":
                self._send(404, {"ok": False, "error": "not found"})
                return
            try:
                action = self._read_json(128_000)
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


__all__ = [
    "ACTIONS",
    "ActionError",
    "Backend",
    "Controller",
    "ShotScale",
    "make_server",
]
