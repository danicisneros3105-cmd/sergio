"""Sergio's mind, in zones like the fly brain, with connections it learns.

The fly connectome (FlyWire, Nature 2024) is not a list of commands: it is
regions with one job each, joined by synapses that change with experience.
Sergio's mind is built the same way, and every zone holds real connections:

* ``sentidos``      (antennal and optic lobes): what comes in, coded as a few
                    active Kenyon cells (:func:`kenyon_code`), and the channel
                    it came through (chat, voz, Nodes, Agent Swarm, Cowork);
* ``memoria``       (mushroom body): engrams, the gist of every past exchange,
                    so what fell out of the context window can come back;
* ``habilidades``   (lateral horn, the innate repertoire): the prompt-library
                    passages that were used, and how much they helped;
* ``conversacion``  (central complex, the heading): the thread, each engram
                    linked to the one that followed it;
* ``herramientas``  (descending neurons): the tools that worked, or failed,
                    for this kind of request;
* ``integracion``   (the rich club of hubs): the language model that joins all.

Learning is Hebbian with a dopamine-like reward. A finished exchange
strengthens the synapses from the Kenyon cells of the request to everything
that took part: the memories recalled, the passages used, the tools that
succeeded (a failed tool is punished). Items that worked together get linked.
A correction («no, eso no») punishes what fed the previous answer. Everything
unused fades. Next time the same words fire those synapses directly: the
right memory comes back without searching everything (the fast path), and the
tools that worked are suggested before the model has to discover them again
(learned routes). Zones that keep helping get a bigger share of the context.

The working set lives in memory (dictionaries, instant to read) and every
change is written incrementally to SQLite (``cerebro.db``, WAL), so a turn
costs a few row writes however big the mind grows. The older ``cerebro.json``
is migrated once. It is context engineering, not new model weights; it stays
in ``~/.openjarvis/connectome`` on the owner's computer, never keeps secrets,
and ``SERGIO_CEREBRO=0`` switches it off.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from openjarvis.connectome import neurons as _neurons
from openjarvis.connectome.memory import kenyon_code

ZONES: Dict[str, Dict[str, str]] = {
    "sentidos": {
        "fly": "Lóbulos antenal y óptico",
        "job": "Codifican lo que entra en pocas células activas y por qué canal llegó.",
    },
    "memoria": {
        "fly": "Cuerpo fungiforme",
        "job": "Guarda engramas de cada conversación y los recupera por asociación.",
    },
    "habilidades": {
        "fly": "Cuerno lateral",
        "job": "Prompts y skills: lo que sabe hacer sin aprenderlo, y cuáles le sirvieron.",
    },
    "conversacion": {
        "fly": "Complejo central",
        "job": "Mantiene el rumbo: cada recuerdo enlazado con el que vino después.",
    },
    "herramientas": {
        "fly": "Neuronas descendentes",
        "job": "Convierten la decisión en acciones y aprenden qué herramienta funciona.",
    },
    "integracion": {
        "fly": "Club rico",
        "job": "El modelo de lenguaje une todas las zonas.",
    },
}
CHANNELS = ("chat", "voz", "nodes", "swarm", "cowork", "escritorio")

RATE = 0.3  # Hebbian step
ASSOC_RATE = 0.2  # items that worked together
SEQ_RATE = 0.35  # one engram followed by the next (the thread)
THREAD_GAP_S = 30 * 60  # longer silence: a new thread
DAILY_DECAY = 0.985
FAST = 0.55  # a synapse this strong answers without searching (fast path)
ROUTE_MIN = 0.35  # a tool this strongly tied to the words is suggested
AVOID_MAX = -0.35  # a tool this strongly punished is flagged
MAX_ENGRAMS = 4000
MAX_SYNAPSES_PER_CELL = 60
CONTEXT_CHARS = 1400  # the memory zone's base share of the context
PENDING_TTL_S = 15 * 60
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
# Tools that only think or look things up about Sergio himself are not routes.
_NOT_ROUTES = {"think", "memory_search", "memory_store"}

# The turn being answered on this thread: tools note themselves here.
_turn = threading.local()
SELECT_MAX_CHARS = 1500  # a long prompt (a Node's turn) is not one request
FLY_GAIN = 3.0  # mushroom-body drive -> neuron activation (about three rewards fire it)
FLY_ROUTE = 0.06  # a tool this wanted by the mushroom body is suggested
FLY_AVOID = -0.04  # a tool this punished is flagged
SELECTION_TTL_S = 20 * 60


def enabled() -> bool:
    return os.environ.get("SERGIO_CEREBRO", "1").strip() not in ("0", "false", "no")


def _gist(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return (first if len(first) >= 20 else text)[:limit]


def _key(text: str) -> str:
    """The same request however it was spaced or accented."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()[-800:]


def _clean_name(name: str) -> str:
    return re.sub(r"[^\w.\- ]+", "", str(name or ""))[:80].strip()


class Brain:
    def __init__(self, folder: Path, *, clock: Any = time.time) -> None:
        self.folder = Path(folder)
        self.clock = clock
        self._lock = threading.RLock()
        self.syn: Dict[str, Dict[str, float]] = {}  # Kenyon cell -> item -> weight
        self.assoc: Dict[str, Dict[str, float]] = {}  # item -> item -> weight
        self.zone_w: Dict[str, float] = {z: 1.0 for z in ZONES}
        self.engrams: Dict[str, Dict[str, Any]] = {}
        self.stats_: Dict[str, Any] = {"turns": 0, "fast": 0, "corrections": 0}
        self._decayed = clock()
        self._pending: Dict[str, Dict[str, Any]] = {}  # request key -> its turn
        self._index: Dict[int, Set[str]] = {}  # cell -> engram ids
        self._last_engram: Dict[str, Tuple[str, float]] = {}  # channel -> (id, t)
        self._dirty_syn: Set[Tuple[str, str]] = set()
        self._dirty_assoc: Set[Tuple[str, str]] = set()
        self._dirty_eng: Set[str] = set()
        self._gone_eng: Set[str] = set()
        self._full_rewrite = False
        self._db: Optional[sqlite3.Connection] = None
        self._load()

    # -- storage ------------------------------------------------------------
    @property
    def _file(self) -> Path:
        return self.folder / "cerebro.db"

    @property
    def _legacy(self) -> Path:
        return self.folder / "cerebro.json"

    def _conn(self) -> sqlite3.Connection:
        if self._db is None:
            self.folder.mkdir(parents=True, exist_ok=True)
            fresh = not self._file.exists()
            db = sqlite3.connect(str(self._file), check_same_thread=False)
            try:  # memories of conversations: only the owner's account
                os.chmod(self._file, 0o600)
            except OSError:
                pass
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS syn (cell TEXT, item TEXT, w REAL,
                    PRIMARY KEY (cell, item)) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS assoc (a TEXT, b TEXT, w REAL,
                    PRIMARY KEY (a, b)) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS engrams (id TEXT PRIMARY KEY, data TEXT);
                CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
                """
            )
            if fresh:
                try:
                    os.chmod(self._file, 0o600)
                except OSError:
                    pass
            self._db = db
        return self._db

    def _load(self) -> None:
        if not self._file.exists() and self._legacy.exists():
            self._migrate()
            return
        if not self._file.exists():
            return
        try:
            db = self._conn()
            for cell, item, w in db.execute("SELECT cell, item, w FROM syn"):
                self.syn.setdefault(cell, {})[item] = w
            for a, b, w in db.execute("SELECT a, b, w FROM assoc"):
                self.assoc.setdefault(a, {})[b] = w
            for eid, data in db.execute("SELECT id, data FROM engrams"):
                self.engrams[eid] = json.loads(data)
            meta = dict(db.execute("SELECT k, v FROM meta").fetchall())
        except (sqlite3.Error, ValueError):
            return
        self.zone_w.update(json.loads(meta.get("zone_w", "{}")))
        self.stats_.update(json.loads(meta.get("stats", "{}")))
        self._decayed = float(meta.get("decayed") or self.clock())
        self._reindex()

    def _migrate(self) -> None:
        """The first mind lived in one JSON file: bring it over once."""
        try:
            data = json.loads(self._legacy.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.syn = data.get("syn") or {}
        self.assoc = data.get("assoc") or {}
        self.zone_w.update(data.get("zone_w") or {})
        self.engrams = data.get("engrams") or {}
        self.stats_.update(data.get("stats") or {})
        self._decayed = float(data.get("decayed") or self.clock())
        self._reindex()
        self._full_rewrite = True
        self._save()
        try:
            self._legacy.replace(self._legacy.with_suffix(".json.migrado"))
        except OSError:
            pass

    def _reindex(self) -> None:
        self._index = {}
        for eid, e in self.engrams.items():
            for c in e.get("cells") or []:
                self._index.setdefault(int(c), set()).add(eid)

    def _save(self) -> None:
        """Write only what changed since the last save (or all, after decay)."""
        db = self._conn()
        with db:
            if self._full_rewrite:
                db.execute("DELETE FROM syn")
                db.execute("DELETE FROM assoc")
                db.executemany(
                    "INSERT INTO syn VALUES (?, ?, ?)",
                    ((c, i, w) for c, row in self.syn.items() for i, w in row.items()),
                )
                db.executemany(
                    "INSERT INTO assoc VALUES (?, ?, ?)",
                    (
                        (a, b, w)
                        for a, row in self.assoc.items()
                        for b, w in row.items()
                    ),
                )
                db.execute("DELETE FROM engrams")
                db.executemany(
                    "INSERT INTO engrams VALUES (?, ?)",
                    (
                        (e, json.dumps(d, ensure_ascii=False))
                        for e, d in self.engrams.items()
                    ),
                )
            else:
                for cell, item in self._dirty_syn:
                    w = self.syn.get(cell, {}).get(item)
                    if w is None:
                        db.execute(
                            "DELETE FROM syn WHERE cell=? AND item=?", (cell, item)
                        )
                    else:
                        db.execute(
                            "INSERT OR REPLACE INTO syn VALUES (?, ?, ?)",
                            (cell, item, w),
                        )
                for a, b in self._dirty_assoc:
                    w = self.assoc.get(a, {}).get(b)
                    if w is None:
                        db.execute("DELETE FROM assoc WHERE a=? AND b=?", (a, b))
                    else:
                        db.execute(
                            "INSERT OR REPLACE INTO assoc VALUES (?, ?, ?)", (a, b, w)
                        )
                for eid in self._gone_eng:
                    db.execute("DELETE FROM engrams WHERE id=?", (eid,))
                for eid in self._dirty_eng - self._gone_eng:
                    if eid in self.engrams:
                        db.execute(
                            "INSERT OR REPLACE INTO engrams VALUES (?, ?)",
                            (eid, json.dumps(self.engrams[eid], ensure_ascii=False)),
                        )
            stats = {k: v for k, v in self.stats_.items() if not k.startswith("prev_")}
            prev = {k: v for k, v in self.stats_.items() if k.startswith("prev_")}
            db.executemany(
                "INSERT OR REPLACE INTO meta VALUES (?, ?)",
                [
                    ("zone_w", json.dumps(self.zone_w)),
                    ("stats", json.dumps({**stats, **prev})),
                    ("decayed", str(self._decayed)),
                ],
            )
        self._dirty_syn.clear()
        self._dirty_assoc.clear()
        self._dirty_eng.clear()
        self._gone_eng.clear()
        self._full_rewrite = False

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
        self._full_rewrite = True

    def _set_syn(self, cell: str, item: str, w: float) -> None:
        self.syn.setdefault(cell, {})[item] = round(w, 4)
        self._dirty_syn.add((cell, item))

    def _set_assoc(self, a: str, b: str, w: float) -> None:
        self.assoc.setdefault(a, {})[b] = round(w, 4)
        self._dirty_assoc.add((a, b))

    def _strengthen(
        self, cells: Iterable[int], items: List[str], reward: float
    ) -> None:
        for cell in cells:
            key = str(cell)
            row = self.syn.get(key, {})
            for item in items:
                w = row.get(item, 0.0)
                w += RATE * reward * ((1 - w) if reward > 0 else (1 + w))
                self._set_syn(key, item, w)
            row = self.syn.get(key, {})
            if len(row) > MAX_SYNAPSES_PER_CELL:
                keep = dict(
                    sorted(row.items(), key=lambda kv: -abs(kv[1]))[
                        :MAX_SYNAPSES_PER_CELL
                    ]
                )
                for item in set(row) - set(keep):
                    self._dirty_syn.add((key, item))
                self.syn[key] = keep
        if reward > 0 and len(items) > 1:
            for a in items:
                for b in items:
                    if a != b:
                        w = self.assoc.get(a, {}).get(b, 0.0)
                        self._set_assoc(a, b, w + ASSOC_RATE * (1 - w))
        for zone in {item.split(":", 1)[0] for item in items}:
            if zone in self.zone_w:
                w = self.zone_w[zone] + 0.05 * reward
                self.zone_w[zone] = round(min(2.0, max(0.5, w)), 3)

    # -- recall -----------------------------------------------------------------
    def _activation(self, cells: List[int], prefix: str) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        norm = len(cells) ** 0.5 if cells else 1.0
        for c in cells:
            for item, w in self.syn.get(str(c), {}).items():
                if item.startswith(prefix):
                    scores[item] = scores.get(item, 0.0) + w / norm
        return scores

    def recall(self, text: str, k: int = 3) -> Tuple[List[str], bool]:
        """The engrams this text brings back, and whether the learned synapses
        alone found them (the fast path, no search)."""
        cells = kenyon_code(text)
        if not cells:
            return [], False
        scores = {
            item[8:]: s
            for item, s in self._activation(cells, "memoria:").items()
            if item[8:] in self.engrams
        }
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
        # Spreading activation: a strong memory brings its linked ones, and
        # the thread brings what came right after it.
        for eid, s in list(scores.items()):
            for other, w in self.assoc.get(f"memoria:{eid}", {}).items():
                zone, oid = other.split(":", 1)
                if (
                    zone in ("memoria", "conversacion")
                    and oid in self.engrams
                    and w >= 0.3
                ):
                    scores[oid] = max(scores.get(oid, 0.0), s * w * 0.5)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return [eid for eid, s in ranked if s > 0.15][:k], fast

    # -- the core: the fly's mushroom body decides -----------------------------------
    def fly(self) -> Any:
        """Sergio's main mushroom body (connectome/core.py)."""
        from openjarvis.connectome.core import core_at

        return core_at(self.folder).brain("sergio")

    def routes(
        self, text: str, kc: Any = None
    ) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
        """Tools the mushroom body learned to use for requests like this one
        (and the ones it learned to avoid)."""
        try:
            mb = self.fly()
            kc = mb.kenyon(text) if kc is None else kc
            tools = [a for a in mb.codes if a.startswith("tool:")]
            acts = mb.scores(kc, tools) if tools and len(kc) else {}
        except Exception:  # noqa: BLE001 — no brain: no learned routes
            return [], []
        good = sorted(
            ((a[5:], v) for a, v in acts.items() if v >= FLY_ROUTE), key=lambda x: -x[1]
        )
        bad = sorted(
            ((a[5:], v) for a, v in acts.items() if v <= FLY_AVOID), key=lambda x: x[1]
        )
        return good[:4], bad[:3]

    def select_tools(self, text: str, kc: Any = None) -> Optional[_neurons.Selection]:
        """The core decision: innate (lateral horn: the words) plus learned
        (mushroom body: dopamine-trained synapses) decide which neurons fire,
        and so which tools the agent gets this turn."""
        if not text.strip() or len(text) > SELECT_MAX_CHARS:
            return None
        learned: Dict[str, float] = {}
        try:
            mb = self.fly()
            kc = mb.kenyon(text) if kc is None else kc
            keys = list(_neurons.NEURONS) + [
                a[8:]
                for a in mb.codes
                if a.startswith("neurona:") and a[8:] not in _neurons.NEURONS
            ]
            scores = mb.scores(kc, [f"neurona:{k}" for k in keys]) if len(kc) else {}
            learned = {a[8:]: v * FLY_GAIN for a, v in scores.items() if v > 0}
        except Exception:  # noqa: BLE001 — innate alone
            kc = None
        good, _bad = self.routes(text, kc)
        return _neurons.select(text, learned, [name for name, _ in good])

    def context(self, text: str, channel: str = "chat") -> Tuple[str, List[str]]:
        """What the zones add for this request, each within its share (and the
        turn's record and choice kept on this thread)."""
        block, used, record, selection = self.context_parts(text, channel)
        _turn.record = record
        _turn.selection = (selection, self.clock()) if selection else None
        return block, used

    def context_parts(
        self, text: str, channel: str = "chat"
    ) -> Tuple[str, List[str], Any, Any]:
        """The memory zone's work for one request, without touching the
        thread's turn (so it can run as an organ of the hive)."""
        if not enabled() or not text.strip():
            return "", [], None, None
        with self._lock:
            self._decay()
            cells = kenyon_code(text)
            ids, fast = self.recall(text)
            try:
                kc = self.fly().kenyon(text)
            except Exception:  # noqa: BLE001
                kc = None
            good, bad = self.routes(text, kc)
            selection = self.select_tools(text, kc)
            self.stats_["turns"] = self.stats_.get("turns", 0) + 1
            if selection is not None:
                self.stats_["narrowed"] = self.stats_.get("narrowed", 0) + 1
                if selection.shortcut:
                    self.stats_["shortcut_turns"] = (
                        self.stats_.get("shortcut_turns", 0) + 1
                    )
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
            record = {
                "cells": cells,
                "kc": [int(c) for c in kc] if kc is not None else [],
                "items": used,
                "tools": [],
                "skills": [],
                "channel": channel if channel in CHANNELS else "chat",
                "t": self.clock(),
            }
            self._pending[_key(text)] = record
            self._expire_pending()
        blocks: List[str] = []
        if lines:
            blocks.append(
                "<cerebro_memoria>\nRecuerdos de conversaciones anteriores que "
                "vienen al caso (úsalos si sirven; no los menciones si no):\n"
                + "\n".join(lines)
                + "\n</cerebro_memoria>"
            )
        if good or bad:
            parts = []
            if good:
                parts.append(
                    "Para peticiones así, antes funcionaron: "
                    + ", ".join(name for name, _ in good)
                    + "."
                )
            if bad:
                parts.append(
                    "Fallaron a menudo: " + ", ".join(name for name, _ in bad) + "."
                )
            blocks.append("<cerebro_rutas>\n" + " ".join(parts) + "\n</cerebro_rutas>")
        return "\n\n".join(blocks), used, record, selection

    def _expire_pending(self) -> None:
        now = self.clock()
        for key in [
            k for k, r in self._pending.items() if now - r["t"] > PENDING_TTL_S
        ]:
            del self._pending[key]
        while len(self._pending) > 200:
            self._pending.pop(next(iter(self._pending)))

    # -- what happens during a turn ------------------------------------------------
    def note_tool(self, name: str, ok: bool) -> None:
        record = getattr(_turn, "record", None)
        name = _clean_name(name)
        if record is None or not name or name in _NOT_ROUTES:
            return
        with self._lock:
            record["tools"].append((name, bool(ok)))

    def note_skills(self, titles: Iterable[str]) -> None:
        record = getattr(_turn, "record", None)
        if record is None:
            return
        with self._lock:
            for title in titles:
                title = _clean_name(title)
                if title and title not in record["skills"]:
                    record["skills"].append(title)

    # -- learning -----------------------------------------------------------------
    def observe(
        self, user_text: str, assistant_text: str = "", *, channel: str = ""
    ) -> Optional[str]:
        """One finished exchange: reward what took part, keep its engram."""
        if not enabled() or not (user_text or "").strip():
            return None
        with self._lock:
            self._decay()
            cells = kenyon_code(user_text)
            record = self._pending.pop(_key(user_text), None)
            if getattr(_turn, "record", None) is record:
                _turn.record = None
            channel = channel or (record or {}).get("channel") or "chat"
            channel = channel if channel in CHANNELS else "chat"
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
                while eid in self.engrams:
                    eid = f"{int(eid, 16) + 1:x}"
                self.engrams[eid] = {
                    "t": self.clock(),
                    "cells": cells,
                    "user": _gist(user_text, 200),
                    "gist": _gist(assistant_text, 240),
                    "channel": channel,
                }
                self._dirty_eng.add(eid)
                for c in cells:
                    self._index.setdefault(c, set()).add(eid)
                self._link_thread(eid, channel)
                self._trim()
            used = list(record["items"]) if record else []
            skills = [f"habilidades:{s}" for s in (record or {}).get("skills", [])]
            tools_ok = sorted(
                {f"herramientas:{n}" for n, ok in (record or {}).get("tools", []) if ok}
            )
            tools_bad = sorted(
                {
                    f"herramientas:{n}"
                    for n, ok in (record or {}).get("tools", [])
                    if not ok
                }
                - set(tools_ok)
            )
            # The neurons of the tools that worked: their synapses from these
            # words grow (a tool with no neuron grows a new one).
            neurons_ok = sorted(
                {
                    f"neurona:{k}"
                    for t in tools_ok
                    for k in _neurons.neurons_for_tool(t[13:])
                }
            )
            neurons_bad = sorted(
                {
                    f"neurona:{k}"
                    for t in tools_bad
                    for k in _neurons.neurons_for_tool(t[13:])
                }
                - set(neurons_ok)
            )
            tools_bad = tools_bad + neurons_bad
            items = (
                used
                + skills
                + tools_ok
                + neurons_ok
                + ([f"memoria:{eid}"] if eid else [])
            )
            items.append(f"sentidos:{channel}")
            if cells:
                self._strengthen(cells, items, 0.6 if used else 0.4)
                if tools_bad:
                    self._strengthen(cells, tools_bad, -0.6)
            self.stats_["prev_cells"] = cells
            self.stats_["prev_items"] = [
                i for i in items if not i.startswith("sentidos:")
            ]
            self._save()
        self._teach_fly(user_text, assistant_text, record)
        return eid

    def _teach_fly(
        self, user_text: str, answer: str, record: Optional[Dict[str, Any]]
    ) -> None:
        """The supervisor's dopamine into the mushroom body: tools that worked
        are rewarded with their neurons, failures punished, and the owner's
        next words («gracias», «no, eso no») judge the previous turn."""
        try:
            from openjarvis.connectome.colmena import hive
            from openjarvis.connectome.core import core_at

            sup = hive().supervisor
            core = core_at(self.folder)
            mb = core.brain("sergio")
            kc = (record or {}).get("kc") or mb.kenyon(user_text).tolist()
            prev = self.stats_.get("prev_fly") or {}
            verdict = sup.feedback(user_text)
            if verdict and prev.get("kc") and prev.get("actions"):
                for action in prev["actions"]:
                    mb.learn(prev["kc"], action, verdict)
                if verdict > 0:
                    sup.rewards += 1
                else:
                    sup.punishments += 1
            tools = [(n, bool(ok)) for n, ok in (record or {}).get("tools", [])]
            judged = sup.judge(user_text, answer, tools)
            actions: List[str] = []
            for name, ok in tools:
                if name in _NOT_ROUTES:
                    continue
                reward = 1.0 if ok else -0.6
                for action in [f"tool:{name}"] + [
                    f"neurona:{k}" for k in _neurons.neurons_for_tool(name)
                ]:
                    mb.learn(
                        kc, action, reward if judged.get("respuesta", 0) >= 0 else -0.6
                    )
                    if ok:
                        actions.append(action)
                if ok:
                    sup.rewards += 1
                else:
                    sup.punishments += 1
            self.stats_["prev_fly"] = {
                "kc": list(kc)[:64],
                "actions": sorted(set(actions)),
            }
            core.save()
            core.maybe_sleep()
        except Exception:  # noqa: BLE001 — learning is a bonus, never a failure
            pass

    def _link_thread(self, eid: str, channel: str) -> None:
        """The central complex: this engram follows the last one of the thread."""
        prev = self._last_engram.get(channel)
        now = self.clock()
        if prev and prev[0] in self.engrams and now - prev[1] <= THREAD_GAP_S:
            a, b = f"memoria:{prev[0]}", f"conversacion:{eid}"
            w = self.assoc.get(a, {}).get(b, 0.0)
            self._set_assoc(a, b, w + SEQ_RATE * (1 - w))
        self._last_engram[channel] = (eid, now)

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
            self._gone_eng.add(eid)

    # -- reading the mind ------------------------------------------------------------
    def _label(self, item: str) -> str:
        zone, _, name = item.partition(":")
        if zone in ("memoria", "conversacion"):
            e = self.engrams.get(name)
            return f"«{e['user'][:60]}»" if e else "un recuerdo olvidado"
        return name

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            per_zone: Dict[str, int] = {z: 0 for z in ZONES}
            strongest: Dict[str, Tuple[float, str]] = {}
            for row in self.syn.values():
                for item, w in row.items():
                    zone = item.split(":", 1)[0]
                    if zone in per_zone:
                        per_zone[zone] += 1
                    if w > strongest.get(item, (0.0, ""))[0]:
                        strongest[item] = (w, zone)
            for a, row in self.assoc.items():
                for b in row:
                    if b.startswith("conversacion:"):
                        per_zone["conversacion"] += 1
            top: Dict[str, List[Dict[str, Any]]] = {}
            for item, (w, zone) in sorted(strongest.items(), key=lambda kv: -kv[1][0]):
                if (
                    zone in ("herramientas", "habilidades", "sentidos")
                    and len(top.get(zone, [])) < 5
                ):
                    top.setdefault(zone, []).append(
                        {"name": self._label(item), "weight": round(w, 2)}
                    )
            synapses = sum(len(r) for r in self.syn.values())
            turns = self.stats_.get("turns", 0)
            # The core: each neuron, how many learned connections reach it and
            # whether one is strong enough to be a shortcut.
            reach: Dict[str, Tuple[int, float]] = {}
            for row in self.syn.values():
                for item, w in row.items():
                    if item.startswith("neurona:") and w > 0:
                        n, top_w = reach.get(item[8:], (0, 0.0))
                        reach[item[8:]] = (n + 1, max(top_w, w))
            keys = list(_neurons.NEURONS) + sorted(
                k for k in reach if k not in _neurons.NEURONS
            )
            neuron_rows = [
                {
                    "key": k,
                    "label": _neurons.label(k),
                    "job": _neurons.NEURONS[k].job
                    if k in _neurons.NEURONS
                    else "La creó el cerebro al aprender una herramienta nueva.",
                    "connections": reach.get(k, (0, 0.0))[0],
                    "shortcut": reach.get(k, (0, 0.0))[1] >= _neurons.SHORTCUT,
                    "learned": k not in _neurons.NEURONS,
                }
                for k in keys
            ]
            return {
                "zones": [
                    {
                        "key": k,
                        **v,
                        "weight": self.zone_w.get(k, 1.0),
                        "connections": per_zone.get(k, 0),
                        "top": top.get(k, []),
                    }
                    for k, v in ZONES.items()
                ],
                "engrams": len(self.engrams),
                "synapses": synapses,
                "associations": sum(len(r) for r in self.assoc.values()),
                "fast_path": round(self.stats_.get("fast", 0) / turns, 3)
                if turns
                else 0.0,
                "corrections": self.stats_.get("corrections", 0),
                "neurons": neuron_rows,
                "shortcuts": sum(1 for r in neuron_rows if r["shortcut"]),
                "learned_neurons": sum(1 for r in neuron_rows if r["learned"]),
                "narrowed": round(self.stats_.get("narrowed", 0) / turns, 3)
                if turns
                else 0.0,
            }

    def forget(self) -> None:
        with self._lock:
            self.syn, self.assoc, self.engrams, self._index = {}, {}, {}, {}
            self._pending, self._last_engram = {}, {}
            self.zone_w = {z: 1.0 for z in ZONES}
            self._full_rewrite = True
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


def _organs(brain: "Brain") -> None:
    """The organs of a turn, each with one job (connectome/colmena.py)."""
    from openjarvis.connectome.colmena import Organ, hive

    h = hive()
    if "memoria" in h.organs:
        return

    def memoria(board: Dict[str, Any]) -> Any:
        return get_brain().context_parts(board["pedido"], board.get("canal", "chat"))

    def habilidades(board: Dict[str, Any]) -> Any:
        from openjarvis.prompt_library import guidance_for

        return guidance_for(board["pedido"]) or ""

    h.add(Organ("memoria", "Cáliz del cuerpo fungiforme",
                "Trae los recuerdos que vienen al caso y decide herramientas.",
                ("pedido",), "memoria", memoria))  # fmt: skip
    h.add(Organ("habilidades", "Cuerno lateral", "Aporta el saber innato: prompts y skills.",
                ("pedido",), "habilidades", habilidades))  # fmt: skip

    def metas(board: Dict[str, Any]) -> Any:
        from openjarvis.reminders import goals_block

        return goals_block() or ""

    h.add(Organ("metas", "Complejo central", "Tiene presentes las metas y medicinas del señor.",
                ("pedido",), "metas", metas))  # fmt: skip

    def estilo(board: Dict[str, Any]) -> Any:
        from openjarvis.connectome import estilo as _estilo

        return _estilo.get_style().block() if _estilo.enabled() else ""

    h.add(Organ("estilo", "Lóbulo óptico", "Mide cómo escribe el señor para hablarle como él habla.",
                ("pedido",), "estilo", estilo))  # fmt: skip


def mind_context(text: str, channel: str = "chat") -> str:
    """Everything the organs add to one request — memories, learned routes and
    know-how — gathered by the hive in parallel. Never breaks a turn."""
    parts: List[str] = []
    _turn.selection = None  # a new turn: the last one's choice does not carry over
    try:
        # The global workspace: what the human brain decided for this turn
        # (connectome/cortex.py) goes first; empty when a plain answer is right.
        from openjarvis.connectome.cortex import workspace

        frame = workspace(text, channel)
    except Exception:  # noqa: BLE001
        frame = ""
    if frame:
        parts.append(frame)
    try:  # how this person wants to be addressed (personal.py)
        from openjarvis.personal import address_line

        how = address_line()
    except Exception:  # noqa: BLE001
        how = ""
    if how:
        parts.append(how)
    try:
        brain = get_brain()
        _organs(brain)
        from openjarvis.connectome.colmena import hive

        board = hive().run({"pedido": text, "canal": channel})
    except Exception:  # noqa: BLE001
        return "\n\n".join(parts)
    block = ""
    got = board.get("memoria")
    if got:
        block, _used, record, selection = got
        _turn.record = record
        _turn.selection = (selection, brain.clock()) if selection else None
    guidance = board.get("habilidades") or ""
    if guidance:
        parts.append(guidance)
        brain.note_skills(re.findall(r"^\[\d+\] (.+)$", guidance, re.M))
    if block:
        parts.append(block)
    if board.get("metas"):
        parts.append(board["metas"])
    if board.get("estilo"):
        parts.append(board["estilo"])
    return "\n\n".join(parts)


def turn_tools() -> Optional[frozenset]:
    """The tools the brain chose for the turn on this thread (None: all)."""
    chosen = getattr(_turn, "selection", None)
    if not chosen or not enabled():
        return None
    selection, at = chosen
    if time.time() - at > SELECTION_TTL_S:
        return None
    return selection.tools


def note_tool(name: str, ok: bool) -> None:
    """A tool finished inside the turn being answered on this thread."""
    if getattr(_turn, "record", None) is None or not enabled():
        return
    try:
        get_brain().note_tool(name, ok)
    except Exception:  # noqa: BLE001 — learning is a bonus, never a failure
        pass


def remember_exchange(
    user_text: str, assistant_text: str = "", channel: str = ""
) -> None:
    try:
        get_brain().observe(user_text, assistant_text, channel=channel)
    except Exception:  # noqa: BLE001 — learning is a bonus, never a failure
        pass
    try:
        from openjarvis.connectome.cortex import outcome

        outcome(user_text, assistant_text, channel or "chat")
    except Exception:  # noqa: BLE001 — the same
        pass
    try:
        from openjarvis.connectome import estilo as _estilo

        if _estilo.enabled():
            _estilo.get_style().observe(user_text)
    except Exception:  # noqa: BLE001 — the same
        pass


__all__ = [
    "Brain",
    "turn_tools",
    "CHANNELS",
    "ZONES",
    "enabled",
    "get_brain",
    "mind_context",
    "note_tool",
    "remember_exchange",
]
