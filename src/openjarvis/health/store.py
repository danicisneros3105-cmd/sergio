"""Salud's own data, on this computer: every measurement with its source.

One SQLite file (``~/.openjarvis/health/salud.db``):

* ``samples``  — metric, time, value, source; a unique key per reading makes a
  re-import of the same file or a repeated sync harmless.
* ``notes``    — one line per day plus tags («café tarde», «alcohol»), so the
  owner can see what goes with a good or bad night.
* ``settings`` — pinned metrics, goals, the sync key and connected sources.

Nothing here is ever filled with example values: an empty store is empty.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from openjarvis.health.metrics import BY_KEY

DEFAULT_PINS = ["steps", "exercise_min", "resting_hr", "hrv", "sleep_h", "weight_kg"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    uid TEXT PRIMARY KEY,
    metric TEXT NOT NULL,
    at REAL NOT NULL,
    value REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS samples_metric_at ON samples(metric, at);
CREATE TABLE IF NOT EXISTS notes (
    day TEXT PRIMARY KEY,
    text TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS surveys (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    created REAL NOT NULL,
    ready_at REAL NOT NULL,
    answers TEXT NOT NULL,
    scores TEXT NOT NULL,
    reading TEXT NOT NULL DEFAULT '',
    reading_by TEXT NOT NULL DEFAULT '',
    read_at REAL
);
"""


def day_of(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


class HealthError(ValueError):
    pass


class HealthStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._db() as db:
            db.executescript(_SCHEMA)
        from openjarvis.health.privacy import private

        private(self.path)  # health data: only the owner's account reads it

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        """A connection that commits on success and is always closed."""
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # -- samples ---------------------------------------------------------------
    def add(
        self,
        metric: str,
        value: float,
        at: Optional[float] = None,
        source: str = "manual",
        uid: str = "",
    ) -> bool:
        """One reading. Returns False if it was already there (same uid)."""
        return self.add_many([(metric, value, at, source, uid)]) == 1

    def add_many(
        self, rows: Iterable[Tuple[str, float, Optional[float], str, str]]
    ) -> int:
        """Many readings at once; unknown metrics and impossible values are skipped."""
        now = time.time()
        clean = []
        for metric, value, at, source, uid in rows:
            if metric not in BY_KEY:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value != value or value < 0 or value > 1e7:  # NaN or nonsense
                continue
            at = float(at) if at else now
            if at > now + 86400:  # no readings from the future
                continue
            if not uid:
                uid = hashlib.sha1(
                    f"{metric}|{at:.0f}|{value}|{source}".encode()
                ).hexdigest()
            clean.append((uid, metric, at, value, source[:60] or "manual"))
        if not clean:
            return 0
        with self._lock, self._db() as db:
            before = db.total_changes
            db.executemany(
                "INSERT OR IGNORE INTO samples(uid, metric, at, value, source) VALUES (?,?,?,?,?)",
                clean,
            )
            return db.total_changes - before

    def delete(self, uid: str) -> bool:
        with self._lock, self._db() as db:
            return db.execute("DELETE FROM samples WHERE uid=?", (uid,)).rowcount > 0

    def delete_source(self, source: str) -> int:
        with self._lock, self._db() as db:
            return db.execute("DELETE FROM samples WHERE source=?", (source,)).rowcount

    def samples(
        self, metric: str, since: float = 0.0, limit: int = 5000
    ) -> List[Dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT uid, metric, at, value, source FROM samples WHERE metric=? AND at>=? "
                "ORDER BY at DESC LIMIT ?",
                (metric, since, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def daily(
        self, metric: str, days: int = 90, now: Optional[float] = None
    ) -> Dict[str, float]:
        """One value per day, summarised the way the metric asks (sum, avg…)."""
        m = BY_KEY[metric]
        now = now or time.time()
        since = now - days * 86400
        per_day: Dict[str, List[Tuple[float, float]]] = {}
        with self._db() as db:
            for r in db.execute(
                "SELECT at, value FROM samples WHERE metric=? AND at>=? ORDER BY at",
                (metric, since),
            ):
                per_day.setdefault(day_of(r["at"]), []).append((r["at"], r["value"]))
        out: Dict[str, float] = {}
        for day, vals in per_day.items():
            nums = [v for _, v in vals]
            if m.daily == "sum":
                out[day] = sum(nums)
            elif m.daily == "last":
                out[day] = vals[-1][1]
            elif m.daily == "min":
                out[day] = min(nums)
            elif m.daily == "max":
                out[day] = max(nums)
            else:
                out[day] = sum(nums) / len(nums)
        return out

    def metrics_with_data(self) -> Dict[str, Dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT metric, COUNT(*) n, MAX(at) last, MIN(at) first FROM samples GROUP BY metric"
            ).fetchall()
        return {
            r["metric"]: {"count": r["n"], "last": r["last"], "first": r["first"]}
            for r in rows
        }

    def sources(self) -> Dict[str, Dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT source, COUNT(*) n, MAX(at) last FROM samples GROUP BY source"
            ).fetchall()
        return {r["source"]: {"count": r["n"], "last": r["last"]} for r in rows}

    def all_samples(self) -> List[Dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT metric, at, value, source FROM samples ORDER BY at"
            ).fetchall()
        return [dict(r) for r in rows]

    # -- notes and tags -------------------------------------------------------
    def set_note(
        self, day: str, text: str = "", tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError as exc:
            raise HealthError("Fecha no válida (AAAA-MM-DD).") from exc
        tags = sorted(
            {t.strip().lower()[:30] for t in (tags or []) if t and t.strip()}
        )[:12]
        with self._lock, self._db() as db:
            if not text.strip() and not tags:
                db.execute("DELETE FROM notes WHERE day=?", (day,))
            else:
                db.execute(
                    "INSERT INTO notes(day, text, tags) VALUES (?,?,?) "
                    "ON CONFLICT(day) DO UPDATE SET text=excluded.text, tags=excluded.tags",
                    (day, text.strip()[:500], json.dumps(tags, ensure_ascii=False)),
                )
        return {"day": day, "text": text.strip()[:500], "tags": tags}

    def notes(self, days: int = 365) -> Dict[str, Dict[str, Any]]:
        since = day_of(time.time() - days * 86400)
        with self._db() as db:
            rows = db.execute(
                "SELECT day, text, tags FROM notes WHERE day>=? ORDER BY day", (since,)
            ).fetchall()
        return {
            r["day"]: {"text": r["text"], "tags": json.loads(r["tags"])} for r in rows
        }

    # -- settings ---------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        with self._db() as db:
            row = db.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row["value"]) if row else default

    def put(self, key: str, value: Any) -> None:
        with self._lock, self._db() as db:
            db.execute(
                "INSERT INTO settings(key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def pins(self) -> List[str]:
        return [p for p in self.get("pins", DEFAULT_PINS) if p in BY_KEY]

    def set_pins(self, pins: List[str]) -> List[str]:
        clean = [p for p in dict.fromkeys(pins) if p in BY_KEY][:12]
        self.put("pins", clean)
        return clean

    def goals(self) -> Dict[str, float]:
        return {
            k: float(v) for k, v in (self.get("goals", {}) or {}).items() if k in BY_KEY
        }

    def set_goal(self, metric: str, value: Optional[float]) -> Dict[str, float]:
        if metric not in BY_KEY:
            raise HealthError("Métrica desconocida.")
        goals = self.goals()
        if value is None or value <= 0:
            goals.pop(metric, None)
        else:
            goals[metric] = float(value)
        self.put("goals", goals)
        return goals

    def sync_key(self, rotate: bool = False) -> str:
        """The key a phone or watch app sends to push data here."""
        key = self.get("sync_key", "")
        if rotate or not key:
            key = secrets.token_urlsafe(24)
            self.put("sync_key", key)
        return key

    def check_sync_key(self, given: str) -> bool:
        key = self.get("sync_key", "")
        return bool(key) and secrets.compare_digest(key, (given or "").strip())

    # -- surveys (Salud mental) ------------------------------------------------
    def add_survey(
        self,
        kind: str,
        answers: Dict[str, Any],
        scores: Dict[str, Any],
        ready_at: float,
    ) -> str:
        sid = secrets.token_hex(8)
        with self._lock, self._db() as db:
            db.execute(
                "INSERT INTO surveys (id, kind, created, ready_at, answers, scores) VALUES (?,?,?,?,?,?)",
                (
                    sid,
                    kind,
                    time.time(),
                    ready_at,
                    json.dumps(answers),
                    json.dumps(scores),
                ),
            )
        return sid

    def _survey_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "created": row["created"],
            "ready_at": row["ready_at"],
            "answers": json.loads(row["answers"]),
            "scores": json.loads(row["scores"]),
            "reading": row["reading"],
            "reading_by": row["reading_by"],
            "read_at": row["read_at"],
        }

    def survey(self, sid: str) -> Optional[Dict[str, Any]]:
        with self._db() as db:
            row = db.execute("SELECT * FROM surveys WHERE id = ?", (sid,)).fetchone()
        return self._survey_row(row) if row else None

    def surveys(self, kind: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM surveys WHERE kind = ? ORDER BY created DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        return [self._survey_row(r) for r in rows]

    def set_reading(self, sid: str, text: str, by: str) -> None:
        with self._lock, self._db() as db:
            db.execute(
                "UPDATE surveys SET reading = ?, reading_by = ?, read_at = ? WHERE id = ?",
                (text, by, time.time(), sid),
            )

    def delete_survey(self, sid: str) -> bool:
        with self._lock, self._db() as db:
            return db.execute("DELETE FROM surveys WHERE id = ?", (sid,)).rowcount > 0


_STORES: Dict[str, HealthStore] = {}
_STORES_LOCK = threading.Lock()


def get_store(home: Optional[Path] = None) -> HealthStore:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    path = Path(home) / "health" / "salud.db"
    with _STORES_LOCK:
        if str(path) not in _STORES:
            _STORES[str(path)] = HealthStore(path)
        return _STORES[str(path)]


__all__ = ["DEFAULT_PINS", "HealthError", "HealthStore", "day_of", "get_store"]
