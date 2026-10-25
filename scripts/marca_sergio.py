"""Sergio's icons, all drawn from one file: ``assets/marca/sergio.svg``.

    python scripts/marca_sergio.py          # write every icon
    python scripts/marca_sergio.py --check  # fail if one is missing or stale

The web (favicon, PWA, iPhone), the Windows installer and shortcuts, the tray,
the Tauri build (Windows and Mac) and the code agent all show the same mark. Change the SVG, run this, never edit a PNG
by hand.
"""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "marca" / "sergio.svg"

PNGS = {
    "frontend/public/pwa-192x192.png": 192,
    "frontend/public/pwa-512x512.png": 512,
    "frontend/public/apple-touch-icon.png": 180,
    "frontend/src-tauri/icons/32x32.png": 32,
    "frontend/src-tauri/icons/128x128.png": 128,
    "frontend/src-tauri/icons/128x128@2x.png": 256,
    "frontend/src-tauri/icons/256x256.png": 256,
    "frontend/src-tauri/icons/icon.png": 512,
    "extensions/clacky/lib/clacky/web/sergio/icon.png": 256,
    "windows/sergio_escritorio/resources/sergio.png": 256,
}
ICOS = {
    "frontend/public/favicon.ico": (16, 32, 48),
    "installer/sergio.ico": (16, 24, 32, 48, 64, 128, 256),
    "frontend/src-tauri/icons/icon.ico": (16, 32, 48, 256),
}
ICNS = "frontend/src-tauri/icons/icon.icns"  # the Mac build
SVG_COPY = "frontend/public/sergio.svg"


def render(size: int) -> bytes:
    """The mark as PNG bytes, *size* pixels square (Qt's SVG renderer)."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    QGuiApplication.instance() or QGuiApplication(["marca"])
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(SOURCE.read_bytes())).render(
        painter, QRectF(0, 0, size, size)
    )
    painter.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


def ico(sizes: tuple[int, ...]) -> bytes:
    from PIL import Image

    big = Image.open(io.BytesIO(render(max(sizes)))).convert("RGBA")
    out = io.BytesIO()
    big.save(out, format="ICO", sizes=[(s, s) for s in sizes])
    return out.getvalue()


def icns() -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.open(io.BytesIO(render(1024))).convert("RGBA").save(out, format="ICNS")
    return out.getvalue()


def wanted() -> dict[str, bytes]:
    files = {rel: render(size) for rel, size in PNGS.items()}
    files.update({rel: ico(sizes) for rel, sizes in ICOS.items()})
    files[ICNS] = icns()
    files[SVG_COPY] = SOURCE.read_bytes()
    return files


def stamp() -> str:
    """The SVG's fingerprint, kept next to it so --check knows the icons are from it."""
    return hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:16]


def main(argv: list[str]) -> int:
    stamp_file = SOURCE.with_suffix(".sha")
    if "--check" in argv:
        missing = [
            rel for rel in [*PNGS, *ICOS, ICNS, SVG_COPY] if not (ROOT / rel).is_file()
        ]
        stale = (
            stamp_file.read_text().strip() != stamp() if stamp_file.is_file() else True
        )
        if missing or stale:
            print(
                "Faltan o están viejos los iconos de Sergio:",
                ", ".join(missing) or "(huella)",
            )
            return 1
        return 0
    for rel, data in wanted().items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(rel)
    stamp_file.write_text(stamp() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
