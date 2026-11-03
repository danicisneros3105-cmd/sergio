"""Finding pictures in the person's own folders («busca la foto de la playa de
agosto», «las capturas de pantalla de ayer», «fotos donde salga un perro»).

Two passes, cheapest first:

1. **What the file says**: folder, name, date taken (EXIF ``DateTimeOriginal``,
   else the file date), camera, size, portrait or landscape, and whether it is
   a screenshot. Free and instant, on this computer.
2. **What the picture shows** (only when asked for content): the candidates go
   to the vision model as numbered contact sheets of 16 small thumbnails, one
   call per sheet, and the model answers with the numbers that match. Only the
   thumbnails leave the computer, never the originals, and only to the model
   the person already uses.
"""

from __future__ import annotations

import datetime as dt
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
SHEET = 16  # thumbnails per contact sheet
MAX_SCAN = 20_000
MAX_LOOK = 160  # thumbnails sent to the model for one question at most


@dataclass
class Photo:
    path: Path
    when: dt.datetime
    width: int = 0
    height: int = 0
    camera: str = ""
    screenshot: bool = False

    def row(self) -> dict:
        return {
            "ruta": str(self.path),
            "fecha": self.when.strftime("%Y-%m-%d %H:%M"),
            "tamano": f"{self.width}x{self.height}" if self.width else "",
            "camara": self.camera,
            "captura": self.screenshot,
        }


def roots(home: Optional[Path] = None) -> List[Path]:
    base = home or Path.home()
    names = ("Pictures", "Imágenes", "OneDrive/Pictures", "OneDrive/Imágenes", "Desktop",
             "Escritorio", "Downloads", "Descargas")  # fmt: skip
    found = [base / n for n in names if (base / n).is_dir()]
    users = Path("/mnt/c/Users")
    if home is None and users.is_dir():  # WSL: the Windows pictures
        for u in users.iterdir():
            if u.name.lower() in ("public", "default", "default user", "all users"):
                continue
            for n in names:
                p = u / n
                try:
                    if p.is_dir():
                        found.append(p)
                except OSError:
                    continue
    extra = os.environ.get("SERGIO_FOTOS", "")
    found += [Path(p) for p in extra.split(os.pathsep) if p and Path(p).is_dir()]
    return list(dict.fromkeys(found))


def _exif(path: Path) -> tuple[Optional[dt.datetime], int, int, str]:
    try:
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
            ex = im.getexif()
            raw = ex.get(36867) or ex.get_ifd(0x8769).get(36867) or ex.get(306)
            model = str(ex.get(272) or "").strip()
            when = dt.datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S") if raw else None
            return when, w, h, model
    except Exception:  # noqa: BLE001 — unreadable or no EXIF
        return None, 0, 0, ""


def scan(folders: Iterable[Path], *, since: Optional[dt.date] = None, until: Optional[dt.date] = None,
         name: str = "", screenshots: Optional[bool] = None, orientation: str = "",
         limit: int = MAX_SCAN) -> List[Photo]:  # fmt: skip
    """Pictures matching what their files say, newest first."""
    words = [w for w in re.split(r"\W+", name.lower()) if len(w) > 1]
    out: List[Photo] = []
    seen = 0
    for root in folders:
        for dirpath, dirnames, files in os.walk(root):
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith((".", "$")) and d != "node_modules"
            ]
            for f in files:
                p = Path(dirpath) / f
                if p.suffix.lower() not in EXTS:
                    continue
                seen += 1
                if seen > limit:
                    break
                low = str(p).lower()
                if words and not all(w in low for w in words):
                    continue
                shot = bool(re.search(r"screenshot|captura|recorte|screen shot", low))
                if screenshots is not None and shot != screenshots:
                    continue
                try:
                    mtime = dt.datetime.fromtimestamp(p.stat().st_mtime)
                except OSError:
                    continue
                when, w, h, cam = _exif(p)
                when = when or mtime
                if since and when.date() < since or until and when.date() > until:
                    continue
                if orientation == "vertical" and not (h > w):
                    continue
                if orientation == "horizontal" and not (w > h):
                    continue
                out.append(Photo(p, when, w, h, cam, shot))
    out.sort(key=lambda x: x.when, reverse=True)
    return out


def contact_sheet(photos: List[Photo], cell: int = 256) -> bytes:
    """A 4x4 grid of numbered thumbnails (1…16) as JPEG."""
    from PIL import Image, ImageDraw

    cols = 4
    rows = (len(photos) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    for i, ph in enumerate(photos):
        try:
            with Image.open(ph.path) as im:
                im = im.convert("RGB")
                im.thumbnail((cell - 8, cell - 8))
                x, y = (i % cols) * cell, (i // cols) * cell
                sheet.paste(
                    im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2)
                )
        except Exception:  # noqa: BLE001
            continue
        draw.rectangle([x + 4, y + 4, x + 40, y + 30], fill=(0, 0, 0))
        draw.text((x + 10, y + 9), str(i + 1), fill=(255, 255, 255))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def look(
    photos: List[Photo], what: str, ask: Optional[Callable[..., str]] = None
) -> List[Photo]:
    """The photos whose picture shows *what*, asking the vision model one
    contact sheet at a time."""
    if ask is None:
        from openjarvis.creator.llm import ask as _ask

        ask = _ask
    hits: List[Photo] = []
    for start in range(0, min(len(photos), MAX_LOOK), SHEET):
        chunk = photos[start : start + SHEET]
        prompt = [
            contact_sheet(chunk),
            (
                f"Esta hoja tiene {len(chunk)} fotos numeradas. ¿Cuáles muestran: {what}? "
                "Responda solo con los números separados por comas, o «ninguna»."
            ),
        ]
        try:
            answer = ask(prompt, effort="low", max_tokens=200)
        except Exception:  # noqa: BLE001 — a failed sheet is skipped, not invented
            continue
        for n in re.findall(r"\d+", answer or ""):
            i = int(n) - 1
            if 0 <= i < len(chunk):
                hits.append(chunk[i])
    return hits


def find(*, what: str = "", name: str = "", since: str = "", until: str = "",
         screenshots: Optional[bool] = None, orientation: str = "", limit: int = 24,
         folders: Optional[List[Path]] = None, ask: Any = None) -> dict:  # fmt: skip
    def day(s: str) -> Optional[dt.date]:
        try:
            return dt.date.fromisoformat(s) if s else None
        except ValueError:
            return None

    places = folders if folders is not None else roots()
    if not places:
        return {"fotos": [], "nota": "No encuentro carpetas de fotos en este equipo."}
    found = scan(places, since=day(since), until=day(until), name=name,
                 screenshots=screenshots, orientation=orientation)  # fmt: skip
    looked = 0
    if what and found:
        looked = min(len(found), MAX_LOOK)
        found = look(found, what, ask)
    return {
        "fotos": [p.row() for p in found[:limit]],
        "total": len(found),
        "mirando_contenido": bool(what),
        "revisadas_por_imagen": looked,
        "carpetas": [str(p) for p in places[:8]],
    }


__all__ = ["Photo", "contact_sheet", "find", "look", "roots", "scan"]
