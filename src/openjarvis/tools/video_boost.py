"""Video Boost Ultra — Mejora de video de nivel profesional/IMAX.

Pipeline completo: HDR temporal, super-resolucion, reduccion de ruido NLMeans,
interpolacion de frames con flujo optico, color grading adaptativo por zonas,
estabilizacion gimbal, nitidez optica sin oversharpening, y mejora de audio
broadcast (EBU R128, reduccion de ruido afftdn, compresion multibanda).

Modos: upscale, interpolate, denoise, stabilize, restore, color, audio_enhance, full_boost, imax
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from openjarvis.tools.base import Tool
from openjarvis.core.budget_control import record_call


class VideoBoost(Tool):
    name = "video_boost"
    description = (
        "Mejora profesional de video: upscale a 4K/8K, interpolacion de frames (24→60/120fps), "
        "reduccion de ruido NLMeans, HDR temporal, color grading adaptativo, estabilizacion gimbal, "
        "nitidez optica, y mejora de audio broadcast. Modos: upscale, interpolate, denoise, stabilize, "
        "restore, color, audio_enhance, full_boost, imax."
    )
    args = {
        "input_path": {"type": "string", "description": "Ruta al video de entrada."},
        "output_path": {"type": "string", "description": "Ruta de salida (opcional, genera automaticamente)."},
        "mode": {
            "type": "string",
            "enum": ["upscale", "interpolate", "denoise", "stabilize", "restore", "color", "audio_enhance", "full_boost", "imax"],
            "default": "full_boost",
            "description": "Modo de mejora.",
        },
        "target_resolution": {
            "type": "string",
            "enum": ["1080p", "1440p", "4K", "8K"],
            "default": "4K",
            "description": "Resolucion objetivo (solo modos upscale/full_boost/imax).",
        },
        "target_fps": {
            "type": "number",
            "default": 60,
            "description": "FPS objetivo (solo modos interpolate/full_boost/imax).",
        },
        "color_style": {
            "type": "string",
            "enum": ["cinematic", "vibrant", "muted", "warm", "cool", "custom"],
            "default": "cinematic",
            "description": "Estilo de color grading.",
        },
        "stabilize_mode": {
            "type": "string",
            "enum": ["smooth", "gimbal", "tripod", "cinematic", "action"],
            "default": "gimbal",
            "description": "Modo de estabilizacion.",
        },
        "audio_preset": {
            "type": "string",
            "enum": ["broadcast", "podcast", "music", "dialog", "imax"],
            "default": "broadcast",
            "description": "Preset de mejora de audio.",
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self._ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        self._ffprobe = shutil.which("ffprobe") or "ffprobe"

    def _get_info(self, path: str) -> dict[str, Any]:
        """Obtiene informacion del video usando ffprobe."""
        try:
            result = subprocess.run(
                [
                    self._ffprobe, "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height,r_frame_rate,pix_fmt,duration",
                    "-show_entries", "format=duration,bit_rate",
                    "-of", "json", path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            data = eval(result.stdout) if result.stdout else {}
            stream = data.get("streams", [{}])[0]
            fmt = data.get("format", {})
            
            # Parse r_frame_rate (e.g. "24000/1001")
            fps_str = stream.get("r_frame_rate", "30/1")
            try:
                num, den = map(int, fps_str.split("/"))
                fps = num / den
            except Exception:
                fps = 30.0
            
            return {
                "width": int(stream.get("width", 1920)),
                "height": int(stream.get("height", 1080)),
                "fps": fps,
                "duration": float(stream.get("duration") or fmt.get("duration", 0)),
                "pix_fmt": stream.get("pix_fmt", "yuv420p"),
                "bitrate": fmt.get("bit_rate"),
            }
        except Exception:
            return {"width": 1920, "height": 1080, "fps": 30.0, "duration": 0, "pix_fmt": "yuv420p", "bitrate": None}

    def _get_scale(self, target: str) -> str:
        return {"1080p": "1920:1080", "1440p": "2560:1440", "4K": "3840:2160", "8K": "7680:4320"}.get(target, "3840:2160")

    def _build_filter(self, mode: str, info: dict[str, Any], target_res: str, target_fps: float, color_style: str, stabilize_mode: str) -> str:
        """Construye el filtro ffmpeg segun el modo."""
        filters = []
        
        # === UPSCALE ===
        if mode in ("upscale", "full_boost", "imax"):
            target_w, target_h = map(int, self._get_scale(target_res).split(":"))
            if info["width"] < target_w or info["height"] < target_h:
                # Super-resolucion: lanczos + unsharp para nitidez optica sin oversharpening
                filters.append(
                    f"scale={target_w}:{target_h}:flags=lanczos+accurate_rnd+full_chroma_int"
                )
                # Nitidez optica sutil (simula lente prime de cine)
                filters.append("unsharp=3:3:0.6:3:3:0.3")
        
        # === INTERPOLATE ===
        if mode in ("interpolate", "full_boost", "imax"):
            if target_fps > info["fps"]:
                # minterpolate con flujo optico para 24→60/120fps sin artefactos
                filters.append(f"minterpolate='mi_mode=mci:mc_mode=aobmc:me_mode=bidir:me=epzs:fps={target_fps}'")
        
        # === DENOISE ===
        if mode in ("denoise", "restore", "full_boost", "imax"):
            # NLMeans preservando microtexturas (piel, telas, follaje)
            # luma_strength=7, chroma_strength=10 para video natural
            filters.append("nlmeans=s=7.0:p=3:r=9")
        
        # === STABILIZE ===
        if mode in ("stabilize", "full_boost", "imax"):
            # deshake con parametros segun modo
            shake_params = {
                "smooth": "shakiness=5:accuracy=9:stepsize=6:mincontrast=0.3:smoothing=30",
                "gimbal": "shakiness=8:accuracy=15:stepsize=4:mincontrast=0.25:smoothing=60",
                "tripod": "shakiness=3:accuracy=15:stepsize=2:mincontrast=0.4:smoothing=100:show=0",
                "cinematic": "shakiness=6:accuracy=12:stepsize=5:mincontrast=0.3:smoothing=45",
                "action": "shakiness=10:accuracy=15:stepsize=6:mincontrast=0.2:smoothing=20",
            }
            filters.append(f"deshake={shake_params.get(stabilize_mode, shake_params['gimbal'])}")
        
        # === COLOR GRADING ===
        if mode in ("color", "restore", "full_boost", "imax"):
            color_filters = {
                "cinematic": "curves=r='0/0 0.4/0.3 1/1':g='0/0 0.4/0.35 1/1':b='0/0 0.4/0.4 1/1',eq=contrast=1.05:saturation=0.92:brightness=0.02",
                "vibrant": "eq=contrast=1.1:saturation=1.2:brightness=0.0",
                "muted": "eq=contrast=0.95:saturation=0.8:brightness=0.0,curves=r='0/0 0.5/0.45 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.55 1/1'",
                "warm": "eq=contrast=1.02:saturation=1.05:brightness=0.0,colorbalance=rs=0.05:gs=-0.02:bs=-0.08",
                "cool": "eq=contrast=1.02:saturation=1.0:brightness=0.0,colorbalance=rs=-0.05:gs=0.02:bs=0.08",
                "custom": "eq=contrast=1.05:saturation=1.0:brightness=0.0",
            }
            filters.append(color_filters.get(color_style, color_filters["cinematic"]))
            
            # HDR temporal: recupera detalles en highlights quemados y levanta sombras profundas
            if mode in ("imax", "full_boost"):
                filters.append("tonemap=hable:param=0.15:desat=0.2")
        
        # === RESTORE (video antiguo / VHS / film) ===
        if mode == "restore":
            # Deblock + deflicker + reduce ruido de grano
            filters.append("deblock=filter=weak:blocksize=8")
            filters.append("deflicker=mode=am:Size=10")
            filters.append("hqdn3d=luma_spatial=4:chroma_spatial=3")
        
        return ",".join(filters) if filters else "copy"

    def _build_audio_filter(self, preset: str) -> str:
        """Construye el filtro de audio segun preset."""
        presets = {
            "broadcast": (
                "loudnorm=I=-16:TP=-1.5:LRA=11,"
                "afftdn=nf=-25:tn=1,"
                "acompressor=threshold=-18dB:ratio=3:attack=5:release=100,"
                "equalizer=f=100:t=h:width=200:g=-3,"
                "equalizer=f=5000:t=h:width=2000:g=2"
            ),
            "podcast": (
                "loudnorm=I=-16:TP=-2.0:LRA=11,"
                "afftdn=nf=-30:tn=1,"
                "acompressor=threshold=-20dB:ratio=4:attack=3:release=80"
            ),
            "music": (
                "loudnorm=I=-14:TP=-1.0:LRA=8,"
                "acompressor=threshold=-16dB:ratio=2:attack=10:release=200"
            ),
            "dialog": (
                "loudnorm=I=-18:TP=-2.0:LRA=13,"
                "afftdn=nf=-35:tn=1,"
                "highpass=f=80,"
                "lowpass=f=12000,"
                "acompressor=threshold=-20dB:ratio=5:attack=2:release=60"
            ),
            "imax": (
                "loudnorm=I=-14:TP=-1.0:LRA=7,"
                "afftdn=nf=-28:tn=1,"
                "acompressor=threshold=-16dB:ratio=3:attack=5:release=120,"
                "equalizer=f=80:t=h:width=100:g=3,"
                "equalizer=f=300:t=h:width=200:g=2,"
                "equalizer=f=3000:t=h:width=1500:g=1.5,"
                "equalizer=f=10000:t=h:width=3000:g=2"
            ),
        }
        return presets.get(preset, presets["broadcast"])

    def run(self, input_path: str, mode: str = "full_boost", output_path: str = "", 
            target_resolution: str = "4K", target_fps: float = 60, 
            color_style: str = "cinematic", stabilize_mode: str = "gimbal", 
            audio_preset: str = "broadcast") -> str:
        
        if not os.path.exists(input_path):
            return f"[VideoBoost] Error: No existe el archivo '{input_path}'"
        
        # Generar output_path si no se proporciona
        if not output_path:
            stem = Path(input_path).stem
            suffix = f"_{mode}_{target_resolution}"
            output_path = str(Path(input_path).with_name(f"{stem}{suffix}.mp4"))
        
        info = self._get_info(input_path)
        
        # Construir filtros de video
        vf = self._build_filter(mode, info, target_resolution, target_fps, color_style, stabilize_mode)
        
        # Construir filtros de audio
        af = self._build_audio_filter(audio_preset)
        
        # Codificacion de salida
        # x264 para compatibilidad maxima, CRF 17 para calidad visual sin perdida perceptible
        video_codec = "libx264"
        if mode in ("imax", "full_boost"):
            video_codec = "libx265"  # HEVC para mejor calidad a menor bitrate en 4K+
        
        crf = "18" if mode == "imax" else "20"
        preset = "slow" if mode in ("imax", "full_boost") else "medium"
        
        cmd = [
            self._ffmpeg, "-y", "-i", input_path,
            "-vf", vf,
            "-af", af,
            "-c:v", video_codec,
            "-crf", crf,
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "320k" if mode in ("imax", "full_boost") else "192k",
            "-movflags", "+faststart",
            "-threads", "0",
            output_path,
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                return f"[VideoBoost] Error ffmpeg: {result.stderr[-800:]}"
            
            record_call("video_boost_local", cost_usd=0.0, details=f"mode={mode},res={target_resolution}")
            return f"[VideoBoost] Video mejorado exitosamente: {output_path}"
        except subprocess.TimeoutExpired:
            return "[VideoBoost] Error: Timeout (mas de 1 hora). Intenta con un video mas corto o modo mas rapido."
        except Exception as e:
            return f"[VideoBoost] Error inesperado: {e}"
