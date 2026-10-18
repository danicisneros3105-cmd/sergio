"""Sergio's mind, in zones like the fly brain, with connections it learns.

The fly connectome (FlyWire, Nature 2024) is not a list of commands: it is
regions with one job each, joined by synapses that change with experience.
Sergio's mind is built the same way. Each zone holds one kind of knowledge:

* ``sentidos``      (antennal and optic lobes): what comes in, coded as a few
                    active Kenyon cells (:func:`kenyon_code`);
* ``memoria``       (mushroom body): engrams, the gist of every past exchange,
                    so what fell out of the context window can come back;
* ``habilidades``   (lateral horn, the innate repertoire): the prompt library
                    and the skills, the know-how he did not have to learn;
* ``conversacion``  (central complex, the heading): the thread of the talk;
* ``herramientas``  (descending neurons): the actions;
* ``integracion``   (the rich club of hubs): the language model that joins all.

Learning is Hebbian: when a memory helped (the owner went on without
correcting him), the synapses from the words of the request to that memory get
stronger, and memories recalled together get linked. Next time the same words
fire those synapses directly, so the right memory comes back at once without
searching everything (the fast path), and a linked one comes with it. A
correction («no, eso no») weakens them; everything unused fades slowly. Zones
that keep helping get a bigger share of the context budget.

It is context engineering, not new model weights, and everything stays in
``~/.openjarvis/connectome`` on the owner's computer. ``SERGIO_CEREBRO=0``
switches it off.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openjarvis.connectome.memory import kenyon_code

ZONES: Dict[str, Dict[str, str]] = {
    "sentidos": {
        "fly": "Lóbulos antenal y óptico",
        "job": "Codifican lo que entra en pocas células activas.",
    },
    "memoria": {
        "fly": "Cuerpo fungiforme",
        "job": "Guarda engramas de cada conversación y los recupera por asociación.",
    },
    "habilidades": {
        "fly": "Cuerno lateral",
        "job": "Prompts y skills: lo que sabe hacer sin aprenderlo.",
    },
    "conversacion": {
        "fly": "Complejo central",
        "job": "Mantiene el rumbo de la conversación.",
    },
    "herramientas": {
        "fly": "Neuronas descendentes",
        "job": "Convierten la decisión en acciones.",
    },
    "integracion": {
        "fly": "Club rico",
        "job": "El modelo de lenguaje une todas las zonas.",
    },
}

RATE = 0.3  # Hebbian step
ASSOC_RATE = 0.2  # memories recalled together
DAILY_DECAY = 0.985
FAST = 0.55  # a synapse this strong answers without searching (fast path)
MAX_ENGRAMS = 4000
MAX_SYNAPSES_PER_CELL = 40
CONTEXT_CHARS = 1400  # the memory zone's base share of the context
_CORRECTION = re.compile(
    r"^\s*(no[,.!]|no\s+(es|era|eso|asi|así)|eso no|mal\b|incorrect|te equivoc|"
    r"al rev[eé]s|that'?s wrong|wrong)",
    re.I,
)
# Secrets never become memories (keys, tokens, passwords).
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|AQ\.[A-Za-z0-9_-]{20,}|"
    r"xox[abp]-[A-Za-z0-9-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"contrase(n|ñ)a\s*[:=]|password\s*[:=]|[A-Za-z0-9+/=_-]{40,})"
)


def enabled() -> bool:
    return os.environ.get("SERGIO_CEREBRO", "1").strip() not in ("0", "false", "no")


def _gist(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return (first if len(first) >= 20 else text)[:limit]


class Brain:
    def __init__(self, folder: Path, *, clock: Any = time.time) -> None:
        self.folder = Path(folder)
        self.clock = clock
        self._lock = threading.Lock()
        self.syn: Dict[str, Dict[str, float]] = {}  # Kenyon cell -> item -> weight
        self.assoc: Dict[str, Dict[str, float]] = {}  # item -> item -> weight
        self.zone_w: Dict[str, float] = {z: 1.0 for z in ZONES}
        self.engrams: Dict[str, Dict[str, Any]] = {}
        self.stats_: Dict[str, int] = {"turns": 0, "fast": 0, "corrections": 0}
        self._decayed = clock()
        self._last: Optional[Dict[str, Any]] = None  # the turn being answered
        self._index: Dict[int, set] = {}  # cell -> engram ids (built on load)
        self._load()

    # -- storage ------------------------------------------------------------
    @property
    def _file(self) -> Path:
        return self.folder / "cerebro.json"

    def _load(self) -> None:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.syn = data.get("syn") or {}
        self.assoc = data.get("assoc") or {}
        self.zone_w.update(data.get("zone_w") or {})
        self.engrams = data.get("engrams") or {}
        self.stats_.update(data.get("stats") or {})
        self._decayed = float(data.get("decayed") or self.clock())
        for eid, e in self.engrams.items():
            for c in e.get("cells") or []:
                self._index.setdefault(int(c), set()).add(eid)

    def _save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "syn": self.syn,
                    "assoc": self.assoc,
                    "zone_w": self.zone_w,
                    "engrams": self.engrams,
                    "stats": self.stats_,
                    "decayed": self._decayed,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self._file)

    # -- plasticity -----------------------------------------------------------
    def _decay(self) -> None:
        days = (self.clock() - self._decayed) / 86400
        if days < 1:
            return
        f = DAILY_DECAY**days
        for table in (self.syn, self.assoc):
            for key in list(table):
                row = {
                    k: round(v * f, 4)
                    for k, v in table[key].items()
                    if abs(v * f) >= 0.02
                }
                if row:
                    table[key] = row
                else:
                    del table[key]
        self._decayed = self.clock()

    def _strengthen(self, cells: List[int], items: List[str], reward: float) -> None:
        for cell in cells:
            row = self.syn.setdefault(str(cell), {})
            for item in items:
                w = row.get(item, 0.0)
                w += RATE * reward * ((1 - w) if reward > 0 else (1 + w))
                row[item] = round(w, 4)
            if len(row) > MAX_SYNAPSES_PER_CELL:
                keep = sorted(row.items(), key=lambda kv: -abs(kv[1]))[
                    :MAX_SYNAPSES_PER_CELL
                ]
                self.syn[str(cell)] = dict(keep)
        if reward > 0 and len(items) > 1:
            for a in items:
                for b in items:
                    if a != b:
                        row = self.assoc.setdefault(a, {})
                        row[b] = round(
                            row.get(b, 0.0) + ASSOC_RATE * (1 - row.get(b, 0.0)), 4
                        )
        for item in items:
            zone = item.split(":", 1)[0]
            if zone in self.zone_w:
                w = self.zone_w[zone] + 0.05 * reward
                self.zone_w[zone] = round(min(2.0, max(0.5, w)), 3)

    # -- recall -----------------------------------------------------------------
    def recall(self, text: str, k: int = 3) -> Tuple[List[str], bool]:
        """The engrams this text brings back, and whether the learned synapses
        alone found them (the fast path, no search)."""
        cells = kenyon_code(text)
        if not cells:
            return [], False
        scores: Dict[str, float] = {}
        for c in cells:
            for item, w in self.syn.get(str(c), {}).items():
                if item.startswith("memoria:") and item[8:] in self.engrams:
                    scores[item[8:]] = scores.get(item[8:], 0.0) + w / len(cells) ** 0.5
        top = max(scores.values(), default=0.0)
        fast = top >= FAST
        if not fast:
            # The slow path: words in common with every stored engram.
            mine = set(cells)
            seen: Dict[str, int] = {}
            for c in cells:
                for eid in self._index.get(c, ()):
                    seen[eid] = seen.get(eid, 0) + 1
            for eid, n in seen.items():
                theirs = len(self.engrams[eid].get("cells") or []) or 1
                jaccard = n / (len(mine) + theirs - n)
                if jaccard >= 0.2:
                    scores[eid] = scores.get(eid, 0.0) + jaccard
        # Spreading activation: a strong memory brings its linked ones.
        for eid, s in list(scores.items()):
            for other, w in self.assoc.get(f"memoria:{eid}", {}).items():
                oid = other.split(":", 1)[1]
                if oid in self.engrams and w >= 0.3:
                    scores[oid] = max(scores.get(oid, 0.0), s * w * 0.5)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return [eid for eid, s in ranked if s > 0.15][:k], fast

    def context(self, text: str) -> Tuple[str, List[str]]:
        """The memory zone's block for this request, within its share."""
        if not enabled() or not text.strip():
            return "", []
        with self._lock:
            self._decay()
            ids, fast = self.recall(text)
            self.stats_["turns"] = self.stats_.get("turns", 0) + 1
            if fast:
                self.stats_["fast"] = self.stats_.get("fast", 0) + 1
            budget = int(CONTEXT_CHARS * self.zone_w.get("memoria", 1.0))
            lines: List[str] = []
            used: List[str] = []
            for eid in ids:
                e = self.engrams[eid]
                day = time.strftime("%Y-%m-%d", time.localtime(e.get("t", 0)))
                line = f"- {day} · El señor: «{e['user']}» → Sergio: «{e['gist']}»"
                if sum(len(x) for x in lines) + len(line) > budget:
                    break
                lines.append(line)
                used.append(f"memoria:{eid}")
            self._last = {"cells": kenyon_code(text), "items": used, "text": text}
        if not lines:
            return "", []
        block = (
            "<cerebro_memoria>\nRecuerdos de conversaciones anteriores que "
            "vienen al caso (úsalos si sirven; no los menciones si no):\n"
            + "\n".join(lines)
            + "\n</cerebro_memoria>"
        )
        return block, used

    # -- learning -----------------------------------------------------------------
    def observe(self, user_text: str, assistant_text: str = "") -> Optional[str]:
        """One finished exchange: reward what was recalled, keep its engram."""
        if not enabled() or not (user_text or "").strip():
            return None
        with self._lock:
            self._decay()
            cells = kenyon_code(user_text)
            last = (
                self._last
                if self._last and self._last.get("text") == user_text
                else None
            )
            if _CORRECTION.match(user_text) and self.stats_.get("prev_items"):
                # The previous answer was wrong: what fed it loses strength.
                self._strengthen(
                    self.stats_["prev_cells"], self.stats_["prev_items"], -1.0
                )
                self.stats_["corrections"] = self.stats_.get("corrections", 0) + 1
            eid = None
            if (
                cells
                and not _SECRET.search(user_text)
                and not _SECRET.search(assistant_text or "")
            ):
                eid = f"{int(self.clock() * 1000):x}"
                self.engrams[eid] = {
                    "t": self.clock(),
                    "cells": cells,
                    "user": _gist(user_text, 200),
                    "gist": _gist(assistant_text, 240),
                }
                for c in cells:
                    self._index.setdefault(c, set()).add(eid)
                self._trim()
            used = list(last["items"]) if last else []
            items = used + ([f"memoria:{eid}"] if eid else [])
            if cells and items:
                self._strengthen(cells, items, 0.6 if used else 0.4)
            self.stats_["prev_cells"] = cells
            self.stats_["prev_items"] = items
            self._last = None
            self._save()
            return eid

    def _trim(self) -> None:
        if len(self.engrams) <= MAX_ENGRAMS:
            return
        strength: Dict[str, float] = {}
        for row in self.syn.values():
            for item, w in row.items():
                if item.startswith("memoria:"):
                    strength[item[8:]] = strength.get(item[8:], 0.0) + w
        doomed = sorted(
            self.engrams,
            key=lambda e: (strength.get(e, 0.0), self.engrams[e].get("t", 0)),
        )[: len(self.engrams) - MAX_ENGRAMS]
        for eid in doomed:
            for c in self.engrams[eid].get("cells") or []:
                self._index.get(int(c), set()).discard(eid)
            del self.engrams[eid]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            synapses = sum(len(r) for r in self.syn.values())
            turns = self.stats_.get("turns", 0)
            return {
                "zones": [
                    {"key": k, **v, "weight": self.zone_w.get(k, 1.0)}
                    for k, v in ZONES.items()
                ],
                "engrams": len(self.engrams),
                "synapses": synapses,
                "associations": sum(len(r) for r in self.assoc.values()),
                "fast_path": round(self.stats_.get("fast", 0) / turns, 3)
                if turns
                else 0.0,
                "corrections": self.stats_.get("corrections", 0),
            }

    def forget(self) -> None:
        with self._lock:
            self.syn, self.assoc, self.engrams, self._index = {}, {}, {}, {}
            self.zone_w = {z: 1.0 for z in ZONES}
            self._save()


_BRAINS: Dict[str, Brain] = {}
_BRAINS_LOCK = threading.Lock()


def get_brain(home: Optional[Path] = None) -> Brain:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    folder = Path(home) / "connectome"
    with _BRAINS_LOCK:
        if str(folder) not in _BRAINS:
            _BRAINS[str(folder)] = Brain(folder)
        return _BRAINS[str(folder)]


def mind_context(text: str) -> str:
    """Everything the zones add to one request: the know-how (prompt library)
    and the memories that come back. Never breaks a turn."""
    parts: List[str] = []
    try:
        from openjarvis.prompt_library import guidance_for

        guidance = guidance_for(text)
        if guidance:
            parts.append(guidance)
    except Exception:  # noqa: BLE001
        pass
    try:
        block, _ = get_brain().context(text)
        if block:
            parts.append(block)
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)


def remember_exchange(user_text: str, assistant_text: str = "") -> None:
    try:
        get_brain().observe(user_text, assistant_text)
    except Exception:  # noqa: BLE001 — learning is a bonus, never a failure
        pass


__all__ = [
    "Brain",
    "ZONES",
    "enabled",
    "get_brain",
    "mind_context",
    "remember_exchange",
]
