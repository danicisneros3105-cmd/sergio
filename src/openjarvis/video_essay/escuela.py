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
    m = re.search(r"instagram\.com/(?:reels?|p)/([\w-]+)", url)
    if m:
        return f"https://www.instagram.com/reel/{m.group(1)}/"
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
    m = re.search(r"(?:v=|reel/)([\w-]+)", url)
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
) -> List[str]:
    """The latest ``ultimos`` videos of a channel (its ``pestana`` first:
    shorts or videos; the other one if that is empty), kept a day."""
    url = str(channel.get("url") or "").rstrip("/")
    if not re.match(r"https://(www\.)?youtube\.com/@[\w.-]+$", url):
        raise ValueError(f"canal no válido: {url}")
    n = max(1, min(50, int(channel.get("ultimos") or 20)))
    max_min = float(channel.get("max_minutos") or 0)
    tab = str(channel.get("pestana") or "videos")
    slug = re.sub(r"[^\w.-]+", "-", url.rsplit("/", 1)[-1])
    cache = (root or home()) / "canales" / f"{slug}-{tab}-{n}-{int(max_min)}.json"
    try:
        saved = json.loads(cache.read_text("utf-8"))
        if time.time() - float(saved.get("at") or 0) < CHANNEL_TTL_S and saved.get(
            "links"
        ):
            return list(saved["links"])
    except (OSError, ValueError):
        pass
    ids: List[str] = []
    for t in [tab] + [x for x in ("videos", "shorts") if x != tab]:
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
    args = cmd + ["--no-warnings", "--no-playlist", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
                  "--merge-output-format", "mp4", "-o", str(dest / f"{vid}.%(ext)s"), url]  # fmt: skip
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


def _probe(path: Path) -> Dict[str, float]:
    exe = shutil.which("ffprobe") or "ffprobe"
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


def _cut_times(d: Sequence[float], fps: int) -> List[float]:
    """Hard cuts from the histogram jumps between consecutive frames."""
    import numpy as np

    if not len(d):
        return []
    d = np.asarray(d, dtype="float32")
    thr = max(
        0.32, float(np.median(d) + 4 * (np.median(np.abs(d - np.median(d))) + 1e-6))
    )
    out: List[float] = []
    for i, v in enumerate(d, start=1):
        if v >= thr and (not out or i / fps - out[-1] >= 0.2):
            out.append(round(i / fps, 2))
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
    return _cut_times(d, fps)


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


def measure(
    path: Path,
    *,
    words: Optional[List[Dict[str, Any]]] = None,
    fps: int = FPS,
) -> Dict[str, Any]:
    """Every second of *path*, measured: the cut timeline and what is seen and
    heard. Frames are read one second at a time (``fps`` of them), so a long
    video at 30 fps never sits whole in memory."""
    import numpy as np

    from openjarvis.video_essay import color

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    meta = _probe(path)
    w = 96
    h = max(2, int(round(w * (meta["h"] or 16) / (meta["w"] or 9) / 2) * 2))
    audio = _audio(path, ffmpeg)
    rate = 8000
    words = words if words is not None else transcribe(path)
    jumps: List[float] = []  # histogram jump between every two frames (cuts)
    prev = None
    prev_hist = None
    prev_lum = None
    seconds: List[Dict[str, Any]] = []
    frames_seen = 0
    luma = np.asarray(LUMA, dtype="float32")
    for s, chunk in enumerate(_chunks(path, w, h, fps, ffmpeg)):
        frames_seen += len(chunk)
        for f in chunk:
            hist = _hist(f)
            if prev_hist is not None:
                jumps.append(float(0.5 * np.abs(hist - prev_hist).sum()))
            prev_hist = hist
        seq = chunk if prev is None else np.concatenate([prev[None], chunk])
        prev = chunk[-1]
        f = chunk[len(chunk) // 2]
        hsv_s = (f.max(axis=2).astype("int16") - f.min(axis=2)).mean() / 255
        steps = (
            np.abs(np.diff(seq.astype("int16"), axis=0)).mean(axis=(1, 2, 3)) / 255
            if len(seq) > 1
            else np.zeros(1)
        )
        motion = float(np.median(steps))  # a cut is not motion
        lum = (seq.astype("float32") / 255) @ luma  # (n, h, w)
        means = lum.mean(axis=(1, 2))
        # the camera: how the picture slides between frames, cuts left out
        moves = [
            _shift(lum[i - 1], lum[i])
            for i in range(1, len(lum))
            if steps[i - 1] < 0.25
        ]
        speed = [abs(x) + abs(y) for x, y in moves]
        pan = float(np.median(speed)) * fps if speed else 0.0
        shake = float(np.std(np.diff(speed))) * fps if len(speed) > 2 else 0.0
        # effects: a flash jumps up and comes back; black frames are fades
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
        # hits: 20 ms energies that jump to 3x their recent average
        e = (
            (a[: len(a) // 160 * 160].reshape(-1, 160) ** 2).mean(axis=1)
            if len(a) >= 160
            else np.zeros(1)
        )
        avg = np.convolve(e, np.ones(10) / 10, "same") + 1e-7
        hits = int(((e > 3 * avg) & (e > 1e-4)).sum() // 2)
        try:  # one larger frame a second for faces and words
            big = _one_frame(path, s + 0.5, ffmpeg)
            gray = np.asarray(big.convert("L"))
            faces = len(color._faces(gray))
            rows = text_rows(gray)
            main = color.hex_of(color.palette(big, 3)[0][0])
        except Exception:  # noqa: BLE001
            faces, rows, main = 0, {}, ""
        said = [x["w"] for x in words if s <= float(x.get("t", -1)) < s + 1]
        light = light_of(f)
        seconds.append({
            "t": s, "cortes": 0,
            "brillo": round(float(f.mean() / 255), 3), "color": round(float(hsv_s), 3), "principal": main,
            "movimiento": round(motion, 3), "caras": faces,
            "luz": light, "camara": round(pan, 3), "temblor": round(shake, 3),
            "destellos": flashes, "negro": round(blacks, 2),
            "texto": {k: round(v, 2) for k, v in rows.items()},
            "volumen_db": round(20 * float(np.log10(rms + 1e-6)), 1), "golpes": hits,
            "palabras": len(said), "dice": " ".join(said)[:120],
        })  # fmt: skip
    dur = meta["dur"] or frames_seen / fps
    cuts = _cut_times(jumps, fps)
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
    }  # fmt: skip
    return {
        "meta": meta,
        "cortes": cuts,
        "tomas": shots,
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


def transcribe(path: Path) -> List[Dict[str, Any]]:
    """Words and their times (faster-whisper on this PC); none if it is missing."""
    try:
        from faster_whisper import WhisperModel
    except Exception:  # noqa: BLE001
        return []
    try:
        model = WhisperModel(
            os.environ.get("SERGIO_ESCUELA_WHISPER", "small"), compute_type="int8"
        )
        segs, _ = model.transcribe(str(path), word_timestamps=True, vad_filter=True)
        return [
            {"t": round(w.start, 2), "w": w.word.strip()}
            for s in segs
            for w in (s.words or [])
        ]
    except Exception as exc:  # noqa: BLE001
        log.info("no transcription: %s", exc)
        return []


# -- 3. study one video ------------------------------------------------------------------------


def study(url: str, category: str, *, root: Optional[Path] = None,
          watcher: Optional[Callable[[str], Dict[str, Any]]] = None,
          fetch: Optional[Callable[[str, Path], Path]] = None, fps: int = FPS) -> Dict[str, Any]:  # fmt: skip
    """Download, measure every second and (with a model) watch one video."""
    root = root or home()
    folder = root / category
    out = folder / f"{video_id(url)}.json"
    if out.is_file():
        return json.loads(out.read_text("utf-8"))
    path = (fetch or download)(url, root / "videos")
    data: Dict[str, Any] = {
        "url": url,
        "categoria": category,
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
            "destellos_por_min", "negro"]  # fmt: skip
    out: Dict[str, Any] = {k: _median([s.get(k) for s in sums]) for k in keys}
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
    out.append("Vertical 9:16." if m.get("vertical") else "Horizontal 16:9.")
    return out


def synthesize(category: str, *, root: Optional[Path] = None, ask: Optional[Callable[[str], str]] = None,
               refs: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:  # fmt: skip
    """Join a category's studies into its style and its superskill."""
    from openjarvis.video_essay import style

    root = root or home()
    refs = refs or references()
    cat = refs[category]
    studies = [
        json.loads(p.read_text("utf-8"))
        for p in sorted((root / category).glob("*.json"))
    ]
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
                rules, by = lines, "modelo con los números medidos"
        except Exception as exc:  # noqa: BLE001
            log.info("superskill by code only: %s", exc)
    rules = rules + seed  # the hand-written script rules (read from real transcripts)
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
    }  # fmt: skip
    folder = style.learned_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}.json").write_text(
        json.dumps(prof, ensure_ascii=False, indent=1), "utf-8"
    )
    skill = root / "superskills" / category / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
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


def find(ref: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """A studied reference by its link or id (any category)."""
    root = root or home()
    vid = video_id(clean_link(ref)) if "/" in ref else ref.strip()
    for path in sorted(root.glob(f"*/{vid}.json")):
        if path.parent.name != "superskills":
            return json.loads(path.read_text("utf-8"))
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
    ]
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
) -> Dict[str, Any]:
    """Study every reference and write every superskill; a video that fails
    is reported and the rest go on."""
    refs = references()
    todo = [c for c in (categories or refs) if c in refs]
    done: Dict[str, Any] = {"estudiados": 0, "fallos": [], "superskills": []}
    for cat in todo:
        try:
            links = links_of(refs[cat])
        except Exception as exc:  # noqa: BLE001 — a channel that fails: its links still count
            done["fallos"].append({"categoria": cat, "por_que": str(exc)[:200]})
            links = list(refs[cat]["links"])
        fps = int(refs[cat].get("fps") or FPS)
        for url in links:
            _running.update(
                que=f"{cat}: {url}", desde=_running.get("desde") or time.time()
            )
            if on_step:
                on_step(f"Estudiando {url} ({cat})")
            try:
                data = study(url, cat, fps=fps)
                done["estudiados"] += 1
                title = (data.get("tomas_modelo") or {}).get("summary") or ""
                if title:
                    refs[cat].setdefault("ejemplos", []).append(str(title)[:160])
            except Exception as exc:  # noqa: BLE001
                done["fallos"].append({"url": url, "por_que": str(exc)[:200]})
        try:
            done["superskills"].append(synthesize(cat, refs=refs))
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
    "find",
    "guidance",
    "measure",
    "merge",
    "recut",
    "references",
    "rules_from_numbers",
    "run_all",
    "skill_text",
    "start",
    "status",
    "study",
    "synthesize",
    "train_brain",
]
