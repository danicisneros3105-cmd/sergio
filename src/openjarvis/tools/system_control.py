"""Tools for controlling the user's own computer.

These let Sergio act on the laptop directly: change the wallpaper, open
apps, drive Blender headless (e.g. "model a castle"), edit video with
ffmpeg (e.g. "cut this and give it a cinematic look like that other one"),
and manage Windhawk mods on Windows.

Everything runs locally with the user's own programs.  Long-running work
(Blender renders, ffmpeg) honours the tool timeout and never uses
``shell=True`` — commands are built as argv lists.
"""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess  # noqa: S404 — local user-requested execution is the point
import sys
from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_RUN_TIMEOUT = 600  # seconds for blender/ffmpeg jobs

# ---------------------------------------------------------------------------
# Blender: a ready-made castle script so "modele un castillo" just works.
# ---------------------------------------------------------------------------

CASTLE_SCRIPT = r"""
import bpy, math

bpy.ops.wm.read_factory_settings(use_empty=True)

def cube(name, loc, scale):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object; o.name = name
    o.scale = (scale[0]/2, scale[1]/2, scale[2]/2)
    bpy.ops.object.transform_apply(scale=True)
    return o

def cyl(name, loc, radius, depth):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=loc)
    o = bpy.context.object; o.name = name
    return o

def battlements(parent_name, z, half, along_x, count, fixed):
    for i in range(count):
        t = -half + (2*half) * (i + 0.5) / count
        loc = (t, fixed, z) if along_x else (fixed, t, z)
        cube(parent_name + f"_m{i}", loc, (0.8, 0.8, 0.8))

# Ground
cube("suelo", (0, 0, -0.5), (40, 40, 1))

# Walls (square keep)
L, H, T = 10.0, 4.0, 1.2
cube("muro_n", (0,  L, H/2), (2*L+T, T, H))
cube("muro_s", (0, -L, H/2), (2*L+T, T, H))
cube("muro_e", ( L, 0, H/2), (T, 2*L+T, H))
cube("muro_o", (-L, 0, H/2), (T, 2*L+T, H))
for name, fixed, along_x in (("n", L, True), ("s", -L, True),
                             ("e", L, False), ("o", -L, False)):
    battlements("almenas_" + name, H + 0.4, L, along_x, 12,
                fixed if along_x else fixed)

# Corner towers with cone roofs
for i, (x, y) in enumerate(((L, L), (L, -L), (-L, L), (-L, -L))):
    cyl(f"torre_{i}", (x, y, 3.5), 2.0, 7.0)
    bpy.ops.mesh.primitive_cone_add(radius1=2.4, radius2=0.0, depth=3.0,
                                    location=(x, y, 8.5))
    bpy.context.object.name = f"techo_{i}"

# Keep (central tower) and gate
cube("torreon", (0, 0, 5), (6, 6, 10))
battlements("almenas_torreon", 10.4, 3.0, True, 5, 3.0)
battlements("almenas_torreon2", 10.4, 3.0, True, 5, -3.0)
cube("puerta", (0, -L - 0.1, 1.5), (3.0, T, 3.0))

# Camera + sun so the first render looks decent
bpy.ops.object.camera_add(location=(28, -32, 20))
cam = bpy.context.object
cam.rotation_euler = (math.radians(63), 0, math.radians(41))
bpy.context.scene.camera = cam
bpy.ops.object.light_add(type='SUN', location=(10, -10, 20))
bpy.context.object.rotation_euler = (math.radians(45), 0, math.radians(30))
"""


def _which_any(names: list[str], extra_dirs: list[Path] | None = None) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for directory in extra_dirs or []:
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return str(candidate)
    return None


def _run(argv: list[str], timeout: int = _RUN_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — argv list, no shell
        argv, capture_output=True, text=True, timeout=timeout, check=False
    )


class _Tool(BaseTool):
    def _result(self, content: str, success: bool = True, **meta: Any) -> ToolResult:
        return ToolResult(
            tool_name=self.tool_id, content=content, success=success, metadata=meta
        )


# ---------------------------------------------------------------------------
# Wallpaper
# ---------------------------------------------------------------------------


@ToolRegistry.register("system_wallpaper")
class WallpaperTool(_Tool):
    tool_id = "system_wallpaper"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Change the desktop wallpaper to an image file on this "
                "computer. Works on Windows, macOS and Linux (GNOME)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Absolute path to the image.",
                    }
                },
                "required": ["image_path"],
            },
            category="system",
            timeout_seconds=30.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        path = Path(str(params.get("image_path") or "")).expanduser().resolve()
        if not path.is_file():
            return self._result(f"No existe la imagen: {path}", success=False)
        os_name = platform.system()
        try:
            if os_name == "Windows":
                import ctypes

                ok = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
                    20, 0, str(path), 3  # SPI_SETDESKWALLPAPER, update + persist
                )
                if not ok:
                    return self._result(
                        "Windows rechazó el cambio de fondo.", success=False
                    )
            elif os_name == "Darwin":
                _run(
                    [
                        "osascript", "-e",
                        f'tell application "System Events" to set picture of '
                        f'every desktop to "{path}"',
                    ],
                    timeout=30,
                )
            else:  # Linux / GNOME
                proc = _run(
                    [
                        "gsettings", "set", "org.gnome.desktop.background",
                        "picture-uri", f"file://{path}",
                    ],
                    timeout=30,
                )
                if proc.returncode != 0:
                    return self._result(
                        "gsettings falló (¿no es GNOME?): " + proc.stderr.strip(),
                        success=False,
                    )
        except Exception as exc:  # noqa: BLE001
            return self._result(f"No pude cambiar el fondo: {exc}", success=False)
        return self._result(f"Fondo de pantalla cambiado a {path.name}.")


# ---------------------------------------------------------------------------
# Open apps / files
# ---------------------------------------------------------------------------


@ToolRegistry.register("system_open")
class OpenAppTool(_Tool):
    tool_id = "system_open"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Open an application or file on this computer (e.g. 'blender', "
                "'spotify', a video file). Uses the OS default handler."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "App name or file path to open.",
                    }
                },
                "required": ["target"],
            },
            category="system",
            timeout_seconds=30.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        target = str(params.get("target") or "").strip()
        if not target:
            return self._result("Falta el objetivo a abrir.", success=False)
        os_name = platform.system()
        try:
            if os_name == "Windows":
                exe = shutil.which(target)
                if exe:
                    subprocess.Popen([exe])  # noqa: S603
                else:
                    os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
            elif os_name == "Darwin":
                subprocess.Popen(["open", "-a", target])  # noqa: S603
            else:
                exe = shutil.which(target)
                if exe:
                    subprocess.Popen([exe])  # noqa: S603
                else:
                    subprocess.Popen(["xdg-open", target])  # noqa: S603
        except Exception as exc:  # noqa: BLE001
            return self._result(f"No pude abrir {target!r}: {exc}", success=False)
        return self._result(f"Abierto: {target}")


# ---------------------------------------------------------------------------
# Blender (headless scripting)
# ---------------------------------------------------------------------------


@ToolRegistry.register("blender_run")
class BlenderTool(_Tool):
    tool_id = "blender_run"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Run Blender in the background with a Python script and save "
                "a .blend file. Use preset='castillo' to model a castle "
                "without writing code, or pass script_path with your own "
                "Blender Python (write it first with file_write)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "preset": {
                        "type": "string",
                        "description": "Built-in model: currently 'castillo'.",
                    },
                    "script_path": {
                        "type": "string",
                        "description": "Path to a custom Blender Python script.",
                    },
                    "output": {
                        "type": "string",
                        "description": "Where to save the .blend file.",
                    },
                },
                "required": ["output"],
            },
            category="system",
            timeout_seconds=float(_RUN_TIMEOUT),
        )

    def _find_blender(self) -> str | None:
        extra: list[Path] = []
        if platform.system() == "Windows":
            program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            extra += list(program_files.glob("Blender*/Blender*"))
        elif platform.system() == "Darwin":
            extra.append(Path("/Applications/Blender.app/Contents/MacOS"))
        return _which_any(["blender", "blender.exe", "Blender"], extra)

    def execute(self, **params: Any) -> ToolResult:
        output = Path(str(params.get("output") or "")).expanduser().resolve()
        if output.suffix != ".blend":
            output = output.with_suffix(".blend")
        script_arg: list[str]
        preset = str(params.get("preset") or "").strip().lower()
        script_path = str(params.get("script_path") or "").strip()
        if preset == "castillo" and not script_path:
            script_arg = ["--python-expr", CASTLE_SCRIPT]
        elif script_path:
            script = Path(script_path).expanduser()
            if not script.is_file():
                return self._result(
                    f"No existe el script: {script}", success=False
                )
            script_arg = ["--python", str(script)]
        else:
            return self._result(
                "Indica preset='castillo' o script_path.", success=False
            )
        blender = self._find_blender()
        if not blender:
            return self._result(
                "Blender no está instalado o no está en el PATH. "
                "Instálalo desde blender.org y vuelve a intentarlo.",
                success=False,
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        expr_save = f"import bpy; bpy.ops.wm.save_as_mainfile(filepath=r'{output}')"
        try:
            proc = _run(
                [blender, "--background", *script_arg,
                 "--python-expr", expr_save],
            )
        except subprocess.TimeoutExpired:
            return self._result("Blender tardó demasiado (timeout).", success=False)
        if not output.is_file():
            tail = (proc.stdout + proc.stderr)[-800:]
            return self._result(
                f"Blender no generó el archivo. Salida:\n{tail}", success=False
            )
        return self._result(
            f"Modelo creado: {output}", output=str(output), preset=preset or "custom"
        )


# ---------------------------------------------------------------------------
# Video editing (ffmpeg)
# ---------------------------------------------------------------------------

_STYLE_FILTERS = {
    "cinematico": "eq=contrast=1.15:brightness=-0.03:saturation=0.85,vignette",
    "vibrante": "eq=contrast=1.1:saturation=1.5",
    "retro": "curves=vintage,vignette",
    "blanco_y_negro": "hue=s=0",
    "suave": "gblur=sigma=0.6,eq=brightness=0.02",
}


def _ffmpeg_cmd(
    operation: str,
    inputs: list[str],
    output: str,
    *,
    start: str = "",
    end: str = "",
    style: str = "",
    text: str = "",
) -> list[str]:
    """Build the ffmpeg argv for the requested operation (pure, testable)."""
    cmd = ["ffmpeg", "-y"]
    if operation == "cortar":
        if start:
            cmd += ["-ss", start]
        cmd += ["-i", inputs[0]]
        if end:
            cmd += ["-to", end]
        cmd += ["-c", "copy"]
    elif operation == "unir":
        cmd += ["-f", "concat", "-safe", "0", "-i", inputs[0], "-c", "copy"]
    else:  # estilo / subtitulo
        cmd += ["-i", inputs[0]]
        filters: list[str] = []
        if style and style in _STYLE_FILTERS:
            filters.append(_STYLE_FILTERS[style])
        if text:
            safe = text.replace(":", "\\:").replace("'", "\\'")
            filters.append(
                "drawtext=text='{}':fontsize=48:fontcolor=white:"
                "borderw=2:bordercolor=black:x=(w-text_w)/2:y=h-120".format(safe)
            )
        if filters:
            cmd += ["-vf", ",".join(filters)]
        cmd += ["-c:a", "copy"]
    cmd.append(output)
    return cmd


@ToolRegistry.register("video_edit")
class VideoEditTool(_Tool):
    tool_id = "video_edit"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Edit a video locally with ffmpeg: 'cortar' (trim with "
                "start/end, e.g. '00:01:10'), 'unir' (concat a list file), or "
                "'estilo' (apply a look: cinematico, vibrante, retro, "
                "blanco_y_negro, suave) with optional on-screen text. To mimic "
                "another video's style, first inspect it and pick the closest "
                "look. Publishing to YouTube needs the YouTube Data API "
                "credentials — upload stays a manual/approved step."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["cortar", "unir", "estilo"],
                    },
                    "input": {"type": "string", "description": "Input video path."},
                    "output": {"type": "string", "description": "Output video path."},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "style": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["operation", "input", "output"],
            },
            category="system",
            timeout_seconds=float(_RUN_TIMEOUT),
        )

    def execute(self, **params: Any) -> ToolResult:
        if shutil.which("ffmpeg") is None:
            return self._result(
                "ffmpeg no está instalado (winget install ffmpeg).", success=False
            )
        operation = str(params.get("operation") or "")
        input_path = Path(str(params.get("input") or "")).expanduser()
        output = str(params.get("output") or "")
        if not input_path.is_file():
            return self._result(f"No existe el video: {input_path}", success=False)
        style = str(params.get("style") or "")
        if style and style not in _STYLE_FILTERS:
            return self._result(
                "Estilo desconocido. Opciones: " + ", ".join(_STYLE_FILTERS),
                success=False,
            )
        cmd = _ffmpeg_cmd(
            operation,
            [str(input_path)],
            output,
            start=str(params.get("start") or ""),
            end=str(params.get("end") or ""),
            style=style,
            text=str(params.get("text") or ""),
        )
        try:
            proc = _run(cmd)
        except subprocess.TimeoutExpired:
            return self._result("ffmpeg tardó demasiado (timeout).", success=False)
        if proc.returncode != 0:
            return self._result(
                "ffmpeg falló:\n" + proc.stderr[-600:], success=False
            )
        return self._result(f"Video listo: {output}", output=output)


# ---------------------------------------------------------------------------
# Windhawk (Windows UI mods)
# ---------------------------------------------------------------------------


@ToolRegistry.register("windhawk_mod")
class WindhawkTool(_Tool):
    tool_id = "windhawk_mod"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Manage Windhawk mods on Windows (taskbar, start menu, "
                "window styles). Actions: 'listar' (installed mods), "
                "'activar'/'desactivar' (toggle a mod by id), "
                "'abrir' (open the Windhawk UI)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["listar", "activar", "desactivar", "abrir"],
                    },
                    "mod_id": {"type": "string"},
                },
                "required": ["action"],
            },
            category="system",
            timeout_seconds=60.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        if platform.system() != "Windows":
            return self._result(
                "Windhawk solo existe en Windows.", success=False
            )
        action = str(params.get("action") or "")
        windhawk = _which_any(
            ["windhawk.exe"],
            [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Windhawk"],
        )
        if action == "abrir":
            if not windhawk:
                return self._result(
                    "Windhawk no está instalado (windhawk.net).", success=False
                )
            subprocess.Popen([windhawk])  # noqa: S603
            return self._result("Windhawk abierto.")
        if windhawk is None:
            return self._result(
                "Windhawk no está instalado (windhawk.net).", success=False
            )
        if action == "listar":
            proc = _run(
                ["reg", "query", r"HKLM\SOFTWARE\Windhawk\Engine\Mods"], timeout=30
            )
            if proc.returncode != 0:
                return self._result("No hay mods instalados o no pude leerlos.")
            mods = [
                line.rsplit("\\", 1)[-1]
                for line in proc.stdout.splitlines()
                if line.strip().startswith("HKEY")
            ]
            return self._result(
                "Mods instalados: " + (", ".join(mods) if mods else "ninguno"),
                mods=mods,
            )
        mod_id = str(params.get("mod_id") or "").strip()
        if not mod_id:
            return self._result("Falta mod_id.", success=False)
        disabled = "1" if action == "desactivar" else "0"
        proc = _run(
            [
                "reg", "add",
                rf"HKLM\SOFTWARE\Windhawk\Engine\Mods\{mod_id}",
                "/v", "Disabled", "/t", "REG_DWORD", "/d", disabled, "/f",
            ],
            timeout=30,
        )
        if proc.returncode != 0:
            return self._result(
                f"No pude cambiar el mod {mod_id!r}: {proc.stderr.strip()}",
                success=False,
            )
        estado = "desactivado" if disabled == "1" else "activado"
        return self._result(
            f"Mod {mod_id} {estado}. Reinicia Explorer o Windhawk para aplicar."
        )


__all__ = [
    "BlenderTool",
    "OpenAppTool",
    "VideoEditTool",
    "WallpaperTool",
    "WindhawkTool",
]
