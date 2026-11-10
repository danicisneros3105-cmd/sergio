"""Sergio's school: the owner's reference videos, watched second by second.

The owner (2 Nov 2026): «quiero que encuentres la forma de que Sergio vea y
analice cada segundo de ellos cuidadosamente … crear superskills … para que
cree videos exactamente con el mismo estilo». The links live in
``referencias.json`` by category (viral Shorts, animation, entertaining
explainers). For each one, on the owner's PC:

1. **Download** it with yt-dlp, only to study it (``~/.openjarvis/escuela/``).
   Instagram may need his own browser session: ``SERGIO_NAVEGADOR`` (edge,
   chrome, firefox) lends yt-dlp the cookies of the browser where he is
   already signed in. Nothing is downloaded around a login wall otherwise.
2. **Measure every second by code** (:func:`measure`): the cuts (4 frames a
   second), how long each shot lasts, cuts per second, brightness, colour,
   motion, faces, where words sit on the screen, loudness, hits and
   whooshes (sharp jumps in the sound), and words per second with their
   times (faster-whisper, when it is installed).
3. **Watch it with a model** (``style.watch``: every shot with its text
   style, effect, transition and sound), when a Gemini key is there.
4. **Write the superskill** of the category (:func:`synthesize`): the
   numbers of all its videos together (medians, the first three seconds
   apart) and the rules a model writes from them, saved as a style
   (``ref-<category>``) and a ``SKILL.md`` that goes into the script and the
   edit of every video of that kind.
5. **Train the school's own brain** (a fly mushroom body like the other
   specialists): it learns from the reference titles which category a new
   order belongs to, and is measured on a title it never saw.

**Channels** (owner, 2 Nov 2026: «mira sus últimos 20 videos a 30 fps; la
luz, el contraste, las sombras, el movimiento, los efectos, el corte, todo;
transcribe cómo está escrito el guion»): a category may list ``canales``;
the school asks yt-dlp for the latest ``ultimos`` of each (``pestana``:
shorts or videos) and studies them like the links. A category may also set
``fps`` (30 for those): frames are read one second at a time, never the whole
video in memory, so a 30-minute essay at 30 fps fits. Measured too: light
(brightness, contrast, deep shadows, blown highlights, warm or cool grade,
vignette), the camera (pans and shake, by phase correlation between
frames), effects (flashes, black frames) and the **script** (words per
minute, hook, sentence length, questions, turns, open loops, pauses and the
ending) from the transcription.

Only how they are edited is learned, never their footage, voices, drawings
or words. In the public edition (``SERGIO_EDICION=publica``) nothing is
downloaded: studying other people's channels is the owner's own choice.
The language models (Gemini, GPT, Claude…) are not retrained: they receive
the superskill in every video. Sergio's own local brains do
change their weights.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import statistics
import subprocess
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

REFERENCES = Path(__file__).parent / "referencias.json"
FPS = 4  # frames measured per second (cuts are found between them)
_lock = threading.Lock()
_running: Dict[str, Any] = {}


# -- where things live ------------------------------------------------------------------------


def home() -> Path:
    from openjarvis.core.paths import get_config_dir

    return Path(get_config_dir()) / "escuela"


def references(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """The owner's categories with their links (duplicates removed)."""
    data = json.loads((path or REFERENCES).read_text("utf-8"))
    cats = dict(data.get("categorias") or {})
    if path is None:  # the links he adds later live on his PC (agregar)
        try:
            mine = (
                json.loads((home() / "referencias.json").read_text("utf-8")).get(
                    "categorias"
                )
                or {}
            )
        except (OSError, ValueError):
            mine = {}
        for key, cat in mine.items():
            base = dict(
                cats.get(key)
                or {
                    "nombre": cat.get("nombre") or key,
                    "generos": cat.get("generos") or [],
                }
            )
            base["links"] = list(base.get("links") or []) + list(cat.get("links") or [])
            seen = {c.get("url") for c in base.get("canales") or []}
            base["canales"] = list(base.get("canales") or []) + [
                c for c in cat.get("canales") or [] if c.get("url") not in seen
            ]
            if cat.get("fps"):
                base["fps"] = cat["fps"]
            cats[key] = base
    out = {}
    for key, cat in cats.items():
        links = list(dict.fromkeys(clean_link(u) for u in cat.get("links") or [] if u))
        out[key] = {**cat, "links": links}
    return out


def clean_link(url: str) -> str:
    """One form per video: Shorts/watch ids without playlists, Instagram
    without the language parameter."""
    url = url.strip()
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([\w-]{11})", url)
    if m and "youtu" in url:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    m = re.search(r"instagram\.com/(reels?|p)/([\w-]+)", url)
    if m:
        kind = "p" if m.group(1) == "p" else "reel"
        return f"https://www.instagram.com/{kind}/{m.group(2)}/"
    return url.split("&")[0]


def add(
    links: Sequence[str], category: str, name: str = "", genres: Sequence[str] = ()
) -> Dict[str, Any]:
    """More reference links for a category (new or existing), on this PC."""
    path = home() / "referencias.json"
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        data = {"categorias": {}}
    key = (
        re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")[:40]
        or "mis-referencias"
    )
    cat = data["categorias"].setdefault(
        key, {"nombre": name or category, "generos": list(genres), "links": []}
    )
    channel = re.compile(
        r"^https://(www\.)?youtube\.com/@[\w.-]+(/(shorts|videos))?/?$"
    )
    chans = [str(u).strip() for u in links if channel.match(str(u).strip())]
    new = [
        clean_link(u)
        for u in links
        if re.match(r"https?://", str(u).strip()) and str(u).strip() not in chans
    ]
    cat["links"] = list(dict.fromkeys(cat["links"] + new))
    for u in chans:  # a channel: its latest 20, at 30 fps
        url = re.sub(r"/(shorts|videos)?/?$", "", u)
        tab = "shorts" if u.rstrip("/").endswith("/shorts") else "videos"
        known = {c["url"] for c in cat.setdefault("canales", [])}
        if url not in known:
            cat["canales"].append({"url": url, "pestana": tab, "ultimos": 20})
        cat["fps"] = 30
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    return {"categoria": key, "agregados": len(new) + len(chans)}


def video_id(url: str) -> str:
    m = re.search(r"(?:v=|reels?/|/p/)([\w-]+)", url)
    return m.group(1) if m else re.sub(r"\W+", "-", url)[-24:]


# -- 0. a channel's latest videos -------------------------------------------------------------

CHANNEL_TTL_S = 24 * 3600


def _list_ids(
    url: str,
    n: int,
    run: Optional[Callable[[List[str]], str]] = None,
    max_min: float = 0.0,
) -> List[str]:
    """The ids of the first *n* entries of a channel tab, newest first; those
    longer than *max_min* minutes are left out (a 3-hour compilation is not
    studied: it would be gigabytes for one lesson)."""
    from openjarvis.video_essay.sources import ytdlp

    cmd = ytdlp()
    if not cmd and run is None:
        raise RuntimeError("falta yt-dlp (la actualización lo instala)")
    args = (cmd or ["yt-dlp"]) + ["--no-warnings", "--flat-playlist", "--playlist-end", str(n),
                                  "--print", "%(id)s %(duration)s", url]  # fmt: skip
    out = (
        run(args)
        if run
        else subprocess.run(args, capture_output=True, text=True, timeout=180).stdout
    )
    ids: List[str] = []
    for ln in str(out).splitlines():
        vid, _, dur = ln.strip().partition(" ")
        if not re.fullmatch(r"[\w-]{11}", vid):
            continue
        try:
            long = bool(max_min) and float(dur) / 60 > max_min
        except ValueError:  # no duration (a live, a premiere): it stays
            long = False
        if not long:
            ids.append(vid)
    return list(dict.fromkeys(ids))[:n]


def channel_links(
    channel: Dict[str, Any],
    *,
    root: Optional[Path] = None,
    run: Optional[Callable[[List[str]], str]] = None,
    refresh: bool = False,
) -> List[str]:
    """The latest ``ultimos`` videos of a channel (its ``pestana`` first:
    shorts or videos; the other one if that is empty), kept a day."""
    url = str(channel.get("url") or "").rstrip("/")
    if not re.match(r"https://(www\.)?youtube\.com/@[\w.-]+$", url):
        raise ValueError(f"canal no válido: {url}")
    n = max(1, min(50, int(channel.get("ultimos") or 20)))
    max_min = float(channel.get("max_minutos") or 0)
    tab = str(channel.get("pestana") or "videos")
    strict = bool(channel.get("solo_pestana"))
    slug = re.sub(r"[^\w.-]+", "-", url.rsplit("/", 1)[-1])
    scope = "-solo" if strict else ""
    cache = (
        (root or home()) / "canales" / f"{slug}-{tab}-{n}-{int(max_min)}{scope}.json"
    )
    try:
        saved = json.loads(cache.read_text("utf-8"))
        if (
            not refresh
            and time.time() - float(saved.get("at") or 0) < CHANNEL_TTL_S
            and saved.get("links")
        ):
            return list(saved["links"])
    except (OSError, ValueError):
        pass
    ids: List[str] = []
    for t in [tab] + ([] if strict else [x for x in ("videos", "shorts") if x != tab]):
        # ask for more than n when long ones are skipped, so n short ones remain
        ids = _list_ids(f"{url}/{t}", n + 12 if max_min else n, run, max_min)
        if ids:
            break
    links = [f"https://www.youtube.com/watch?v={i}" for i in ids]
    if links:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"at": time.time(), "links": links}), "utf-8")
    return links


def links_of(cat: Dict[str, Any], **kw: Any) -> List[str]:
    """A category's own links plus the latest videos of its channels."""
    out = list(cat.get("links") or [])
    for ch in cat.get("canales") or []:
        out += channel_links(ch, **kw)
    return list(dict.fromkeys(clean_link(u) for u in out))


# -- 1. download ------------------------------------------------------------------------------


def download(
    url: str, dest: Path, runner: Optional[Callable[[List[str]], int]] = None
) -> Path:
    """The video, once, for study only."""
    from openjarvis import edicion
    from openjarvis.video_essay.sources import ytdlp

    if edicion.publica():  # other people's videos: never for customers
        raise RuntimeError("la escuela no descarga videos ajenos en la edición pública")

    dest.mkdir(parents=True, exist_ok=True)
    vid = video_id(url)
    have = sorted(dest.glob(f"{vid}.*"))
    have = [p for p in have if p.suffix in (".mp4", ".mkv", ".webm", ".mov")]
    if have:
        return have[0]
    cmd = ytdlp()
    if not cmd and runner is None:
        raise RuntimeError("falta yt-dlp (la actualización lo instala)")
    args = cmd + ["--no-warnings", "--no-playlist", "--write-info-json", "-f",
                  "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
                  "-o", str(dest / f"{vid}.%(ext)s"), url]  # fmt: skip
    try:
        args[len(cmd) : len(cmd)] = ["--ffmpeg-location", _ffmpeg()]
    except RuntimeError:
        pass
    browser = os.environ.get("SERGIO_NAVEGADOR", "").strip()
    if browser and "instagram.com" in url:
        args[len(cmd) : len(cmd)] = ["--cookies-from-browser", browser]
    code = (
        runner(args)
        if runner
        else subprocess.run(args, capture_output=True, timeout=900).returncode
    )
    found = [
        p
        for p in sorted(dest.glob(f"{vid}.*"))
        if p.suffix in (".mp4", ".mkv", ".webm", ".mov")
    ]
    if code != 0 or not found:
        hint = (
            " Instagram pide sesión: ponga SERGIO_NAVEGADOR=edge (o chrome) en sergio.env."
            if "instagram.com" in url and not browser
            else ""
        )
        raise RuntimeError(f"no se pudo descargar {url}.{hint}")
    return found[0]


# -- 2. every second, measured by code ----------------------------------------------------------


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    from openjarvis.video_essay.render import ffmpeg

    return ffmpeg()


def _probe(path: Path) -> Dict[str, float]:
    exe = shutil.which("ffprobe")
    if exe:
        out = subprocess.run(
            [exe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60,
        ).stdout  # fmt: skip
        data = json.loads(out or "{}")
        st = (data.get("streams") or [{}])[0]
        num, _, den = str(st.get("r_frame_rate") or "30/1").partition("/")
        return {
            "w": float(st.get("width") or 0),
            "h": float(st.get("height") or 0),
            "fps": round(float(num) / float(den or 1), 2) if float(den or 1) else 30.0,
            "dur": float((data.get("format") or {}).get("duration") or 0),
        }

    # imageio-ffmpeg ships FFmpeg without ffprobe. Its input report contains
    # the same measurements needed here; a zero exit is not expected with -i alone.
    report = subprocess.run(
        [_ffmpeg(), "-i", str(path)], capture_output=True, text=True, timeout=60
    ).stderr
    duration = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", report)
    dimensions = re.search(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b", report)
    rate = re.search(r"\b(\d+(?:\.\d+)?)\s*fps\b", report)
    if not duration or not dimensions:
        raise RuntimeError(f"no se pudieron medir las propiedades de {path.name}")
    hours, minutes, seconds = duration.groups()
    return {
        "w": float(dimensions.group(1)),
        "h": float(dimensions.group(2)),
        "fps": float(rate.group(1)) if rate else 30.0,
        "dur": int(hours) * 3600 + int(minutes) * 60 + float(seconds),
    }


def _frames(path: Path, w: int, h: int, fps: int, ffmpeg: str) -> Any:
    import numpy as np

    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=1800,
    ).stdout  # fmt: skip
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], dtype=np.uint8).reshape(n, h, w, 3)


def _chunks(path: Path, w: int, h: int, fps: int, ffmpeg: str) -> Any:
    """The frames one second at a time (never the whole video in memory)."""
    import numpy as np

    size = w * h * 3
    proc = subprocess.Popen(
        [ffmpeg, "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        while True:
            raw = proc.stdout.read(size * fps) if proc.stdout else b""
            n = len(raw) // size
            if not n:
                if proc.wait(timeout=30):
                    raise RuntimeError(f"no se pudo decodificar el video: {path.name}")
                break
            yield np.frombuffer(raw[: n * size], dtype=np.uint8).reshape(n, h, w, 3)
    finally:
        if proc.stdout:
            proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=30)


def _hist(f: Any) -> Any:
    import numpy as np

    q = (f // 32).reshape(-1, 3).astype("int32")
    h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(
        "float32"
    )
    return h / max(1.0, float(h.sum()))


def _cut_times(
    d: Sequence[float], fps: int, spatial: Sequence[float] = ()
) -> List[float]:
    """Hard cuts from colour jumps or abrupt changes in the layout."""
    import numpy as np

    if not len(d):
        return []
    d = np.asarray(d, dtype="float32")
    thr = max(
        0.32, float(np.median(d) + 4 * (np.median(np.abs(d - np.median(d))) + 1e-6))
    )
    out: List[float] = []
    for i, v in enumerate(d, start=1):
        changed = False
        if spatial and spatial[i - 1] >= 0.14:
            nearby = [*spatial[max(0, i - 4) : i - 1], *spatial[i : i + 3]]
            changed = bool(nearby) and spatial[i - 1] >= 3 * float(np.median(nearby))
        if (v >= thr or changed) and (not out or i / fps - out[-1] >= 0.2):
            out.append(round(i / fps, 5))
    return out


LUMA = (0.2126, 0.7152, 0.0722)


def light_of(f: Any) -> Dict[str, float]:
    """How a frame is lit: brightness, contrast (p95 - p5 of the light), deep
    shadows and blown highlights (share of the picture), warm or cool
    (red minus blue) and the vignette (centre against corners; > 1 = darker
    corners)."""
    import numpy as np

    rgb = f.astype("float32") / 255
    y = rgb @ np.asarray(LUMA, dtype="float32")
    h, w = y.shape
    ch, cw = max(1, h // 5), max(1, w // 5)
    corners = np.concatenate(
        [
            y[:ch, :cw].ravel(),
            y[:ch, -cw:].ravel(),
            y[-ch:, :cw].ravel(),
            y[-ch:, -cw:].ravel(),
        ]
    )
    centre = y[h // 3 : 2 * h // 3, w // 3 : 2 * w // 3]
    p5, p95 = np.percentile(y, [5, 95])
    return {
        "brillo": round(float(y.mean()), 3),
        "contraste": round(float(p95 - p5), 3),
        "sombras": round(float((y < 0.15).mean()), 3),
        "luces": round(float((y > 0.92).mean()), 3),
        "calidez": round(float(rgb[..., 0].mean() - rgb[..., 2].mean()), 3),
        "vineta": round(float(centre.mean() / max(0.02, float(corners.mean()))), 2),
    }


def _shift(a: Any, b: Any) -> tuple:
    """How far the picture moved between two grey frames (phase correlation),
    as a share of its width and height."""
    import numpy as np

    h, w = a.shape
    win = np.outer(np.hanning(h), np.hanning(w)).astype("float32")
    fa, fb = np.fft.rfft2(a * win), np.fft.rfft2(b * win)
    r = fa * np.conj(fb)
    r /= np.abs(r) + 1e-9
    corr = np.fft.irfft2(r, s=(h, w))
    y, x = np.unravel_index(int(np.argmax(corr)), corr.shape)
    y = y - h if y > h // 2 else y
    x = x - w if x > w // 2 else x
    return x / w, y / h


def _audio(path: Path, ffmpeg: str, rate: int = 8000) -> Any:
    import numpy as np

    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        capture_output=True, timeout=900,
    ).stdout  # fmt: skip
    return (
        np.frombuffer(raw[: len(raw) // 2 * 2], dtype=np.int16).astype("float32")
        / 32768.0
    )


def cuts_of(frames: Any, fps: int = FPS) -> List[float]:
    """Times of the hard cuts: colour histograms that jump far more than
    the motion around them."""
    import numpy as np

    if len(frames) < 2:
        return []
    hist = [_hist(f) for f in frames]
    d = [float(0.5 * np.abs(hist[i] - hist[i - 1]).sum()) for i in range(1, len(hist))]
    spatial = [
        float(np.abs(b.astype("int16") - a).mean() / 255)
        for a, b in zip(frames, frames[1:])
    ]
    return _cut_times(d, fps, spatial)


def text_rows(gray: Any) -> Dict[str, float]:
    """Where words seem to sit (top, middle, bottom): rows crossed by many
    sharp light/dark edges, as letters make. An estimate, not OCR."""
    import numpy as np

    g = gray.astype("float32")
    dx = np.abs(np.diff(g, axis=1)) > 60
    dens = dx.mean(axis=1)
    # letter rows stand out from the picture's own texture
    line = max(0.05, 3 * float(np.median(dens)))
    h = len(dens)
    out = {}
    for name, (a, b) in {
        "arriba": (0.05, 0.35),
        "centro": (0.35, 0.65),
        "abajo": (0.65, 0.95),
    }.items():
        band = dens[int(a * h) : int(b * h)]
        out[name] = float((band > line).mean()) if len(band) else 0.0
    return out


_SECOND_PERSON = re.compile(
    r"\b(you|your|you're|yourself|tú|tu|te|ti|usted|ustedes|vos)\b", re.I
)
_TURNS = re.compile(
    r"\b(but|however|until|except|instead|actually|turns out|pero|sin embargo|hasta que|en cambio|resulta)\b",
    re.I,
)
_LOOPS = re.compile(
    r"(here's|here is|wait|what happened next|but first|stay|watch|by the end|keep watching|la clave|espera|"
    r"lo que pasó|quédate|al final|mira esto)",
    re.I,
)
_NUMBER = re.compile(
    r"(\d|\b(one|two|three|four|five|ten|hundred|thousand|million|billion|uno|dos|tres|cuatro|cinco|diez|"
    r"cien|mil|millón|millones)\b)",
    re.I,
)


def script_of(words: Sequence[Dict[str, Any]], dur: float) -> Dict[str, Any]:
    """How the script is written, from the timed words: pace, hook, sentence
    length, questions, talking to «you», turns, open loops, numbers, pauses,
    parts and the ending. Their words stay on this PC; only the numbers and
    the shape go into the superskill."""
    ws = [w for w in words if str(w.get("w") or "").strip()]
    if not ws:
        return {}
    minutes = max(1 / 60, dur / 60)
    sentences: List[List[str]] = [[]]
    for w in ws:
        sentences[-1].append(str(w["w"]))
        if re.search(r"[.!?…]$", str(w["w"])):
            sentences.append([])
    sentences = [x for x in sentences if x]
    text = " ".join(str(w["w"]) for w in ws)
    times = [float(w.get("t") or 0) for w in ws]
    gaps = [b - a for a, b in zip(times, times[1:])]
    parts = 1 + sum(1 for g in gaps if g > 1.5)
    first = " ".join(sentences[0]) if sentences else ""
    return {
        "palabras_por_minuto": round(len(ws) / minutes, 1),
        "frase_mediana": statistics.median(len(x) for x in sentences)
        if sentences
        else 0,
        "frases": len(sentences),
        "preguntas_por_min": round(
            sum(1 for x in sentences if x[-1].endswith("?")) / minutes, 2
        ),
        "tu_por_frase": round(
            len(_SECOND_PERSON.findall(text)) / max(1, len(sentences)), 2
        ),
        "giros_por_min": round(len(_TURNS.findall(text)) / minutes, 2),
        "lazos_por_min": round(len(_LOOPS.findall(text)) / minutes, 2),
        "numeros_por_min": round(len(_NUMBER.findall(text)) / minutes, 2),
        "pausas_por_min": round(sum(1 for g in gaps if g > 0.8) / minutes, 2),
        "partes": parts,
        "primera_frase": first[:200],
        "primera_frase_palabras": len(first.split()),
        "final": " ".join(str(w["w"]) for w in ws[-20:])[:200],
    }


# -- what kind of editing (owner, 3 Nov 2026: «mejora el análisis de los cuatro
# canales y su tipo de edición»). Four channels, four grammars: flat animation
# with captions, moving type, a documentary of maps and archive, a first-person
# vlog of punch-ins. These numbers tell them apart.

ZOOMS = (0.94, 0.97, 1.0, 1.03, 1.06)
PUNCH = (1.15, 1.3, 1.5)


def _zoomed(gray: Any, s: float) -> Any:
    """*gray* seen through a lens *s* times closer (s > 1) or farther, same size."""
    import numpy as np

    h, w = gray.shape
    ys = np.clip(((np.arange(h) - h / 2) / s + h / 2).round().astype(int), 0, h - 1)
    xs = np.clip(((np.arange(w) - w / 2) / s + w / 2).round().astype(int), 0, w - 1)
    return gray[ys][:, xs]


def scale_between(a: Any, b: Any) -> float:
    """How much closer *b* is than *a* (1.03 = a 3 % push in). Grey frames, no cut."""
    import numpy as np

    m = max(2, a.shape[0] // 8), max(2, a.shape[1] // 8)  # leave the edges out
    errs = {
        s: float(
            np.abs(
                _zoomed(a, s)[m[0] : -m[0], m[1] : -m[1]]
                - b[m[0] : -m[0], m[1] : -m[1]]
            ).mean()
        )
        for s in ZOOMS
    }
    best = min(errs, key=errs.get)
    # only a clear win counts: a sideways move or a moving object is not a zoom
    return best if errs[best] < 0.8 * errs[1.0] else 1.0


def punch_in(before: Any, after: Any) -> bool:
    """A cut that only moves closer to the same picture (the vlog «punch-in»):
    the frame after the cut is the frame before, magnified."""
    import numpy as np

    flat = float(np.abs(after - before).mean())
    for s in PUNCH:
        e = float(np.abs(_zoomed(before, s) - after).mean())
        if e < 0.6 * flat and e < 0.06:
            return True
    return False


def flatness(rgb: Any) -> float:
    """Share of the picture in perfectly even areas. Drawn, flat animation and
    graphics are mostly even; filmed footage almost never is (grain, light)."""
    import numpy as np

    g = rgb.astype("int16")
    dx = np.abs(np.diff(g, axis=1)).max(axis=2)[:-1, :]
    dy = np.abs(np.diff(g, axis=0)).max(axis=2)[:, :-1]
    return float(((dx <= 2) & (dy <= 2)).mean())


def kind_of_shot(rgb: Any, faces: int, text: Dict[str, float]) -> str:
    """cara (someone talking to camera), texto (a card of words), grafico (flat
    drawing, map or animation) or real (filmed footage)."""
    flat = flatness(rgb)
    words = max(text.values()) if text else 0.0
    if words >= 0.12 and flat >= 0.45:
        return "texto"
    if flat >= 0.55:
        return "grafico"
    if faces:
        return "cara"
    return "real"


def rhythm(cuts: Sequence[float], dur: float, parts: int = 10) -> List[float]:
    """Cuts per second in each tenth of the video: where the edit speeds up."""
    if dur <= 0:
        return []
    step = dur / parts
    return [
        round(sum(1 for c in cuts if i * step <= c < (i + 1) * step) / step, 2)
        for i in range(parts)
    ]


def on_hits(cuts: Sequence[float], hits: Sequence[float], tol: float = 0.12) -> float:
    """Share of cuts that land on a sound hit (a whoosh, a drum, a click)."""
    if not cuts:
        return 0.0
    import bisect

    hs = sorted(hits)
    n = 0
    for c in cuts:
        i = bisect.bisect_left(hs, c - tol)
        if i < len(hs) and hs[i] <= c + tol:
            n += 1
    return round(n / len(cuts), 2)


def silences(words: Sequence[Dict[str, Any]], dur: float, gap: float = 1.2) -> float:
    """Pauses in the narration (no new word for *gap* s or more) per minute."""
    times = sorted(float(w.get("t", 0)) for w in words if w.get("t") is not None)
    if len(times) < 2 or dur <= 0:
        return 0.0
    n = sum(1 for a, b in zip(times, times[1:]) if b - a >= gap)
    return round(n / max(1 / 60, dur / 60), 2)


def editing_type(m: Dict[str, Any]) -> str:
    """One line that names the grammar, from the numbers."""
    planos = m.get("planos") or {}
    top = max(planos, key=planos.get) if planos else ""
    pace = m.get("toma_mediana_s") or 0
    bits = {
        "grafico": "animación o gráficos planos",
        "texto": "tipografía en movimiento",
        "cara": "a cámara, en primera persona",
        "real": "imagen filmada y de archivo",
    }
    out = [bits.get(top, "mixta")]
    out.append(
        "cortes muy rápidos"
        if pace and pace < 1.2
        else "cortes medios"
        if pace and pace < 3
        else "planos largos"
    )
    if (m.get("punch_ins_por_min") or 0) >= 2:
        out.append("acercamientos de golpe")
    if abs(m.get("zoom_medio") or 0) >= 0.01:
        out.append("zoom lento constante")
    if (m.get("cortes_en_golpe") or 0) >= 0.4:
        out.append("cortes sobre golpes de sonido")
    if (m.get("texto_en_pantalla") or 0) >= 0.5:
        out.append("texto casi siempre en pantalla")
    return ", ".join(out)


def measure(
    path: Path,
    *,
    words: Optional[List[Dict[str, Any]]] = None,
    fps: int = FPS,
) -> Dict[str, Any]:
    """Measure every sampled frame and aggregate its timeline by second.

    Frames are decoded one second at a time, so sampling a long video at 32 fps
    never requires holding the whole video in memory. Frame rows describe code
    measurements, not semantic labels invented for frames a model did not see.
    """
    import bisect

    import numpy as np

    from openjarvis.video_essay import color

    ffmpeg = _ffmpeg()
    meta = _probe(path)
    w = 96
    h = max(2, int(round(w * (meta["h"] or 16) / (meta["w"] or 9) / 2) * 2))
    audio = _audio(path, ffmpeg)
    rate = 8000
    if words is None:
        words, transcription_status = transcribe_detailed(path)
    else:
        transcription_status = "proporcionada"
    jumps: List[float] = []
    spatial: List[float] = []
    prev = None
    prev_hist = None
    prev_lum = None
    seconds: List[Dict[str, Any]] = []
    frame_rows: List[Dict[str, Any]] = []
    punches: List[float] = []
    hit_times: List[float] = []
    frames_seen = 0
    big_w = 360
    big_h = max(2, int(round(big_w * h / w / 2) * 2))
    big_chunks = _chunks(path, big_w, big_h, 1, ffmpeg)
    luma = np.asarray(LUMA, dtype="float32")
    for s, chunk in enumerate(_chunks(path, w, h, fps, ffmpeg)):
        frame_start = frames_seen
        frames_seen += len(chunk)
        has_prev = prev is not None
        offset = 1 if has_prev else 0
        for f in chunk:
            hist = _hist(f)
            if prev_hist is not None:
                jumps.append(float(0.5 * np.abs(hist - prev_hist).sum()))
            prev_hist = hist
        seq = chunk if not has_prev else np.concatenate([prev[None], chunk])
        prev = chunk[-1]
        f = chunk[len(chunk) // 2]
        hsv_s = (f.max(axis=2).astype("int16") - f.min(axis=2)).mean() / 255
        steps = (
            np.abs(np.diff(seq.astype("int16"), axis=0)).mean(axis=(1, 2, 3)) / 255
            if len(seq) > 1
            else np.zeros(1)
        )
        if len(seq) > 1:
            spatial.extend(steps.tolist())
        motion = float(np.median(steps))
        lum = (seq.astype("float32") / 255) @ luma
        means = lum.mean(axis=(1, 2))
        moves = [
            _shift(lum[i - 1], lum[i])
            for i in range(1, len(lum))
            if steps[i - 1] < 0.25
        ]
        speed = [abs(x) + abs(y) for x, y in moves]
        scales: List[float] = []
        scale_by_frame: Dict[int, float] = {}
        for i in range(1, len(lum)):
            if steps[i - 1] >= 0.25:
                continue
            scale = scale_between(lum[i - 1], lum[i])
            scales.append(scale)
            if scale != 1.0:
                scale_by_frame[frame_start + i - offset] = scale
        zoom = float(np.median([np.log(x) for x in scales])) * fps if scales else 0.0
        for i in range(1, len(lum)):
            if steps[i - 1] >= 0.25 and punch_in(lum[i - 1], lum[i]):
                punches.append(s + i / max(1, len(lum)))
        pan = float(np.median(speed)) * fps if speed else 0.0
        shake = float(np.std(np.diff(speed))) * fps if len(speed) > 2 else 0.0
        flashes = sum(
            1
            for i in range(1, len(means) - 1)
            if means[i] - means[i - 1] > 0.15
            and means[i] - means[min(i + 4, len(means) - 1)] > 0.1
        )
        blacks = (
            float((means[1 if prev_lum is not None else 0 :] < 0.04).mean())
            if len(means)
            else 0.0
        )
        prev_lum = means[-1]
        a = audio[s * rate : (s + 1) * rate]
        rms = float(np.sqrt((a**2).mean())) if len(a) else 0.0
        e = (
            (a[: len(a) // 160 * 160].reshape(-1, 160) ** 2).mean(axis=1)
            if len(a) >= 160
            else np.zeros(1)
        )
        avg = (
            np.asarray(
                [e[max(0, i - 4) : min(len(e), i + 5)].mean() for i in range(len(e))]
            )
            + 1e-7
        )
        loud = (e > 3 * avg) & (e > 1e-4)
        hits = int(loud.sum() // 2)
        hit_times.extend(
            s + i * 0.02 for i in np.flatnonzero(loud[1:] & ~loud[:-1]) + 1
        )
        for i in range(len(chunk)):
            index = frame_start + i
            start = round(index * rate / fps)
            end = round((index + 1) * rate / fps)
            frame_audio = audio[start:end]
            frame_rms = (
                float(np.sqrt((frame_audio**2).mean())) if len(frame_audio) else 0.0
            )
            frame_rows.append(
                {
                    "i": index,
                    "t": round(index / fps, 5),
                    "brillo": round(float(means[i + offset]), 4),
                    "cambio_color": round(jumps[index - 1], 4) if index else 0.0,
                    "cambio_visual": round(spatial[index - 1], 4) if index else 0.0,
                    "zoom": scale_by_frame.get(index, 1.0),
                    "volumen_db": round(20 * float(np.log10(frame_rms + 1e-6)), 1),
                }
            )
        try:
            from PIL import Image

            big_chunk = next(big_chunks)
            big = Image.fromarray(big_chunk[0])
            gray = np.asarray(big.convert("L"))
            faces = len(color._faces(gray))
            rows = text_rows(gray)
            main = color.hex_of(color.palette(big, 3)[0][0])
        except Exception:  # noqa: BLE001
            faces, rows, main = 0, {}, ""
        kind = kind_of_shot(f, faces, rows)
        said = [x["w"] for x in words if s <= float(x.get("t", -1)) < s + 1]
        light = light_of(f)
        seconds.append({
            "t": s, "cortes": 0,
            "brillo": round(float(f.mean() / 255), 3), "color": round(float(hsv_s), 3), "principal": main,
            "movimiento": round(motion, 3), "caras": faces, "plano": kind, "zoom": round(zoom, 3),
            "luz": light, "camara": round(pan, 3), "temblor": round(shake, 3),
            "destellos": flashes, "negro": round(blacks, 2),
            "texto": {k: round(v, 2) for k, v in rows.items()},
            "volumen_db": round(20 * float(np.log10(rms + 1e-6)), 1), "golpes": hits,
            "palabras": len(said), "dice": " ".join(said)[:120],
        })  # fmt: skip
    if not frames_seen:
        raise RuntimeError(f"el video no tiene fotogramas: {path.name}")
    dur = meta["dur"] or frames_seen / fps
    cuts = _cut_times(jumps, fps, spatial)
    cut_frames = {round(cut * fps) for cut in cuts}
    hit_times.sort()
    brightness = [float(row["brillo"]) for row in frame_rows]
    for i, row in enumerate(frame_rows):
        hit = bisect.bisect_left(hit_times, float(row["t"]) - 0.02)
        row["corte"] = i in cut_frames
        row["golpe"] = bool(
            hit < len(hit_times) and hit_times[hit] <= float(row["t"]) + 0.02
        )
        effects = []
        if row["zoom"] != 1.0:
            effects.append("zoom-in" if row["zoom"] > 1.0 else "zoom-out")
        if brightness[i] < 0.04:
            effects.append("negro")
        if (
            0 < i < len(frame_rows) - 1
            and brightness[i] - brightness[i - 1] > 0.15
            and brightness[i] - brightness[min(i + 4, len(frame_rows) - 1)] > 0.1
        ):
            effects.append("destello")
        row["efecto_visual"] = ",".join(effects)
    for sec in seconds:
        sec["cortes"] = sum(1 for c in cuts if sec["t"] <= c < sec["t"] + 1)
    bounds = [0.0, *cuts, round(dur, 2)]
    shots = [round(b - a, 2) for a, b in zip(bounds, bounds[1:]) if b - a > 0.05]
    text_on = [s for s in seconds if max((s["texto"] or {"x": 0}).values()) >= 0.08]
    where = {}
    for s in text_on:
        best = max(s["texto"], key=s["texto"].get)
        where[best] = where.get(best, 0) + 1
    first3 = [c for c in cuts if c < 3]
    spoken = [s["palabras"] for s in seconds if s["palabras"]]

    def avg(key: str, inner: str = "") -> float:
        vals = [(s[key][inner] if inner else s[key]) for s in seconds]
        return round(statistics.mean(vals), 3) if vals else 0.0

    minutes = max(1 / 60, dur / 60)
    summary = {
        "duracion_s": round(dur, 1), "vertical": meta["h"] > meta["w"], "fps": meta["fps"], "fps_medido": fps,
        "fps_muestreo_real": round(frames_seen / max(0.01, dur), 3),
        "intervalo_fotograma_s": round(1 / fps, 5),
        "tomas": len(shots), "toma_mediana_s": round(statistics.median(shots), 2) if shots else round(dur, 1),
        "cortes_por_segundo": round(len(cuts) / max(1.0, dur), 2), "cortes_primeros_3s": len(first3),
        "toma_mas_larga_s": max(shots) if shots else round(dur, 1),
        "texto_en_pantalla": round(len(text_on) / max(1, len(seconds)), 2),
        "texto_donde": max(where, key=where.get) if where else "",
        "caras": round(sum(1 for s in seconds if s["caras"]) / max(1, len(seconds)), 2),
        "movimiento_medio": round(statistics.mean(s["movimiento"] for s in seconds), 3) if seconds else 0,
        "golpes_por_segundo": round(sum(s["golpes"] for s in seconds) / max(1, len(seconds)), 2),
        "volumen_medio_db": round(statistics.mean(s["volumen_db"] for s in seconds), 1) if seconds else 0,
        "palabras_por_segundo": round(sum(spoken) / max(1, len(seconds)), 2) if spoken else 0,
        "gancho": " ".join(x["w"] for x in words if float(x.get("t", 99)) < 3)[:160],
        "colores": [c for c in dict.fromkeys(s["principal"] for s in seconds if s["principal"])][:8],
        "brillo_medio": avg("luz", "brillo"), "contraste": avg("luz", "contraste"),
        "sombras": avg("luz", "sombras"), "luces": avg("luz", "luces"),
        "calidez": avg("luz", "calidez"), "vineta": avg("luz", "vineta"),
        "camara": avg("camara"), "temblor": avg("temblor"),
        "destellos_por_min": round(sum(s["destellos"] for s in seconds) / minutes, 2),
        "negro": avg("negro"),
        "guion": script_of(words, dur),
        "transcripcion_estado": transcription_status,
        "transcripcion_palabras": len(words),
        "planos": {k: round(sum(1 for x in seconds if x.get("plano") == k) / max(1, len(seconds)), 2)
                   for k in ("cara", "texto", "grafico", "real")},
        "zoom_medio": avg("zoom"),
        "punch_ins_por_min": round(len(punches) / minutes, 2),
        "ritmo_por_tramo": rhythm(cuts, dur),
        "cortes_en_golpe": on_hits(cuts, hit_times),
        "silencios_por_min": silences(words, dur),
    }  # fmt: skip
    summary["tipo_de_edicion"] = editing_type(summary)
    summary["fotogramas_muestreados"] = frames_seen
    return {
        "meta": meta,
        "cortes": cuts,
        "tomas": shots,
        "fotogramas": frame_rows,
        "eventos_sonido": [round(t, 3) for t in hit_times],
        "transcripcion": words,
        "segundos": seconds,
        "resumen": summary,
    }


def _one_frame(path: Path, at: float, ffmpeg: str) -> Any:
    import io

    from PIL import Image

    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-ss", f"{at:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=360:-2",
         "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60,
    ).stdout  # fmt: skip
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _vtt_seconds(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def vtt_words(path: Path) -> tuple[List[Dict[str, Any]], bool]:
    """Read YouTube VTT, including inline word timings when present."""
    text = path.read_text("utf-8-sig")
    out: List[Dict[str, Any]] = []
    exact = False
    previous_plain: List[str] = []
    for block in re.split(r"\n\s*\n", text):
        timing = re.search(
            r"(\d{2,}:\d{2}:\d{2}[.,]\d{3})\s+-->\s+"
            r"(\d{2,}:\d{2}:\d{2}[.,]\d{3})",
            block,
        )
        if not timing:
            continue
        start, end = map(_vtt_seconds, timing.groups())
        payload = block[timing.end() :].strip().replace("\n", " ")
        inline = bool(re.search(r"<\d{2,}:\d{2}:\d{2}[.,]\d{3}>", payload))
        exact = exact or inline
        current = start
        words: List[Dict[str, Any]] = []
        for part in re.split(r"(<[^>]+>)", payload):
            stamp = re.fullmatch(r"<(\d{2,}:\d{2}:\d{2}[.,]\d{3})>", part.strip())
            if stamp:
                current = _vtt_seconds(stamp.group(1))
                continue
            clean = re.sub(r"<[^>]+>", "", part).strip()
            for word in clean.split():
                words.append({"t": round(current, 2), "w": word})
        if not inline:
            plain = [row["w"] for row in words]
            overlap = len(previous_plain)
            while overlap and plain[:overlap] != previous_plain[:overlap]:
                overlap -= 1
            words = words[overlap:]
            previous_plain = plain
            if words:
                step = max(0.0, end - start) / len(words)
                for i, row in enumerate(words):
                    row["t"] = round(start + i * step, 2)
        out.extend(words)
    unique = {(row["t"], row["w"]): row for row in out}
    return sorted(unique.values(), key=lambda row: row["t"]), exact


@lru_cache(maxsize=2)
def _whisper_model(name: str) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe_detailed(path: Path) -> tuple[List[Dict[str, Any]], str]:
    """Words and a machine-readable status; an error is never called silence."""
    for suffix in (".en.vtt", ".es.vtt", ".en-orig.vtt", ".es-orig.vtt"):
        candidate = path.with_suffix(suffix)
        if candidate.is_file():
            words, exact = vtt_words(candidate)
            if words:
                return words, "subtitulos_youtube" if exact else "subtitulos_estimados"
    try:
        model = _whisper_model(os.environ.get("SERGIO_ESCUELA_WHISPER", "small"))
        segs, _ = model.transcribe(str(path), word_timestamps=True, vad_filter=True)
        words = [
            {"t": round(float(w.start), 2), "w": w.word.strip()}
            for s in segs
            for w in (s.words or [])
            if w.word.strip()
        ]
        return words, "ok" if words else "sin_voz_detectada"
    except Exception as exc:  # noqa: BLE001
        log.info("no transcription: %s", exc)
        return [], f"error: {exc}"


def transcribe(path: Path) -> List[Dict[str, Any]]:
    """Words and their times (faster-whisper on this PC)."""
    return transcribe_detailed(path)[0]


def update_transcription(
    measured: Dict[str, Any], words: List[Dict[str, Any]], status: str
) -> None:
    """Replace only the language layer of a study, keeping its frame measurements."""
    measured["transcripcion"] = words
    for sec in measured.get("segundos") or []:
        s = int(sec["t"])
        said = [x["w"] for x in words if s <= float(x.get("t", -1)) < s + 1]
        sec["palabras"] = len(said)
        sec["dice"] = " ".join(said)[:120]
    summary = measured["resumen"]
    seconds = measured.get("segundos") or []
    spoken = [s["palabras"] for s in seconds if s.get("palabras")]
    duration = float(summary["duracion_s"])
    summary["palabras_por_segundo"] = (
        round(sum(spoken) / max(1, len(seconds)), 2) if spoken else 0
    )
    summary["gancho"] = " ".join(x["w"] for x in words if float(x.get("t", 99)) < 3)[
        :160
    ]
    summary["guion"] = script_of(words, duration)
    summary["silencios_por_min"] = silences(words, duration)
    summary["transcripcion_estado"] = status
    summary["transcripcion_palabras"] = len(words)


# -- 3. study one video ------------------------------------------------------------------------


def source_metadata(path: Path) -> Dict[str, Any]:
    """Public source and music fields supplied by the platform, never guessed."""
    try:
        info = json.loads(path.with_suffix(".info.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    fields = {
        "titulo": "title",
        "canal": "channel",
        "vistas": "view_count",
        "me_gusta": "like_count",
        "comentarios": "comment_count",
        "fecha": "upload_date",
        "pista": "track",
        "artista": "artist",
        "album": "album",
    }
    out = {
        key: info[source]
        for key, source in fields.items()
        if info.get(source) is not None
    }
    credits = [
        line.strip()
        for line in str(info.get("description") or "").splitlines()
        if re.match(r"(?:music|sound design)\s+by\b", line.strip(), re.I)
    ]
    if credits:
        out["creditos_sonido"] = "; ".join(dict.fromkeys(credits))
    return out


def study(url: str, category: str, *, root: Optional[Path] = None,
          watcher: Optional[Callable[[str], Dict[str, Any]]] = None,
          fetch: Optional[Callable[[str, Path], Path]] = None, fps: int = FPS,
          require_frames: bool = False) -> Dict[str, Any]:  # fmt: skip
    """Download, measure every frame and (with a model) watch one video."""
    root = root or home()
    folder = root / category
    out = folder / f"{video_id(url)}.json"
    if out.is_file():
        cached = json.loads(out.read_text("utf-8"))
        summary = (cached.get("medido") or {}).get("resumen") or {}
        if _measured_fps(cached) == fps and (
            not require_frames or summary.get("fotogramas_muestreados")
        ):
            return cached
    path = (fetch or download)(url, root / "videos")
    data: Dict[str, Any] = {
        "url": url,
        "categoria": category,
        "fuente": source_metadata(path),
        "medido": measure(path, fps=fps),
    }
    try:
        from openjarvis.video_essay import style

        data["tomas_modelo"] = (watcher or style.watch)(str(path))
    except Exception as exc:  # noqa: BLE001 — the numbers are already there
        data["sin_modelo"] = str(exc)[:200]
    folder.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    return data


# -- 4. the superskill of a category --------------------------------------------------------------

SKILL_PROMPT = """You are teaching an AI video editor to reproduce the EDITING of a group of reference
videos («{name}»), not their content. Below: numbers measured second by second by code on {n} videos,
and (when available) a model's shot list of each. Write the superskill: 12-20 precise, numbered rules
an editor can follow (hook in the first 3 s, shot length and cut rhythm with the numbers, where and how
the words appear, zooms and effects, sound and hits, colour, LIGHT, CONTRAST AND SHADOWS, camera movement
and shake, flashes and fades, structure and ending, topics that work) and 5-8 rules for the SCRIPT (the
hook formula, sentence length and pace, questions, turns and open loops, how it talks to the viewer, how
it ends), written from the measured script numbers and the first sentences' shape, never their words.
Every number you give must come from the data. Never name the creators or copy their characters,
drawings, voices or words. English, imperative, no preamble.

MEASURED:
{measured}

SHOT LISTS (summaries):
{shots}"""


def _median(values: Sequence[float]) -> float:
    values = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.median(values), 2) if values else 0.0


def merge(studies: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The category's numbers: medians over its videos."""
    sums = [s["medido"]["resumen"] for s in studies if s.get("medido")]
    keys = ["duracion_s", "toma_mediana_s", "cortes_por_segundo", "cortes_primeros_3s", "texto_en_pantalla",
            "caras", "movimiento_medio", "golpes_por_segundo", "volumen_medio_db", "palabras_por_segundo",
            "brillo_medio", "contraste", "sombras", "luces", "calidez", "vineta", "camara", "temblor",
            "destellos_por_min", "negro", "zoom_medio", "punch_ins_por_min", "cortes_en_golpe",
            "silencios_por_min"]  # fmt: skip
    out: Dict[str, Any] = {k: _median([s.get(k) for s in sums]) for k in keys}
    planos = [s["planos"] for s in sums if s.get("planos")]
    if planos:
        out["planos"] = {
            k: _median([p.get(k) for p in planos])
            for k in ("cara", "texto", "grafico", "real")
        }
    curves = [
        s["ritmo_por_tramo"] for s in sums if len(s.get("ritmo_por_tramo") or []) == 10
    ]
    if curves:
        out["ritmo_por_tramo"] = [_median([c[i] for c in curves]) for i in range(10)]
    out["tipo_de_edicion"] = editing_type(out)
    scripts = [s["guion"] for s in sums if s.get("guion")]
    if scripts:
        skeys = ["palabras_por_minuto", "frase_mediana", "preguntas_por_min", "tu_por_frase", "giros_por_min",
                 "lazos_por_min", "numeros_por_min", "pausas_por_min", "partes", "primera_frase_palabras"]  # fmt: skip
        out["guion"] = {k: _median([g.get(k) for g in scripts]) for k in skeys}
        out["primeras_frases"] = [
            g["primera_frase"] for g in scripts if g.get("primera_frase")
        ][:12]
        out["finales"] = [g["final"] for g in scripts if g.get("final")][:8]
    where = [s.get("texto_donde") for s in sums if s.get("texto_donde")]
    out["texto_donde"] = max(set(where), key=where.count) if where else ""
    out["vertical"] = sum(1 for s in sums if s.get("vertical")) > len(sums) / 2
    out["ganchos"] = [s["gancho"] for s in sums if s.get("gancho")][:10]
    out["colores"] = [c for s in sums for c in s.get("colores", [])][:12]
    out["videos"] = len(sums)
    return out


def rules_from_numbers(m: Dict[str, Any]) -> List[str]:
    """The rules code can write alone (no model): straight from the numbers."""
    out = [
        f"Cut every {m['toma_mediana_s']} s on average ({m['cortes_por_segundo']} cuts per second); "
        f"{m['cortes_primeros_3s']} cuts in the first 3 seconds.",
        f"Keep the whole video around {m['duracion_s']} s.",
    ]
    if m.get("texto_en_pantalla"):
        place = {
            "arriba": "at the top",
            "centro": "in the middle",
            "abajo": "at the bottom",
        }
        out.append(
            f"Words on screen in {int(m['texto_en_pantalla'] * 100)} % of the seconds, mostly "
            f"{place.get(m['texto_donde'], 'where the picture is free')}."
        )
    if m.get("golpes_por_segundo"):
        out.append(
            f"About {m['golpes_por_segundo']} sound hits or whooshes per second, on the cuts."
        )
    if m.get("palabras_por_segundo"):
        out.append(f"Narration at about {m['palabras_por_segundo']} words per second.")
    if m.get("caras"):
        out.append(f"A face on screen in {int(m['caras'] * 100)} % of the seconds.")
    if m.get("contraste"):
        grade = (
            "warm"
            if m.get("calidez", 0) > 0.03
            else "cool"
            if m.get("calidez", 0) < -0.03
            else "neutral"
        )
        out.append(
            f"Light: average brightness {m.get('brillo_medio')}, contrast (p95-p5 of the light) "
            f"{m['contraste']}; {int(m.get('sombras', 0) * 100)} % of the picture in deep shadow and "
            f"{int(m.get('luces', 0) * 100)} % blown to white; a {grade} grade; vignette (centre/corners) "
            f"{m.get('vineta')}."
        )
    if m.get("camara") or m.get("temblor"):
        out.append(
            f"Camera: slides about {m.get('camara')} of the frame per second, shake {m.get('temblor')}; "
            f"{m.get('destellos_por_min', 0)} flashes a minute; "
            f"black frames {int(m.get('negro', 0) * 100)} % of the time."
        )
    g = m.get("guion") or {}
    if g.get("palabras_por_minuto"):
        out.append(
            f"Script: {g['palabras_por_minuto']} words a minute, sentences of about {g.get('frase_mediana')} words, "
            f"a first sentence of {g.get('primera_frase_palabras')} words; {g.get('preguntas_por_min')} questions, "
            f"{g.get('giros_por_min')} turns (but, until…) and {g.get('lazos_por_min')} open loops a minute; "
            f"«you» {g.get('tu_por_frase')} times a sentence; {g.get('pausas_por_min')} pauses a minute; "
            f"{g.get('partes')} parts."
        )
    if m.get("tipo_de_edicion"):
        out.append(f"Editing grammar: {m['tipo_de_edicion']}.")
    p = m.get("planos") or {}
    if p:
        names = {"cara": "a face talking to camera", "texto": "cards of words", "grafico": "flat drawing, map or "
                 "animation", "real": "filmed or archive footage"}  # fmt: skip
        mix = ", ".join(
            f"{int(v * 100)} % {names[k]}"
            for k, v in sorted(p.items(), key=lambda x: -x[1])
            if v
        )
        out.append(f"Shots: {mix}.")
    if m.get("punch_ins_por_min"):
        out.append(
            f"{m['punch_ins_por_min']} punch-ins a minute: cut closer on the same shot to stress a word."
        )
    if m.get("zoom_medio"):
        way = "in" if m["zoom_medio"] > 0 else "out"
        out.append(
            f"A slow constant zoom {way} ({abs(m['zoom_medio']):.3f} a second) keeps still images alive."
        )
    curve = m.get("ritmo_por_tramo") or []
    if len(curve) == 10 and max(curve) > 0:
        peak = curve.index(max(curve)) + 1
        out.append(
            f"Rhythm across the video (cuts/s per tenth): {curve}; fastest in tenth {peak}. "
            "Follow the same curve, not one flat pace."
        )
    if m.get("cortes_en_golpe"):
        out.append(
            f"{int(m['cortes_en_golpe'] * 100)} % of the cuts land on a sound hit."
        )
    if m.get("silencios_por_min"):
        out.append(
            f"{m['silencios_por_min']} narration pauses (1.2 s+) a minute: silence is part of the edit."
        )
    out.append("Vertical 9:16." if m.get("vertical") else "Horizontal 16:9.")
    return out


def compare(
    categories: Optional[Sequence[str]] = None, root: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """The studied categories side by side: what tells their editing apart."""
    out = []
    for cat in categories or list(references().keys()):
        try:
            m = json.loads(
                ((root or home()) / "superskills" / cat / "medido.json").read_text(
                    "utf-8"
                )
            )
        except (OSError, ValueError):
            continue
        out.append({
            "categoria": cat, "tipo": m.get("tipo_de_edicion", ""), "toma_s": m.get("toma_mediana_s"),
            "planos": m.get("planos", {}), "punch_ins_min": m.get("punch_ins_por_min"),
            "texto": m.get("texto_en_pantalla"), "golpes": m.get("cortes_en_golpe"),
            "palabras_min": (m.get("guion") or {}).get("palabras_por_minuto"), "videos": m.get("videos"),
        })  # fmt: skip
    return out


def synthesize(category: str, *, root: Optional[Path] = None, ask: Optional[Callable[[str], str]] = None,
               refs: Optional[Dict[str, Dict[str, Any]]] = None,
               cohort: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:  # fmt: skip
    """Join a category's studies into its style and its superskill."""
    from openjarvis.video_essay import style

    root = root or home()
    refs = refs or references()
    cat = refs[category]
    studies = (
        list(cohort)
        if cohort is not None
        else [
            json.loads(p.read_text("utf-8"))
            for p in sorted((root / category).glob("*.json"))
        ]
    )
    if cat.get("fps"):
        studies = [s for s in studies if _measured_fps(s) == cat["fps"]]
    if cat.get("cohorte_canal") and (
        cohort is None
        or len({s["url"] for s in studies})
        != sum(int(c["ultimos"]) for c in cat["canales"] if c.get("solo_pestana"))
        or not all(
            s["medido"]["resumen"].get("fotogramas_muestreados") for s in studies
        )
    ):
        raise RuntimeError("la cohorte de Shorts aún no está completa")
    if not studies:
        raise RuntimeError(f"no hay videos estudiados en «{category}»")
    m = merge(studies)
    shot_lists = []
    for s in studies:
        t = s.get("tomas_modelo") or {}
        if t:
            shot_lists.append(json.dumps({k: t.get(k) for k in ("summary", "pacing", "typography", "recurring_effects",
                                                                "transitions", "music_and_sound", "color_grade")},
                                         ensure_ascii=False)[:1500])  # fmt: skip
    rules = rules_from_numbers(m)
    seed = [str(x) for x in cat.get("guion_semilla") or []]
    by = "código"
    if ask is None:
        try:
            from openjarvis.creator import llm

            def ask(p: str) -> str:
                return llm.ask(p, effort="high", max_tokens=6000)
        except Exception:  # noqa: BLE001
            ask = None
    if ask is not None:
        try:
            text = ask(SKILL_PROMPT.format(name=cat["nombre"], n=len(studies),
                                          measured=json.dumps(m, ensure_ascii=False),
                                          shots="\n".join(shot_lists) or "(none)"))  # fmt: skip
            lines = [
                re.sub(r"^\s*(\d+[.)]|[-*])\s*", "", ln).strip()
                for ln in str(text).splitlines()
            ]
            lines = [ln for ln in lines if len(ln) > 12][:20]
            if len(lines) >= 5:
                # the measured grammar stays, whatever the model wrote
                keep = [
                    r
                    for r in rules
                    if r.startswith(("Editing grammar", "Shots:", "Rhythm across"))
                ]
                rules, by = keep + lines, "modelo con los números medidos"
        except Exception as exc:  # noqa: BLE001
            log.info("superskill by code only: %s", exc)
    rules = rules + seed  # the hand-written script rules (read from real transcripts)
    visual_seed = str(cat.get("guia_miniaturas") or "").strip()
    if visual_seed:
        rules.append(visual_seed)
    key = f"ref-{category}"
    profiles = [style.profile_from(s["tomas_modelo"], key, cat["nombre"], s["url"])
                for s in studies if s.get("tomas_modelo")]  # fmt: skip
    prof = {
        "key": key, "name": f"{cat['nombre']} (sus referencias)", "source": "escuela",
        "shots_measured": sum(len(s["medido"]["tomas"]) for s in studies),
        "length_s": m["duracion_s"], "median_shot_s": m["toma_mediana_s"] or 1.6,
        "min_shot_s": 0.3, "max_shot_s": max(2.0, m["toma_mediana_s"] * 3),
        "text_share": m["texto_en_pantalla"], "palette_seen": m["colores"][:8],
        "mix": profiles[0]["mix"] if profiles else {"broll": 1.0},
        "typography": profiles[0]["typography"] if profiles else {},
        "effects": sorted({e for p in profiles for e in p.get("effects") or []})[:12],
        "transitions_seen": sorted({e for p in profiles for e in p.get("transitions_seen") or []})[:12],
        "pacing": f"{m['cortes_por_segundo']} cuts/s, {m['cortes_primeros_3s']} in the first 3 s",
        "superskill": rules, "medido": m, "aspect": "9:16" if m["vertical"] else "16:9",
        **({"cohorte": [s["url"] for s in studies]} if cohort is not None else {}),
    }  # fmt: skip
    if cat.get("cohorte_canal"):
        prof.update(
            production="animation",
            narration_mode="voice",
            sources=["ai", "3d", "image"],
        )
        if visual_seed:
            prof["look"] = visual_seed
    folder = style.learned_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}.json").write_text(
        json.dumps(prof, ensure_ascii=False, indent=1), "utf-8"
    )
    skill = root / "superskills" / category / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    (skill.parent / "medido.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=1), "utf-8"
    )
    skill.write_text(
        f"---\nname: {key}\ndescription: Edición como las referencias del dueño: {cat['nombre']}\n---\n\n"
        f"# {cat['nombre']}\n\nMedido segundo a segundo en {m['videos']} videos; reglas escritas por {by}.\n\n"
        + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)) + "\n",
        "utf-8",
    )  # fmt: skip
    trained = train_brain(refs)
    return {"categoria": category, "videos": m["videos"], "reglas": rules, "por": by, "estilo": key,
            "skill": str(skill), "cerebro": trained}  # fmt: skip


# -- 5. the school's own brain ----------------------------------------------------------------------


def _titles(refs: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """Examples per category: its name, its genres and the titles of its
    studied videos (written next to each study)."""
    out = {}
    for key, cat in refs.items():
        ex = [cat["nombre"], *cat.get("ejemplos", [])]
        out[key] = [e for e in ex if e]
    return out


def train_brain(
    refs: Optional[Dict[str, Dict[str, Any]]] = None, core: Any = None, epochs: int = 6
) -> Dict[str, Any]:
    """The fly brain that picks the category for an order; really trained
    (its synapses change), measured on one example per category it never saw."""
    refs = refs or references()
    try:
        from openjarvis.connectome.core import get_core

        core = core or get_core()
        examples = _titles(refs)
        texts = [t for ts in examples.values() for t in ts]
        mb = core.brain("especialista:escuela")
        mb.reset()  # trained again from all the examples, never stacked twice
        if core.receptors.space:
            core.receptors.warm(texts)
    except Exception as exc:  # noqa: BLE001 — the superskill works without it
        return {"entrenado": False, "por_que": str(exc)[:160]}
    actions = [f"cat:{k}" for k in examples]
    held = {k: ts[-1] for k, ts in examples.items() if len(ts) >= 3}
    for _ in range(epochs):
        for k, ts in examples.items():
            for t in ts:
                if held.get(k) == t:
                    continue
                mb.learn(t, f"cat:{k}", 1.0)
    hit = sum(
        1
        for k, t in held.items()
        if max(actions, key=lambda a: mb.scores(t, actions)[a]) == f"cat:{k}"
    )
    mb.save()
    core.save(force=True)
    return {
        "entrenado": True,
        "ejemplos": len(texts),
        "prueba": f"{hit}/{len(held)} sin verlos",
    }


def category_for(
    brief: str, genre: str = "", aspect: str = "", core: Any = None
) -> str:
    """The reference category a new video belongs to: by its genre first,
    then the school's brain on the order's words."""
    try:
        refs = references()
    except (OSError, ValueError):
        return ""
    learned = {k for k in refs if skill_text(k)}
    if not learned:
        return ""
    by_genre = [k for k in learned if genre and genre in refs[k].get("generos", [])]
    if len(by_genre) == 1:
        return by_genre[0]
    pool = by_genre or sorted(learned)
    try:
        from openjarvis.connectome.core import get_core

        mb = (core or get_core()).brain("especialista:escuela")
        s = mb.scores(brief, [f"cat:{k}" for k in pool])
        return max(pool, key=lambda k: s[f"cat:{k}"])
    except Exception:  # noqa: BLE001
        return pool[0]


def skill_text(category: str, root: Optional[Path] = None) -> str:
    path = (root or home()) / "superskills" / category / "SKILL.md"
    try:
        return path.read_text("utf-8")
    except OSError:
        return ""


def guidance(brief: str, genre: str = "", aspect: str = "") -> str:
    """The superskill for this order, for the director and the editor."""
    cat = category_for(brief, genre, aspect)
    text = skill_text(cat) if cat else ""
    if not text:
        return ""
    body = text.split("---", 2)[-1].strip()
    return (f"\nOWNER'S REFERENCE SUPERSKILL («{cat}», measured second by second on his chosen videos). "
            f"Follow it closely; reproduce the editing, never their content:\n{body[:4000]}\n")  # fmt: skip


# -- recreating one reference exactly («molde») -------------------------------------------------


def _measured_fps(study: Dict[str, Any]) -> int:
    return int((study.get("medido") or {}).get("resumen", {}).get("fps_medido") or 0)


def find(ref: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """A studied reference by its link or id (any category)."""
    root = root or home()
    vid = video_id(clean_link(ref)) if "/" in ref else ref.strip()
    if not re.fullmatch(r"[\w-]+", vid):
        raise ValueError("identificador de referencia no válido")
    candidates = [
        json.loads(path.read_text("utf-8"))
        for path in sorted(root.glob(f"*/{vid}.json"))
        if path.parent.name != "superskills"
    ]
    # A link shared by multiple categories should use its highest requested
    # sampling rate, even if a lower-rate study already exists.
    min_fps = max(
        (
            int(cat.get("fps") or 0)
            for cat in references().values()
            if any(video_id(url) == vid for url in cat["links"])
        ),
        default=0,
    )
    candidates = [data for data in candidates if _measured_fps(data) >= min_fps]
    if candidates:
        return max(candidates, key=_measured_fps)
    raise RuntimeError(
        f"Todavía no estudié ese video ({vid}). Diga «estudia las referencias» primero."
    )


def ficha(ref: str, root: Optional[Path] = None) -> str:
    """Everything Sergio knows about one reference, second by second."""
    data = find(ref, root)
    m = data["medido"]
    r = m["resumen"]
    lines = [
        f"{data['url']} ({data['categoria']}): {r['duracion_s']} s, {'vertical' if r['vertical'] else 'horizontal'}, "
        f"{r['tomas']} tomas (mediana {r['toma_mediana_s']} s), {r['cortes_primeros_3s']} cortes en los primeros 3 s, "
        f"texto en pantalla {int(r['texto_en_pantalla'] * 100)} % ({r['texto_donde'] or '—'}), "
        f"{r['golpes_por_segundo']} golpes de sonido por segundo, {r['palabras_por_segundo']} palabras por segundo.",
        f"Cobertura: {r.get('fotogramas_muestreados', 0)} fotogramas a {r.get('fps_medido')} FPS de análisis; "
        f"archivo original {r.get('fps')} FPS; intervalo {r.get('intervalo_fotograma_s')} s.",
    ]
    source = data.get("fuente") or {}
    if source.get("titulo"):
        lines.append(
            f"Fuente: {source['titulo']} — {source.get('canal', 'canal no disponible')}."
        )
    if source.get("vistas") is not None:
        lines.append(
            f"Métricas públicas al descargar: {source['vistas']} vistas, "
            f"{source.get('me_gusta', '—')} me gusta, {source.get('comentarios', '—')} comentarios."
        )
    if source.get("pista") or source.get("artista"):
        lines.append(
            f"Música declarada por la plataforma: {source.get('pista', '—')} — "
            f"{source.get('artista', '—')}."
        )
    elif source.get("creditos_sonido"):
        lines.append(f"Créditos de sonido: {source['creditos_sonido']}.")
    else:
        lines.append(
            "Música: sin título fiable en los metadatos; no se identifica de oído ni se inventa."
        )
    if data.get("sin_modelo"):
        lines.append(
            "Etiquetas semánticas por toma no disponibles; las mediciones de código sí están guardadas."
        )
    if r.get("gancho"):
        lines.append(f"Gancho (0-3 s): «{r['gancho']}»")
    lines.append("Cortes (s): " + ", ".join(str(c) for c in m["cortes"][:80]))
    for sec in m["segundos"]:
        where = (
            max(sec["texto"], key=sec["texto"].get)
            if sec.get("texto") and max(sec["texto"].values()) >= 0.08
            else ""
        )
        bits = [f"{sec['t']}s", f"{sec['cortes']} cortes" if sec["cortes"] else "", f"texto {where}" if where else "",
                "cara" if sec["caras"] else "", f"{sec['golpes']} golpes" if sec["golpes"] else "",
                f"«{sec['dice']}»" if sec.get("dice") else ""]  # fmt: skip
        lines.append(" · ".join(b for b in bits if b))
    shots = (data.get("tomas_modelo") or {}).get("shots") or []
    for sh in shots[:120]:
        lines.append(
            f"toma {sh.get('t')}s ({sh.get('dur')} s): {sh.get('visual', '')} | texto: {sh.get('on_screen_text', '')} "
            f"({sh.get('text_style', '')}) | efecto: {sh.get('effect', '')} | entra: {sh.get('transition_in', '')} "
            f"| sonido: {sh.get('sfx', '')}"
        )
    return "\n".join(lines)


def frame_ficha(
    ref: str, start: float = 0.0, end: float = 10.0, root: Optional[Path] = None
) -> str:
    """Measured frame rows for a bounded interval (60 s at most per response)."""
    data = find(ref, root)
    measured = data["medido"]
    duration = float(measured["resumen"]["duracion_s"])
    start = max(0.0, float(start))
    requested_end = float(end)
    if requested_end - start > 60:
        raise ValueError("el intervalo debe ser positivo y de 60 segundos como máximo")
    end = min(duration, requested_end)
    if end <= start:
        raise ValueError("el intervalo debe ser positivo y de 60 segundos como máximo")
    rows = [
        row
        for row in measured.get("fotogramas") or []
        if start <= float(row["t"]) < end
    ]
    return json.dumps(
        {
            "url": data["url"],
            "desde": start,
            "hasta": end,
            "fps_analisis": measured["resumen"]["fps_medido"],
            "total_fotogramas_video": measured["resumen"]["fotogramas_muestreados"],
            "fotogramas": rows,
        },
        ensure_ascii=False,
    )


def blueprint(
    ref: str, seconds: float = 0.0, root: Optional[Path] = None
) -> Dict[str, Any]:
    """The reference's skeleton scaled to *seconds*: where each cut falls,
    and what each shot does (text place, effect, way in, sound)."""
    data = find(ref, root)
    m = data["medido"]
    dur = float(m["resumen"]["duracion_s"] or 1)
    scale = (seconds or dur) / dur
    shots = (data.get("tomas_modelo") or {}).get("shots") or []
    bounds = [0.0, *m["cortes"], dur]
    out = []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        mid = (a + b) / 2
        sh = (
            min(
                shots,
                key=lambda s: abs(
                    float(s.get("t") or 0) + float(s.get("dur") or 0) / 2 - mid
                ),
            )
            if shots
            else {}
        )
        sec = (
            m["segundos"][min(len(m["segundos"]) - 1, int(mid))]
            if m["segundos"]
            else {}
        )
        text = sec.get("texto") or {}
        where = max(text, key=text.get) if text and max(text.values()) >= 0.08 else ""
        out.append({
            "desde": round(a * scale, 2), "hasta": round(b * scale, 2),
            "posicion": {"arriba": "upper", "centro": "center", "abajo": "lower"}.get(where, ""),
            "efecto": str(sh.get("effect") or ""), "entra": str(sh.get("transition_in") or ""),
            "sonido": str(sh.get("sfx") or ""), "texto_estilo": str(sh.get("text_style") or ""),
            "visual": str(sh.get("visual") or ""), "golpes": int(sec.get("golpes") or 0),
        })  # fmt: skip
    return {
        "url": data["url"],
        "duracion": round(seconds or dur, 1),
        "aspect": "9:16" if m["resumen"]["vertical"] else "16:9",
        "tomas": out,
        "gancho": m["resumen"].get("gancho", ""),
        "resumen": m["resumen"],
    }


def blueprint_note(bp: Dict[str, Any]) -> str:
    """The skeleton as instructions for the director and the editor."""
    rows = "\n".join(
        f"- {t['desde']}-{t['hasta']} s: text {t['posicion'] or 'free'} ({t['texto_estilo'] or 'any'}), effect "
        f"{t['efecto'] or 'none'}, in {t['entra'] or 'cut'}, sound {t['sonido'] or 'none'}; shows: {t['visual'][:80]}"
        for t in bp["tomas"][:150]
    )
    return (
        f"\nRECREATE THIS EDIT EXACTLY (owner's reference {bp['url']}, measured second by second): "
        f"{len(bp['tomas'])} shots in {bp['duracion']} s, cuts at the same moments, the same kind of hook "
        f"in the first 3 s, words in the same places, the same effects, ways in and sounds. New content "
        f"(the order's topic), never the reference's footage, words or people.\n{rows}\n"
    )


def rhythm_note(bp: Dict[str, Any]) -> str:
    """Measured cut timings only; keep source words and footage out of the brief."""
    cuts = ", ".join(str(shot["desde"]) for shot in bp["tomas"][1:30])
    return (
        f"\nReference rhythm scaled to {bp['duracion']:g} s. Cut targets (s): {cuts or 'no cuts'}. "
        "Use them where the new story supports them. Use original visuals and wording."
    )


def recut(shots: List[Any], words: List[Any], bp: Dict[str, Any]) -> List[Any]:
    """The planned shots cut again at the reference's moments (snapped to
    the nearest gap between words), each one dressed like the reference's
    shot at that moment. What the editor chose to show is kept."""
    from dataclasses import asdict

    if not shots or not words or not bp.get("tomas"):
        return shots
    shot_cls = type(shots[0])
    gaps = [(i, words[i].start) for i in range(1, len(words))]
    starts = [0]
    for t in bp["tomas"][1:]:
        if not gaps:
            break
        i, _ = min(gaps, key=lambda g: abs(g[1] - t["desde"]))
        if i > starts[-1]:
            starts.append(i)
    starts.append(len(words))
    out = []
    for k, (a, b) in enumerate(zip(starts, starts[1:])):
        if b <= a:
            continue
        mid = (words[a].start + words[b - 1].end) / 2
        base = min(shots, key=lambda s: abs((s.start + s.end) / 2 - mid))
        ref = bp["tomas"][min(k, len(bp["tomas"]) - 1)]
        new = shot_cls(**{**asdict(base), "first": a, "last": b, "text": ""})
        new.start, new.end = words[a].start, words[b - 1].end
        if ref["posicion"]:
            new.position = ref["posicion"]
        for field, key in (
            ("effect", "efecto"),
            ("transition", "entra"),
            ("sfx", "sonido"),
        ):
            value = ref[key].split(",")[0].strip().lower()
            if value and hasattr(new, field):
                setattr(new, field, value[:40])
        new.notes = list(new.notes) + [f"molde: toma {k + 1} de la referencia"]
        out.append(new)
    return out


# -- the whole school, in the background --------------------------------------------------------


def run_all(
    categories: Optional[Sequence[str]] = None,
    on_step: Optional[Callable[[str], None]] = None,
    *,
    shorts_ids: Optional[Sequence[str]] = None,
    shorts_media: Optional[Path] = None,
) -> Dict[str, Any]:
    """Study every reference and write every superskill; a video that fails
    is reported and the rest go on."""
    refs = references()
    todo = [c for c in (categories or refs) if c in refs]
    if shorts_media is not None and shorts_ids is None:
        raise ValueError("los archivos locales necesitan una lista fija de IDs")
    if shorts_ids is not None and (
        todo != ["shorts-animados"]
        or len(shorts_ids) != 20
        or len(set(shorts_ids)) != 20
        or not all(re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) for vid in shorts_ids)
    ):
        raise ValueError("la tanda fija necesita 20 IDs de Shorts distintos")

    def local_video(url: str, _cache: Path) -> Path:
        vid = video_id(url)
        assert shorts_media is not None
        files = [
            p
            for ext in (".mp4", ".mkv", ".webm", ".mov")
            if (p := shorts_media / (vid + ext)).is_file()
        ]
        if len(files) != 1:
            raise RuntimeError(f"Se necesita un único archivo de video para {vid}.")
        return files[0]

    done: Dict[str, Any] = {
        "estudiados": 0,
        "fallos": [],
        "superskills": [],
        "cohortes": {},
    }
    for cat in todo:
        category = refs[cat]
        strict = bool(category.get("cohorte_canal"))
        channels = [c for c in category.get("canales", []) if c.get("solo_pestana")]
        wanted = sum(int(c["ultimos"]) for c in channels)
        try:
            if strict and shorts_ids is not None:
                links = [f"https://www.youtube.com/watch?v={vid}" for vid in shorts_ids]
            elif strict:
                links = list(
                    dict.fromkeys(
                        url
                        for ch in channels
                        for url in channel_links(ch, refresh=True)
                    )
                )
            else:
                links = links_of(category)
        except Exception as exc:  # noqa: BLE001 — a channel that fails: its links still count
            done["fallos"].append({"categoria": cat, "por_que": str(exc)[:200]})
            links = [] if strict else list(category["links"])
        fps = int(category.get("fps") or FPS)
        cohort: List[Dict[str, Any]] = []
        videos = []
        for url in links:
            _running.update(
                que=f"{cat}: {url}", desde=_running.get("desde") or time.time()
            )
            if on_step:
                on_step(f"Estudiando {url} ({cat})")
            try:
                if shorts_ids is not None:
                    data = study(
                        url,
                        cat,
                        fps=fps,
                        require_frames=True,
                        watcher=lambda _: {},
                        fetch=local_video if shorts_media is not None else None,
                    )
                elif strict:
                    data = study(url, cat, fps=fps, require_frames=True)
                else:
                    data = study(url, cat, fps=fps)
                if strict:
                    measured = data["medido"]["resumen"]
                    if _measured_fps(data) != fps or not measured.get(
                        "fotogramas_muestreados"
                    ):
                        raise RuntimeError(
                            "la referencia no tiene cobertura de fotogramas comprobada"
                        )
                    cohort.append(data)
                    videos.append(
                        {
                            "url": url,
                            "estado": "medido",
                            "fps_original": measured.get("fps"),
                            "fps_medido": fps,
                            "fotogramas": measured["fotogramas_muestreados"],
                            "duracion_s": measured.get("duracion_s"),
                            "tomas": measured.get("tomas"),
                            "toma_mediana_s": measured.get("toma_mediana_s"),
                            "cortes_primeros_3s": measured.get("cortes_primeros_3s"),
                            "cortes_en_golpe": measured.get("cortes_en_golpe"),
                            "analisis_visual": bool(
                                (data.get("tomas_modelo") or {}).get("shots")
                            ),
                        }
                    )
                done["estudiados"] += 1
                title = (data.get("tomas_modelo") or {}).get("summary") or ""
                if title:
                    refs[cat].setdefault("ejemplos", []).append(str(title)[:160])
            except Exception as exc:  # noqa: BLE001
                done["fallos"].append({"url": url, "por_que": str(exc)[:200]})
                if strict:
                    videos.append({"url": url, "estado": "no_medido"})
        if strict:
            complete = wanted > 0 and len(links) == len(cohort) == wanted
            done["cohortes"][cat] = {
                "solicitados": wanted,
                "encontrados": len(links),
                "medidos": len(cohort),
                "fps": fps,
                "completa": complete,
                "videos": videos,
                "perfil_actualizado": False,
            }
            if shorts_ids is not None:
                done["cohortes"][cat]["origen"] = (
                    "archivos_locales" if shorts_media else "lista_fija"
                )
            if not complete:
                done["fallos"].append(
                    {
                        "categoria": cat,
                        "por_que": f"Cohorte incompleta: {len(cohort)}/{wanted} medidos. No se reemplazó el perfil.",
                    }
                )
                continue
        try:
            kwargs: Dict[str, Any] = (
                {"ask": lambda _: ""} if shorts_ids is not None else {}
            )
            done["superskills"].append(
                synthesize(cat, refs=refs, cohort=cohort if strict else None, **kwargs)
            )
            if strict:
                done["cohortes"][cat]["perfil_actualizado"] = True
        except Exception as exc:  # noqa: BLE001
            done["fallos"].append({"categoria": cat, "por_que": str(exc)[:200]})
    _running.clear()
    (home()).mkdir(parents=True, exist_ok=True)
    (home() / "ultimo.json").write_text(
        json.dumps({**done, "fin": time.time()}, ensure_ascii=False), "utf-8"
    )
    return done


def start(categories: Optional[Sequence[str]] = None) -> bool:
    """The school in the background (one at a time); False if it is running."""
    with _lock:
        if _running:
            return False
        _running.update(que="empezando", desde=time.time())
    threading.Thread(
        target=run_all, args=(categories,), daemon=True, name="escuela"
    ).start()
    return True


def status() -> Dict[str, Any]:
    try:
        last = json.loads((home() / "ultimo.json").read_text("utf-8"))
    except (OSError, ValueError):
        last = {}
    refs = references()
    return {
        "en_curso": dict(_running),
        "ultimo": last,
        "categorias": {
            k: {"nombre": c["nombre"],
                "videos": len(c["links"]) + sum(int(x.get("ultimos") or 20) for x in c.get("canales") or []),
                "estudiados": len(list((home() / k).glob("*.json"))) if (home() / k).is_dir() else 0,
                "superskill": bool(skill_text(k))}
            for k, c in refs.items()
        },
    }  # fmt: skip


__all__ = [
    "add",
    "channel_links",
    "light_of",
    "links_of",
    "script_of",
    "blueprint",
    "blueprint_note",
    "category_for",
    "clean_link",
    "cuts_of",
    "ficha",
    "frame_ficha",
    "find",
    "guidance",
    "measure",
    "merge",
    "recut",
    "references",
    "rhythm_note",
    "rules_from_numbers",
    "run_all",
    "skill_text",
    "start",
    "status",
    "study",
    "synthesize",
    "train_brain",
]
