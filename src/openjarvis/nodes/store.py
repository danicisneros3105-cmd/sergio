"""SQLite state. Audit records contain action metadata, not record contents."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any


class NodeStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        if os.name != "nt":
            path.chmod(0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT, node TEXT, body TEXT)"
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS records_kind ON records(kind,node)")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, node TEXT, action TEXT, at REAL)"
        )
        self.db.commit()

    def put(
        self, kind: str, data: dict[str, Any], node: str = "", rid: str = ""
    ) -> dict[str, Any]:
        with self.lock:
            rid = rid or uuid.uuid4().hex
            record = {**data, "id": rid, "updated_at": time.time()}
            body = json.dumps(record, ensure_ascii=False, allow_nan=False)
            if len(body.encode()) > 32_768:
                raise ValueError("Registro demasiado grande")
            if kind in {"memory", "goal", "connection"}:
                count = self.db.execute(
                    "SELECT COUNT(*) FROM records WHERE kind=? AND node=?", (kind, node)
                ).fetchone()[0]
                exists = self.db.execute(
                    "SELECT 1 FROM records WHERE id=?", (rid,)
                ).fetchone()
                if count >= 300 and not exists:
                    raise ValueError("Máximo 300 registros; elimina entradas antiguas")
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO records VALUES (?,?,?,?)",
                    (rid, kind, node, body),
                )
                self.db.execute(
                    "INSERT INTO audit(node,action,at) VALUES (?,?,?)",
                    (node or rid, f"save:{kind}", time.time()),
                )
                self.db.execute(
                    "DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 2000)"
                )
                if kind == "execution":
                    self.db.execute(
                        "DELETE FROM records WHERE kind='execution' AND node=? AND id NOT IN "
                        "(SELECT id FROM records WHERE kind='execution' AND node=? ORDER BY rowid DESC LIMIT 100)",
                        (node, node),
                    )
            return record

    def get(self, kind: str, rid: str) -> dict[str, Any]:
        with self.lock:
            row = self.db.execute(
                "SELECT body FROM records WHERE kind=? AND id=?", (kind, rid)
            ).fetchone()
        if row is None:
            raise KeyError(rid)
        return json.loads(row[0])

    def list(self, kind: str, node: str | None = None) -> list[dict[str, Any]]:
        with self.lock:
            if node is None:
                rows = self.db.execute(
                    "SELECT body FROM records WHERE kind=? ORDER BY rowid DESC LIMIT 300",
                    (kind,),
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT body FROM records WHERE kind=? AND node=? ORDER BY rowid DESC LIMIT 300",
                    (kind, node),
                ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete(self, kind: str, rid: str, node: str = "") -> None:
        with self.lock, self.db:
            self.db.execute(
                "DELETE FROM records WHERE kind=? AND id=? AND node=?",
                (kind, rid, node),
            )
            self.db.execute(
                "INSERT INTO audit(node,action,at) VALUES (?,?,?)",
                (node or rid, f"delete:{kind}", time.time()),
            )
            self.db.execute(
                "DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 2000)"
            )

    def events(self, node: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT action,at FROM audit WHERE node=? ORDER BY id DESC LIMIT 100",
                (node,),
            ).fetchall()
        return [{"action": action, "at": at} for action, at in rows]

    def close(self) -> None:
        with self.lock:
            self.db.close()


__all__ = ["NodeStore"]
