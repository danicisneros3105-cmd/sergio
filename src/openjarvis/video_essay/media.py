"""What each shot shows: every source tried in the order the director chose,
inside the job's budget.

For each shot that still needs a picture, the sources go in order (the
shot's own ``source`` first, then the treatment's list): the owner's clips,
free stock and public archives, web and film clips, AI video, a 3D shot in
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
}


def order_for(shot: Shot, preferred: List[str]) -> List[str]:
    out: List[str] = []
    for s in ([shot.source] if shot.source not in ("", "auto") else []) + list(
        preferred or DEFAULT_ORDER
    ):
        if s not in out:
            out.append(s)
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

    # -- one source -------------------------------------------------------------------
    def _spend(self, kind: str, amount: float = 1) -> bool:
        try:
            self.budget.spend(kind, amount)
        except OverBudget:
            return False
        self.on_spend()
        return True

    def _clips(self, shot: Shot, src: str, want: int) -> List[S.Candidate]:
        query = (shot.visual or shot.text)[:120]
        found = S.find(
            query,
            want * 2,
            order=SEARCH_ORDER[src],
            landscape=self.aspect != "9:16",
            searches=self.searches,
        )
        got: List[S.Candidate] = []
        for c in found:
            if len(got) >= want or not self._spend("downloads"):
                break
            if self.fetch(c, self.folder / "clips", shot.dur, self.ffmpeg):
                got.append(c)
        return got

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
        tag = hashlib.sha1(prompt.encode()).hexdigest()[:12]
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
        tag = hashlib.sha1(query.encode()).hexdigest()[:10]
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
                if src in self.broken or (src == "web" and not self.allow_web):
                    continue
                if src == "library":
                    found = self.library.pick(shot) if self.library else None
                    if found:
                        shot.asset, used = found, "su biblioteca"
                        self.credits.append({"source": "library", "url": found})
                elif src in SEARCH_ORDER:
                    got = self._clips(shot, src, want)
                    if got:
                        shot.asset, used = got[0].path, got[0].source
                        if len(got) > 1:
                            waiting.append((shot, got))
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
                    found = self._image(shot)
                    if found:
                        shot.asset, used = found, "imagen de Sergio"
                if used:
                    break
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
                best = cands[picks.get(row, 0)]
                shot.asset = best.path
                self.credits.append(best.to_dict())


__all__ = ["DEFAULT_ORDER", "Filler", "order_for"]
