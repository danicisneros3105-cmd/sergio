"""What each shot shows: the owner's clips first, then free stock, then a
picture Sergio makes.

The reference essays cut films, news and archive footage. Those belong to
others: Sergio never downloads or uses them. In their place, in this order:

1. **the owner's own clips** (a folder he chooses), matched to the shot by
   the words in their names;
2. **free stock video** with a licence that allows any use: Pexels
   (``PEXELS_API_KEY``) or Pixabay (``PIXABAY_API_KEY``), both free keys;
3. **a picture Sergio makes** for the shot (``studio.generate_image``), as a
   film still, which the renderer keeps moving.

A shot with nothing usable becomes a black card with its words, never an
error.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from openjarvis.video_essay.plan import Shot

VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
LOOK = (
    "cinematic film still, 35mm, shallow depth of field, dramatic natural light, "
    "rich texture, no text, no letters, no logos, no watermark"
)


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-záéíóúñü0-9]{3,}", text.lower())}


class Library:
    """The owner's clips and pictures, matched by the words in their names."""

    def __init__(self, folders: Iterable[str]) -> None:
        self.files: List[Path] = []
        for folder in folders:
            root = Path(folder).expanduser()
            if root.is_dir():
                for p in sorted(root.rglob("*")):
                    if p.suffix.lower() in VIDEO_EXT + IMAGE_EXT:
                        self.files.append(p)
        self.used: Dict[str, int] = {}

    def pick(self, shot: Shot) -> Optional[str]:
        if not self.files:
            return None
        want = _words(shot.visual + " " + shot.text)
        scored = []
        for p in self.files:
            name = _words(p.stem.replace("_", " ").replace("-", " "))
            score = len(want & name) * 3 - self.used.get(str(p), 0)
            scored.append((score, str(p)))
        score, best = max(scored)
        if score <= 0:
            return None  # nothing of his fits: better a matching stock clip
        self.used[best] = self.used.get(best, 0) + 1
        return best


def _download(url: str, dest: Path, timeout: float = 120) -> Optional[str]:
    import httpx

    try:
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
        return str(dest) if dest.stat().st_size > 10_000 else None
    except Exception:  # noqa: BLE001 — the next source
        dest.unlink(missing_ok=True)
        return None


def pexels(query: str, dest: Path, landscape: bool = True) -> Optional[str]:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key or not query:
        return None
    import httpx

    try:
        r = httpx.get(
            "https://api.pexels.com/videos/search",
            params={
                "query": query[:100],
                "per_page": 6,
                "orientation": "landscape" if landscape else "portrait",
            },
            headers={"Authorization": key},
            timeout=30,
        )
        r.raise_for_status()
        videos = r.json().get("videos") or []
    except Exception:  # noqa: BLE001
        return None
    for video in videos:
        files = [f for f in video.get("video_files") or [] if f.get("link")]
        files.sort(key=lambda f: abs((f.get("width") or 0) - 1920))
        for f in files[:2]:
            got = _download(f["link"], dest)
            if got:
                return got
    return None


def pixabay(query: str, dest: Path) -> Optional[str]:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key or not query:
        return None
    import httpx

    try:
        r = httpx.get(
            "https://pixabay.com/api/videos/",
            params={"key": key, "q": query[:100], "per_page": 5, "safesearch": "true"},
            timeout=30,
        )
        r.raise_for_status()
        hits = r.json().get("hits") or []
    except Exception:  # noqa: BLE001
        return None
    for hit in hits:
        sizes = hit.get("videos") or {}
        for size in ("large", "medium", "small"):
            url = (sizes.get(size) or {}).get("url")
            if url:
                got = _download(url, dest)
                if got:
                    return got
    return None


def generated(
    prompt: str, dest: Path, make: Optional[Callable[[str], bytes]] = None
) -> Optional[str]:
    if not prompt:
        return None
    try:
        if make is None:
            from openjarvis.creator import studio

            make = studio.generate_image
        data = make(f"{prompt}. {LOOK}")
    except Exception:  # noqa: BLE001
        return None
    ext = ".jpg" if data[:3] == b"\xff\xd8\xff" else ".png"
    path = dest.with_suffix(ext)
    path.write_bytes(data)
    return str(path)


def fill(
    shots: List[Shot],
    folder: Path,
    *,
    library: Optional[Library] = None,
    stock: bool = True,
    images: bool = True,
    make_image: Optional[Callable[[str], bytes]] = None,
    landscape: bool = True,
    progress: Optional[Callable[[float, str], None]] = None,
) -> List[Shot]:
    """Give every non-card shot something to show (cached in *folder*)."""
    folder.mkdir(parents=True, exist_ok=True)
    todo = [s for s in shots if s.kind != "card"]
    for k, shot in enumerate(todo):
        if shot.asset and Path(shot.asset).exists():
            continue  # resumed job: already found
        query = shot.visual or shot.text
        tag = hashlib.sha1(query.encode()).hexdigest()[:10]
        found = library.pick(shot) if library else None
        source = "su biblioteca" if found else ""
        if not found and stock:
            found = pexels(query, folder / f"{tag}-pexels.mp4", landscape) or pixabay(
                query, folder / f"{tag}-pixabay.mp4"
            )
            source = "video libre" if found else ""
        if not found and images:
            found = generated(query, folder / f"{tag}-img", make_image)
            source = "imagen de Sergio" if found else ""
        if found:
            shot.asset = found
            shot.notes.append(f"imagen: {source}")
        else:
            shot.kind, shot.card = "card", "black"
            shot.notes.append("sin imagen: ficha negra")
        if progress:
            progress((k + 1) / max(1, len(todo)), source or "ficha")
    return shots


__all__ = ["Library", "fill", "generated", "pexels", "pixabay"]
