#!/usr/bin/env python3
"""Render Sergio's original vertical short with Pillow, NumPy and FFmpeg."""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, RATE = 576, 1024, 30, 24000
BEATS = (
    (
        0,
        2.8,
        "GANÓ CON EL MOTOR APAGADO",
        "This robot won a race by turning off its engine.",
    ),
    (
        2.8,
        5.8,
        "UNA META · DOS ROBOTS",
        "Two robots. One gate. The fastest one had a huge lead.",
    ),
    (
        5.8,
        9.0,
        "LA PUERTA OYÓ EL MOTOR",
        "Then its engine made a noise. The gate slammed shut.",
    ),
    (
        9.0,
        12.4,
        "ASÍ FUNCIONA LA TRAMPA",
        "A sound sensor was wired straight to the gate.",
    ),
    (
        12.4,
        15.9,
        "EL AZUL APAGA EL MOTOR",
        "So the blue robot cut the power before the ramp.",
    ),
    (
        15.9,
        19.7,
        "LA PENDIENTE HACE EL RESTO",
        "Gravity did the rest. The sensor heard nothing.",
    ),
    (
        19.7,
        23.0,
        "GANÓ SIN HACER RUIDO",
        "To win a race, sometimes you have to slow down.",
    ),
)
BLUE, CORAL, CREAM, INK = "#47BFFF", "#FF754E", "#F5F0DD", "#121827"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def font(size: int, mono: bool = False):
    face = "DejaVuSansMono-Bold.ttf" if mono else "DejaVuSans-Bold.ttf"
    return ImageFont.truetype(
        face if not (FONT_DIR / face).exists() else str(FONT_DIR / face), size
    )


TITLE, LABEL, MINI = font(38), font(20, True), font(13, True)


def interp(a, b, u):
    return a + (b - a) * max(0, min(1, u))


def ease(u):
    u = max(0, min(1, u))
    return u * u * (3 - 2 * u)


def room():
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    y, x = np.mgrid[:H, :W]
    light = np.maximum(0, 1 - np.hypot((x - 370) / 600, (y - 310) / 820))
    for i, (base, add) in enumerate(((12, 26), (21, 40), (35, 51))):
        arr[:, :, i] = base + light * add + ((x * 13 + y * 17) % 5)
    return Image.fromarray(arr)


ROOM = room()


def track(d, p, hot=False):
    def at(x, y):
        return p(x, y)

    d.polygon(
        [
            at(0, 465),
            at(302, 465),
            at(580, 590),
            at(700, 590),
            at(700, 715),
            at(520, 715),
            at(278, 588),
            at(0, 588),
        ],
        fill="#28334B",
    )
    for y in (465, 527, 588):
        points = [at(-80, y), at(302, y), at(580, y + 125), at(740, y + 125)]
        d.line(
            points, fill=CREAM if y == 465 else "#41506B", width=4 if y == 465 else 2
        )
    for x in range(-40, 740, 40):
        y = 465 + max(0, min(278, x - 302)) * 125 / 278
        d.line([at(x, y + 16), at(x + 9, y + 17)], fill="#7B8BA6", width=3)
    for i in range(6):
        for j in range(2):
            x, y = 492 + j * 11, 552 + i * 10
            d.rectangle(
                [at(x, y), at(x + 10, y + 9)], fill=CREAM if (i + j) % 2 else INK
            )
    for x in (418, 512):
        d.line([at(x, 492), at(x, 335)], fill="#61708A", width=12)
    d.line([at(416, 335), at(514, 335)], fill="#C3CDE1", width=14)
    x, y = at(465, 335)
    d.ellipse((x - 10, y - 10, x + 10, y + 10), fill=CORAL if hot else "#BCEB88")


def bot(im, d, p, x, y, color, roll, s=1):
    x, y = p(x, y)
    d.ellipse((x - 52 * s, y - 12 * s, x + 53 * s, y + 10 * s), fill="#101624")
    for dx in (-29, 29):
        cx, cy = x + dx * s, y - 7 * s
        d.ellipse(
            (cx - 16 * s, cy - 16 * s, cx + 16 * s, cy + 16 * s),
            fill="#111524",
            outline="#67799B",
            width=max(1, int(2 * s)),
        )
        for i in range(3):
            a = roll + i * math.tau / 3
            d.line(
                (cx, cy, cx + 11 * s * math.cos(a), cy + 11 * s * math.sin(a)),
                fill=CREAM,
                width=max(1, int(2 * s)),
            )
    d.rounded_rectangle(
        (x - 45 * s, y - 62 * s, x + 47 * s, y - 17 * s),
        radius=round(12 * s),
        fill=color,
        outline=INK,
        width=max(1, round(3 * s)),
    )
    d.polygon(
        (
            x - 45 * s,
            y - 44 * s,
            x - 28 * s,
            y - 73 * s,
            x + 27 * s,
            y - 73 * s,
            x + 47 * s,
            y - 62 * s,
        ),
        fill=color,
    )
    d.rounded_rectangle(
        (x + 3 * s, y - 55 * s, x + 37 * s, y - 29 * s), radius=round(6 * s), fill=INK
    )
    for dx in (14, 28):
        d.ellipse(
            (x + (dx - 2) * s, y - 46 * s, x + (dx + 3) * s, y - 38 * s), fill=CREAM
        )
    d.line(
        (x - 24 * s, y - 67 * s, x - 29 * s, y - 85 * s),
        fill=CREAM,
        width=max(1, round(2 * s)),
    )
    d.ellipse((x - 33 * s, y - 89 * s, x - 24 * s, y - 81 * s), fill=CREAM)


def bounds(draw, txt, xy, width, font_, color, gap=9):
    lines, row = [], ""
    for word in txt.split():
        candidate = f"{row} {word}".strip()
        if row and draw.textlength(candidate, font=font_) > width:
            lines.append(row)
            row = word
        else:
            row = candidate
    lines.append(row)
    for i, ln in enumerate(lines):
        draw.text(
            (xy[0], xy[1] + i * (font_.size + gap)),
            ln,
            fill=color,
            font=font_,
            stroke_width=1,
        )


def frame(t):
    idx = next(i for i, (_, end, *_rest) in enumerate(BEATS) if t < end)
    start, end, title, _ = BEATS[idx]
    u = (t - start) / (end - start)
    im = ROOM.copy()
    d = ImageDraw.Draw(im)
    for x in range(15, W, 24):
        for y in range(180, 808, 24):
            d.point((x, y), fill="#51627E")
    d.rounded_rectangle(
        (28, 35, 548, 103), radius=18, fill="#151D2B", outline="#68758C", width=2
    )
    d.ellipse((49, 58, 72, 81), fill=BLUE)
    d.ellipse((56, 65, 65, 74), outline=CREAM, width=2)
    d.text((86, 61), "SERGIO  /  HISTORIA ANIMADA", font=MINI, fill=CREAM)
    d.text((480, 57), f"{idx + 1:02d}", font=LABEL, fill=BLUE)
    bounds(d, title, (38, 126), 493, TITLE, CREAM)
    lens, cx, cy = (
        (1.03, 300, 400),
        (0.93, 284, 400),
        (1.48, 430, 417),
        (1.67, 440, 380),
        (1.53, interp(180, 308, ease(u)), 430),
        (1.07, interp(300, 395, ease(u)), 432),
        (1.31, 485, 475),
    )[idx]

    def p(x, y):
        return ((x - cx) * lens + 288, (y - cy) * lens + 515)

    scene = im.copy()
    action = ImageDraw.Draw(scene)
    hot = idx == 2 or idx == 3
    track(action, p, hot)
    gx, gy = p(460, 335)
    lift = 0 if not hot else ease(u * 3) if idx == 2 else 1
    top = gy - 2 + 100 * lift
    action.rounded_rectangle(
        (gx - 24 * lens, top, gx + 24 * lens, top + 56 * lens),
        radius=6,
        fill=CORAL if hot else "#BDD6E7",
        outline=INK,
        width=3,
    )
    if idx in (2, 3, 4):
        rx, ry = p(443, 305)
        for k in range(3):
            radius = 12 + 13 * k + 10 * (u * 4 % 1)
            action.arc(
                (rx - radius, ry - radius, rx + radius, ry + radius),
                185,
                355,
                fill=CORAL if hot else BLUE,
                width=2,
            )
    if idx == 0:
        rx, bx = 406, interp(275, 523, ease(u))
    elif idx == 1:
        rx, bx = interp(154, 360, u), interp(40, 154, u)
    elif idx in (2, 3):
        rx, bx = interp(360, 416, ease(u * 3)) if idx == 2 else 416, 180
    elif idx == 4:
        rx, bx = 416, interp(180, 308, ease(u))
    else:
        rx, bx = 416, interp(308, 570, ease(u)) if idx == 5 else interp(570, 655, u)

    def road(x):
        return 466 + max(0, min(278, x - 302)) * 125 / 278

    bot(scene, action, p, rx, road(rx), CORAL, t * 10 if idx < 3 else 4, lens)
    bot(scene, action, p, bx, road(bx), BLUE, t * 11, lens)
    im.paste(scene.crop((0, 255, W, 752)), (0, 255))
    labels = (
        "RESULTADO",
        "VENTAJA",
        "GOLPE",
        "SENSOR DE SONIDO",
        "MOTOR: OFF",
        "GRAVEDAD",
        "GIRO FINAL",
    )
    d.rounded_rectangle((37, 760, 539, 869), radius=22, fill=CREAM)
    d.text((58, 780), labels[idx], font=LABEL, fill=INK)
    snippets = (
        "La última toma va primero.",
        "El rojo acelera.",
        "Ruido = puerta cerrada.",
        "El ruido activa el cierre.",
        "El azul corta la corriente.",
        "La pendiente lo empuja.",
        "La meta premia el silencio.",
    )
    d.text((59, 821), snippets[idx], font=MINI, fill=INK)
    d.rounded_rectangle((40, 917, 536, 923), radius=3, fill="#3D4A65")
    d.rounded_rectangle(
        (40, 917, 40 + max(2, int(496 * t / BEATS[-1][1])), 923), radius=3, fill=BLUE
    )
    d.text((40, 941), "FICCIÓN ORIGINAL  /  9:16  /  30 FPS", font=MINI, fill=CREAM)
    return im


def audio(ffmpeg: str, wav: Path):
    signal = np.zeros(round(BEATS[-1][1] * RATE))
    rng = np.random.default_rng(42)
    for i, (start, end, _, line) in enumerate(BEATS):
        try:
            voice = subprocess.check_output(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"flite=voice=slt:text={line}",
                    "-af",
                    "atempo=1.17",
                    "-ac",
                    "1",
                    "-ar",
                    str(RATE),
                    "-f",
                    "s16le",
                    "-",
                ],
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            data = np.frombuffer(voice, dtype="<i2").astype(float) / 32768
        except subprocess.CalledProcessError:
            data = np.zeros(0)
        at = int((start + 0.10) * RATE)
        n = min(len(data), max(0, int(end * RATE) - at))
        signal[at : at + n] += data[:n] * 1.25
        if i:
            n = RATE // 7
            tt = np.arange(n) / RATE
            at = round(start * RATE)
            signal[at : at + n] += (
                (
                    np.sin(2 * np.pi * (98 if i == 2 else 540) * tt)
                    + 0.20 * rng.normal(size=n)
                )
                * np.exp(-tt * 45)
                * 0.16
            )
    t = np.arange(len(signal)) / RATE
    signal += (
        0.015
        * np.sin(2 * np.pi * 55 * t)
        * (0.4 + 0.6 * np.cos(2 * np.pi * 2 * t) ** 4)
    )
    with wave.open(str(wav), "wb") as out:
        out.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        out.writeframes((np.clip(signal, -0.96, 0.96) * 32767).astype("<i2").tobytes())


def render(output: Path):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("Necesita FFmpeg.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "demo.wav"
        audio(ffmpeg, wav)
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
            "pipe:0",
            "-i",
            str(wav),
            "-c:v",
            "libx264",
            "-threads",
            "3",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output),
        ]
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc:
            assert proc.stdin is not None
            for i in range(round(BEATS[-1][1] * FPS)):
                proc.stdin.write(frame(i / FPS).tobytes())
            proc.stdin.close()
            if proc.wait():
                raise RuntimeError("No se pudo exportar el demo.")


if __name__ == "__main__":
    render(Path(sys.argv[1] if len(sys.argv) > 1 else "demo-short-sergio.mp4"))
