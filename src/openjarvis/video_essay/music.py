"""Music from the internet, with its licence, for the video's bed.

The owner (27 Oct 2026): «que pueda sacar clips de internet y música
también». Sergio looks, best first:

0. **Jamendo** (free key ``JAMENDO_CLIENT_ID``) — the most played songs
   *this week* for the video's genre and mood, instrumental, licences that
   allow money only: «trending but fitting» without someone's chart hit;
1. **Openverse** (no key) — songs under Creative Commons from Jamendo,
   Freesound, ccMixter and others; only the licences that allow use in a
   video that earns money (CC0, BY, BY-SA) unless the owner says the video
   is not for money;
2. **ccMixter** (no key) — remixes and instrumentals under CC, most
   popular first, same rule;
3. **the Internet Archive** — public-domain and CC recordings (old records,
   netlabels);
4. **a song he names** (``música: "canción: …"``) — found with yt-dlp on
   YouTube and the other sites it reads. It is someone's music: the
   platforms usually claim the video (ads go to the owner of the song, or the
   sound is muted), so it is used only when he asks for that song by name and
   the posting package says so. Never by default.

The candidates are ranked (popular now, fits the genre's words, long
enough, no singing over the narration) before one is fetched. The chosen
track is cut or looped to the video's length, faded out, and its
author, licence and link go to the credits (CC BY requires it). Every search
returns a list and never raises; the job falls back to Sergio's own bed.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

UA = {"User-Agent": "Sergio/1.0 (personal video editor)"}
FREE_FOR_MONEY = ("cc0", "pdm", "by", "by-sa")
ASKED = re.compile(r"^\s*(canci[oó]n|song|web)\s*:\s*(.+)$", re.I)
MOODS = {
    # words of a style's music line -> what to search
    "upbeat": "upbeat",
    "motivational": "motivational",
    "cinematic": "cinematic",
    "epic": "epic orchestral",
    "electronic": "electronic",
    "lofi": "lofi chill",
    "lo-fi": "lofi chill",
    "chill": "chill",
    "dark": "dark ambient",
    "tension": "suspense",
    "suspense": "suspense",
    "piano": "piano",
    "ambient": "ambient",
    "hip hop": "hip hop beat",
    "trap": "trap beat",
    "corporate": "corporate",
    "happy": "happy",
    "sad": "sad piano",
    "jazz": "jazz",
    "rock": "rock",
}


# what each genre sounds like when the style says nothing better
GENRE_MUSIC = {
    "inspiracional": "motivational cinematic",
    "cine": "cinematic dramatic",
    "animacion": "playful whimsical",
    "pesada": "energetic hip hop beat",
    "explicado3d": "curious electronic",
    "corto3d": "cinematic adventure",
    "documental": "documentary ambient",
}
_SUNG = re.compile(
    r"\b(feat\.?|ft\.|vocal|vocals|lyrics|remix vocal|acapella|a cappella)\b", re.I
)


@dataclass
class Track:
    url: str  # the audio file (or the page yt-dlp reads, for "web")
    source: str  # openverse | ccmixter | archive | web
    title: str = ""
    creator: str = ""
    licence: str = ""  # short: "CC BY 4.0", "Dominio público"
    licence_url: str = ""
    page: str = ""  # where a person can see it
    seconds: float = 0.0
    path: str = ""  # the local wav, once fetched
    plays: int = 0  # how popular it is right now (when the source says)
    tags: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def credit(self) -> Dict[str, Any]:
        """The line it gets in the job's credits."""
        return {
            "kind": "música",
            "source": self.source,
            "credit": " — ".join(
                x for x in (f"«{self.title}»" if self.title else "", self.creator) if x
            ),
            "licence": self.licence,
            "url": self.page or self.url,
            "licence_url": self.licence_url,
        }


def _get(url: str, **kw: Any) -> Any:
    import httpx

    r = httpx.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=30,
                  follow_redirects=True, **kw)  # fmt: skip
    r.raise_for_status()
    return r.json()


def mood_query(
    profile: Optional[Dict[str, Any]] = None, extra: str = "", genre: str = ""
) -> str:
    """What to search for, from the style's music line ("Upbeat, motivational,
    cinematic electronic music.") or the owner's words; the genre's own
    sound when the style says nothing."""
    if extra.strip():  # his own words win
        return extra.strip()[:60]
    line = str(((profile or {}).get("audio") or {}).get("music") or "").lower()
    found: List[str] = []
    for word, query in MOODS.items():
        if word in line and query not in found:
            found.append(query)
    return " ".join(found[:2]) or GENRE_MUSIC.get(genre, "") or "cinematic"


def rank(tracks: List[Track], query: str, total: float = 0.0) -> List[Track]:
    """Best first: popular now, fits the mood's words, long enough to loop
    little, and no singing (it fights the narration)."""
    want = set(re.findall(r"[a-z]{3,}", query.lower()))
    top = max([t.plays for t in tracks] + [1])

    def score(item: Any) -> float:
        i, t = item
        text = f"{t.title} {t.tags}".lower()
        s = 2.0 * len(want & set(re.findall(r"[a-z]{3,}", text)))
        s += 3.0 * (t.plays / top)  # trending
        s += 1.0 if t.seconds and t.seconds >= min(90.0, total or 90.0) else 0.0
        s -= 4.0 if _SUNG.search(text) else 0.0
        return s - 0.15 * i  # the source's own order (its popularity) breaks ties

    return [t for _, t in sorted(enumerate(tracks), key=score, reverse=True)]


def search_jamendo(query: str, n: int, for_money: bool = True) -> List[Track]:
    """The most played instrumentals of the week on Jamendo for the mood."""
    import os

    key = os.environ.get("JAMENDO_CLIENT_ID", "").strip()
    if not key:
        return []
    try:
        data = _get("https://api.jamendo.com/v3.0/tracks/", params={
            "client_id": key, "format": "json", "limit": max(10, n * 3),
            "fuzzytags": "+".join(re.findall(r"[a-z]{3,}", query.lower())[:3]) or "cinematic",
            "order": "popularity_week", "vocalinstrumental": "instrumental",
            "include": "licenses+musicinfo+stats", "audioformat": "mp32",
        })  # fmt: skip
    except Exception:  # noqa: BLE001
        return []
    out = []
    for item in data.get("results") or []:
        lic = str(item.get("license_ccurl") or "")
        if for_money and ("-nc" in lic or "-nd" in lic):
            continue  # not for money, or no edits (a video is an edit)
        if not item.get("audio"):
            continue
        m = re.search(r"licenses/([a-z\-]+)/([\d.]+)", lic)
        stats = item.get("stats") or {}
        tags = (item.get("musicinfo") or {}).get("tags") or {}
        out.append(Track(
            url=str(item["audio"]), source="jamendo", title=str(item.get("name") or "")[:90],
            creator=str(item.get("artist_name") or "")[:80],
            licence=_short_licence(m.group(1), m.group(2)) if m else "Creative Commons",
            licence_url=lic, page=str(item.get("shareurl") or ""),
            seconds=float(item.get("duration") or 0),
            plays=int(stats.get("rate_listened_total") or stats.get("listened") or 0)
            or max(1, 100 - len(out)),  # the week's order is the popularity
            tags=" ".join(sum((list(v) for v in tags.values() if isinstance(v, list)), [])),
        ))  # fmt: skip
    return out[:n]


def _short_licence(code: str, version: str = "") -> str:
    code = (code or "").lower()
    if code in ("cc0", "pdm", "publicdomain"):
        return "Dominio público (CC0)"
    return f"CC {code.upper()} {version}".strip()


def search_openverse(query: str, n: int, for_money: bool = True) -> List[Track]:
    params: Dict[str, Any] = {
        "q": query[:80],
        "page_size": max(5, n * 3),
        "category": "music",
    }
    if for_money:
        params["license_type"] = "commercial"
    try:
        data = _get("https://api.openverse.org/v1/audio/", params=params)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for item in data.get("results") or []:
        lic = str(item.get("license") or "").lower()
        if for_money and lic not in FREE_FOR_MONEY:
            continue
        secs = float(item.get("duration") or 0) / 1000
        if not item.get("url") or (secs and secs < 20):
            continue
        out.append(Track(
            url=str(item["url"]), source="openverse", title=str(item.get("title") or "")[:90],
            creator=str(item.get("creator") or "")[:80],
            licence=_short_licence(lic, str(item.get("license_version") or "")),
            licence_url=str(item.get("license_url") or ""),
            page=str(item.get("foreign_landing_url") or ""), seconds=secs,
        ))  # fmt: skip
        if len(out) >= n:
            break
    return out


def search_ccmixter(query: str, n: int, for_money: bool = True) -> List[Track]:
    tags = (
        ",".join(re.sub(r"[^a-z0-9 ]", "", query.lower()).split()[:3]) or "instrumental"
    )
    try:
        data = _get("https://ccmixter.org/api/query",
                    params={"f": "json", "tags": tags, "limit": max(5, n * 3), "sort": "rank"})  # fmt: skip
    except Exception:  # noqa: BLE001
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        lic_url = str(item.get("license_url") or "")
        if for_money and ("-nc" in lic_url or "sampling" in lic_url):
            continue
        files = item.get("files") or []
        mp3 = next(
            (f for f in files if str(f.get("download_url", "")).endswith(".mp3")), None
        )
        if not mp3:
            continue
        m = re.search(r"licenses/([a-z\-]+)/([\d.]+)", lic_url)
        out.append(Track(
            url=str(mp3["download_url"]), source="ccmixter",
            title=str(item.get("upload_name") or "")[:90], creator=str(item.get("user_name") or "")[:80],
            licence=_short_licence(m.group(1), m.group(2)) if m else str(item.get("license_name") or "CC"),
            licence_url=lic_url, page=str(item.get("file_page_url") or ""),
        ))  # fmt: skip
        if len(out) >= n:
            break
    return out


def search_archive_audio(query: str, n: int, for_money: bool = True) -> List[Track]:
    free = "(licenseurl:*publicdomain* OR licenseurl:*creativecommons.org/licenses/by/* OR licenseurl:*by-sa*)"
    if not for_money:
        free = "(licenseurl:*publicdomain* OR licenseurl:*creativecommons*)"
    q = f"({query[:80]}) AND mediatype:audio AND {free}"
    try:
        data = _get("https://archive.org/advancedsearch.php",
                    params={"q": q, "fl[]": ["identifier", "title", "creator", "licenseurl"],
                            "rows": n * 2, "output": "json"})  # fmt: skip
    except Exception:  # noqa: BLE001
        return []
    out = []
    for doc in (data.get("response") or {}).get("docs", [])[: n * 2]:
        ident = doc.get("identifier")
        try:
            meta = _get(f"https://archive.org/metadata/{ident}")
        except Exception:  # noqa: BLE001
            continue
        mp3 = next(
            (
                f
                for f in meta.get("files") or []
                if str(f.get("name", "")).lower().endswith(".mp3")
            ),
            None,
        )
        if not mp3:
            continue
        lic_url = str(doc.get("licenseurl") or "")
        creator = doc.get("creator")
        out.append(Track(
            url=f"https://archive.org/download/{ident}/{mp3['name']}", source="archive",
            title=str(mp3.get("title") or doc.get("title") or ident)[:90],
            creator=str(creator[0] if isinstance(creator, list) else creator or "")[:80],
            licence=("Dominio público" if "publicdomain" in lic_url else "Creative Commons") + " (Internet Archive)",
            licence_url=lic_url, page=f"https://archive.org/details/{ident}",
        ))  # fmt: skip
        if len(out) >= n:
            break
    return out


def search_song(
    query: str, n: int, runner: Optional[Callable[[List[str]], str]] = None
) -> List[Track]:
    """A song the owner named, on YouTube and the sites yt-dlp reads."""
    from openjarvis.video_essay import sources

    cmd = sources.ytdlp()
    if not sources.web_allowed() or not (cmd or runner):
        return []
    args = cmd + [
        "--dump-json",
        "--flat-playlist",
        "--no-warnings",
        f"ytsearch{max(1, n)}:{query[:90]}",
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
        ident = item.get("id")
        if not ident and not item.get("url"):
            continue
        out.append(Track(
            url=item.get("url") or f"https://www.youtube.com/watch?v={ident}", source="web",
            title=str(item.get("title") or "")[:90],
            creator=str(item.get("channel") or item.get("uploader") or "")[:80],
            licence="Con derechos de autor, pedida por el dueño (no libre)",
            page=item.get("url") or f"https://www.youtube.com/watch?v={ident}",
            seconds=float(item.get("duration") or 0),
        ))  # fmt: skip
        if len(out) >= n:
            break
    return out


SEARCHES: Dict[str, Callable[..., List[Track]]] = {
    "jamendo": search_jamendo,
    "openverse": search_openverse,
    "ccmixter": search_ccmixter,
    "archive": search_archive_audio,
}


def find(
    query: str,
    n: int = 3,
    *,
    for_money: bool = True,
    order: Iterable[str] = ("jamendo", "ccmixter", "openverse", "archive"),
    searches: Optional[Dict[str, Callable[..., List[Track]]]] = None,
) -> List[Track]:
    """Up to *n* free tracks for *query*, from the first sources that have
    them, best first (:func:`rank`)."""
    table = SEARCHES if searches is None else searches
    out: List[Track] = []
    for name in order:
        if name not in table or len(out) >= n:
            continue
        try:
            out += table[name](query, n - len(out), for_money)
        except Exception:  # noqa: BLE001
            continue
    return rank(out, query)[:n]


def fetch(
    t: Track, dest: Path, total: float, ffmpeg: str, sr: int = 48_000
) -> Optional[str]:
    """The track as a mono wav of *total* seconds: looped when short, faded out."""
    dest.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(
        f"{t.url}|{total:.1f}".encode(), usedforsecurity=False
    ).hexdigest()[:12]
    out = dest / f"musica-{t.source}-{tag}.wav"
    if out.exists() and out.stat().st_size > 10_000:
        t.path = str(out)
        return t.path
    src = t.url
    raw: Optional[Path] = None
    try:
        if t.source == "web":
            from openjarvis.video_essay import sources

            base = sources.ytdlp()
            if not base:
                return None
            pattern = dest / f"cancion-{tag}.%(ext)s"
            subprocess.run(base + ["-q", "--no-warnings", "--no-playlist", "-f", "bestaudio/best",
                                   "-o", str(pattern), t.url],
                           check=True, capture_output=True, timeout=300)  # fmt: skip
            raw = next(iter(sorted(dest.glob(f"cancion-{tag}.*"))), None)
            if raw is None:
                return None
            src = str(raw)
        fade = min(2.5, max(0.5, total * 0.08))
        cmd = [ffmpeg, "-y", "-v", "error", "-stream_loop", "-1", "-i", src, "-t", f"{total + 0.5:.2f}",
               "-ac", "1", "-ar", str(sr),
               "-af", f"afade=t=in:d=0.4,afade=t=out:st={max(0.0, total + 0.5 - fade):.2f}:d={fade:.2f}",
               str(out)]  # fmt: skip
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except Exception:  # noqa: BLE001 — the next track, or Sergio's own bed
        out.unlink(missing_ok=True)
        return None
    finally:
        if raw is not None:
            raw.unlink(missing_ok=True)
    if not out.exists() or out.stat().st_size < 10_000:
        return None
    t.path = str(out)
    return t.path


def pick(
    wish: str,
    profile: Optional[Dict[str, Any]],
    dest: Path,
    total: float,
    ffmpeg: str,
    *,
    for_money: bool = True,
    searches: Optional[Dict[str, Callable[..., List[Track]]]] = None,
    song: Optional[Callable[[str, int], List[Track]]] = None,
    fetcher: Optional[Callable[..., Optional[str]]] = None,
    genre: str = "",
) -> Optional[Track]:
    """The music for a video: the song he named, or a free track for the mood."""
    get = fetcher or fetch
    asked = ASKED.match(wish or "")
    if asked:
        for t in (song or search_song)(asked.group(2).strip(), 2):
            if get(t, dest, total, ffmpeg):
                return t
        return None  # he wanted that song: not a different one in its place
    query = mood_query(
        profile,
        "" if (wish or "").strip().lower() in ("", "auto", "internet") else wish,
        genre,
    )
    for t in find(query, 4, for_money=for_money, searches=searches):
        if get(t, dest, total, ffmpeg):
            return t
    return None


__all__ = [
    "FREE_FOR_MONEY",
    "GENRE_MUSIC",
    "Track",
    "fetch",
    "find",
    "mood_query",
    "pick",
    "search_archive_audio",
    "rank",
    "search_ccmixter",
    "search_jamendo",
    "search_openverse",
    "search_song",
]
