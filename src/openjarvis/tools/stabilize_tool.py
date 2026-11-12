"""Stabilize Tool — Estabilizacion digital avanzada de video.

Usa ffmpeg deshake con 5 modos preconfigurados:
- smooth: suavizado ligero para entrevistas y vlogs
- gimbal: elimina micro-vibraciones, simula estabilizador mecanico
- tripod: bloqueo total de camara, elimina TODO movimiento
- cinematic: suavizado cinematografico para producciones profesionales
- action: mantiene energia de movimiento pero elimina sacudidas brutales

Tambien soporta interpolacion de frames para suavizado adicional.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from openjarvis.tools.base import Tool


class StabilizeTool(Tool):
    name = "stabilize_video"
    description = (
        "Estabilizacion digital avanzada de video con 5 modos: smooth, gimbal, tripod, "
        "cinematic, action. Elimina vibraciones, sacudidas y pasos al caminar usando flujo optico."
    )
    args = {
        "input_path": {"type": "string", "description": "Ruta al video de entrada."},
        "output_path": {"type": "string", "description": "Ruta de salida (opcional)."},
        "mode": {
            "type": "string",
            "enum": ["smooth", "gimbal", "tripod", "cinematic", "action"],
            "default": "gimbal",
            "description": "Modo de estabilizacion.",
        },
        "intensity": {
            "type": "number",
            "default": 1.0,
            "description": "Intensidad de 0.0 a 2.0 (1.0 = default).",
        },
        "interpolate": {
            "type": "boolean",
            "default": False,
            "description": "Si True, interpola frames para suavizado adicional.",
        },
        "target_fps": {
            "type": "number",
            "default": 60,
            "description": "FPS para interpolacion (si interpolate=True).",
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self._ffmpeg = shutil.which("ffmpeg") or "ffmpeg"

    def run(self, input_path: str, mode: str = "gimbal", output_path: str = "",
            intensity: float = 1.0, interpolate: bool = False, target_fps: float = 60) -> str:
        
        if not os.path.exists(input_path):
            return f"[Stabilize] Error: No existe '{input_path}'"
        
        if not output_path:
            stem = Path(input_path).stem
            output_path = str(Path(input_path).with_name(f"{stem}_stabilized_{mode}.mp4"))
        
        # Parametros base por modo
        base_params = {
            "smooth": {
                "shakiness": 5,
                "accuracy": 9,
                "stepsize": 6,
                "mincontrast": 0.3,
                "smoothing": 30,
            },
            "gimbal": {
                "shakiness": 8,
                "accuracy": 15,
                "stepsize": 4,
                "mincontrast": 0.25,
                "smoothing": 60,
            },
            "tripod": {
                "shakiness": 3,
                "accuracy": 15,
                "stepsize": 2,
                "mincontrast": 0.4,
                "smoothing": 100,
            },
            "cinematic": {
                "shakiness": 6,
                "accuracy": 12,
                "stepsize": 5,
                "mincontrast": 0.3,
                "smoothing": 45,
            },
            "action": {
                "shakiness": 10,
                "accuracy": 15,
                "stepsize": 6,
                "mincontrast": 0.2,
                "smoothing": 20,
            },
        }
        
        p = base_params.get(mode, base_params["gimbal"])
        
        # Ajustar por intensidad
        smoothing = int(p["smoothing"] * intensity)
        shakiness = min(15, int(p["shakiness"] * intensity))
        
        deshake = (
            f"deshake=shakiness={shakiness}:accuracy={p['accuracy']}:"
            f"stepsize={p['stepsize']}:mincontrast={p['mincontrast']}:"
            f"smoothing={smoothing}:show=0"
        )
        
        filters = [deshake]
        
        # Interpolacion opcional
        if interpolate:
            filters.append(f"minterpolate='mi_mode=mci:mc_mode=aobmc:me_mode=bidir:me=epzs:fps={target_fps}'")
        
        vf = ",".join(filters)
        
        cmd = [
            self._ffmpeg, "-y", "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264", "-crf", "20", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-threads", "0",
            output_path,
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0:
                return f"[Stabilize] Error ffmpeg: {result.stderr[-800:]}"
            return f"[Stabilize] Video estabilizado exitosamente: {output_path} (modo: {mode})"
        except subprocess.TimeoutExpired:
            return "[Stabilize] Error: Timeout. Intenta con un video mas corto."
        except Exception as e:
            return f"[Stabilize] Error inesperado: {e}"
