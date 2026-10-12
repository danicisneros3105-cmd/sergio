"""Anatomy figures in Sergio: build the examples, create new ones.

The *anatomy* kit (MIT, vendored in ``creator/anatomy``) writes an
isometric technical figure as a standalone HTML page from a Node build
script. Sergio copies the kit to the owner's data folder once, builds there,
and serves the pages to Creator.

New figures: Gemini writes a ``build.mjs`` with the kit, Node builds it, and
when Node fails Sergio feeds the error back and tries again (3 times at most).
A figure is only reported as made when Node wrote its page.

Safety for a script written by a model: it is checked before it runs (no
child processes, network, environment, dynamic code or paths outside the
kit), and Node runs it with its permission model, able to read the kit and
write only its own folder, with a time limit.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

from openjarvis.creator.llm import CreatorError

KIT_ROOT = Path(__file__).parent / "anatomy"

EXAMPLES: dict[str, tuple[str, str]] = {
    "dial-indicator": (
        "Indicador de cuadrante",
        "Un comparador sobre su soporte: la aguja se mueve según el bloque que toca.",
    ),
    "desk-computer": (
        "Ordenador de escritorio",
        "Un ordenador con teclado: lo que escribe aparece en la pantalla CRT.",
    ),
    "arcade-cabinet": (
        "Máquina recreativa",
        "El panel lateral abierto: la moneda baja, cierra un contacto y la pantalla arranca.",
    ),
    "ripple-tank": (
        "Cubeta de ondas",
        "Ondas, luz y cáusticas con dos capas WebGL, desde un modelo físico real.",
    ),
    "turning-dial": (
        "Cuadrante 3D",
        "Modo 3D: una cerradura de combinación que una mano robótica hace girar.",
    ),
    "raptor-engine": (
        "Motor cohete",
        "Un motor en su banco de pruebas que se despieza (la primera vez tarda ~2 min).",
    ),
}

BUILD_TIMEOUT = {"raptor-engine": 420.0}
DEFAULT_TIMEOUT = 180.0
CREATE_TIMEOUT = 120.0
MAX_ATTEMPTS = 3
MAX_SCRIPT = 120_000

# What a figure script must never do (it only draws).
FORBIDDEN = (
    (r"child_process|worker_threads|node:cluster|\bcluster\b", "procesos"),
    (
        r"\bfetch\s*\(|node:https?|['\"]https?['\"]|node:net|node:dgram|WebSocket|node:tls",
        "red",
    ),
    (r"process\.env|process\.exit\s*\(\s*[^)0-9]", "entorno"),
    (r"\beval\s*\(|new\s+Function\s*\(|node:vm|\bvm\.", "código dinámico"),
    (r"require\s*\(", "require"),
    (
        r"(readFileSync|writeFileSync|readdirSync|rmSync|unlinkSync)\s*\(\s*['\"]/",
        "rutas absolutas",
    ),
    (r"\.\./\.\./\.\.", "rutas fuera del kit"),
)


def node_binary() -> str:
    """Node.js (22.6+ for the permission model), from PATH or Sergio's toolchain."""
    found = shutil.which("node")
    if found:
        return found
    toolchain = sorted(
        (Path.home() / ".local" / "share" / "sergio-toolchain").glob("node-*/bin/node"),
        reverse=True,
    )
    if toolchain:
        return str(toolchain[0])
    raise CreatorError(
        "Anatomía necesita Node.js 22: ejecute la actualización de Sergio, que lo instala."
    )


def workspace(root: Path | None = None) -> Path:
    """The owner's copy of the kit, refreshed when Sergio's kit changes."""
    if root is None:
        from openjarvis.core.config import get_config_dir

        root = Path(get_config_dir()) / "creator" / "anatomy"
    root.mkdir(parents=True, exist_ok=True)
    stamp = (
        (KIT_ROOT / "UPSTREAM").read_text().strip()
        if (KIT_ROOT / "UPSTREAM").exists()
        else "?"
    )
    marker = root / ".kit-version"
    if not marker.exists() or marker.read_text().strip() != stamp:
        for part in ("kit", "scripts", "references"):
            shutil.copytree(KIT_ROOT / part, root / part, dirs_exist_ok=True)
        for example in EXAMPLES:
            shutil.copytree(
                KIT_ROOT / "examples" / example,
                root / "examples" / example,
                dirs_exist_ok=True,
            )
        marker.write_text(stamp)
    (root / "figures").mkdir(exist_ok=True)
    return root


def _run(
    node: str, script: Path, root: Path, out_dir: Path, args: list[str], timeout: float
) -> Any:
    from openjarvis.security.process_runner import run_bounded

    return run_bounded(
        [
            node,
            "--permission",
            f"--allow-fs-read={root}",
            f"--allow-fs-write={out_dir}",
            str(script),
            *args,
        ],
        timeout=timeout,
        cwd=str(out_dir),
        env={"PATH": str(Path(node).parent), "NODE_OPTIONS": ""},
        max_output_bytes=60_000,
    )


def examples(root: Path | None = None) -> list[dict[str, Any]]:
    ws = workspace(root)
    out = []
    for name, (title, text) in EXAMPLES.items():
        page = ws / "examples" / name / f"{name}.html"
        out.append(
            {
                "name": name,
                "title": title,
                "description": text,
                "built": page.exists(),
                "kind": "ejemplo",
            }
        )
    for folder in sorted((ws / "figures").iterdir(), key=lambda p: -p.stat().st_mtime):
        meta = folder / "figure.json"
        if folder.is_dir() and meta.exists() and (folder / "figure.html").exists():
            info = json.loads(meta.read_text())
            out.append(
                {
                    "name": folder.name,
                    "title": info.get("title") or folder.name,
                    "description": info.get("request", ""),
                    "built": True,
                    "kind": "suya",
                }
            )
    return out


def page_path(name: str, light: bool = False, root: Path | None = None) -> Path | None:
    """The built page of an example or a created figure (None if not built)."""
    ws = workspace(root)
    if name in EXAMPLES:
        page = ws / "examples" / name / f"{name}{'-light' if light else ''}.html"
    elif re.fullmatch(r"[a-z0-9-]{1,60}", name or ""):
        page = ws / "figures" / name / "figure.html"
    else:
        return None
    return page if page.exists() else None


def build_example(name: str, light: bool = False, root: Path | None = None) -> Path:
    if name not in EXAMPLES:
        raise CreatorError(f"No conozco la lámina «{name}».")
    ws = workspace(root)
    folder = ws / "examples" / name
    script = folder / "build.mjs"
    page = folder / f"{name}{'-light' if light else ''}.html"
    recipe = _sha256(script)
    stamp = page.with_suffix(".sha256")
    if page.exists() and stamp.exists() and stamp.read_text().strip() == recipe:
        return page
    if (
        page.exists()
        and not stamp.exists()
        and page.stat().st_mtime >= script.stat().st_mtime
    ):
        return page  # built before stamps existed
    # A heavy example ships already built from this exact recipe: no wait.
    shipped = KIT_ROOT / "prebuilt" / page.name
    if shipped.exists() and _prebuilt_stamps().get(name) == recipe:
        shutil.copyfile(shipped, page)
        stamp.write_text(recipe)
        return page
    done = _run(
        node_binary(),
        script,
        ws,
        folder,
        ["--light"] if light else [],
        BUILD_TIMEOUT.get(name, DEFAULT_TIMEOUT),
    )
    if done.timed_out:
        raise CreatorError("La lámina tardó demasiado en construirse.")
    if done.returncode != 0 or not page.exists():
        raise CreatorError(
            "Node no pudo construir la lámina: " + (done.stderr or done.stdout)[-600:]
        )
    stamp.write_text(recipe)
    return page


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prebuilt_stamps() -> dict[str, str]:
    try:
        return json.loads((KIT_ROOT / "prebuilt" / "STAMPS.json").read_text())
    except (OSError, ValueError):
        return {}


# -- new figures ------------------------------------------------------------------


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    out = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:40]
    return out or f"lamina-{int(time.time())}"


def check_script(code: str) -> str:
    """The script, if it only draws with the kit (CreatorError otherwise)."""
    if not code or len(code) > MAX_SCRIPT:
        raise CreatorError("El guion de la lámina está vacío o es demasiado largo.")
    if "../../kit/iso-kit.mjs" not in code:
        raise CreatorError("El guion debe importar el kit (../../kit/iso-kit.mjs).")
    for pattern, what in FORBIDDEN:
        if re.search(pattern, code):
            raise CreatorError(
                f"El guion intentó algo que una lámina no necesita ({what})."
            )
    return code


def extract_script(text: str) -> str:
    """The JavaScript inside a model answer (fenced or plain)."""
    fenced = re.findall(r"```(?:js|javascript|mjs)?\s*\n(.*?)```", text, re.S)
    code = max(fenced, key=len) if fenced else text
    return code.strip()


PROMPT = """You write build scripts for the *anatomy* kit: crafted isometric \
SVG figures that explain a technical idea as a REAL physical machine (never \
boxes with arrows). The object is the explanation.

Write ONE complete Node ES module, `build.mjs`, for this request:
«{request}»

Rules:
- Import exactly like the template: `import * as k from "../../kit/iso-kit.mjs";` \
and `import {{ kitScript }} from "../../scripts/inline-kit.mjs";` (also \
`../../kit/lathe.mjs` / `../../kit/tube.mjs` if you need round parts or pipes).
- Write the page with `writeFileSync(join(HERE, "figure.html"), k.pageHtml(...))` \
exactly as the template writes its page, but the file name MUST be figure.html.
- A Figure: one mechanism, 40-80 small precise parts (base on feet, rails or \
posts, the mechanism, knobs, screws as dots, a label plate), tone hierarchy \
lo/mid/hi with ONE lit part, every line ending on something, painter's order \
back to front.
- Frame it in the card: "Fig 1" top left, a short Spanish title top right, a \
Spanish interaction hint bottom left and a live readout bottom right. Captions \
in Spanish. Calm time-based motion (an idle tour) like the template.
- No network, no child processes, no environment variables, no eval, no \
require, no absolute paths. Only draw.
- Answer with the JavaScript only, in one ```js block.

The template (a dial indicator, a complete working figure) follows; keep its \
structure and API usage, change the machine:

```js
{template}
```

Kit exports available as k.*: {exports}
"""


def _kit_exports(ws: Path) -> str:
    text = (ws / "kit" / "iso-kit.mjs").read_text()
    names = re.findall(r"^export (?:function|const|class) ([A-Za-z_]\w*)", text, re.M)
    return ", ".join(names)


def create(
    request: str,
    *,
    root: Path | None = None,
    ask: Callable[..., str] | None = None,
    attempts: int = MAX_ATTEMPTS,
) -> dict[str, Any]:
    """A new figure from words. Returns {name, title, attempts, log}."""
    request = " ".join((request or "").split())[:600]
    if len(request) < 4:
        raise CreatorError("Describa qué quiere explicar con la lámina.")
    if ask is None:
        from openjarvis.creator.llm import ask as ask_gemini

        ask = ask_gemini
    ws = workspace(root)
    name = slug(request)
    folder = ws / "figures" / name
    folder.mkdir(parents=True, exist_ok=True)
    template = (ws / "examples" / "dial-indicator" / "build.mjs").read_text()
    prompt = PROMPT.format(request=request, template=template, exports=_kit_exports(ws))
    node = node_binary()
    log: list[str] = []
    feedback = ""
    for attempt in range(1, attempts + 1):
        text = ask(
            prompt + feedback,
            effort="medium",
            max_tokens=24000,
            check=lambda t: check_script(extract_script(t)),
        )
        code = check_script(extract_script(text))
        script = folder / "build.mjs"
        script.write_text(code)
        page = folder / "figure.html"
        page.unlink(missing_ok=True)
        done = _run(node, script, ws, folder, [], CREATE_TIMEOUT)
        if done.returncode == 0 and page.exists() and page.stat().st_size > 2000:
            (folder / "figure.json").write_text(
                json.dumps(
                    {"request": request, "title": request[:60], "attempts": attempt}
                )
            )
            return {
                "name": name,
                "title": request[:60],
                "attempts": attempt,
                "log": log,
            }
        error = ("tiempo agotado" if done.timed_out else (done.stderr or done.stdout))[
            -1500:
        ]
        log.append(f"Intento {attempt}: {error[-300:]}")
        feedback = (
            "\n\nYour previous script failed when Node ran it. Fix it and answer "
            f"with the whole corrected script.\nError:\n{error}\n\nPrevious script:\n```js\n{code[:30000]}\n```"
        )
    raise CreatorError(
        "No logré construir la lámina tras varios intentos. " + " ".join(log)[-500:]
    )


__all__ = [
    "EXAMPLES",
    "build_example",
    "check_script",
    "create",
    "examples",
    "extract_script",
    "node_binary",
    "page_path",
    "slug",
    "workspace",
]
