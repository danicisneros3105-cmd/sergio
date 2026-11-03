"""SQLite store for goals, medications and reminders (``~/.openjarvis/recordatorios.db``)."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

KINDS = ("medicina", "meta", "recordatorio")
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
DUE_WINDOW_MIN = 90  # a dose is still «due» this long after its time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT DEFAULT '',
  times TEXT DEFAULT '[]', days TEXT DEFAULT '[]', date TEXT DEFAULT '',
  active INTEGER DEFAULT 1, created REAL, extra TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT NOT NULL, slot TEXT NOT NULL,
  status TEXT NOT NULL, at REAL NOT NULL, UNIQUE(item, slot)
);
"""


def clean_times(times: Any) -> List[str]:
    out = []
    for t in times or []:
        m = _TIME.match(str(t).strip())
        if m:
            out.append(f"{int(m.group(1)):02d}:{m.group(2)}")
    return sorted(set(out))


def clean_days(days: Any) -> List[int]:
    return sorted({int(d) for d in days or [] if str(d).isdigit() and 0 <= int(d) <= 6})


class ReminderStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._db() as db:
            db.executescript(_SCHEMA)
        self.seal_missing()  # medicines and goals written before the vault

    # -- the vault (security/boveda.py): what the person takes and wants is sealed --
    @property
    def _home(self) -> Path:
        return self.path.parent

    def _seal(self, text: str, iid: str, field: str) -> str:
        from openjarvis.security import boveda

        return (
            boveda.seal_text(text, f"recordatorio:{iid}:{field}", "salud", self._home)
            if text
            else text
        )

    def _open(self, value: str, iid: str, field: str) -> str:
        from openjarvis.security import boveda

        return boveda.open_text(
            value, f"recordatorio:{iid}:{field}", "salud", self._home
        )

    def seal_missing(self) -> int:
        from openjarvis.security import boveda

        if not boveda.enabled():
            return 0
        n = 0
        with self._db() as db:
            for r in db.execute(
                "SELECT id, title, detail, extra FROM items"
            ).fetchall():
                if all(
                    boveda.is_sealed(r[k]) or not r[k]
                    for k in ("title", "detail", "extra")
                ):
                    continue
                db.execute(
                    "UPDATE items SET title=?, detail=?, extra=? WHERE id=?",
                    (
                        self._seal(r["title"], r["id"], "title"),
                        self._seal(r["detail"], r["id"], "detail"),
                        self._seal(r["extra"], r["id"], "extra"),
                        r["id"],
                    ),
                )
                n += 1
        return n

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            db = sqlite3.connect(self.path)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            finally:
                db.close()

    # -- items ---------------------------------------------------------------------
    def add(
        self,
        kind: str,
        title: str,
        *,
        detail: str = "",
        times: Any = (),
        days: Any = (),
        date: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"tipo desconocido: {kind}")
        title = " ".join(str(title or "").split())[:160]
        if not title:
            raise ValueError("falta el título")
        item = {
            "id": secrets.token_hex(6),
            "kind": kind,
            "title": title,
            "detail": str(detail or "")[:1000],
            "times": clean_times(times),
            "days": clean_days(days),
            "date": str(date or "")[:10],
            "active": True,
            "created": time.time(),
            "extra": dict(extra or {}),
        }
        with self._db() as db:
            db.execute(
                "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?)",
                (item["id"], kind, self._seal(item["title"], item["id"], "title"),
                 self._seal(item["detail"], item["id"], "detail"), json.dumps(item["times"]),
                 json.dumps(item["days"]), item["date"], 1, item["created"],
                 self._seal(json.dumps(item["extra"], ensure_ascii=False), item["id"], "extra")),
            )  # fmt: skip
        return item

    def update(self, iid: str, **changes: Any) -> Optional[Dict[str, Any]]:
        item = self.get(iid)
        if item is None:
            return None
        if "times" in changes:
            changes["times"] = clean_times(changes["times"])
        if "days" in changes:
            changes["days"] = clean_days(changes["days"])
        for k in ("title", "detail", "times", "days", "date", "active", "extra"):
            if k in changes and changes[k] is not None:
                item[k] = changes[k]
        with self._db() as db:
            db.execute(
                "UPDATE items SET title=?, detail=?, times=?, days=?, date=?, active=?, extra=? WHERE id=?",
                (self._seal(item["title"], iid, "title"), self._seal(item["detail"], iid, "detail"),
                 json.dumps(item["times"]), json.dumps(item["days"]), item["date"], int(bool(item["active"])),
                 self._seal(json.dumps(item["extra"], ensure_ascii=False), iid, "extra"), iid),
            )  # fmt: skip
        return item

    def delete(self, iid: str) -> bool:
        with self._db() as db:
            gone = db.execute("DELETE FROM items WHERE id = ?", (iid,)).rowcount
            db.execute("DELETE FROM log WHERE item = ?", (iid,))
        return bool(gone)

    def _row(self, r: sqlite3.Row) -> Dict[str, Any]:
        iid = r["id"]
        return {
            "id": iid, "kind": r["kind"], "title": self._open(r["title"], iid, "title"),
            "detail": self._open(r["detail"], iid, "detail"),
            "times": json.loads(r["times"] or "[]"), "days": json.loads(r["days"] or "[]"),
            "date": r["date"] or "", "active": bool(r["active"]), "created": r["created"],
            "extra": json.loads(self._open(r["extra"] or "{}", iid, "extra")),
        }  # fmt: skip

    def get(self, iid: str) -> Optional[Dict[str, Any]]:
        with self._db() as db:
            r = db.execute("SELECT * FROM items WHERE id = ?", (iid,)).fetchone()
        return self._row(r) if r else None

    def items(self, kind: str = "", active_only: bool = False) -> List[Dict[str, Any]]:
        q, args = "SELECT * FROM items", []
        where = []
        if kind:
            where.append("kind = ?")
            args.append(kind)
        if active_only:
            where.append("active = 1")
        if where:
            q += " WHERE " + " AND ".join(where)
        with self._db() as db:
            rows = db.execute(q + " ORDER BY created", args).fetchall()
        return [self._row(r) for r in rows]

    # -- when ----------------------------------------------------------------------
    @staticmethod
    def _on_day(item: Dict[str, Any], day: datetime) -> bool:
        if item["date"]:
            return item["date"] == day.strftime("%Y-%m-%d")
        return not item["days"] or day.weekday() in item["days"]

    def occurrences(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        """Every (item, time) between *start* and *end*, with its slot id."""
        out = []
        for item in self.items(active_only=True):
            day = start.replace(hour=0, minute=0, second=0, microsecond=0)
            while day <= end:
                if self._on_day(item, day):
                    for t in item["times"]:
                        h, m = map(int, t.split(":"))
                        when = day.replace(hour=h, minute=m)
                        if start <= when <= end:
                            out.append(
                                {
                                    "item": item,
                                    "when": when,
                                    "slot": when.strftime("%Y-%m-%dT%H:%M"),
                                }
                            )
                day += timedelta(days=1)
        return sorted(out, key=lambda o: o["when"])

    def due(
        self, now: Optional[datetime] = None, window_min: int = DUE_WINDOW_MIN
    ) -> List[Dict[str, Any]]:
        """What should be on screen now: times passed in the last window, not yet answered."""
        now = now or datetime.now()
        done = self._logged()
        return [
            {**o["item"], "slot": o["slot"], "at": o["when"].strftime("%H:%M")}
            for o in self.occurrences(now - timedelta(minutes=window_min), now)
            if (o["item"]["id"], o["slot"]) not in done
        ]

    def upcoming(
        self, now: Optional[datetime] = None, hours: int = 24
    ) -> List[Dict[str, Any]]:
        now = now or datetime.now()
        return [
            {**o["item"], "slot": o["slot"], "at": o["when"].strftime("%H:%M")}
            for o in self.occurrences(now, now + timedelta(hours=hours))
        ]

    # -- answered ------------------------------------------------------------------
    def _logged(self) -> set:
        with self._db() as db:
            return {
                (r["item"], r["slot"]) for r in db.execute("SELECT item, slot FROM log")
            }

    def mark(self, iid: str, slot: str, status: str = "hecho") -> bool:
        if status not in ("hecho", "saltado") or self.get(iid) is None:
            return False
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO log (item, slot, status, at) VALUES (?,?,?,?)",
                (iid, slot[:16], status, time.time()),
            )
        return True

    def adherence(
        self, iid: str, days: int = 7, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Of the doses due in the last *days*, how many were taken (real data only)."""
        now = now or datetime.now()
        item = self.get(iid)
        if item is None:
            return {"due": 0, "taken": 0, "share": None}
        start = max(now - timedelta(days=days), datetime.fromtimestamp(item["created"]))
        slots = [
            o["slot"] for o in self.occurrences(start, now) if o["item"]["id"] == iid
        ]
        with self._db() as db:
            taken = {
                r["slot"]
                for r in db.execute(
                    "SELECT slot FROM log WHERE item = ? AND status = 'hecho'", (iid,)
                )
            }
        hits = sum(1 for s in slots if s in taken)
        return {
            "due": len(slots),
            "taken": hits,
            "share": round(hits / len(slots), 2) if slots else None,
        }


_STORES: Dict[str, ReminderStore] = {}
_LOCK = threading.Lock()


def get_store(home: Optional[Path] = None) -> ReminderStore:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    path = Path(home) / "recordatorios.db"
    with _LOCK:
        if str(path) not in _STORES:
            _STORES[str(path)] = ReminderStore(path)
        return _STORES[str(path)]


def goals_block(store: Optional[ReminderStore] = None, limit: int = 6) -> str:
    """The owner's active goals and today's medications, for every turn."""
    try:
        store = store or get_store()
        goals = store.items("meta", active_only=True)[:limit]
        meds = store.items("medicina", active_only=True)[:limit]
    except Exception:  # noqa: BLE001 — never break a conversation for this
        return ""
    if not goals and not meds:
        return ""
    lines = ["<metas_del_senor>"]
    for g in goals:
        why = g["extra"].get("why") or ""
        lines.append(f"- Meta: {g['title']}" + (f" (por qué: {why})" if why else ""))
    for m in meds:
        dose = m["extra"].get("dose") or ""
        lines.append(
            f"- Medicina: {m['title']}"
            + (f", {dose}" if dose else "")
            + (f" a las {', '.join(m['times'])}" if m["times"] else "")
        )
    lines.append(
        "Téngalas presentes: cuando venga al caso, pregúntele cómo va o ayúdele a dar el "
        "siguiente paso, sin sermones. Nunca dé consejo médico sobre las medicinas."
    )
    lines.append("</metas_del_senor>")
    return "\n".join(lines)


__all__ = [
    "KINDS",
    "ReminderStore",
    "clean_days",
    "clean_times",
    "get_store",
    "goals_block",
]
