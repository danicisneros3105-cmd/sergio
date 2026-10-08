"""Blender add-ons from GitHub, installed and wired into Sergio.

* MeshGen (huggingface/meshgen): an AI agent inside Blender that builds and
  edits the scene from chat. Sergio sets it up to think with Gemini (the
  user's key, through LiteLLM), so it needs no other account.
* Tripo 3D (VAST-AI-Research/tripo-3d-for-blender): text or image -> a
  textured 3D model in Tripo's cloud (needs a Tripo key, ``tsk_...``).
  Sergio also calls Tripo directly from the server for "hazlo con Tripo".
* SculptMate (shravan-d/SculptMate): image -> organic, textured mesh on the
  user's own PC (TripoSR / Stable Fast 3D; it installs PyTorch and its
  checkpoint from its preferences the first time).
* Image to Mesh (iamameme/blender-2d-to-3d-plugin): a PNG silhouette or
  logo -> a clean extruded / rounded technical mesh, headless.

Everything installs into the user's Blender in the background (no window):
``install_all()``; ``image_to_mesh()`` and ``sculptmate()`` run them on an
image and return the generated model file.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from sergio_escritorio.media import HOME, find_blender, run_blender_background

ADDONS: dict[str, dict[str, Any]] = {
    "meshgen": {
        "repo": "huggingface/meshgen",
        "kind": "extension",  # Blender 4.2+ extension
        "asset": r"meshgen-{gpu}-win64\.zip",
        "fallback": "https://github.com/huggingface/meshgen/releases/latest/download/meshgen-{gpu}-win64.zip",
        "module": "meshgen",
        "min_blender": (4, 2),
        "what": "agente de IA dentro de Blender (con Gemini)",
    },
    "tripo": {
        "repo": "VAST-AI-Research/tripo-3d-for-blender",
        "kind": "addon",
        "asset": r"tripo-3d-for-blender-v[\d.]+\.zip",
        "fallback": "",
        "module": "tripo-3d-for-blender",
        "min_blender": (3, 0),
        "what": "texto o imagen a 3D con textura (nube de Tripo, clave tsk_)",
    },
    "sculptmate": {
        "repo": "shravan-d/SculptMate",
        "kind": "addon",
        "asset": r"SculptMate\.zip",
        "fallback": "https://github.com/shravan-d/SculptMate/releases/download/v0.5/SculptMate.zip",
        "module": "SculptMate",
        "min_blender": (3, 6),
        "what": "imagen a 3D orgánico y texturizado, en su PC (TripoSR / Stable Fast 3D)",
    },
    "img2mesh": {
        "repo": "iamameme/blender-2d-to-3d-plugin",
        "kind": "script",
        "asset": "",
        "fallback": "https://raw.githubusercontent.com/iamameme/blender-2d-to-3d-plugin/main/ImageToMeshPlugin.py",
        "module": "ImageToMeshPlugin",
        "min_blender": (3, 6),
        "what": "imagen (PNG, logo, silueta) a 3D técnico extruido",
    },
}
FOLDER = HOME / "addons"


def release_url(name: str, gpu: bool = False, get: Callable[[str], Any] | None = None) -> str:
    """The download link of the add-on's latest release (GitHub API), or the
    known link when the API cannot be asked."""
    spec = ADDONS[name]
    if spec["kind"] == "script":
        return spec["fallback"]
    pattern = spec["asset"].replace("{gpu}", "cuda" if gpu else "cpu")
    try:
        if get is None:
            import httpx

            resp = httpx.get(f"https://api.github.com/repos/{spec['repo']}/releases/latest", timeout=20,
                             headers={"Accept": "application/vnd.github+json"})
            data = resp.json() if resp.status_code == 200 else {}
        else:
            data = get(spec["repo"])
        for asset in data.get("assets", []):
            if re.fullmatch(pattern, asset.get("name", "")):
                return asset["browser_download_url"]
    except Exception:  # noqa: BLE001 — offline API: the known link
        pass
    if spec["fallback"]:
        return spec["fallback"].replace("{gpu}", "cuda" if gpu else "cpu")
    raise RuntimeError(f"No encontré la última versión de {name} en GitHub.")


def download(url: str, folder: Path | None = None) -> Path:
    import httpx

    folder = folder or FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / url.rsplit("/", 1)[-1]
    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as resp, path.open("wb") as fh:
        resp.raise_for_status()
        for chunk in resp.iter_bytes(1 << 20):
            fh.write(chunk)
    return path


def install_script(path: str, name: str) -> str:
    """The bpy script that installs and enables one add-on and saves the
    preferences (Blender in the background)."""
    spec = ADDONS[name]
    return f'''
import bpy, addon_utils
path = {path!r}
kind = {spec["kind"]!r}
module = {spec["module"]!r}
try:
    if kind == "extension" and hasattr(bpy.ops.extensions, "package_install_files"):
        bpy.ops.extensions.package_install_files(filepath=path, repo="user_default", enable_on_install=True)
        enabled = [m for m in bpy.context.preferences.addons.keys() if m.endswith(module)]
    else:
        bpy.ops.preferences.addon_install(filepath=path, overwrite=True)
        found = [m.__name__ for m in addon_utils.modules() if m.__name__.lower().replace("_", "-") == module.lower()
                 or m.__name__ == module]
        for m in found or [module]:
            bpy.ops.preferences.addon_enable(module=m)
        enabled = [m for m in bpy.context.preferences.addons.keys() if m in (found or [module])]
    bpy.ops.wm.save_userpref()
    print("SERGIO_ADDON_OK", module, enabled)
except Exception as exc:
    print("SERGIO_ADDON_FAIL", module, type(exc).__name__, exc)
'''


# Blender's own numpy stays exactly as Blender ships it (bpy needs it; a
# newer one breaks Blender's modules), so pip picks the versions of OpenCV
# and scikit-image that work with it.
IMG2MESH_DEPS = """import sys, subprocess
import numpy
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "Pillow", "scikit-image",
                           "opencv-python-headless", "numpy==" + numpy.__version__])
    print("SERGIO_DEPS_OK numpy", numpy.__version__)
except Exception as exc:
    print("SERGIO_DEPS_FAIL", exc)
"""


def meshgen_config_script(gemini_key: str, model: str = "gemini/gemini-2.5-flash") -> str:
    """MeshGen thinking with Gemini: its "OpenAI" provider goes through
    LiteLLM, which routes the "gemini/" model to Google with this key."""
    return f'''
import bpy
mods = [m for m in bpy.context.preferences.addons.keys() if m.endswith("meshgen")]
if not mods:
    print("SERGIO_ADDON_FAIL meshgen not enabled")
else:
    prefs = bpy.context.preferences.addons[mods[0]].preferences
    for key, value in (("backend_type", "REMOTE"), ("llm_provider", "openai"),
                       ("openai_model_id", {model!r}), ("openai_api_key", {gemini_key!r})):
        try:
            setattr(prefs, key, value)
        except Exception as exc:
            print("SERGIO_MESHGEN_PREF", key, exc)
    bpy.ops.wm.save_userpref()
    print("SERGIO_MESHGEN_OK", {model!r})
'''


def blender_version_tuple(version: str) -> tuple[int, int]:
    found = re.match(r"(\d+)\.(\d+)", version or "")
    return (int(found.group(1)), int(found.group(2))) if found else (0, 0)


def install(name: str, version: str, gpu: bool = False, run: Callable[[str], str] | None = None) -> str:
    """Download and install one add-on; returns a line for the user."""
    spec = ADDONS[name]
    if version and blender_version_tuple(version) < spec["min_blender"]:
        need = ".".join(map(str, spec["min_blender"]))
        return f"{name}: necesita Blender {need} o más nuevo (tiene {version})."
    path = download(release_url(name, gpu))
    if spec["kind"] == "script":
        # Its libraries go into Blender's Python in their own run: installed
        # in the middle of a job they swap numpy under Blender's feet.
        log = (run or run_blender_background)(IMG2MESH_DEPS)
        ok = "SERGIO_DEPS_OK" in log
        return f"{name}: listo ({spec['what']})" + ("." if ok else "; sus librerías se instalan en el primer uso.")
    log = (run or run_blender_background)(install_script(str(path), name))
    if "SERGIO_ADDON_OK" in log:
        return f"{name}: instalado y activado ({spec['what']})."
    fail = next((ln for ln in log.splitlines() if "SERGIO_ADDON_FAIL" in ln), log[-160:])
    return f"{name}: no se pudo instalar ({fail[:160]})."


def install_all(version: str, gemini_key: str = "", gpu: bool = False,
                run: Callable[[str], str] | None = None) -> list[str]:
    """Every add-on; MeshGen set up with Gemini when the key is given."""
    lines = []
    for name in ADDONS:
        try:
            lines.append(install(name, version, gpu, run))
        except Exception as exc:  # noqa: BLE001 — one failing add-on does not stop the rest
            lines.append(f"{name}: falló la descarga ({str(exc)[:120]}).")
    if gemini_key and any(ln.startswith("meshgen: instalado") for ln in lines):
        log = (run or run_blender_background)(meshgen_config_script(gemini_key))
        lines.append("MeshGen conectado a Gemini." if "SERGIO_MESHGEN_OK" in log else "MeshGen: configúrelo en Preferencias.")
    return lines


# -- running them on an image -------------------------------------------------------------
def transparent_png(image: bytes) -> bytes:
    """The image with its background (the colour around the edges) made
    transparent: Image-to-Mesh needs a PNG with alpha."""
    import io

    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(image)).convert("RGBA")
    arr = np.array(img)
    if arr[:, :, 3].min() < 250:
        return image  # already has transparency
    rgb = arr[:, :, :3].astype(int)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    dist = np.abs(rgb - bg).sum(axis=2)
    arr[:, :, 3] = np.where(dist > 60, 255, 0).astype(np.uint8)
    out = io.BytesIO()
    Image.fromarray(arr).save(out, "PNG")
    return out.getvalue()


def image_to_mesh(image: bytes, extrude: float = 0.1, rounded: bool = False, enclosed: bool = True) -> Path:
    """Image-to-Mesh, headless: the image's shape as a technical 3D mesh
    (GLB). Returns the file."""
    script = FOLDER / "ImageToMeshPlugin.py"
    if not script.exists():
        download(ADDONS["img2mesh"]["fallback"])
    work = FOLDER / "trabajos"
    work.mkdir(parents=True, exist_ok=True)
    src = work / f"imagen-{os.getpid()}.png"
    png = transparent_png(image)
    src.write_bytes(png)
    import io

    from PIL import Image

    w, h = Image.open(io.BytesIO(png)).size
    cmd = [find_blender(), "-b", "--python", str(script), "--", "--image", str(src), "--extrude", str(extrude),
           "--filetype", "gltf", "--minlength", str(round(0.3 * (w + h))),  # small details too, not only big shapes
           *(["--rounded"] if rounded else []), *(["--enclosed"] if enclosed else [])]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for out in (src.with_suffix(".gltf"), src.with_suffix(".glb")):
        if out.exists():
            return out
    raise RuntimeError("Image-to-Mesh no generó el modelo: " + (done.stdout + done.stderr)[-300:])


SCULPTMATE_SCRIPT = r'''
import bpy, time, addon_utils
addon_utils.enable("SculptMate", default_set=True)
wm = bpy.context.window_manager
scn = bpy.context.scene
wm.input_image_path = __IMAGE__
try:
    scn.my_props.model_type = __MODEL__
except Exception as exc:
    print("SERGIO_SCULPTMATE_NOTE", exc)
before = set(bpy.data.objects.keys())
bpy.ops.tool.generate()
deadline = time.time() + 1200
while time.time() < deadline and not wm.buttons_enabled:
    time.sleep(1)
new = [o for o in bpy.data.objects if o.name not in before and o.type == "MESH"]
if not new:
    print("SERGIO_SCULPTMATE_FAIL", wm.message)
else:
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=__OUT__, export_format="GLB", use_selection=True)
    print("SERGIO_SCULPTMATE_OK", len(new))
'''


def sculptmate(image: bytes, model: str = "lean") -> Path:
    """SculptMate on the user's PC: an organic, textured mesh from an image.
    *model*: "lean" (TripoSR, works on the processor) or "fast" (Stable Fast
    3D, needs an NVIDIA card)."""
    work = FOLDER / "trabajos"
    work.mkdir(parents=True, exist_ok=True)
    src = work / f"organico-{os.getpid()}.png"
    src.write_bytes(image)
    out = src.with_suffix(".glb")
    script = (SCULPTMATE_SCRIPT.replace("__IMAGE__", json.dumps(str(src))).replace("__MODEL__", json.dumps(model))
              .replace("__OUT__", json.dumps(str(out))))
    log = run_blender_background(script, timeout=1500)
    if "SERGIO_SCULPTMATE_OK" not in log or not out.exists():
        hint = "Abra Blender > Preferencias > SculptMate e instale las dependencias y el checkpoint la primera vez."
        raise RuntimeError(f"SculptMate no generó el modelo. {hint} ({log[-160:]})")
    return out


IMPORT_SCRIPT = r'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=__PATH__)
roots = [o for o in bpy.context.scene.objects if o.parent is None]
SERGIO_LAYOUT = []
'''


def import_glb_script(path: Path) -> str:
    """A model script that brings a generated GLB into Sergio's pipeline
    (then lights, camera, checks, render and save as usual)."""
    return IMPORT_SCRIPT.replace("__PATH__", json.dumps(str(path)))


__all__ = ["ADDONS", "image_to_mesh", "import_glb_script", "install_all", "release_url", "sculptmate",
           "transparent_png"]
