"""Orders and the ledger of Sergio Pagos (SQLite, local, 0600).

Every paid order leaves four lines: ``ingreso`` (what the customer paid),
``comision`` (the processor's fee, estimated), ``proveedor`` (the most the
customer's AI may cost this month: their sub-key's limit) and ``margen`` (what
stays with the owner). A notice that arrives twice is recorded once
(``events`` is keyed by the processor's own event id).

The ledger is append-only and **sealed**: each line carries an HMAC (under
Sergio's master key, :mod:`.cifrado`) of its content and of the line before
it, so a line edited, removed or slipped in by hand breaks the chain and
:func:`verify` says where. A refund is a new line with a negative amount,
never an edit. Each paid order gets a receipt number (``SG-AAAA-000001``).
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
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entries (
  order_id TEXT NOT NULL, kind TEXT NOT NULL, usd REAL NOT NULL, at REAL NOT NULL,
  prev TEXT DEFAULT '', sig TEXT DEFAULT ''
);
"""
_ADDED = (("orders", "recibo", "TEXT DEFAULT ''"), ("entries", "prev", "TEXT DEFAULT ''"),
          ("entries", "sig", "TEXT DEFAULT ''"), ("events", "order_id", "TEXT DEFAULT ''"))  # fmt: skip


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
        for table, col, kind in _ADDED:
            cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
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
            "INSERT OR IGNORE INTO events (method, event, at) VALUES (?,?,?)",
            (method, event, time.time()),
        )
        return cur.rowcount == 1


def _line_text(oid: str, kind: str, usd: float, at: float, prev: str) -> str:
    return f"{oid}|{kind}|{usd:.2f}|{at:.6f}|{prev}"


def _write_lines(
    db: sqlite3.Connection, oid: str, lines: Dict[str, float], now: float, home: Any
) -> None:
    from openjarvis.pagos import cifrado

    last = db.execute("SELECT sig FROM entries ORDER BY rowid DESC LIMIT 1").fetchone()
    prev = last["sig"] if last else ""
    for kind, usd in lines.items():
        usd = round(usd, 2)
        sig = cifrado.sign(_line_text(oid, kind, usd, now, prev), _home_of(home))
        db.execute(
            "INSERT INTO entries (order_id, kind, usd, at, prev, sig) VALUES (?,?,?,?,?,?)",
            (oid, kind, usd, now, prev, sig),
        )
        prev = sig
    _checkpoint(db, home)


def _checkpoint(db: sqlite3.Connection, home: Any) -> None:
    """How many lines there are and the last one's seal, sealed too: removing
    the newest lines (which the chain alone cannot see) breaks it."""
    from openjarvis.pagos import cifrado

    n = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    last = db.execute("SELECT sig FROM entries ORDER BY rowid DESC LIMIT 1").fetchone()
    value = f"{n}|{last['sig'] if last else ''}"
    sig = cifrado.sign("checkpoint|" + value, _home_of(home))
    db.execute(
        "INSERT OR REPLACE INTO meta VALUES ('checkpoint', ?)", (f"{value}|{sig}",)
    )


def _home_of(home: Any) -> Any:
    return _path(home).parent


def mark_paid(oid: str, until: float, lines: Dict[str, float], home: Any = None) -> str:
    """Paid: the order's month, its receipt number and its ledger lines."""
    now = time.time()
    year = time.strftime("%Y", time.localtime(now))
    with _LOCK, _db(home) as db:
        n = db.execute(
            "SELECT COUNT(*) FROM orders WHERE recibo LIKE ?", (f"SG-{year}-%",)
        ).fetchone()[0]
        receipt = f"SG-{year}-{n + 1:06d}"
        db.execute(
            "UPDATE orders SET status = 'pagado', paid = ?, until = ?, recibo = ? "
            "WHERE id = ?",
            (now, until, receipt, oid),
        )
        _write_lines(db, oid, lines, now, home)
    return receipt


def event_order(method: str, event: str, home: Any = None) -> Optional[str]:
    """The order a processor's event was already recorded for (None: new)."""
    if not event:
        return None
    with _db(home) as db:
        r = db.execute(
            "SELECT order_id FROM events WHERE method = ? AND event = ?",
            (method, event),
        ).fetchone()
    return (r["order_id"] or "") if r else None


def settle_paid(
    method: str,
    event: str,
    oid: str,
    until: float,
    lines: Dict[str, float],
    home: Any = None,
) -> Optional[str]:
    """Record a confirmed payment all at once: the processor's event, the
    order paid with its receipt and its ledger lines. A crash leaves either
    all of it or none of it. None if that event was already recorded."""
    now = time.time()
    year = time.strftime("%Y", time.localtime(now))
    with _LOCK, _db(home) as db:
        db.execute("BEGIN IMMEDIATE")
        if event:
            seen = db.execute(
                "SELECT 1 FROM events WHERE method = ? AND event = ?", (method, event)
            ).fetchone()
            if seen:
                db.execute("ROLLBACK")
                return None
            db.execute(
                "INSERT INTO events (method, event, at, order_id) VALUES (?,?,?,?)",
                (method, event, now, oid),
            )
        n = db.execute(
            "SELECT COUNT(*) FROM orders WHERE recibo LIKE ?", (f"SG-{year}-%",)
        ).fetchone()[0]
        receipt = f"SG-{year}-{n + 1:06d}"
        db.execute(
            "UPDATE orders SET status = 'pagado', paid = ?, until = ?, recibo = ? "
            "WHERE id = ?",
            (now, until, receipt, oid),
        )
        _write_lines(db, oid, lines, now, home)
    return receipt


def add_lines(oid: str, lines: Dict[str, float], home: Any = None) -> None:
    """More ledger lines for an order (a refund: negative amounts)."""
    with _LOCK, _db(home) as db:
        _write_lines(db, oid, lines, time.time(), home)


def verify(home: Any = None) -> Dict[str, Any]:
    """Walk the sealed chain. ``integro`` False names the first broken line."""
    from openjarvis.pagos import cifrado

    with _db(home) as db:
        rows = db.execute("SELECT rowid, * FROM entries ORDER BY rowid").fetchall()
    prev = ""
    for i, r in enumerate(rows):
        want = cifrado.sign(
            _line_text(r["order_id"], r["kind"], r["usd"], r["at"], prev),
            _home_of(home),
        )
        if r["prev"] != prev or not cifrado.same(want, r["sig"]):
            return {"integro": False, "lineas": len(rows), "rota_en": i + 1}
        prev = r["sig"]
    with _db(home) as db:
        row = db.execute("SELECT v FROM meta WHERE k = 'checkpoint'").fetchone()
    if not rows and row is None:
        return {"integro": True, "lineas": 0, "rota_en": None}
    try:
        n, last, sig = (row["v"] if row else "").split("|")
    except ValueError:
        return {"integro": False, "lineas": len(rows), "rota_en": len(rows)}
    ok = cifrado.same(cifrado.sign(f"checkpoint|{n}|{last}", _home_of(home)), sig)
    if not ok or int(n) != len(rows) or last != prev:
        return {
            "integro": False,
            "lineas": len(rows),
            "rota_en": min(int(n or 0), len(rows)) + 1 if ok else len(rows),
        }
    return {"integro": True, "lineas": len(rows), "rota_en": None}


def opened_since(uid: str, since: float, home: Any = None) -> int:
    with _db(home) as db:
        return db.execute(
            "SELECT COUNT(*) FROM orders WHERE uid = ? AND created >= ?", (uid, since)
        ).fetchone()[0]


def mark(oid: str, status: str, home: Any = None) -> None:
    with _LOCK, _db(home) as db:
        db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, oid))


def latest_paid(home: Any = None) -> List[Dict[str, Any]]:
    """Each customer's most recent paid plan (the owner's test charges aside)."""
    with _db(home) as db:
        rows = db.execute(
            "SELECT * FROM orders WHERE status = 'pagado' AND plan != 'prueba' "
            "AND paid = (SELECT MAX(paid) FROM orders o WHERE o.uid = orders.uid "
            "AND o.status = 'pagado' AND o.plan != 'prueba')"
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


def active_plan(uid: str, home: Any = None) -> str:
    """The plan of the customer's paid month still in force ("" if none)."""
    with _db(home) as db:
        r = db.execute(
            "SELECT plan FROM orders WHERE uid = ? AND status = 'pagado' "
            "AND plan != 'prueba' AND until > ? ORDER BY until DESC LIMIT 1",
            (uid, time.time()),
        ).fetchone()
    return r["plan"] if r else ""


def totals(since: float = 0.0, home: Any = None) -> Dict[str, float]:
    with _db(home) as db:
        rows = db.execute(
            "SELECT kind, SUM(usd) AS usd FROM entries WHERE at >= ? GROUP BY kind",
            (since,),
        ).fetchall()
    out = {"ingreso": 0.0, "comision": 0.0, "proveedor": 0.0, "margen": 0.0}
    out.update({r["kind"]: round(r["usd"] or 0.0, 2) for r in rows})
    return out


def order_fee(order_id: str, home: Any = None) -> float:
    """The processor's fee recorded for one order (0 when none)."""
    with _db(home) as db:
        r = db.execute(
            "SELECT SUM(usd) AS usd FROM entries WHERE order_id = ? AND kind = 'comision'",
            (order_id,),
        ).fetchone()
    return round(float(r["usd"] or 0.0), 2)


def recent(limit: int = 20, home: Any = None) -> List[Dict[str, Any]]:
    with _db(home) as db:
        rows = db.execute(
            "SELECT * FROM orders ORDER BY created DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


__all__ = [
    "active_plan",
    "add_lines",
    "by_ext",
    "end_now",
    "first_time",
    "get",
    "latest_paid",
    "mark",
    "mark_paid",
    "new_order",
    "order_fee",
    "opened_since",
    "paid_until",
    "recent",
    "set_ext",
    "settle_paid",
    "totals",
    "verify",
]
