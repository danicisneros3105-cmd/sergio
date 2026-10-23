"""The finishing, with Creator's own tools: colour, master and cover.

Post quality and Absolut Cinema go through the colour chain of Creator's
``video_master`` (the same one ``video_pro`` uses: 10-bit processing, a
curve, an optional LUT and sharpening) and Absolut Cinema also gets its
10-bit master (HEVC 10 bits for delivery). When the desktop package is not
next to the server, the same filters are used directly.

The cover (thumbnail) is the strongest frame of the video with the
package's two to four words in big type.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

GRADE = "eq=contrast=1.06:saturation=1.08:gamma=0.98"


def video_master() -> Optional[Any]:
    """Creator's ``video_master`` module (None when it is not installed here)."""
    root = Path(__file__).resolve().parents[3] / "windows"
    if root.is_dir() and str(root) not in sys.path:
        sys.path.append(str(root))
    try:
        return importlib.import_module("sergio_escritorio.video_master")
    except Exception:  # noqa: BLE001 — the same filters without it
        return None


def color_chain(lut: str = "") -> str:
    vm = video_master()
    if vm is not None:
        return vm.color_chain(lut=lut, contrast_curve=True, sharpen=True, grade=GRADE)
    steps = ["format=yuv444p10le"]
    if lut:
        steps.append(f"lut3d=file='{lut}':interp=tetrahedral")
    steps += ["curves=preset=medium_contrast", GRADE, "unsharp=5:5:0.6:5:5:0.0"]
    return ",".join(steps)


def grade(src: Path, out: Path, ffmpeg: str, *, lut: str = "") -> Path:
    """*src* with the colour chain, as a delivery mp4 (audio copied)."""
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(src), "-vf", color_chain(lut) + ",format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-c:a", "copy", "-movflags", "+faststart", str(out)],
        check=True, capture_output=True, timeout=7200,
    )  # fmt: skip
    return out


def master(src: Path, ffmpeg: str, kind: str = "hevc10") -> Optional[Path]:
    """A 10-bit master next to the video (None when it fails: the mp4 stays)."""
    vm = video_master()
    if vm is None or kind not in getattr(vm, "MASTERS", {}):
        return None
    out = src.with_name(f"{src.stem}-master{vm.MASTERS[kind]['ext']}")
    done = subprocess.run(
        vm.master_command(src, out, kind, exe=ffmpeg), capture_output=True, timeout=7200
    )
    return out if done.returncode == 0 and out.exists() else None


def cover(frame: Any, text: str, out: Path) -> Path:
    """The thumbnail: the frame, darker at the bottom, with big words."""
    from PIL import Image, ImageDraw

    from openjarvis.video_essay.render import font

    img = frame.convert("RGB").resize((1280, 720))
    shade = Image.new("L", (1, 720))
    for y in range(720):
        shade.putpixel((0, y), int(max(0, (y - 300) / 420) * 190))
    img.paste((0, 0, 0), (0, 0, 1280, 720), shade.resize((1280, 720)))
    d = ImageDraw.Draw(img)
    words = text.upper().split()[:4]
    size = 150 if len(" ".join(words)) < 14 else 112
    f = font("black", size)
    lines, cur = [], ""
    for w in words:
        if cur and f.getlength(cur + " " + w) > 1160:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    y = 690 - len(lines) * size * 1.02
    for line in lines:
        d.text((62, y + 5), line, font=f, fill=(0, 0, 0))
        d.text((58, y), line, font=f, fill=(255, 255, 255))
        y += size * 1.02
    img.save(out, quality=92)
    return out


__all__ = ["color_chain", "cover", "grade", "master", "video_master"]
