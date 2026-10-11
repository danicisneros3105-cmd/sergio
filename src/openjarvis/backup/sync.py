"""Zero-knowledge sync of Sergio's knowledge between your devices.

What syncs (relative to ``~/.openjarvis``): Sergio's memory (``memory.db``,
merged note by note), the memory files (``SOUL.md``, ``USER.md``,
``MEMORY.md``, ``*.jsonl``), your skills, reminders, profile, health and
study plans, meeting notes, Cowork trust, and ``config.toml``. Never synced:
API keys (unless you ask), the face book (biometrics stay on the device
that enrolled them), logs, caches and models.

How it stays private: a random 256-bit data key, kept on the target only as
an ``age`` file locked with your passphrase (scrypt). Every object is
ChaCha20-Poly1305 encrypted with that key, and its name is an HMAC of the
file's path, so the storage (S3, B2, a shared folder…) sees neither names
nor contents. Each device remembers the unlocked key in its own
``~/.openjarvis/sync/key`` (0600) until ``sergio sync olvidar``.

Conflicts: when a file changed on both sides since the last sync,
``*.jsonl`` files keep the lines of both, the memory keeps the notes of
both, and anything else follows last-writer-wins (newest edit) — the losing
version is kept next to it as ``<file>.conflicto-<device>`` so nothing is
lost silently.
"""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
import os
import platform
import socket
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.backup.age import decrypt_bytes, encrypt_bytes
from openjarvis.backup.archive import home
from openjarvis.backup.targets import Target, TargetError

INCLUDE = (
    "config.toml",
    "SOUL.md",
    "USER.md",
    "MEMORY.md",
    "*.jsonl",
    "skills/*",
    "recordatorios.json",
    "salud.json",
    "escuela.json",
    "curriculum.json",
    "sueno.json",
    "psicologo.json",
    "reuniones/*",
    "profile/*",
    "cowork/trust.json",
    "workspace/pages/*",
    "workspace/files/*",
)
SECRET_FILES = ("sergio.env", "credentials.toml")
NEVER = (
    "faces/*",
    "*.log",
    "logs/*",
    "cache/*",
    "models/*",
    "bin/*",
    "sync/*",
    "backup/*",
)
MEMORY_ITEM = "@memory"
KEY_OBJECT = "sync/key.age"
MANIFEST_OBJECT = "sync/manifest.bin"


class SyncError(RuntimeError):
    """Sync could not run (locked, wrong passphrase, target unreachable)."""


def _aead(key: bytes):  # noqa: ANN202
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    return ChaCha20Poly1305(key)


def seal(key: bytes, data: bytes, label: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + _aead(key).encrypt(nonce, data, label.encode())


def unseal(key: bytes, blob: bytes, label: str) -> bytes:
    try:
        return _aead(key).decrypt(blob[:12], blob[12:], label.encode())
    except Exception as exc:  # InvalidTag
        raise SyncError("datos de sincronización dañados o de otra clave") from exc


def object_name(key: bytes, rel: str) -> str:
    tag = hmac.new(key, ("path:" + rel).encode(), hashlib.sha256).hexdigest()[:40]
    return f"sync/o/{tag}"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _device_id() -> str:
    path = home() / "sync" / "device"
    try:
        return path.read_text("utf-8").strip()
    except OSError:
        pass
    name = (
        f"{socket.gethostname() or platform.node() or 'equipo'}-{uuid.uuid4().hex[:6]}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name, "utf-8")
    return name


# -- the data key ---------------------------------------------------------------


def _key_path() -> Path:
    return home() / "sync" / "key"


def unlock(
    target: Target, passphrase: str, *, create: bool = False, work: int = 18
) -> bytes:
    """The sync data key (created on the first device), remembered locally."""
    try:
        blob = target.get(KEY_OBJECT)
    except TargetError:
        if not create:
            raise SyncError(
                "No hay sincronización en ese destino todavía: empiécela con "
                "sergio sync configurar"
            ) from None
        from openjarvis.backup.archive import _work

        key = os.urandom(32)
        target.put(KEY_OBJECT, encrypt_bytes(key, passphrase, work=work or _work()))
    else:
        try:
            key = decrypt_bytes(blob, passphrase)
        except ValueError as exc:
            raise SyncError(str(exc)) from exc
    path = _key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(key)
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return key


def local_key() -> Optional[bytes]:
    try:
        key = _key_path().read_bytes()
        return key if len(key) == 32 else None
    except OSError:
        return None


def forget() -> None:
    _key_path().unlink(missing_ok=True)


# -- what to sync ---------------------------------------------------------------


def wanted(rel: str, with_secrets: bool) -> bool:
    if any(fnmatch.fnmatch(rel, p) for p in NEVER):
        return False
    if rel in SECRET_FILES:
        return with_secrets
    return any(fnmatch.fnmatch(rel, p) for p in INCLUDE)


def local_files(root: Path, with_secrets: bool) -> Dict[str, bytes]:
    out: Dict[str, bytes] = {}
    if not root.is_dir():
        return out
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink() and ".conflicto-" not in path.name:
            rel = path.relative_to(root).as_posix()
            if wanted(rel, with_secrets) and path.stat().st_size < 64 * 1024 * 1024:
                out[rel] = path.read_bytes()
    return out


# -- memory.db: notes merged one by one ------------------------------------------


def memory_export(db_path: Path) -> bytes:
    """The memory's notes as JSON lines, each with a stable ``sync_id``."""
    if not db_path.is_file():
        return b""
    rows = []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for doc_id, content, source, metadata in con.execute(
            "SELECT id, content, source, metadata FROM documents"
        ):
            try:
                meta = json.loads(metadata or "{}")
            except ValueError:
                meta = {}
            sync_id = str(meta.pop("sync_id", "") or doc_id)
            # created_at is left out on purpose: each device stamps its own
            # copy, and the export must be identical once both hold the note.
            rows.append(
                {
                    "sync_id": sync_id,
                    "content": content,
                    "source": source or "",
                    "metadata": meta,
                }
            )
    except sqlite3.Error:
        return b""
    finally:
        con.close()
    rows.sort(key=lambda r: r["sync_id"])
    return "\n".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows
    ).encode()


def memory_import(db_path: Path, data: bytes) -> int:
    """Add notes from *data* that this device does not have yet."""
    have = {
        json.loads(line)["sync_id"]
        for line in memory_export(db_path).splitlines()
        if line
    }
    new = [json.loads(line) for line in data.splitlines() if line]
    new = [r for r in new if r["sync_id"] not in have]
    if not new:
        return 0
    from openjarvis.tools.storage.sqlite import SQLiteMemory

    memory = SQLiteMemory(db_path=str(db_path))
    try:
        for row in new:
            memory.store(
                row["content"],
                source=row.get("source", ""),
                metadata={**(row.get("metadata") or {}), "sync_id": row["sync_id"]},
            )
    finally:
        close = getattr(memory, "close", None)
        if callable(close):
            close()
    return len(new)


def merge_lines(a: bytes, b: bytes) -> bytes:
    """Lines of both, each once, in first-seen order."""
    seen, out = set(), []
    for line in a.splitlines() + b.splitlines():
        if line.strip() and line not in seen:
            seen.add(line)
            out.append(line)
    return b"\n".join(out) + (b"\n" if out else b"")


# -- the sync itself ------------------------------------------------------------


@dataclass
class SyncReport:
    uploaded: List[str] = field(default_factory=list)
    downloaded: List[str] = field(default_factory=list)
    merged: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    memory_added: int = 0

    def summary(self) -> str:
        parts = []
        for label, items in (
            ("subidos", self.uploaded),
            ("bajados", self.downloaded),
            ("combinados", self.merged),
            ("borrados", self.deleted),
            ("conflictos guardados", self.conflicts),
        ):
            if items:
                parts.append(f"{len(items)} {label}")
        if self.memory_added:
            parts.append(f"{self.memory_added} recuerdos nuevos")
        return ", ".join(parts) or "todo estaba al día"


def _state_path() -> Path:
    return home() / "sync" / "state.json"


def _load_state() -> Dict[str, Any]:
    try:
        return json.loads(_state_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), "utf-8")
    tmp.replace(path)


def _read_manifest(target: Target, key: bytes) -> Dict[str, Any]:
    try:
        blob = target.get(MANIFEST_OBJECT)
    except TargetError:
        return {"files": {}, "devices": {}}
    return json.loads(unseal(key, blob, "manifest"))


def sync(
    target: Target,
    key: bytes,
    *,
    root: Optional[Path] = None,
    with_secrets: bool = False,
    memory_db: Optional[Path] = None,
    now: Optional[float] = None,
) -> SyncReport:
    """One round: pull what others changed, push what this device changed."""
    root = root or home()
    now = now or time.time()
    device = _device_id()
    memory_db = memory_db or root / "memory.db"
    report = SyncReport()
    state = _load_state()
    if state.get("target") != target.describe():
        state = {}  # another target: nothing is known to be in sync with it
    synced: Dict[str, str] = dict(state.get("files", {}))  # rel -> hash at last sync
    manifest = _read_manifest(target, key)
    remote: Dict[str, Dict[str, Any]] = manifest.setdefault("files", {})

    local = local_files(root, with_secrets)
    local[MEMORY_ITEM] = memory_export(memory_db)
    names = (
        set(local)
        | {r for r, e in remote.items() if not e.get("deleted")}
        | set(synced)
    )

    def remote_bytes(rel: str) -> bytes:
        return unseal(key, target.get(object_name(key, rel)), rel)

    def edited_at(rel: str) -> float:
        """When the file was last edited here (what last-writer-wins compares)."""
        try:
            return (root / rel).stat().st_mtime
        except OSError:
            return now

    def push(rel: str, data: bytes) -> None:
        target.put(object_name(key, rel), seal(key, data, rel))
        remote[rel] = {
            "hash": _sha(data),
            "mtime": edited_at(rel) if rel != MEMORY_ITEM else now,
            "device": device,
            "deleted": False,
        }
        synced[rel] = _sha(data)

    def write_local(rel: str, data: bytes) -> None:
        if rel == MEMORY_ITEM:
            report.memory_added += memory_import(memory_db, data)
            synced[rel] = _sha(memory_export(memory_db))
            return
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".sync-tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        edited = (remote.get(rel) or {}).get("mtime")
        if edited:  # keep the original edit time, so the next comparison is fair
            os.utime(path, (float(edited), float(edited)))
        synced[rel] = _sha(data)

    for rel in sorted(names):
        mine = local.get(rel)
        mine_hash = _sha(mine) if mine is not None else None
        entry = remote.get(rel)
        theirs_hash = (
            None if entry is None or entry.get("deleted") else entry.get("hash")
        )
        base = synced.get(rel)
        if mine_hash == theirs_hash:
            if mine_hash is not None:
                synced[rel] = mine_hash
            continue
        local_changed = mine_hash != base
        if entry is None:
            # No record at all (a new target, a lost manifest): never read
            # that as "deleted elsewhere" — this device's copy wins.
            remote_changed = False
            local_changed = mine is not None
        else:
            remote_changed = theirs_hash != base
        if local_changed and not remote_changed:
            if mine is None:  # deleted here
                target.delete(object_name(key, rel))
                remote[rel] = {"deleted": True, "mtime": now, "device": device}
                synced.pop(rel, None)
                report.deleted.append(rel)
            else:
                push(rel, mine)
                report.uploaded.append(rel)
        elif remote_changed and not local_changed:
            if theirs_hash is None:  # deleted elsewhere
                if rel != MEMORY_ITEM:
                    (root / rel).unlink(missing_ok=True)
                synced.pop(rel, None)
                report.deleted.append(rel)
            else:
                write_local(rel, remote_bytes(rel))
                report.downloaded.append(rel)
        else:  # both changed
            theirs = remote_bytes(rel) if theirs_hash is not None else None
            if rel == MEMORY_ITEM:
                if theirs:
                    report.memory_added += memory_import(memory_db, theirs)
                push(rel, memory_export(memory_db))
                report.merged.append(rel)
            elif rel.endswith(".jsonl") and mine is not None and theirs is not None:
                combined = merge_lines(theirs, mine)
                write_local(rel, combined)
                push(rel, combined)
                report.merged.append(rel)
            else:
                mine_time = edited_at(rel) if mine is not None else 0.0
                theirs_time = float(entry.get("mtime", 0.0)) if entry else 0.0
                if mine is not None and (theirs is None or mine_time >= theirs_time):
                    if theirs is not None:
                        keep = root / f"{rel}.conflicto-{entry.get('device', 'otro')}"
                        keep.write_bytes(theirs)
                        report.conflicts.append(rel)
                    push(rel, mine)
                    report.uploaded.append(rel)
                elif theirs is not None:
                    if mine is not None:
                        keep = root / f"{rel}.conflicto-{device}"
                        keep.write_bytes(mine)
                        report.conflicts.append(rel)
                    write_local(rel, theirs)
                    report.downloaded.append(rel)
    manifest.setdefault("devices", {})[device] = {"last_sync": now}
    target.put(MANIFEST_OBJECT, seal(key, json.dumps(manifest).encode(), "manifest"))
    state.update({"target": target.describe(), "files": synced, "last_sync": now})
    _save_state(state)
    return report


_NUDGE: Optional[Any] = None
NUDGE_DELAY_S = 20.0  # a burst of edits becomes one sync
RETRY_S = 60.0  # offline or unreachable: try again soon, not in an hour


def nudge() -> None:
    """Something worth backing up changed (e.g. a Workspace page): sync soon."""
    if _NUDGE is not None:
        _NUDGE.set()


def start_periodic(config: Any) -> Optional[Any]:
    """Sync every ``[sync] interval_minutes`` in the background (server only),
    and about 20 s after a change is nudged (``nudge()``), so edits reach the
    encrypted target almost as they happen; when the network is down it keeps
    retrying every minute until it is back.

    Needs this device to be unlocked once (``sergio sync configurar``).
    Returns a ``threading.Event``; set it to stop. None when not configured.
    """
    import logging
    import threading

    global _NUDGE
    minutes = int(getattr(config.sync, "interval_minutes", 0) or 0)
    url = str(getattr(config.sync, "target", "") or "")
    if minutes <= 0 or not url or local_key() is None:
        return None
    wake = threading.Event()

    class _Stop(threading.Event):
        def set(self) -> None:  # stopping also wakes the loop
            super().set()
            wake.set()

    stop = _Stop()
    _NUDGE = wake
    log = logging.getLogger(__name__)

    def loop() -> None:
        from openjarvis.backup.targets import open_target

        pending = False
        while not stop.is_set():
            timeout = RETRY_S if pending else max(1, minutes) * 60
            if wake.wait(timeout):
                wake.clear()
                if stop.is_set() or stop.wait(NUDGE_DELAY_S):
                    return
                wake.clear()
            if stop.is_set():
                return
            key = local_key()
            if key is None:
                return
            try:
                report = sync(
                    open_target(url), key, with_secrets=bool(config.sync.with_secrets)
                )
                pending = False
                log.info("Sync: %s", report.summary())
            except Exception as exc:  # noqa: BLE001 - try again soon
                pending = True
                log.warning("Sync failed (will retry): %s", exc)

    threading.Thread(target=loop, name="sergio-sync", daemon=True).start()
    return stop


def status() -> Dict[str, Any]:
    state = _load_state()
    return {
        "device": _device_id(),
        "target": state.get("target", ""),
        "last_sync": state.get("last_sync"),
        "files": len(state.get("files", {})),
        "unlocked": local_key() is not None,
    }


__all__ = [
    "INCLUDE",
    "SyncError",
    "SyncReport",
    "forget",
    "local_key",
    "memory_export",
    "memory_import",
    "merge_lines",
    "nudge",
    "object_name",
    "seal",
    "status",
    "start_periodic",
    "sync",
    "unlock",
    "unseal",
    "wanted",
]
