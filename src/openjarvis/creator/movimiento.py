"""How the characters of a game move: NVIDIA's open motion models, on his PC.

The owner (2 Nov 2026): «para la creación de juegos los movimientos de los
personajes usarán MotionBricks, Audio2Face y movimiento a partir de texto
como Kimodo». Three engines, each for one job:

* **Kimodo** (nv-tlabs/kimodo; code Apache-2.0, SOMA/G1 checkpoints under
  the NVIDIA Open Model License, commercial use allowed) — a sentence
  («salta un muro y aterriza rodando») becomes a body animation. Sergio
  runs ``kimodo_gen`` and turns the result into a BVH and, with Blender, an
  FBX that Unreal imports. The SMPL-X checkpoint is research-only under its
  licence and is never used.
* **MotionBricks** (NVlabs/motionbricks; code Apache-2.0, models NVIDIA Open
  Model Agreement) — real-time locomotion (walk, run, strafe, crouch and
  styles) built from poses; Sergio installs it, exports its ONNX model for
  the SOMA body into the game, and opens its Scene Preview to try the moves.
* **Audio2Face-3D** (NVIDIA/Audio2Face-3D-SDK MIT, models NVIDIA Open Model;
  the Unreal plugin is MIT) — a voice line moves the face (blendshapes and
  lips). Sergio prepares the dialogue audio and, when the SDK's sample is
  built, the ``output_blendshape.csv`` per line; in Unreal the official ACE
  plugin plays them.

All three need an NVIDIA GPU (Kimodo about 17 GB of VRAM, or under 3 GB with
the text encoder on the CPU). Nothing is installed by default: «instala los
movimientos» runs ``scripts/instalar-movimiento.sh`` in the background, into
``~/.openjarvis/movimiento/``. With the engines missing, each call says
exactly what is missing, never pretends.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

KIMODO_MODEL = "Kimodo-SOMA-RP-v1.2"  # NVIDIA Open Model License (not the SMPL-X one)
FORBIDDEN_MODELS = ("SMPLX",)  # research-only licence
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "instalar-movimiento.sh"
_install: Dict[str, Any] = {}


class MovimientoError(RuntimeError):
    """What is missing, in plain words."""


def home() -> Path:
    from openjarvis.core.paths import get_config_dir

    return Path(
        os.environ.get("SERGIO_MOVIMIENTO_DIR") or Path(get_config_dir()) / "movimiento"
    )


def gpu() -> Dict[str, Any]:
    """The NVIDIA GPU on this PC (name and memory), if there is one."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {}
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=15).stdout  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return {}
    first = out.strip().splitlines()[0] if out.strip() else ""
    if "," not in first:
        return {}
    name, mem = first.rsplit(",", 1)
    try:
        return {"nombre": name.strip(), "vram_gb": round(int(mem.strip()) / 1024, 1)}
    except ValueError:
        return {"nombre": name.strip(), "vram_gb": 0.0}


def _repo(name: str) -> Path:
    return home() / name


def estado() -> Dict[str, Any]:
    """Which engines are installed and whether this PC can run them."""
    g = gpu()
    a2f = _repo("audio2face")
    return {
        "gpu": g,
        "kimodo": (_repo("kimodo") / "pyproject.toml").is_file(),
        "motionbricks": (_repo("motionbricks") / "pyproject.toml").is_file(),
        "audio2face": a2f.is_dir() and bool(_a2f_sample()),
        "blender": bool(shutil.which("blender")),
        "instalando": dict(_install),
    }


# -- installing (in the background) -------------------------------------------------------------


def instalar(on_done: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
    """Install the three engines in the background (one at a time)."""
    if _install.get("corriendo"):
        return "Ya estoy instalando los motores de movimiento."
    if not gpu():
        return (
            "Kimodo, MotionBricks y Audio2Face necesitan una tarjeta NVIDIA y aquí no la veo "
            "(nvidia-smi no responde). En un PC con NVIDIA y sus controladores, pídamelo otra vez."
        )
    if not SCRIPT.is_file():
        return "No encuentro scripts/instalar-movimiento.sh; actualice Sergio."

    def run() -> None:
        _install.update(corriendo=True, desde=time.time())
        log = home() / "instalacion.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w", encoding="utf-8") as f:
            code = subprocess.run(
                ["bash", str(SCRIPT), str(home())], stdout=f, stderr=subprocess.STDOUT
            ).returncode
        _install.clear()
        result = {**estado(), "codigo": code, "registro": str(log)}
        if on_done:
            on_done(result)

    threading.Thread(target=run, daemon=True, name="instalar-movimiento").start()
    return "Instalando Kimodo, MotionBricks y Audio2Face en segundo plano; son varios GB y tarda un rato."


# -- Kimodo: a sentence becomes a body animation -----------------------------------------------


def _kimodo_env(vram: float) -> Dict[str, str]:
    env = dict(os.environ)
    if vram < 17:
        env["TEXT_ENCODER_DEVICE"] = "cpu"  # under 3 GB on the GPU, slower
    return env


def texto_a_movimiento(
    prompt: str,
    seconds: float = 5.0,
    *,
    out_dir: Path,
    name: str = "",
    model: str = KIMODO_MODEL,
    samples: int = 1,
    seed: Optional[int] = None,
    runner: Optional[Callable[[List[str], Dict[str, str], Path], int]] = None,
) -> Dict[str, Any]:
    """A body animation for *prompt*: the NPZ Kimodo writes, plus BVH and FBX
    when they can be made here."""
    prompt = " ".join(str(prompt or "").split())[:300]
    if not prompt:
        raise MovimientoError(
            "Dígame qué movimiento quiere («salta y aterriza rodando»)."
        )
    if any(f in model.upper() for f in FORBIDDEN_MODELS):
        raise MovimientoError(
            "Ese modelo de Kimodo es solo para investigación; uso el de SOMA."
        )
    repo = _repo("kimodo")
    if runner is None and not (repo / "pyproject.toml").is_file():
        raise MovimientoError(
            "Kimodo no está instalado. Diga «instala los movimientos» (necesita NVIDIA)."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        re.sub(r"[^a-z0-9]+", "-", (name or prompt).lower()).strip("-")[:40]
        or "movimiento"
    )
    out = out_dir / stem
    args = ["uv", "run", "--project", str(repo), "kimodo_gen", prompt, "--model", model,
            "--duration", f"{max(1.0, min(float(seconds), 20.0)):.1f}", "--num_samples", str(max(1, samples)),
            "--output", str(out)]  # fmt: skip
    if seed is not None:
        args += ["--seed", str(seed)]
    env = _kimodo_env(float(gpu().get("vram_gb") or 0))
    code = (runner or _run)(args, env, repo)
    npz = sorted(out_dir.glob(f"{stem}*.npz"))
    if code != 0 or not npz:
        raise MovimientoError(
            f"Kimodo no generó el movimiento (código {code}); vea {home() / 'kimodo.log'}."
        )
    result: Dict[str, Any] = {
        "motor": "Kimodo",
        "modelo": model,
        "texto": prompt,
        "npz": [str(p) for p in npz],
    }
    bvh = _kimodo_bvh(npz[0], out_dir / f"{stem}.bvh", repo, runner)
    if bvh:
        result["bvh"] = str(bvh)
        fbx = bvh_a_fbx(bvh)
        if fbx:
            result["fbx"] = str(fbx)
    if "fbx" not in result:
        result["aviso"] = (
            "Quedó en el formato de Kimodo (NPZ). Para Unreal hace falta BVH y Blender para el FBX."
            if "bvh" not in result
            else "Quedó en BVH; con Blender instalado lo paso a FBX para Unreal."
        )
    return result


_BVH_PY = """
import sys
import numpy as np
from kimodo.exports import save_motion_bvh
data = dict(np.load(sys.argv[1], allow_pickle=False))
save_motion_bvh(data, sys.argv[2])
"""


def _kimodo_bvh(npz: Path, bvh: Path, repo: Path, runner: Any) -> Optional[Path]:
    """Kimodo's own BVH writer (SOMA skeleton, root «Root», ZYX)."""
    if runner is not None:
        return None
    try:
        done = subprocess.run(["uv", "run", "--project", str(repo), "python", "-c", _BVH_PY, str(npz), str(bvh)],
                              capture_output=True, text=True, timeout=600, cwd=repo)  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    return bvh if done.returncode == 0 and bvh.is_file() else None


_FBX_PY = """
import bpy, sys
args = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_anim.bvh(filepath=args[0], axis_forward="-Z", axis_up="Y", update_scene_duration=True)
bpy.ops.export_scene.fbx(filepath=args[1], use_selection=False, add_leaf_bones=False, bake_anim=True)
"""


def bvh_a_fbx(bvh: Path) -> Optional[Path]:
    """BVH to FBX with Blender (headless), the format Unreal imports."""
    exe = shutil.which("blender")
    if not exe:
        return None
    fbx = bvh.with_suffix(".fbx")
    try:
        done = subprocess.run([exe, "-b", "--python-expr", _FBX_PY, "--", str(bvh), str(fbx)],
                              capture_output=True, timeout=600)  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    return fbx if done.returncode == 0 and fbx.is_file() else None


def _run(args: List[str], env: Dict[str, str], cwd: Path) -> int:
    log = home() / "kimodo.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n$ {' '.join(args)}\n")
        f.flush()
        return subprocess.run(
            args, env=env, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, timeout=1800
        ).returncode


# -- MotionBricks: real-time locomotion ----------------------------------------------------------


def motionbricks_onnx(
    out_dir: Path, runner: Optional[Callable[[List[str], Path], int]] = None
) -> Dict[str, Any]:
    """The SOMA locomotion model as ONNX, for the game (the documented export)."""
    repo = _repo("motionbricks")
    if runner is None and not (repo / "pyproject.toml").is_file():
        raise MovimientoError(
            "MotionBricks no está instalado. Diga «instala los movimientos» (necesita NVIDIA)."
        )
    args = ["uv", "run", "--locked", "--project", "tools/onnx", "motionbricks-onnx", "--model", "soma",
            "--checkpoints", "checkpoints/MotionBricks/soma"]  # fmt: skip
    code = (
        runner(args, repo)
        if runner
        else subprocess.run(
            args, cwd=repo, capture_output=True, timeout=1800
        ).returncode
    )
    found = (
        sorted(repo.rglob("*soma*.onnx"))
        if runner is None
        else sorted(out_dir.glob("*.onnx"))
    )
    if code != 0 or not found:
        raise MovimientoError(
            "MotionBricks no exportó su modelo; revise que bajó los checkpoints (hf download)."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    copies = []
    for p in found[:2]:
        dest = out_dir / p.name
        if p.resolve() != dest.resolve():
            shutil.copy2(p, dest)
        copies.append(str(dest))
    return {
        "motor": "MotionBricks",
        "onnx": copies,
        "movimientos": ["caminar", "correr", "lateral", "agachado"],
    }


def motionbricks_vista() -> str:
    """Open MotionBricks' Scene Preview on this PC to try the moves."""
    repo = _repo("motionbricks")
    if not (repo / "pyproject.toml").is_file():
        raise MovimientoError("MotionBricks no está instalado.")
    subprocess.Popen(["uv", "run", "python", "-m", "app.scene_preview", "--scene", "assets/scenes/soma_gym.scene.json"],
                     cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    return "Abrí la vista previa de MotionBricks: muévase con el teclado para ver caminar, correr y agacharse."


# -- Audio2Face: a voice line moves the face -----------------------------------------------------


def _a2f_sample() -> Optional[Path]:
    root = _repo("audio2face")
    if not root.is_dir():
        return None
    for name in (
        "a2f-3d-authoring-sample-app",
        "audio2face_3d_microservices_interaction_app",
    ):
        hits = list(root.rglob(f"{name}*"))
        if hits:
            return hits[0]
    return None


def cara_desde_audio(
    audio: Path, out_dir: Path, runner: Optional[Callable[[Path, Path], int]] = None
) -> Dict[str, Any]:
    """Blendshapes (ARKit-style names, values and time codes) for one voice line."""
    if not Path(audio).is_file():
        raise MovimientoError(f"No encuentro el audio {Path(audio).name}.")
    out_dir.mkdir(parents=True, exist_ok=True)
    if runner is None:
        sample = _a2f_sample()
        if not sample:
            raise MovimientoError(
                "Audio2Face no está listo. Diga «instala los movimientos»; en Unreal, el plugin oficial "
                "de Audio2Face (MIT) mueve la cara con el mismo audio."
            )
        code = subprocess.run(["python", str(sample if sample.suffix == ".py" else sample / "main.py"), str(audio),
                               "--output", str(out_dir)], capture_output=True, timeout=900).returncode  # fmt: skip
    else:
        code = runner(Path(audio), out_dir)
    csv = sorted(out_dir.glob("*blendshape*.csv"))
    if code != 0 or not csv:
        raise MovimientoError("Audio2Face no devolvió las expresiones de la cara.")
    return {"motor": "Audio2Face-3D", "audio": str(audio), "blendshapes": str(csv[0])}


def manifest(anims: List[Dict[str, Any]]) -> str:
    """What the game's folder of animations holds, for its LEEME."""
    return json.dumps(anims, ensure_ascii=False, indent=1)


__all__ = [
    "KIMODO_MODEL",
    "MovimientoError",
    "bvh_a_fbx",
    "cara_desde_audio",
    "estado",
    "gpu",
    "instalar",
    "manifest",
    "motionbricks_onnx",
    "motionbricks_vista",
    "texto_a_movimiento",
]
