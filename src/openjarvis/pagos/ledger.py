"""Orders and the ledger of Sergio Pagos (SQLite, local, 0600).

Every paid order leaves four lines: ``ingreso`` (what the customer paid),
``comision`` (the processor's fee, estimated), ``proveedor`` (the most the
customer's AI may cost this month: their sub-key's limit) and ``margen`` (what
stays with the owner). A notice that arrives twice is recorded once
(``events`` is keyed by the processor's own event id).
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

_LOCK = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY, uid TEXT NOT NULL, plan TEXT NOT NULL, mult INTEGER,
  usd REAL NOT NULL, method TEXT NOT NULL, ext TEXT DEFAULT '',
  status TEXT NOT NULL, created REAL NOT NULL, paid REAL, until REAL
);
CREATE INDEX IF NOT EXISTS orders_uid ON orders(uid);
CREATE TABLE IF NOT EXISTS events (
  method TEXT NOT NULL, event TEXT NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (method, event)
);
CREATE TABLE IF NOT EXISTS entries (
  order_id TEXT NOT NULL, kind TEXT NOT NULL, usd REAL NOT NULL, at REAL NOT NULL
);
"""


def _path(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = Path(get_config_dir())
    return Path(home) / "pagos.db"


@contextmanager
def _db(home: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    path = _path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        if new:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        con.executescript(_SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def new_order(
    uid: str, plan: str, mult: int, usd: float, method: str, home: Any = None
) -> Dict[str, Any]:
    oid = "pd_" + uuid.uuid4().hex[:20]
    with _LOCK, _db(home) as db:
        db.execute(
            "INSERT INTO orders (id, uid, plan, mult, usd, method, status, created)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (oid, uid, plan, mult, round(usd, 2), method, "abierto", time.time()),
        )
    return get(oid, home) or {}


def get(oid: str, home: Any = None) -> Optional[Dict[str, Any]]:
    with _db(home) as db:
        r = db.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    return dict(r) if r else None


def by_ext(method: str, ext: str, home: Any = None) -> Optional[Dict[str, Any]]:
    with _db(home) as db:
        r = db.execute(
            "SELECT * FROM orders WHERE method = ? AND ext = ?", (method, ext)
        ).fetchone()
    return dict(r) if r else None


def set_ext(oid: str, ext: str, home: Any = None) -> None:
    with _LOCK, _db(home) as db:
        db.execute("UPDATE orders SET ext = ? WHERE id = ?", (ext, oid))


def first_time(method: str, event: str, home: Any = None) -> bool:
    """True the first time a processor's event id is seen (idempotency)."""
    if not event:
        return True
    with _LOCK, _db(home) as db:
        cur = db.execute(
            "INSERT OR IGNORE INTO events VALUES (?,?,?)", (method, event, time.time())
        )
        return cur.rowcount == 1


def mark_paid(
    oid: str, until: float, lines: Dict[str, float], home: Any = None
) -> None:
    now = time.time()
    with _LOCK, _db(home) as db:
        db.execute(
            "UPDATE orders SET status = 'pagado', paid = ?, until = ? WHERE id = ?",
            (now, until, oid),
        )
        db.executemany(
            "INSERT INTO entries VALUES (?,?,?,?)",
            [(oid, k, round(v, 2), now) for k, v in lines.items()],
        )


def mark(oid: str, status: str, home: Any = None) -> None:
    with _LOCK, _db(home) as db:
        db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, oid))


def latest_paid(home: Any = None) -> List[Dict[str, Any]]:
    """Each customer's most recent paid order."""
    with _db(home) as db:
        rows = db.execute(
            "SELECT * FROM orders WHERE status = 'pagado' AND paid = "
            "(SELECT MAX(paid) FROM orders o WHERE o.uid = orders.uid "
            "AND o.status = 'pagado')"
        ).fetchall()
    return [dict(r) for r in rows]


def paid_until(uid: str, home: Any = None) -> float:
    """Until when the customer has already paid (0 if nothing in force)."""
    with _db(home) as db:
        r = db.execute(
            "SELECT MAX(until) AS u FROM orders WHERE uid = ? AND status = 'pagado'",
            (uid,),
        ).fetchone()
    return float(r["u"] or 0.0)


def end_now(uid: str, home: Any = None) -> None:
    """The subscription was cancelled: what is paid ends now at the latest."""
    now = time.time()
    with _LOCK, _db(home) as db:
        db.execute(
            "UPDATE orders SET until = MIN(COALESCE(until, ?), ?) "
            "WHERE uid = ? AND status = 'pagado'",
            (now, now, uid),
        )


def totals(since: float = 0.0, home: Any = None) -> Dict[str, float]:
    with _db(home) as db:
        rows = db.execute(
            "SELECT kind, SUM(usd) AS usd FROM entries WHERE at >= ? GROUP BY kind",
            (since,),
        ).fetchall()
    out = {"ingreso": 0.0, "comision": 0.0, "proveedor": 0.0, "margen": 0.0}
    out.update({r["kind"]: round(r["usd"] or 0.0, 2) for r in rows})
    return out


def recent(limit: int = 20, home: Any = None) -> List[Dict[str, Any]]:
    with _db(home) as db:
        rows = db.execute(
            "SELECT * FROM orders ORDER BY created DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


__all__ = [
    "by_ext",
    "end_now",
    "first_time",
    "get",
    "latest_paid",
    "mark",
    "mark_paid",
    "new_order",
    "paid_until",
    "recent",
    "set_ext",
    "totals",
]
