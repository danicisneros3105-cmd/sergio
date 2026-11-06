"""SQLite store for accounts, sessions, one-time codes and sign-up events
(``~/.openjarvis/cuentas/cuentas.db``, file readable only by the owner)."""

from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from openjarvis.accounts import security

SESSION_DAYS = 30
CODE_MINUTES = 10
CODE_TRIES = 5
LOCK_AFTER = 5  # failed sign-ins before the account waits
LOCK_SECONDS = 15 * 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT, canonical TEXT UNIQUE, phone TEXT UNIQUE, name TEXT DEFAULT '',
  password TEXT DEFAULT '', email_ok INTEGER DEFAULT 0, phone_ok INTEGER DEFAULT 0,
  provider TEXT DEFAULT '', subject TEXT DEFAULT '', role TEXT DEFAULT 'pendiente',
  created REAL, failed INTEGER DEFAULT 0, locked_until REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY, user TEXT NOT NULL, device TEXT DEFAULT '', created REAL, expires REAL
);
CREATE TABLE IF NOT EXISTS codes (
  target TEXT PRIMARY KEY, code TEXT NOT NULL, purpose TEXT, expires REAL, tries INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS signups (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, device TEXT, network TEXT, at REAL
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS consents (
  user TEXT PRIMARY KEY, terms TEXT, adult INTEGER, auto INTEGER DEFAULT 0, at REAL
);
CREATE TABLE IF NOT EXISTS passkeys (
  id TEXT PRIMARY KEY, user TEXT NOT NULL, public TEXT NOT NULL, alg INTEGER, count INTEGER DEFAULT 0,
  name TEXT DEFAULT '', created REAL, used REAL DEFAULT 0
);
"""


class AccountStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._db() as db:
            db.executescript(_SCHEMA)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self.pepper = self._pepper()

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

    def _pepper(self) -> str:
        with self._db() as db:
            row = db.execute("SELECT v FROM meta WHERE k = 'pepper'").fetchone()
            if row:
                return row["v"]
            value = secrets.token_hex(32)
            db.execute("INSERT INTO meta VALUES ('pepper', ?)", (value,))
            return value

    # -- users ----------------------------------------------------------------------
    def count(self) -> int:
        with self._db() as db:
            return int(db.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def create(self, *, email: str = "", canonical: str = "", phone: str = "", name: str = "",
               password: str = "", provider: str = "", subject: str = "", role: str = "pendiente",
               email_ok: bool = False, consent: Optional[tuple[str, bool, bool]] = None) -> Dict[str, Any]:  # fmt: skip
        uid = secrets.token_hex(8)
        with self._db() as db:
            db.execute(
                "INSERT INTO users (id, email, canonical, phone, name, password, email_ok, provider, subject, role, "
                "created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (uid, email or None, canonical or None, phone or None, name[:80],
                 security.hash_password(password) if password else "", int(email_ok), provider, subject,
                 role, time.time()),
            )  # fmt: skip
            if consent:
                terms, adult, auto = consent
                db.execute(
                    "INSERT INTO consents VALUES (?,?,?,?,?)",
                    (uid, terms, int(adult), int(auto), time.time()),
                )
        return self.get(uid) or {}

    @staticmethod
    def _row(r: sqlite3.Row) -> Dict[str, Any]:
        return {k: r[k] for k in r.keys()}

    def get(self, uid: str) -> Optional[Dict[str, Any]]:
        with self._db() as db:
            r = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        return self._row(r) if r else None

    def find(
        self,
        *,
        canonical: str = "",
        phone: str = "",
        provider: str = "",
        subject: str = "",
    ) -> Optional[Dict[str, Any]]:
        with self._db() as db:
            if canonical:
                r = db.execute(
                    "SELECT * FROM users WHERE canonical = ?", (canonical,)
                ).fetchone()
            elif phone:
                r = db.execute(
                    "SELECT * FROM users WHERE phone = ?", (phone,)
                ).fetchone()
            else:
                r = db.execute(
                    "SELECT * FROM users WHERE provider = ? AND subject = ?",
                    (provider, subject),
                ).fetchone()
        return self._row(r) if r else None

    def set(self, uid: str, **fields: Any) -> None:
        allowed = {
            "email",
            "canonical",
            "phone",
            "name",
            "email_ok",
            "phone_ok",
            "role",
            "failed",
            "locked_until",
        }
        keys = [k for k in fields if k in allowed]
        if "password" in fields:
            keys.append("password")
            fields["password"] = security.hash_password(fields["password"])
        if not keys:
            return
        with self._db() as db:
            db.execute(
                f"UPDATE users SET {', '.join(f'{k} = ?' for k in keys)} WHERE id = ?",  # noqa: S608 — fixed names
                [fields[k] for k in keys] + [uid],
            )

    def users(self) -> List[Dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM users ORDER BY created").fetchall()
        return [self._row(r) for r in rows]

    def delete(self, uid: str) -> bool:
        with self._db() as db:
            gone = db.execute("DELETE FROM users WHERE id = ?", (uid,)).rowcount
            db.execute("DELETE FROM sessions WHERE user = ?", (uid,))
            db.execute("DELETE FROM passkeys WHERE user = ?", (uid,))
        return bool(gone)

    # -- sign-in failures -----------------------------------------------------------------
    def locked(self, user: Dict[str, Any]) -> float:
        return max(0.0, float(user.get("locked_until") or 0) - time.time())

    def failed(self, user: Dict[str, Any]) -> None:
        n = int(user.get("failed") or 0) + 1
        until = (
            time.time() + LOCK_SECONDS * (2 ** max(0, n // LOCK_AFTER - 1))
            if n % LOCK_AFTER == 0
            else 0
        )
        self.set(
            user["id"], failed=n, locked_until=until or user.get("locked_until") or 0
        )

    # -- sessions ----------------------------------------------------------------------
    def open_session(self, uid: str, device: str = "") -> str:
        raw, _short = security.new_token()
        now = time.time()
        with self._db() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?)",
                (
                    security.digest(raw, self.pepper),
                    uid,
                    device[:64],
                    now,
                    now + SESSION_DAYS * 86400,
                ),
            )
        self.set(uid, failed=0, locked_until=0)
        return raw

    def session_user(self, raw: str) -> Optional[Dict[str, Any]]:
        if not raw or not raw.startswith("sg_"):
            return None
        with self._db() as db:
            r = db.execute(
                "SELECT user, expires FROM sessions WHERE token = ?",
                (security.digest(raw, self.pepper),),
            ).fetchone()
        if not r or r["expires"] < time.time():
            return None
        return self.get(r["user"])

    def close_session(self, raw: str) -> None:
        with self._db() as db:
            db.execute(
                "DELETE FROM sessions WHERE token = ?",
                (security.digest(raw, self.pepper),),
            )

    # -- passkeys (the device's face, finger or PIN) ------------------------------------
    def add_passkey(self, uid: str, key: Dict[str, Any], name: str = "") -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO passkeys (id, user, public, alg, count, name, created) VALUES (?,?,?,?,?,?,?)",
                (
                    key["id"],
                    uid,
                    key["public"],
                    int(key["alg"]),
                    int(key["count"]),
                    name[:60],
                    time.time(),
                ),
            )

    def passkey(self, key_id: str) -> Optional[Dict[str, Any]]:
        with self._db() as db:
            r = db.execute("SELECT * FROM passkeys WHERE id = ?", (key_id,)).fetchone()
        return self._row(r) if r else None

    def passkeys_of(self, uid: str) -> List[Dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT id, name, created, used FROM passkeys WHERE user = ? ORDER BY created",
                (uid,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def used_passkey(self, key_id: str, count: int) -> None:
        with self._db() as db:
            db.execute(
                "UPDATE passkeys SET count = ?, used = ? WHERE id = ?",
                (int(count), time.time(), key_id),
            )

    def delete_passkey(self, uid: str, key_id: str) -> bool:
        with self._db() as db:
            cur = db.execute(
                "DELETE FROM passkeys WHERE id = ? AND user = ?", (key_id, uid)
            )
            return cur.rowcount > 0

    # -- one-time codes -------------------------------------------------------------------
    def put_code(self, target: str, purpose: str) -> str:
        code = security.new_code()
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO codes VALUES (?,?,?,?,0)",
                (
                    target,
                    security.digest(code, self.pepper),
                    purpose,
                    time.time() + CODE_MINUTES * 60,
                ),
            )
        return code

    def check_code(self, target: str, code: str, purpose: str) -> bool:
        with self._db() as db:
            r = db.execute("SELECT * FROM codes WHERE target = ?", (target,)).fetchone()
            if (
                not r
                or r["purpose"] != purpose
                or r["expires"] < time.time()
                or r["tries"] >= CODE_TRIES
            ):
                return False
            ok = secrets.compare_digest(
                r["code"], security.digest((code or "").strip(), self.pepper)
            )
            if ok:
                db.execute("DELETE FROM codes WHERE target = ?", (target,))
            else:
                db.execute(
                    "UPDATE codes SET tries = tries + 1 WHERE target = ?", (target,)
                )
            return ok

    # -- terms accepted and who may open by itself (accounts/registro.py) -------------------
    def record_consent(self, uid: str, terms: str, adult: bool, auto: bool) -> None:
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO consents VALUES (?,?,?,?,?)",
                       (uid, terms, int(adult), int(auto), time.time()))  # fmt: skip

    def consent_of(self, uid: str) -> Optional[Dict[str, Any]]:
        with self._db() as db:
            r = db.execute("SELECT * FROM consents WHERE user = ?", (uid,)).fetchone()
        return dict(r) if r else None

    # -- sign-up events (fraud signals) ---------------------------------------------------------
    def note_signup(self, uid: str, device: str, network: str) -> None:
        with self._db() as db:
            db.execute("INSERT INTO signups (user, device, network, at) VALUES (?,?,?,?)",
                       (uid, device[:64], network, time.time()))  # fmt: skip

    def signups_since(
        self, seconds: float, *, device: str = "", network: str = ""
    ) -> int:
        since = time.time() - seconds
        with self._db() as db:
            if device:
                q = db.execute(
                    "SELECT COUNT(*) FROM signups WHERE device = ? AND at > ?",
                    (device, since),
                )
            else:
                q = db.execute(
                    "SELECT COUNT(*) FROM signups WHERE network = ? AND at > ?",
                    (network, since),
                )
            return int(q.fetchone()[0])


_STORES: Dict[str, AccountStore] = {}
_LOCK = threading.Lock()


def get_store(home: Optional[Path] = None) -> AccountStore:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    path = Path(home) / "cuentas" / "cuentas.db"
    with _LOCK:
        if str(path) not in _STORES:
            _STORES[str(path)] = AccountStore(path)
        return _STORES[str(path)]


def public(user: Dict[str, Any]) -> Dict[str, Any]:
    """What the app may see of an account (never the password hash)."""
    return {k: user.get(k) for k in ("id", "email", "phone", "name", "email_ok", "phone_ok", "provider", "role",
                                     "created")}  # fmt: skip


__all__ = ["AccountStore", "get_store", "public"]
