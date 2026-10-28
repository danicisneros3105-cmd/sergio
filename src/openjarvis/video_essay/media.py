"""What each shot shows: every source tried in the order the director chose,
inside the job's budget.

For each shot that still needs a picture, the sources go in order (the
shot's own ``source`` first, then the treatment's list): the owner's clips,
free stock and public archives, web clips, film and series scenes, AI video, a 3D shot in
Blender, a picture Sergio makes. Clips are fetched as several candidates
when the mode asks for it and an editor keeps the best (one look per
eight shots, not one per shot). A source that fails for the whole job (no
AI video provider, no Blender) is not tried again, so nothing loops; a shot
with nothing becomes a black card with its words.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openjarvis.video_essay import sources as S
from openjarvis.video_essay.modes import Budget, Mode, OverBudget
from openjarvis.video_essay.plan import Shot

DEFAULT_ORDER = ("library", "stock", "archive", "web", "image")
SEARCH_ORDER = {
    "stock": ("stock", "commons", "nasa"),
    "archive": ("archive", "commons", "nasa"),
    "web": ("web",),
    # a scene of a film or a series (yt-dlp), else a public-domain film
    "film": ("film", "archive"),
}


_STOP = {
    "a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "to", "for", "from", "by",
    "is", "are", "his", "her", "its", "their", "into", "over", "under", "shot", "close", "up",
    "wide", "slow", "camera", "light", "lighting", "cinematic", "view", "scene", "while",
}  # fmt: skip


def queries(shot: Shot, look: str = "") -> List[str]:
    """What to search for a shot: the editor's full picture, then its core
    (the first nouns and verbs), then the two strongest words — a long,
    precise description often finds nothing where a short one finds plenty.
    *look* (the genre's words: «cinematic film still…», «animation
    cartoon…») first goes with the core, so the footage has the genre's look."""
    full = (shot.visual or shot.text)[:120].strip()
    core = [
        w
        for w in "".join(c if c.isalnum() else " " for c in full).split()
        if w.lower() not in _STOP
    ]
    styled = f"{' '.join(core[:4])} {look}".strip() if look and core else ""
    # a named scene chosen for this moment goes first (films.py)
    out = [shot.search.strip(), styled, full, " ".join(core[:5]), " ".join(core[:2])]
    seen: List[str] = []
    for q in out:
        if q and q not in seen:
            seen.append(q)
    return seen


def _url_of(filler: "Filler", path: str) -> str:
    for c in reversed(filler.pool):
        if c.path == path:
            return c.url
    return path


REAL = ("library", "stock", "web", "film", "archive")


def order_for(shot: Shot, preferred: List[str]) -> List[str]:
    """Where to look for a shot's picture, in order. Real footage always
    comes before anything made by a model (owner, 27 Oct 2026: «no solo
    imágenes, sino videos y clips de películas o de internet; casi nunca
    generadas por el modelo»): a shot the editor marked for an AI picture
    first tries the real sources, and a generated one is the last resort."""
    own = [shot.source] if shot.source not in ("", "auto") else []
    if own and own[0] in ("ai", "image"):
        own = [s for s in (preferred or DEFAULT_ORDER) if s in REAL] + own
    out: List[str] = []
    for s in own + list(preferred or DEFAULT_ORDER):
        if s not in out:
            out.append(s)
    made = [s for s in out if s in ("ai", "image")]
    out = [s for s in out if s not in ("ai", "image")] + made
    if "image" not in out:
        out.append("image")
    return out


class Filler:
    """Finds the pictures for a job's shots (state kept between calls)."""

    def __init__(
        self,
        folder: Path,
        mode: Mode,
        budget: Budget,
        *,
        ffmpeg: str,
        style: Dict[str, Any],
        characters: List[Dict[str, str]],
        preferred: List[str],
        library: Optional[Any] = None,
        aspect: str = "16:9",
        searches: Optional[Dict[str, Callable[..., list]]] = None,
        fetch: Optional[Callable[..., Optional[str]]] = None,
        make_image: Optional[Callable[[str], bytes]] = None,
        ai_provider: Optional[Callable[..., str]] = None,
        blender: Optional[Callable[[Shot, Path], str]] = None,
        choose_ask: Optional[Callable[[List[Any], str], str]] = None,
        allow_web: bool = True,
        on_spend: Optional[Callable[[], None]] = None,
    ) -> None:
        self.folder = folder
        self.mode = mode
        self.budget = budget
        self.ffmpeg = ffmpeg
        self.style = style
        self.characters = characters
        self.preferred = [p for p in preferred if p != "web" or allow_web] or list(
            DEFAULT_ORDER
        )
        self.library = library
        self.aspect = aspect
        self.searches = searches
        self.fetch = fetch or S.fetch
        self.make_image = make_image
        self.ai_provider = ai_provider
        self.blender = blender
        self.choose_ask = choose_ask
        self.allow_web = allow_web
        self.on_spend = on_spend or (lambda: None)
        self.broken: set = set()  # sources that cannot work in this job
        self.credits: List[Dict[str, Any]] = []
        # every clip fetched, to cut a new piece of one for a shot that found
        # nothing (better than a still or a black card), and how often each
        # source was used (the same piece never twice)
        self.pool: List[S.Candidate] = []
        self.used: Dict[str, int] = {}

    # -- one source -------------------------------------------------------------------
    def _spend(self, kind: str, amount: float = 1) -> bool:
        try:
            self.budget.spend(kind, amount)
        except OverBudget:
            return False
        self.on_spend()
        return True

    def _clips(self, shot: Shot, src: str, want: int) -> List[S.Candidate]:
        found: List[S.Candidate] = []
        look = str(self.style.get("search_words") or "")
        for query in queries(
            shot, look
        ):  # the genre's look, the full picture, then its core
            found = S.find(
                query,
                want * 2,
                order=SEARCH_ORDER[src],
                landscape=self.aspect != "9:16",
                searches=self.searches,
            )
            if found:
                break
        got: List[S.Candidate] = []
        for c in found:
            if len(got) >= want or not self._spend("downloads"):
                break
            seen = self.used.get(c.url, 0)
            if seen:  # already in the video: a later piece of it, not the same
                c.start = round(c.start + 6.0 * seen, 1)
            if self.fetch(c, self.folder / "clips", shot.dur, self.ffmpeg):
                self.used[c.url] = seen + 1
                self.pool.append(c)
                got.append(c)
        return got

    def _reuse(self, shot: Shot, recent: List[str]) -> Optional[S.Candidate]:
        """A new piece of a clip already found, for a shot that found nothing:
        the one that shares most words with the shot, the last two shots'
        clips only when there is no other."""
        if not self.pool:
            return None
        want = shot.visual or shot.text
        # only a clip that shows the same thing (owner, 28 Oct 2026: «las
        # fotos no tienen sentido»): a hot dog never stands in for a runner.
        # The closest in meaning first; the last shots' clips last.
        options = sorted(
            (c for c in self.pool if S.related(want, c.query) >= 1),
            key=lambda c: (c.url in recent, -S.related(want, c.query)),
        )
        if not options or not self._spend("downloads"):
            return None
        for c in options[:3]:
            seen = self.used.get(c.url, 0)
            step = 2.5 if c.source == "library" else 6.0  # his clips can be short
            piece = S.Candidate(c.url, c.source, c.credit, c.licence, round(c.start + step * seen, 1),
                                query=c.query)  # fmt: skip
            if self.fetch(piece, self.folder / "clips", shot.dur, self.ffmpeg):
                self.used[c.url] = seen + 1
                return piece
        return None

    def _ai(self, shot: Shot) -> Optional[str]:
        from openjarvis.video_essay import aivideo

        if "ai" in self.broken or (
            self.ai_provider is None and not aivideo.available()
        ):
            return None
        secs = max(4.0, shot.dur)
        if not self._spend("ai_seconds", secs):
            return None
        prompt = aivideo.shot_prompt(
            shot.visual or shot.text, self.style, self.characters, shot.camera
        )
        tag = hashlib.sha1(prompt.encode(), usedforsecurity=False).hexdigest()[:12]
        try:
            return aivideo.generate(
                prompt,
                self.folder / "ia" / f"{tag}.mp4",
                secs,
                self.aspect,
                provider=self.ai_provider,
            )
        except Exception:  # noqa: BLE001 — no AI video in this job: do not keep paying for failures
            self.broken.add("ai")
            return None

    def _3d(self, shot: Shot) -> Optional[str]:
        if "3d" in self.broken or self.blender is None:
            return None
        if not self.budget.can("blender") or not self.budget.can("llm"):
            return None
        self._spend("blender")
        try:
            return self.blender(shot, self.folder / "3d")
        except Exception:  # noqa: BLE001 — no Blender here: pictures instead
            self.broken.add("3d")
            return None

    def _image(self, shot: Shot) -> Optional[str]:
        from openjarvis.video_essay.assets import generated

        if "image" in self.broken or not self._spend("images"):
            return None
        query = shot.visual or shot.text
        tag = hashlib.sha1(query.encode(), usedforsecurity=False).hexdigest()[:10]
        made = generated(
            f"{query}. {self.style.get('look', '')[:200]}",
            self.folder / f"{tag}-img",
            self.make_image,
        )
        if made is None:
            self.broken.add("image")  # no image quota today: stop asking
        return made

    # -- all shots --------------------------------------------------------------------
    def fill(
        self, shots: List[Shot], progress: Optional[Callable[[float, str], None]] = None
    ) -> List[Shot]:
        self.folder.mkdir(parents=True, exist_ok=True)
        todo = [
            s
            for s in shots
            if s.kind != "card" and not (s.asset and Path(s.asset).exists())
        ]
        waiting: List[tuple] = []  # (shot, candidates) to choose by eye
        recent: List[str] = []  # the sources of the last shots (no repeats)
        for k, shot in enumerate(todo):
            left = max(1, len(todo) - k)
            want = max(
                1,
                min(
                    self.mode.candidates,
                    int(self.budget.left("downloads") // left) or 1,
                ),
            )
            used = ""
            for src in order_for(shot, self.preferred):
                if src in self.broken or (
                    src in ("web", "film") and not self.allow_web
                ):
                    continue
                if src == "library":
                    found = self.library.pick(shot) if self.library else None
                    if found:
                        shot.asset, used = found, "su biblioteca"
                        self.credits.append({"source": "library", "url": found})
                        if found.lower().endswith(S.VIDEO_EXT):  # reusable too
                            self.used[found] = self.used.get(found, 0) + 1
                            if all(c.url != found for c in self.pool):
                                self.pool.append(S.Candidate(found, "library", path=found,
                                                             query=shot.visual or shot.text))  # fmt: skip
                elif src in SEARCH_ORDER:
                    got = self._clips(shot, src, want)
                    if got:
                        shot.asset, used = got[0].path, got[0].source
                        if len(got) > 1 or self.choose_ask is not None:
                            waiting.append((shot, got))  # checked by eye
                        else:
                            self.credits.append(got[0].to_dict())
                elif src == "ai":
                    found = self._ai(shot)
                    if found:
                        shot.asset, used = found, "video con IA"
                elif src == "3d":
                    found = self._3d(shot)
                    if found:
                        shot.asset, used = found, "toma 3D"
                elif src == "image":
                    piece = self._reuse(shot, recent)
                    if piece is not None:
                        shot.asset, used = piece.path, f"otro trozo de {piece.source}"
                        self.credits.append(piece.to_dict())
                        break
                    found = self._image(shot)
                    if found:
                        shot.asset, used = found, "imagen de Sergio"
                if used:
                    break
            recent = (recent + [_url_of(self, shot.asset) if used else ""])[-2:]
            if used:
                shot.notes.append(f"imagen: {used}")
            else:
                shot.kind, shot.card = "card", "black"
                shot.notes.append("sin imagen: ficha negra")
            if progress:
                progress((k + 1) / max(1, len(todo)), used or "ficha")
        self._choose(waiting)
        return shots

    def _choose(self, waiting: List[tuple]) -> None:
        for i in range(0, len(waiting), 8):
            group = waiting[i : i + 8]
            picks: Dict[int, int] = {}
            if self.choose_ask is not None and self._spend("llm"):
                rows = [
                    {
                        "shot": s.visual or s.text,
                        "frames": [S.frame_of(c.path, self.ffmpeg) for c in cands],
                    }
                    for s, cands in group
                ]
                try:
                    picks = S.choose(rows, self.choose_ask)
                except Exception:  # noqa: BLE001 — the first candidate stays
                    picks = {}
            for row, (shot, cands) in enumerate(group):
                k = picks.get(row, 0)
                if k < 0:  # none of them shows what is said
                    self._replace(shot, cands)
                    continue
                best = cands[k]
                shot.asset = best.path
                self.credits.append(best.to_dict())

    def _replace(self, shot: Shot, rejected: List[S.Candidate]) -> None:
        """A shot whose footage the editor rejected (it shows something else):
        a picture made for it, a related clip, or a card with its words —
        never footage that makes no sense."""
        bad = {c.url for c in rejected}
        self.pool = [c for c in self.pool if c.url not in bad]
        made = self._image(shot)
        if made:
            shot.asset = made
            shot.notes.append("imagen: imagen de Sergio (la toma no encajaba)")
            return
        piece = self._reuse(shot, [])
        if piece is not None:
            shot.asset = piece.path
            self.credits.append(piece.to_dict())
            shot.notes.append(
                f"imagen: otro trozo de {piece.source} (la toma no encajaba)"
            )
            return
        shot.asset, shot.kind, shot.card = "", "card", "black"
        shot.notes.append("sin imagen que encaje: ficha")


__all__ = ["DEFAULT_ORDER", "Filler", "order_for"]
