"""Where the real clips come from, best first, and how one is chosen.

For each shot Sergio looks, in this order (each step only if the shot still
has nothing):

1. **the owner's clips** — the folder he gives and ``~/.openjarvis/video_clips``
   (his films, recordings, anything he drops there), matched by name;
2. **free stock** — Pexels and Pixabay (free keys), licences for any use;
3. **public archives without a key** — Wikimedia Commons (free licences,
   credited), NASA (public domain) and the Internet Archive's public-domain
   films (old cinema, newsreels, educational films);
4. **clips from the web and short film clips** — YouTube and the other sites
   yt-dlp reads, when the owner allows it (``SERGIO_CLIPS_WEB``, on by his
   decision of 23 Oct 2026). Only a few seconds of each, credited; videos
   with clips of others can be claimed by their owners on the platforms
   (the posting package says so).

Every clip is cut to the few seconds the shot needs (ffmpeg reads only that
part when the server allows it), and its source and licence go to the job's
credits. With several candidates per shot (Post quality and Absolut Cinema)
an editor looks at a frame of each and keeps the best (:func:`choose`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v", ".ogv")
UA = {"User-Agent": "Sergio/1.0 (personal video editor)"}


@dataclass
class Candidate:
    url: str  # where it comes from (a file path for his own clips)
    source: str  # library | pexels | pixabay | commons | nasa | archive | web
    credit: str = ""  # who made it
    licence: str = ""
    start: float = 0.0  # where the useful part starts, seconds
    path: str = ""  # the local cut, once fetched

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def web_allowed() -> bool:
    return os.environ.get("SERGIO_CLIPS_WEB", "1").strip().lower() not in (
        "0",
        "no",
        "false",
        "off",
    )


def own_folders(extra: Iterable[str] = ()) -> List[str]:
    from openjarvis.core.paths import get_config_dir

    return [*[e for e in extra if e], str(get_config_dir() / "video_clips")]


def _get(url: str, **kw: Any) -> Any:
    import httpx

    r = httpx.get(
        url,
        headers={**UA, **kw.pop("headers", {})},
        timeout=30,
        follow_redirects=True,
        **kw,
    )
    r.raise_for_status()
    return r.json()


# -- the searches (each returns candidates, never raises) ------------------------------


def search_pexels(query: str, n: int, landscape: bool = True) -> List[Candidate]:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    try:
        data = _get(
            "https://api.pexels.com/videos/search",
            params={
                "query": query[:100],
                "per_page": n,
                "orientation": "landscape" if landscape else "portrait",
            },
            headers={"Authorization": key},
        )
    except Exception:  # noqa: BLE001
        return []
    out = []
    for v in data.get("videos") or []:
        files = sorted(
            (f for f in v.get("video_files") or [] if f.get("link")),
            key=lambda f: abs((f.get("width") or 0) - 1920),
        )
        if files:
            who = (v.get("user") or {}).get("name", "")
            out.append(Candidate(files[0]["link"], "pexels", who, "Licencia de Pexels"))
    return out[:n]


def search_pixabay(query: str, n: int) -> List[Candidate]:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    try:
        data = _get(
            "https://pixabay.com/api/videos/",
            params={"key": key, "q": query[:100], "per_page": max(3, n)},
        )
    except Exception:  # noqa: BLE001
        return []
    out = []
    for hit in data.get("hits") or []:
        sizes = hit.get("videos") or {}
        url = next(
            (
                (sizes.get(s) or {}).get("url")
                for s in ("large", "medium", "small")
                if (sizes.get(s) or {}).get("url")
            ),
            "",
        )
        if url:
            out.append(
                Candidate(url, "pixabay", hit.get("user", ""), "Licencia de Pixabay")
            )
    return out[:n]


def search_commons(query: str, n: int) -> List[Candidate]:
    try:
        data = _get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                "gsrsearch": f"{query[:80]} filetype:video", "gsrlimit": n * 2,
                "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
            },
        )  # fmt: skip
    except Exception:  # noqa: BLE001
        return []
    out = []
    for page in (data.get("query") or {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        if not str(info.get("mime", "")).startswith("video/"):
            continue
        artist = re.sub(
            r"<[^>]+>", "", str((meta.get("Artist") or {}).get("value", ""))
        )[:80]
        licence = str((meta.get("LicenseShortName") or {}).get("value", ""))
        out.append(
            Candidate(
                info.get("url", ""), "commons", artist, licence or "Wikimedia Commons"
            )
        )
    return [c for c in out if c.url][:n]


def search_nasa(query: str, n: int) -> List[Candidate]:
    try:
        data = _get(
            "https://images-api.nasa.gov/search",
            params={"q": query[:80], "media_type": "video"},
        )
    except Exception:  # noqa: BLE001
        return []
    out = []
    for item in ((data.get("collection") or {}).get("items") or [])[: n * 2]:
        try:
            files = _get(item["href"])
        except Exception:  # noqa: BLE001
            continue
        mp4 = next((f for f in files if f.endswith("~orig.mp4")), "") or next(
            (f for f in files if f.endswith(".mp4")), ""
        )
        if mp4:
            out.append(
                Candidate(
                    mp4.replace("http://", "https://"),
                    "nasa",
                    "NASA",
                    "Dominio público (NASA)",
                )
            )
        if len(out) >= n:
            break
    return out


def search_archive(query: str, n: int) -> List[Candidate]:
    """Public-domain films and newsreels of the Internet Archive."""
    free = "(collection:prelinger OR collection:feature_films OR licenseurl:*publicdomain*)"
    q = f"({query[:80]}) AND mediatype:movies AND {free}"
    try:
        data = _get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": q,
                "fl[]": ["identifier", "title", "licenseurl"],
                "rows": n * 2,
                "output": "json",
            },
        )
    except Exception:  # noqa: BLE001
        return []
    out = []
    for doc in (data.get("response") or {}).get("docs", [])[: n * 2]:
        ident = doc.get("identifier")
        try:
            meta = _get(f"https://archive.org/metadata/{ident}")
        except Exception:  # noqa: BLE001
            continue
        files = [
            f
            for f in meta.get("files") or []
            if str(f.get("name", "")).lower().endswith(".mp4")
        ]
        if not files:
            continue
        length = (
            float(files[0].get("length") or 0)
            if str(files[0].get("length", "")).replace(".", "").isdigit()
            else 0
        )
        out.append(
            Candidate(
                f"https://archive.org/download/{ident}/{files[0]['name']}",
                "archive",
                str(doc.get("title") or ident)[:80],
                "Dominio público (Internet Archive)",
                start=round(length * 0.3, 1) if length > 30 else 0.0,
            )
        )
        if len(out) >= n:
            break
    return out


def ytdlp() -> List[str]:
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    try:
        import sys

        import yt_dlp  # noqa: F401

        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        return []


def search_web(
    query: str, n: int, runner: Optional[Callable[[List[str]], str]] = None
) -> List[Candidate]:
    """Clips from YouTube and the other sites yt-dlp reads (no download yet)."""
    cmd = ytdlp()
    if not web_allowed() or not (cmd or runner):
        return []
    args = cmd + [
        "--dump-json",
        "--flat-playlist",
        "--no-warnings",
        f"ytsearch{n * 2}:{query[:90]}",
    ]
    try:
        text = (
            runner(args)
            if runner
            else subprocess.run(args, capture_output=True, text=True, timeout=90).stdout
        )
    except Exception:  # noqa: BLE001
        return []
    out = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        dur = float(item.get("duration") or 0)
        if not item.get("url") and not item.get("id"):
            continue
        if dur and (dur < 6 or dur > 3 * 3600):
            continue
        url = item.get("url") or f"https://www.youtube.com/watch?v={item['id']}"
        start = round(dur * 0.35, 1) if dur > 20 else 0.0  # skip intros and logos
        out.append(
            Candidate(
                url,
                "web",
                str(item.get("channel") or item.get("uploader") or "")[:80],
                "Uso con cita (no libre)",
                start,
            )
        )
        if len(out) >= n:
            break
    return out


SCENE_WORDS = ("movie scene", "film clip", "series scene")


def search_scenes(
    query: str, n: int, runner: Optional[Callable[[List[str]], str]] = None
) -> List[Candidate]:
    """A scene of a film or a series that shows the idea (official clip
    channels and trailers on YouTube, found with yt-dlp). Same rule as web
    clips: a few seconds, credited, and the posting package warns that the
    owner of the film can claim it."""
    out: List[Candidate] = []
    for words in SCENE_WORDS[:2]:
        if len(out) >= n:
            break
        for c in search_web(f"{query[:70]} {words}", n - len(out), runner):
            if all(c.url != o.url for o in out):
                c.source, c.licence = (
                    "web",
                    "Escena de película o serie: uso con cita (no libre)",
                )
                out.append(c)
    return out[:n]


# -- fetching ------------------------------------------------------------------------------


def fetch(c: Candidate, dest: Path, seconds: float, ffmpeg: str) -> Optional[str]:
    """The *seconds* the shot needs, cut and saved as a small mp4."""
    if c.path and Path(c.path).exists():
        return c.path
    tag = hashlib.sha1(
        f"{c.url}|{c.start}|{seconds:.1f}".encode(), usedforsecurity=False
    ).hexdigest()[:12]
    out = dest / f"{c.source}-{tag}.mp4"
    if out.exists() and out.stat().st_size > 5000:
        c.path = str(out)
        return c.path
    dest.mkdir(parents=True, exist_ok=True)
    length = max(1.5, min(seconds + 0.6, 12.0))
    try:
        if c.source == "web":
            base = ytdlp()
            if not base:
                return None
            raw = dest / f"web-{tag}.%(ext)s"
            subprocess.run(
                base + ["-q", "--no-warnings", "--no-playlist",
                        "-f", "bv*[height<=1080][ext=mp4]/bv*[height<=1080]/best",
                        "--download-sections", f"*{c.start:.1f}-{c.start + length:.1f}", "-o", str(raw), c.url],
                check=True, capture_output=True, timeout=240,
            )  # fmt: skip
            got = next(iter(sorted(dest.glob(f"web-{tag}.*"))), None)
            if got is None:
                return None
            src, start = str(got), 0.0
        else:
            src, start = c.url, c.start
        cmd = [ffmpeg, "-y", "-v", "error"]
        if start:
            cmd += ["-ss", f"{start:.2f}"]
        cmd += ["-i", src, "-t", f"{length:.2f}", "-an", "-vf", "scale=-2:'min(1080,ih)'",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]  # fmt: skip
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        if c.source == "web":
            Path(src).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 — the next candidate
        out.unlink(missing_ok=True)
        return None
    if not out.exists() or out.stat().st_size < 5000:
        return None
    c.path = str(out)
    return c.path


SEARCHES = {
    "stock": lambda q, n, landscape: (
        search_pexels(q, n, landscape) + search_pixabay(q, n)
    ),
    "commons": lambda q, n, landscape: search_commons(q, n),
    "nasa": lambda q, n, landscape: search_nasa(q, n),
    "archive": lambda q, n, landscape: search_archive(q, n),
    "web": lambda q, n, landscape: search_web(q, n),
    "film": lambda q, n, landscape: search_scenes(q, n),
}


def find(
    query: str,
    n: int,
    *,
    order: Iterable[str] = ("stock", "commons", "nasa", "archive", "web"),
    landscape: bool = True,
    searches: Optional[Dict[str, Callable[..., List[Candidate]]]] = None,
) -> List[Candidate]:
    """Up to *n* candidates for a shot, from the first sources that have them."""
    table = SEARCHES if searches is None else searches
    out: List[Candidate] = []
    for name in order:
        if name not in table or len(out) >= n:
            continue
        try:
            out += table[name](query, n - len(out), landscape)
        except Exception:  # noqa: BLE001
            continue
    return out[:n]


CHOOSE_PROMPT = """You are the film editor choosing footage. For each numbered row of the \
sheet (one row per shot) pick the candidate (A, B, C…, left to right) that shows the \
shot's idea best, looks most cinematic, has no watermark, logo or burned-in text, and \
fits the style. Shots:
{shots}
Answer ONLY JSON: {{"picks": {{"row number": "letter"}}}}"""


def choose(
    rows: List[Dict[str, Any]], ask: Callable[[List[Any], str], str]
) -> Dict[int, int]:
    """{row: candidate index} chosen by an editor from a sheet of frames.

    *rows*: [{"shot": text, "frames": [PIL images]}]."""
    from PIL import Image, ImageDraw

    if not rows:
        return {}
    w, h, cols = 240, 135, max(len(r["frames"]) for r in rows)
    sheet = Image.new("RGB", (40 + w * cols, h * len(rows)), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for i, row in enumerate(rows):
        d.text((6, i * h + 6), str(i), fill=(255, 255, 255), font_size=20)
        for k, frame in enumerate(row["frames"]):
            sheet.paste(frame.convert("RGB").resize((w, h)), (40 + k * w, i * h))
            d.text(
                (44 + k * w, i * h + 4), "ABCDEFGH"[k], fill=(255, 255, 0), font_size=18
            )
    import io

    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=80)
    text = ask(
        [buf.getvalue()],
        CHOOSE_PROMPT.format(
            shots="\n".join(f"{i}: {r['shot'][:120]}" for i, r in enumerate(rows))
        ),
    )
    try:
        picks = json.loads(text).get("picks") or {}
    except (ValueError, AttributeError):
        return {}
    out = {}
    for row, letter in picks.items():
        try:
            i, k = int(row), "ABCDEFGH".index(str(letter).strip().upper()[:1])
        except (ValueError, TypeError):
            continue
        if 0 <= i < len(rows) and k < len(rows[i]["frames"]):
            out[i] = k
    return out


def frame_of(path: str, ffmpeg: str, at: float = 0.5) -> Any:
    """One frame of a clip (or the picture itself)."""
    from PIL import Image

    p = Path(path)
    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        return Image.open(p).convert("RGB")
    import io

    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-ss", f"{at:.2f}", "-i", str(p), "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, timeout=60,
    ).stdout  # fmt: skip
    return (
        Image.open(io.BytesIO(raw)).convert("RGB")
        if raw
        else Image.new("RGB", (320, 180))
    )


def credits_text(items: Iterable[Dict[str, Any]]) -> str:
    """The credits for the description, one line per source used."""
    seen, lines = set(), []
    for c in items:
        if c.get("source") == "library":
            continue
        key = (c.get("source"), c.get("url"))
        if key in seen:
            continue
        seen.add(key)
        who = f"{c.get('credit')} — " if c.get("credit") else ""
        if c.get("kind") == "música":
            who = "Música: " + who
        lines.append(f"{who}{c.get('licence', '')}: {c.get('url', '')}")
    return "\n".join(lines)


__all__ = [
    "Candidate", "SEARCHES", "choose", "credits_text", "fetch", "find", "frame_of", "own_folders",
    "search_archive", "search_commons", "search_nasa", "search_pexels", "search_pixabay", "search_scenes", "search_web",
    "web_allowed", "ytdlp",
]  # fmt: skip
