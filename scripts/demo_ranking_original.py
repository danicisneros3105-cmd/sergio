#!/usr/bin/env python3
"""Render an original, asset-free animated ranking with Sergio's audio tools."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from openjarvis.video_essay import audio, mezcla, render

W, H, FPS, TOTAL = 576, 1024, 30, 24.0
INK, PAPER, BLUE, CORAL, GOLD = "#172033", "#F8F3E8", "#47BFFF", "#FF754E", "#FFD166"
SCENES = (
    ("Cargador tapado", "La almohada retiene el calor.", "pop"),
    ("Vaso junto al portátil", "Un pequeño vuelco basta.", "whoosh"),
    ("Regleta cubierta", "Menos ventilación, más calor.", "subdrop"),
    ("Vela junto a cortina", "La tela también arde.", "sizzle"),
    ("Metal en microondas", "Las chispas salen sin avisar.", "glitch"),
    ("Plancha sin apagar", "El último botón también cuenta.", "impact"),
)
BG = []


def background(index: int) -> Image.Image:
    if len(BG) == 6:
        return BG[index].copy()
    y, x = np.mgrid[:H, :W]
    palettes = (
        (29, 48, 76),
        (47, 43, 70),
        (39, 54, 64),
        (61, 37, 54),
        (30, 53, 72),
        (53, 37, 45),
    )
    base = np.array(palettes[index], dtype=np.float32)
    light = np.maximum(0, 1 - np.hypot((x - 350) / 700, (y - 300) / 900))
    arr = base + light[..., None] * np.array((27, 31, 35), dtype=np.float32)
    arr += ((x * 11 + y * 17) % 4)[..., None]
    image = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGB")
    BG.append(image)
    return image.copy()


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def centered(
    draw: ImageDraw.ImageDraw, text: str, y: int, size: int, color: str
) -> None:
    face = render.font("bold", size)
    box = draw.textbbox((0, 0), text, font=face)
    draw.text(((W - box[2]) / 2, y), text, font=face, fill=color)


def heat(
    draw: ImageDraw.ImageDraw, x: float, y: float, phase: float, color: str = CORAL
) -> None:
    for i in range(3):
        rise = (phase * 32 + i * 15) % 48
        draw.arc(
            (x - 34 + i * 25, y - rise, x - 8 + i * 25, y + 34 - rise),
            80,
            275,
            fill=color,
            width=3,
        )


def shadow(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    draw.ellipse(box, fill="#10152288")


def scene(index: int, u: float) -> Image.Image:
    im = background(index)
    d = ImageDraw.Draw(im)
    phase = u * 4
    shadow(d, (96, 696, 486, 740))
    if index == 0:
        d.rounded_rectangle(
            (85, 470, 493, 700), 55, fill="#A9B4D4", outline=INK, width=6
        )
        d.rounded_rectangle(
            (205, 430, 363, 655), 18, fill="#253B62", outline=INK, width=5
        )
        d.rounded_rectangle((218, 449, 350, 596), 8, fill=BLUE)
        d.line((360, 580, 435, 620, 446, 687), fill=INK, width=8)
        d.rounded_rectangle((421, 675, 466, 702), 8, fill=PAPER, outline=INK, width=4)
        heat(d, 286, 402, phase)
    elif index == 1:
        d.polygon(
            ((115, 510), (410, 510), (478, 680), (66, 680)), fill="#8393B3", outline=INK
        )
        d.polygon(
            ((115, 510), (132, 398), (390, 398), (410, 510)),
            fill="#2C4D72",
            outline=INK,
        )
        d.rectangle((148, 423, 372, 486), fill=BLUE, outline=INK, width=4)
        d.rounded_rectangle((355, 462, 455, 565), 15, fill=PAPER, outline=INK, width=5)
        d.ellipse((358, 452, 452, 481), fill="#6D3B2A", outline=INK, width=4)
        for k in range(4):
            yy = 568 + ((phase * 36 + k * 17) % 72)
            d.ellipse((371 + k * 16, yy, 379 + k * 16, yy + 11), fill=BLUE)
    elif index == 2:
        d.rounded_rectangle((116, 600, 465, 672), 15, fill=PAPER, outline=INK, width=5)
        for x in (157, 235, 313, 391):
            d.ellipse((x, 618, x + 28, 646), fill=INK)
        d.line((463, 644, 520, 690), fill=INK, width=8)
        cover = int(390 * ease(min(1, u * 1.5)))
        d.polygon(
            ((65, 420 + cover // 3), (492, 420 + cover // 3), (458, 665), (89, 665)),
            fill="#7C669B",
            outline=INK,
        )
        for y in range(470 + cover // 3, 650, 30):
            d.line((92, y, 461, y + 4), fill="#A28BC0", width=3)
        heat(d, 283, 397, phase)
    elif index == 3:
        d.rectangle((0, 270, 170, 760), fill="#4E6A8E")
        for x in range(18, 170, 36):
            d.line((x, 280, x, 750), fill="#7391AE", width=4)
        d.rounded_rectangle((283, 505, 357, 688), 10, fill=PAPER, outline=INK, width=5)
        d.ellipse((281, 674, 359, 704), fill="#D5C8B7", outline=INK, width=4)
        flame = 24 + int(13 * math.sin(phase * 3))
        d.ellipse((300, 452 - flame, 340, 520), fill=GOLD, outline=INK, width=3)
        d.ellipse((311, 471 - flame // 2, 329, 515), fill=CORAL)
        heat(d, 320, 402, phase, GOLD)
    elif index == 4:
        d.rounded_rectangle(
            (85, 395, 490, 685), 24, fill="#C6D0DD", outline=INK, width=6
        )
        d.rectangle((111, 425, 365, 655), fill="#263C5B", outline=INK, width=5)
        d.ellipse((145, 455, 330, 625), outline="#8AA4C0", width=4)
        d.line((224, 478, 224, 604), fill=PAPER, width=8)
        for yy in (505, 544, 583):
            d.line((224, yy, 250, yy - 13), fill=PAPER, width=5)
        d.ellipse((408, 448, 449, 489), fill=INK)
        d.ellipse((408, 524, 449, 565), fill=INK)
        if int(phase * 3) % 2:
            for angle in range(0, 360, 45):
                a = math.radians(angle)
                d.line(
                    (238, 541, 238 + 90 * math.cos(a), 541 + 90 * math.sin(a)),
                    fill=GOLD,
                    width=5,
                )
    else:
        d.polygon(
            ((155, 666), (409, 666), (377, 480), (217, 480)),
            fill="#B7C3D4",
            outline=INK,
        )
        d.arc((208, 387, 375, 551), 180, 360, fill=INK, width=18)
        d.polygon(
            ((216, 487), (376, 487), (392, 530), (201, 530)), fill=BLUE, outline=INK
        )
        d.ellipse(
            (253, 588, 303, 632),
            fill=CORAL if int(phase * 4) % 2 else GOLD,
            outline=INK,
            width=4,
        )
        heat(d, 283, 405, phase)
    zoom = 1.0 + 0.07 * ease(u)
    if zoom > 1:
        cw, ch = int(W / zoom), int(H / zoom)
        left, top = (W - cw) // 2, (H - ch) // 2
        im = im.crop((left, top, left + cw, top + ch)).resize(
            (W, H), Image.Resampling.LANCZOS
        )
    return im


def frame(t: float) -> Image.Image:
    index = min(5, int(t // 4))
    u = (t - index * 4) / 4
    im = scene(index, u)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 20, 556, 116), 20, fill="#121827")
    d.text((38, 37), "ERRORES CASEROS", font=render.font("bold", 29), fill=PAPER)
    d.text(
        (39, 78),
        "Parecen inofensivos. No lo son.",
        font=render.font("medium", 18),
        fill=BLUE,
    )
    d.text((473, 43), f"0{index + 1}", font=render.font("black", 43), fill=CORAL)
    d.text((33, 139), "RANKING VISUAL", font=render.font("bold", 16), fill=GOLD)
    for i, (title, _tip, _sfx) in enumerate(SCENES):
        y = 177 + i * 35
        color = PAPER if i < index else GOLD if i == index else "#778399"
        marker = "●" if i <= index else "○"
        d.text(
            (34, y),
            f"{marker} {i + 1}. {title}",
            font=render.font("bold" if i == index else "medium", 17),
            fill=color,
        )
    d.rounded_rectangle((27, 774, 549, 873), 20, fill=PAPER)
    d.text((47, 791), SCENES[index][0], font=render.font("black", 25), fill=INK)
    d.text((48, 832), SCENES[index][1], font=render.font("medium", 19), fill=INK)
    d.rounded_rectangle((30, 917, 546, 925), 4, fill="#3C4963")
    d.rounded_rectangle((30, 917, 30 + int(516 * t / TOTAL), 925), 4, fill=BLUE)
    d.text(
        (31, 949),
        "ANIMACIÓN Y SONIDO CREADOS POR SERGIO",
        font=render.font("bold", 13),
        fill=PAPER,
    )
    if t % 4 < 0.18:
        d.rectangle((0, 0, W, H), fill=INK)
    return im


def render_video(output: Path) -> dict:
    ffmpeg = render.ffmpeg()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        music_path, fx_path, mix_path = (
            tmp / "music.wav",
            tmp / "fx.wav",
            tmp / "mix.wav",
        )
        music_path.write_bytes(
            audio.write_wav(audio.music_bed(TOTAL, mood="inspiring", seed=31))
        )
        events = [(i * 4, sfx) for i, (_title, _tip, sfx) in enumerate(SCENES) if i]
        fx_path.write_bytes(audio.write_wav(audio.effects_stereo(events, TOTAL)))
        sound = mezcla.master(
            mix_path,
            voice=None,
            music=music_path,
            fx=fx_path,
            total=TOTAL,
            ffmpeg=ffmpeg,
        )
        silent = output.with_suffix(".video.mp4")
        cmd = [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{W}x{H}",
            "-r",
            str(FPS),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(silent),
        ]
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc:
            assert proc.stdin is not None
            for i in range(round(TOTAL * FPS)):
                proc.stdin.write(frame(i / FPS).tobytes())
            proc.stdin.close()
            if proc.wait():
                raise RuntimeError("FFmpeg no pudo codificar el ranking")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-i",
                str(silent),
                "-i",
                str(mix_path),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "256k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
            capture_output=True,
            timeout=600,
        )
        silent.unlink()
    return sound


def qa(output: Path, sound: dict) -> dict:
    from openjarvis.video_essay.escuela import _probe

    meta = _probe(output)
    sources = {
        "original_only": True,
        "externos": [],
        "dibujos": "Pillow/NumPy",
        "musica": "audio.music_bed",
        "efectos": "audio.effects_stereo",
        "proveedores_de_ia": [],
    }
    (output.parent / "fuentes.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2), "utf-8"
    )
    sheet = render.sheet(
        [frame(i * 4 + 2) for i in range(6)], cols=3, width=1200
    ).convert("RGB")
    sheet.save(output.parent / "qa-sheet.jpg", quality=88)
    return {
        "archivo": str(output),
        "duracion": meta["dur"],
        "fps": meta["fps"],
        "fotogramas_esperados": round(TOTAL * FPS),
        "sonido": sound,
        "fuentes": sources,
    }


if __name__ == "__main__":
    destination = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path.home()
        / ".openjarvis"
        / "video_jobs"
        / "ranking-original"
        / "6-errores-domesticos.mp4"
    )
    audio_qa = render_video(destination)
    print(json.dumps(qa(destination, audio_qa), ensure_ascii=False, indent=2))
