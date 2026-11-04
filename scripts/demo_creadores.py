"""Render a reproducible motion-design sample using original procedural artwork.

Usage: python scripts/demo_creadores.py /absolute/path/demo.mp4
Requires Pillow and ffmpeg. This is a design demonstration, not footage of a
live AI job, a user account or a Blender render. No external media is used.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def render(output: Path) -> None:
    width, height, fps, seconds = 720, 1280, 24, 6
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("Install ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        font = ImageFont.truetype(font_path, 40)
        small = ImageFont.truetype(font_path, 20)
    except OSError:
        font = ImageFont.load_default(size=40)
        small = ImageFont.load_default(size=20)
    process = subprocess.Popen(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ],
        stdin=subprocess.PIPE,
    )
    try:
        for frame in range(fps * seconds):
            t = frame / fps
            image = Image.new("RGB", (width, height), "#f5f7fb")
            draw = ImageDraw.Draw(image)
            draw.text((46, 58), "SERGIO / ESTUDIO", font=small, fill="#0055cf")
            draw.text(
                (46, 1140),
                "DEMO PROCEDURAL · SIN MATERIAL AJENO",
                font=small,
                fill="#525b68",
            )
            if t < 2:
                # Geometry follows assets/marca/sergio.svg; the source icon is unchanged.
                scale = min(1, t / 0.8)
                ease = 1 - (1 - scale) ** 3
                radius = 140 * ease
                cx, cy = width / 2, 480
                draw.ellipse(
                    (cx - radius, cy - radius, cx + radius, cy + radius), fill="#0a6cfe"
                )
                ring = radius * 13.7 / 47
                draw.ellipse(
                    (cx - ring, cy - ring, cx + ring, cy + ring),
                    outline="white",
                    width=max(1, round(radius * 10.2 / 47)),
                )
                draw.text(
                    (120, 730), "Una idea. Un lenguaje.", font=font, fill="#111827"
                )
            elif t < 4:
                draw.text((68, 260), "Del guion al plano", font=font, fill="#111827")
                for i, label in enumerate(("GANCHO", "DESARROLLO", "REMATE")):
                    y = 400 + i * 175
                    offset = max(0, 1 - (t - 2 - i * 0.18) * 3) * 120
                    draw.rounded_rectangle(
                        (60 + offset, y, 660 + offset, y + 140),
                        radius=20,
                        fill="white",
                        outline="#d9e1ed",
                        width=2,
                    )
                    draw.rectangle(
                        (86 + offset, y + 28, 91 + offset, y + 108), fill="#0a6cfe"
                    )
                    draw.text((115 + offset, y + 49), label, font=small, fill="#111827")
            else:
                draw.text((84, 260), "Diseño en movimiento", font=font, fill="#111827")
                angle = (t - 4) * math.pi
                points = []
                for x, y, z in (
                    (x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)
                ):
                    rx = x * math.cos(angle) + z * math.sin(angle)
                    rz = -x * math.sin(angle) + z * math.cos(angle)
                    factor = 150 / (1 + (rz + 2) * 0.15)
                    points.append((360 + rx * factor, 620 + y * factor + rz * 30))
                for a in range(8):
                    for bit in (1, 2, 4):
                        b = a ^ bit
                        if a < b:
                            draw.line((points[a], points[b]), fill="#0a6cfe", width=5)
                draw.text(
                    (105, 900), "TIPOGRAFÍA · RITMO · COLOR", font=small, fill="#525b68"
                )
            process.stdin.write(image.tobytes())
        process.stdin.close()
        if process.wait(timeout=120) != 0:
            raise RuntimeError("ffmpeg render failed")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


if __name__ == "__main__":
    render(Path(sys.argv[1]).resolve())
