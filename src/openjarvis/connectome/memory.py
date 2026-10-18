"""The mushroom body: learned shortcuts from the owner's own choices.

A query is coded by a few Kenyon cells out of 2 000 (the fly has about 2 000
per side, and only a small fraction fire for any one odor). When the owner picks
a destination, dopamine strengthens the synapses from those cells to it; when a
suggestion is dismissed they weaken; everything fades slowly so old habits lose
to new ones. The output for a destination is the sum of its active synapses.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
import unicodedata
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KENYON_CELLS = 2000
MAX_ACTIVE = 14  # sparse: well under 1 % of the cells for one query
LEARNING_RATE = 0.35
DAILY_DECAY = 0.99
_STOP = {
    "a", "al", "de", "del", "el", "la", "las", "lo", "los", "en", "y", "o", "un", "una", "por", "para",
    "con", "mi", "me", "que", "quiero", "abre", "abrir", "ir", "ve", "the", "to", "open", "go", "my",
}  # fmt: skip
_ACTION = re.compile(r"^[a-z0-9][a-z0-9_.:/?=&-]{0,120}$")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def kenyon_code(query: str) -> List[int]:
    """The few Kenyon cells this query activates (whole words and their first
    letters, so «presion» and «presión arterial» share cells)."""
    words = [w for w in re.findall(r"[a-z0-9]+", _fold(query)) if w not in _STOP]
    features: List[str] = []
    for w in words:
        features.append(f"w:{w}")
        if len(w) > 4:
            features.append(f"p:{w[:4]}")
    cells: List[int] = []
    for f in features:
        cell = zlib.crc32(f.encode()) % KENYON_CELLS
        if cell not in cells:
            cells.append(cell)
    return cells[:MAX_ACTIVE]


class MushroomBody:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._w: Dict[str, Dict[str, float]] = {}
        self._uses: Dict[str, int] = {}
        self._decayed_at = time.time()
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self._w = {
            str(k): {str(a): float(v) for a, v in row.items()}
            for k, row in (data.get("w") or {}).items()
        }
        self._uses = {str(a): int(n) for a, n in (data.get("uses") or {}).items()}
        self._decayed_at = float(data.get("decayed_at") or time.time())

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {"w": self._w, "uses": self._uses, "decayed_at": self._decayed_at}
            ),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def _decay(self, now: float) -> None:
        days = (now - self._decayed_at) / 86400
        if days < 1:
            return
        factor = DAILY_DECAY**days
        for cell in list(self._w):
            row = {
                a: v * factor
                for a, v in self._w[cell].items()
                if abs(v * factor) >= 0.01
            }
            if row:
                self._w[cell] = row
            else:
                del self._w[cell]
        self._decayed_at = now

    def reinforce(
        self, query: str, action: str, reward: float = 1.0, now: Optional[float] = None
    ) -> bool:
        """Dopamine: +1 when the owner chose *action* for *query*, below 0 when dismissed."""
        if not _ACTION.match(action or ""):
            return False
        cells = kenyon_code(query)
        if not cells:
            return False
        reward = max(-1.0, min(1.0, float(reward)))
        with self._lock:
            self._decay(now or time.time())
            for cell in cells:
                row = self._w.setdefault(str(cell), {})
                w = row.get(action, 0.0)
                # Bounded Hebbian step: saturates near +1 and -1.
                w += LEARNING_RATE * reward * ((1 - w) if reward > 0 else (1 + w))
                row[action] = round(w, 4)
            if reward > 0:
                self._uses[action] = self._uses.get(action, 0) + 1
            self._save()
        return True

    def predict(
        self, query: str, k: int = 5, threshold: float = 0.15
    ) -> List[Tuple[str, float]]:
        """Mushroom body output: destinations ranked by their active synapses."""
        cells = kenyon_code(query)
        if not cells:
            return []
        scores: Dict[str, float] = {}
        with self._lock:
            for cell in cells:
                for action, w in self._w.get(str(cell), {}).items():
                    scores[action] = scores.get(action, 0.0) + w
        norm = math.sqrt(len(cells))
        ranked = sorted(((a, s / norm) for a, s in scores.items()), key=lambda x: -x[1])
        return [(a, round(s, 3)) for a, s in ranked if s >= threshold][:k]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            synapses = sum(len(r) for r in self._w.values())
            top = sorted(self._uses.items(), key=lambda x: -x[1])[:5]
        return {
            "kenyon_cells": KENYON_CELLS,
            "active_cells": len(self._w),
            "synapses": synapses,
            "top": top,
        }

    def forget(self) -> None:
        with self._lock:
            self._w, self._uses = {}, {}
            self._save()


_MEMORIES: Dict[str, MushroomBody] = {}
_MEMORIES_LOCK = threading.Lock()


def get_memory(home: Optional[Path] = None) -> MushroomBody:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    path = Path(home) / "connectome" / "memoria.json"
    with _MEMORIES_LOCK:
        if str(path) not in _MEMORIES:
            _MEMORIES[str(path)] = MushroomBody(path)
        return _MEMORIES[str(path)]


__all__ = ["KENYON_CELLS", "MAX_ACTIVE", "MushroomBody", "get_memory", "kenyon_code"]
