"""Creator's studio helpers: design layouts, images, plans and code.

* ``design_layout``: a Canva-style layout (texts, shapes, colours) for a
  canvas size, written by Gemini and checked field by field.
* ``cutout``: removes the background of a photo on this computer with a
  segmentation network (``segment.py``; GrabCut when it cannot be
  downloaded), no cloud needed.
* ``generate_image`` / ``edit_image``: Firefly-style generation and
  generative edits with Gemini's image model; a refused quota is reported as
  it is, never replaced by something else in silence.
* ``plan_dxf``: walls, doors and windows drawn in Creator's floor plan as a
  DXF drawing (ezdxf), with dimensions, ready for any CAD program.
* Code: a project folder per owner, files listed / read / saved inside it
  only, an AI edit that returns the whole new file (shown as a diff before
  saving), and a bounded run of Python or Node files.
"""

from __future__ import annotations

import io
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Callable

from openjarvis.creator.llm import CreatorError

# -- design --------------------------------------------------------------------

DESIGN_PROMPT = """You are a senior graphic designer (Canva / Figma level). \
Design «{request}» for a canvas of {width}x{height} px. Bold, modern, \
readable for everyday people; strong hierarchy; 2-3 brand colours with good \
contrast; generous margins (at least 6% of the width).
Answer ONLY JSON:
{{"background": "#hex", "elements": [
  {{"type": "rect", "x": 0, "y": 0, "w": 100, "h": 100, "fill": "#hex", "radius": 0}},
  {{"type": "circle", "x": 0, "y": 0, "r": 50, "fill": "#hex"}},
  {{"type": "text", "x": 0, "y": 0, "w": 400, "text": "Spanish text", "size": 48, \
"weight": 800, "color": "#hex", "align": "left"}}
]}}
Coordinates are the top-left corner in pixels inside the canvas. 4-14 \
elements, texts in Spanish, no images.
Layout rules (they are checked): a text block is about lines x size x 1.25 \
px tall (estimate the lines from its width: ~0.55 x size px per character); \
a text placed on a shape sits fully inside it with padding; nothing leaves \
the canvas; use the whole height (no empty third), clear visual order from \
top to bottom."""

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _hex(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", text):
        text = "#" + "".join(c * 2 for c in text[1:])
    return text if HEX.match(text) else default


def check_layout(text: str, width: int, height: int) -> dict[str, Any]:
    """Gemini's layout, cleaned: known element types, inside the canvas."""
    found = re.search(r"\{.*\}", text or "", re.S)
    data = json.loads(found.group(0)) if found else {}
    if not isinstance(data, dict):
        raise ValueError("no es un objeto")
    out: list[dict[str, Any]] = []

    def num(v: Any, lo: float, hi: float, default: float) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return default
        return min(max(x, lo), hi) if math.isfinite(x) else default

    for raw in data.get("elements") or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("type") or "")
        base = {
            "type": kind,
            "x": num(raw.get("x"), -width, width * 2, 0),
            "y": num(raw.get("y"), -height, height * 2, 0),
        }
        if kind == "rect":
            base.update(
                w=num(raw.get("w"), 1, width * 2, 100),
                h=num(raw.get("h"), 1, height * 2, 100),
                fill=_hex(raw.get("fill"), "#4f7cff"),
                radius=num(raw.get("radius"), 0, 400, 0),
            )
        elif kind == "circle":
            base.update(
                r=num(raw.get("r"), 1, max(width, height), 50),
                fill=_hex(raw.get("fill"), "#8b5cf6"),
            )
        elif kind == "text":
            words = " ".join(str(raw.get("text") or "").split())[:400]
            if not words:
                continue
            base.update(
                text=words,
                w=num(raw.get("w"), 40, width, width * 0.8),
                size=num(raw.get("size"), 10, 400, 40),
                weight=int(num(raw.get("weight"), 300, 900, 700)),
                color=_hex(raw.get("color"), "#0f1222"),
                align=raw.get("align")
                if raw.get("align") in ("left", "center", "right")
                else "left",
            )
        else:
            continue
        out.append(base)
        if len(out) >= 24:
            break
    if not any(e["type"] == "text" for e in out):
        raise ValueError("el diseño no tiene textos")
    return {"background": _hex(data.get("background"), "#ffffff"), "elements": out}


def design_layout(
    request: str, width: int, height: int, *, ask: Callable[..., str] | None = None
) -> dict[str, Any]:
    width = int(min(max(width, 64), 8000))
    height = int(min(max(height, 64), 8000))
    request = " ".join((request or "").split())[:500]
    if len(request) < 3:
        raise CreatorError("Describa qué quiere diseñar.")
    if ask is None:
        from openjarvis.creator.llm import ask as ask_gemini

        ask = ask_gemini
    text = ask(
        DESIGN_PROMPT.format(request=request, width=width, height=height),
        json_mode=True,
        check=lambda t: check_layout(t, width, height),
    )
    return check_layout(text, width, height)


# -- images ------------------------------------------------------------------------

MAX_IMAGE = 15 * 1024 * 1024


def _decode(data: bytes) -> Any:
    import cv2
    import numpy as np

    if not data or len(data) > MAX_IMAGE:
        raise CreatorError("La imagen está vacía o pasa de 15 MB.")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise CreatorError("No es una imagen que pueda leer.")
    return image


def cutout(data: bytes, box: tuple[float, float, float, float] | None = None) -> bytes:
    """The subject with a transparent background (PNG), computed here."""
    return cutout_detail(data, box)[0]


def cutout_detail(
    data: bytes,
    box: tuple[float, float, float, float] | None = None,
    neural: bool = True,
) -> tuple[bytes, str]:
    """(PNG, method). The segmentation network first ("red"); without it
    (no download possible) GrabCut ("grabcut"), which is cruder.

    *box* (x, y, w, h as fractions) marks the subject; by default the whole
    picture for the network and the centre 90 % for GrabCut.
    """
    import cv2
    import numpy as np

    image = _decode(data)
    h, w = image.shape[:2]
    alpha = None
    method = "grabcut"
    if neural:
        try:
            from openjarvis.creator import segment

            alpha = (segment.alpha(image) * 255).astype(np.uint8)
            method = "red"
        except Exception:  # noqa: BLE001 — offline or no onnxruntime: GrabCut
            alpha = None
    if alpha is None:
        alpha = _grabcut_alpha(image, box)
    if box is not None:  # outside the marked box is background
        fx, fy, fw, fh = box
        keep = np.zeros((h, w), np.uint8)
        keep[
            int(max(0, fy) * h) : int(min(1, fy + fh) * h),
            int(max(0, fx) * w) : int(min(1, fx + fw) * w),
        ] = 1
        alpha = alpha * keep
    if alpha.mean() < 2:
        raise CreatorError(
            "No distinguí el sujeto del fondo: pruebe con más contraste."
        )
    rgba = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = alpha
    ok, png = cv2.imencode(".png", rgba)
    if not ok:
        raise CreatorError("No pude guardar el recorte.")
    return png.tobytes(), method


def _grabcut_alpha(image: Any, box: tuple[float, float, float, float] | None) -> Any:
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    scale = min(1.0, 900.0 / max(h, w))
    small = cv2.resize(image, (int(w * scale), int(h * scale))) if scale < 1 else image
    sh, sw = small.shape[:2]
    fx, fy, fw, fh = box or (0.05, 0.05, 0.9, 0.9)
    rect = (
        int(max(0, fx) * sw),
        int(max(0, fy) * sh),
        max(2, int(min(1, fw) * sw) - 1),
        max(2, int(min(1, fh) * sh) - 1),
    )
    mask = np.zeros((sh, sw), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(small, mask, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(
        np.uint8
    )
    alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
    if scale < 1:
        alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
    return alpha


IMAGE_MODELS = (
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "gemini-2.5-flash-image",
)


def _image_call(parts: list[Any], client: Any = None) -> bytes:
    from google.genai import types

    from openjarvis.creator.llm import gemini_key
    from openjarvis.engine.google_client import SwitchingClient

    client = client or SwitchingClient(gemini_key())
    errors = []
    for model in IMAGE_MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=parts,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            for cand in resp.candidates or []:
                for part in cand.content.parts or []:
                    blob = getattr(part, "inline_data", None)
                    if blob is not None and blob.data:
                        return bytes(blob.data)
            errors.append(f"{model}: sin imagen")
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {str(exc)[:120]}")
    if all(
        "429" in e or "RESOURCE_EXHAUSTED" in e or "quota" in e.lower() for e in errors
    ):
        raise CreatorError(
            "Su clave de Gemini no tiene cuota para generar imágenes ahora. "
            "Active la facturación en Google AI Studio o inténtelo más tarde."
        )
    raise CreatorError("No pude generar la imagen: " + " | ".join(errors))


def generate_image(prompt: str, client: Any = None) -> bytes:
    prompt = " ".join((prompt or "").split())[:1500]
    if len(prompt) < 3:
        raise CreatorError("Describa la imagen.")
    return _image_call([prompt], client)


def edit_image(data: bytes, instruction: str, client: Any = None) -> bytes:
    from google.genai import types

    _decode(data)
    instruction = " ".join((instruction or "").split())[:1500]
    if len(instruction) < 3:
        raise CreatorError("Diga qué cambiar en la imagen.")
    mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    return _image_call(
        [types.Part.from_bytes(data=data, mime_type=mime), instruction], client
    )


# -- plans (DXF) -------------------------------------------------------------------


def plan_dxf(
    walls: list[dict[str, Any]], openings: list[dict[str, Any]] | None = None
) -> bytes:
    """A floor plan as DXF (metres): walls as closed outlines, openings, dimensions."""
    import ezdxf

    if not walls:
        raise CreatorError("El plano no tiene muros.")
    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.M
    for name, color in (("MUROS", 7), ("HUECOS", 4), ("COTAS", 1)):
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    for wall in walls[:500]:
        try:
            x1, y1, x2, y2 = (float(wall[k]) for k in ("x1", "y1", "x2", "y2"))
            t = min(max(float(wall.get("thickness", 0.2)), 0.02), 2.0)
        except (KeyError, TypeError, ValueError):
            continue
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 0.01:
            continue
        nx, ny = -(y2 - y1) / length * t / 2, (x2 - x1) / length * t / 2
        msp.add_lwpolyline(
            [
                (x1 + nx, y1 + ny),
                (x2 + nx, y2 + ny),
                (x2 - nx, y2 - ny),
                (x1 - nx, y1 - ny),
            ],
            close=True,
            dxfattribs={"layer": "MUROS"},
        )
        dim = msp.add_aligned_dim(
            p1=(x1 + nx * 3, y1 + ny * 3),
            p2=(x2 + nx * 3, y2 + ny * 3),
            distance=0.4,
            dxfattribs={"layer": "COTAS"},
        )
        dim.render()
    for opening in (openings or [])[:500]:
        try:
            x, y = float(opening["x"]), float(opening["y"])
            width = min(max(float(opening.get("width", 0.9)), 0.3), 6.0)
            angle = math.radians(float(opening.get("angle", 0.0)))
        except (KeyError, TypeError, ValueError):
            continue
        dx, dy = math.cos(angle) * width / 2, math.sin(angle) * width / 2
        msp.add_line((x - dx, y - dy), (x + dx, y + dy), dxfattribs={"layer": "HUECOS"})
        if opening.get("kind") == "puerta":  # the door's swing
            msp.add_arc(
                (x - dx, y - dy),
                width,
                math.degrees(angle),
                math.degrees(angle) + 90,
                dxfattribs={"layer": "HUECOS"},
            )
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode()


# -- code ----------------------------------------------------------------------------

CODE_EXT = {
    ".py",
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".sh",
}
MAX_FILE = 400_000


def projects_root(root: Path | None = None) -> Path:
    if root is None:
        from openjarvis.core.config import get_config_dir

        root = Path(get_config_dir()) / "creator" / "proyectos"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _inside(root: Path, rel: str) -> Path:
    rel = (rel or "").replace("\\", "/").lstrip("/")
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()) or ".." in Path(rel).parts:
        raise CreatorError("Esa ruta está fuera de sus proyectos.")
    return path


def list_files(root: Path | None = None) -> list[dict[str, Any]]:
    base = projects_root(root)
    if not any(base.iterdir()):
        (base / "hola").mkdir(exist_ok=True)
        (base / "hola" / "hola.py").write_text(
            '"""Su primer programa en Creator: pulse Ejecutar."""\n\n'
            'nombre = "señor"\nprint(f"Hola, {nombre}. Creator funciona.")\n'
        )
    out = []
    for path in sorted(base.rglob("*")):
        if (
            path.is_file()
            and path.suffix.lower() in CODE_EXT
            and ".git" not in path.parts
        ):
            out.append(
                {"path": path.relative_to(base).as_posix(), "size": path.stat().st_size}
            )
        if len(out) >= 2000:
            break
    return out


def read_file(rel: str, root: Path | None = None) -> str:
    path = _inside(projects_root(root), rel)
    if not path.is_file():
        raise CreatorError("Ese archivo no existe.")
    if path.stat().st_size > MAX_FILE:
        raise CreatorError("El archivo es demasiado grande para el editor.")
    return path.read_text(errors="replace")


def save_file(rel: str, content: str, root: Path | None = None) -> dict[str, Any]:
    base = projects_root(root)
    path = _inside(base, rel)
    if path.suffix.lower() not in CODE_EXT:
        raise CreatorError("Creator guarda archivos de código y texto.")
    if len(content.encode()) > MAX_FILE:
        raise CreatorError("El archivo es demasiado grande.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.replace(path)
    return {
        "path": path.relative_to(base).as_posix(),
        "size": path.stat().st_size,
        "saved_at": time.time(),
    }


CODE_PROMPT = """You are an expert software engineer editing one file in the \
owner's project (like Cursor). File `{path}`:
```
{content}
```
Instruction (Spanish): «{instruction}»
Return the WHOLE new file and nothing else, in one fenced code block. Keep \
everything that the instruction does not ask to change. Do not invent APIs."""


def ai_edit(
    path: str, content: str, instruction: str, *, ask: Callable[..., str] | None = None
) -> str:
    instruction = " ".join((instruction or "").split())[:2000]
    if len(instruction) < 3:
        raise CreatorError("Diga qué quiere cambiar.")
    if len(content) > MAX_FILE:
        raise CreatorError("El archivo es demasiado grande.")
    if ask is None:
        from openjarvis.creator.llm import ask as ask_gemini

        ask = ask_gemini

    def code_of(text: str) -> str:
        blocks = re.findall(r"```[\w.+-]*\n(.*?)```", text, re.S)
        if not blocks:
            raise ValueError("sin bloque de código")
        return max(blocks, key=len)

    text = ask(
        CODE_PROMPT.format(path=path, content=content, instruction=instruction),
        effort="medium",
        max_tokens=32000,
        check=code_of,
    )
    return code_of(text)


def run_file(
    rel: str, root: Path | None = None, timeout: float = 20.0
) -> dict[str, Any]:
    """Run a Python or Node file of the project (bounded time and output)."""
    import sys

    from openjarvis.security.process_runner import run_bounded

    base = projects_root(root)
    path = _inside(base, rel)
    if not path.is_file():
        raise CreatorError("Ese archivo no existe.")
    if path.suffix == ".py":
        command = [sys.executable, "-I", str(path)]
    elif path.suffix in (".js", ".mjs"):
        from openjarvis.creator.anatomy_build import node_binary

        node = node_binary()
        command = [
            node,
            "--permission",
            f"--allow-fs-read={path.parent}",
            f"--allow-fs-write={path.parent}",
            str(path),
        ]
    else:
        raise CreatorError("Creator ejecuta archivos .py, .js o .mjs.")
    started = time.perf_counter()
    done = run_bounded(
        command,
        timeout=timeout,
        cwd=str(path.parent),
        env={
            "PATH": str(Path(command[0]).parent) + ":/usr/bin:/bin",
            "PYTHONIOENCODING": "utf-8",
            "HOME": str(base),
        },
        max_output_bytes=60_000,
        max_memory_bytes=512 * 1024 * 1024,
    )
    return {
        "stdout": done.stdout,
        "stderr": done.stderr,
        "code": done.returncode,
        "timed_out": done.timed_out,
        "ms": round((time.perf_counter() - started) * 1000),
    }


__all__ = [
    "ai_edit",
    "check_layout",
    "cutout",
    "cutout_detail",
    "design_layout",
    "edit_image",
    "generate_image",
    "list_files",
    "plan_dxf",
    "projects_root",
    "read_file",
    "run_file",
    "save_file",
]
