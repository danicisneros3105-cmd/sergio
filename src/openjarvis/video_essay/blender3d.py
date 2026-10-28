"""3D shots made in Blender (like the owner's first reference: a cinematic
short where every shot is a 3D render).

The director describes the shot; the model writes the scene as a Blender
script with Sergio's modelling kit (real shapes, not cubes), its own lights
and an animated camera (keyframes over the shot's frames). Before running,
the script goes through the same safety check as every Blender script Sergio
makes (only modelling: no files, network or system). Sergio then adds the
render settings himself (size, frame rate, EEVEE, where the frames go) and
Blender renders the frames, which ffmpeg joins into the shot's clip.

Blender is found as for the rest of Creator (``SERGIO_BLENDER``, the PATH or
the usual install folders, also the Windows install from Ubuntu on WSL).
Without Blender the shot falls back to AI video or a picture.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

SCENE_PROMPT = """You are a senior 3D artist and cinematographer making ONE shot of a \
cinematic short film in Blender (Python, bpy). Shot ({seconds:.1f} s, {frames} frames at \
{fps} fps): {visual}
Look of the film: {look}
{characters}
{kit}
Rules: start with bpy.ops.wm.read_factory_settings(use_empty=True); build the set and \
the subjects with the kit (real shapes, materials, believable scale in metres); add \
your own lights (key, fill, rim) and a world colour; create ONE camera named "Camera", \
set it as scene.camera and ANIMATE it with keyframes from frame 1 to frame {frames} \
(dolly, orbit, push-in or crane, as the shot asks); animate the subjects too if the \
shot has action. Clean explainer shots: kit_studio() for the light and backdrop and \
kit_camera_push(...) for the slow push-in; when the narration goes INSIDE something \
(the body, an engine, a device), show it with kit_cutaway (cross-section) or kit_xray \
on the outer shell with solid, labelled-looking inner parts; slow motion = fewer \
changes per frame at the key moment. No file paths, no rendering, no saving: Sergio \
renders it.
Answer ONLY the Python script."""

RENDER_SUFFIX = """
# --- Sergio: render settings (added after the safety check) ---
import bpy as _bpy
_s = _bpy.context.scene
if _s.camera is None:
    _cams = [o for o in _s.objects if o.type == "CAMERA"]
    if _cams:
        _s.camera = _cams[0]
    else:
        _c = _bpy.data.objects.new("Camera", _bpy.data.cameras.new("Camera"))
        _s.collection.objects.link(_c)
        _c.location = (6, -6, 3.5)
        _c.rotation_euler = (1.15, 0, 0.785)
        _s.camera = _c
for _engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
    try:
        _s.render.engine = _engine
        break
    except Exception:
        pass
_s.render.resolution_x, _s.render.resolution_y = {w}, {h}
_s.render.resolution_percentage = 100
_s.render.fps = {fps}
_s.frame_start, _s.frame_end = 1, {frames}
try:
    _s.render.image_settings.media_type = "IMAGE"
except Exception:
    pass
_s.render.image_settings.file_format = "PNG"
_s.render.filepath = {out}
_bpy.ops.render.render(animation=True)
print("SERGIO_RENDERED", {frames})
"""


def blender_cmd() -> Optional[List[str]]:
    """How to run Blender here (also the Windows one from WSL)."""
    from openjarvis.vfx._base import find_blender

    cmd = find_blender()
    if cmd:
        return cmd
    for root in sorted(
        Path("/mnt/c/Program Files/Blender Foundation").glob("Blender*"), reverse=True
    ):
        exe = root / "blender.exe"
        if exe.exists():
            return [
                str(exe),
                "-b",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
            ]
    return None


def _host_path(path: Path, cmd: List[str]) -> str:
    """A path the Blender in *cmd* understands (Windows paths for blender.exe)."""
    if cmd[0].lower().endswith(".exe") and shutil.which("wslpath"):
        return subprocess.run(
            ["wslpath", "-w", str(path)], capture_output=True, text=True
        ).stdout.strip()
    return str(path)


def script_for(
    visual: str,
    seconds: float,
    look: str,
    characters: str,
    ask: Callable[[str], str],
    fps: int = 30,
) -> str:
    from openjarvis.tools.blender_kit import KIT_DOC
    from openjarvis.tools.blender_model import check_script

    frames = max(12, round(seconds * fps))
    text = ask(
        SCENE_PROMPT.format(
            seconds=seconds,
            frames=frames,
            fps=fps,
            visual=visual,
            look=look[:400],
            characters=characters,
            kit=KIT_DOC,
        )
    )
    code = text.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1].rsplit("```", 1)[0]
    check_script(code)
    return code


def render_shot(
    code: str,
    out: Path,
    seconds: float,
    size: tuple,
    ffmpeg: str,
    *,
    fps: int = 30,
    timeout: float = 3600,
    runner: Optional[Callable[[List[str]], int]] = None,
) -> str:
    """Render the checked scene *code* into the clip *out*."""
    from openjarvis.tools.blender_kit import KIT
    from openjarvis.tools.blender_model import RESILIENT

    cmd = blender_cmd()
    if cmd is None and runner is None:
        raise RuntimeError("Blender no está instalado.")
    frames = max(12, round(seconds * fps))
    with tempfile.TemporaryDirectory(prefix="sergio-3d-") as tmp:
        tmpd = Path(tmp)
        frames_dir = tmpd / "f"
        frames_dir.mkdir()
        sep = "\\" if (cmd or ["x"])[0].endswith(".exe") else "/"
        full = RESILIENT.replace("__SOURCE__", json.dumps(code)).replace(
            "__KIT__", json.dumps(KIT)
        )
        full += RENDER_SUFFIX.format(
            w=int(size[0]), h=int(size[1]), fps=fps, frames=frames,
            out=json.dumps(_host_path(frames_dir, cmd or ["x"]) + sep),
        )  # fmt: skip
        script = tmpd / "toma.py"
        script.write_text(full, "utf-8")
        args = (cmd or []) + [_host_path(script, cmd or ["x"])]
        code_rc = (
            runner(args)
            if runner
            else subprocess.run(args, capture_output=True, timeout=timeout).returncode
        )
        pngs = sorted(frames_dir.glob("*.png"))
        if code_rc != 0 or not pngs:
            raise RuntimeError("Blender no pudo renderizar la toma.")
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-framerate", str(fps), "-pattern_type", "glob",
             "-i", str(frames_dir / "*.png"),
             "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(out)],
            check=True, capture_output=True, timeout=600,
        )  # fmt: skip
    return str(out)


__all__ = ["blender_cmd", "render_shot", "script_for"]
