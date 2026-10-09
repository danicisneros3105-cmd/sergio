"""Encrypted, incremental backups of Sergio's folder (``~/.openjarvis``).

``create`` packs what changed since the last backup (or everything, every
eighth time or when asked) into a compressed tar, encrypts it with the
owner's passphrase in the ``age`` format and puts it on the target as
``sergio-backup-<id>-<full|inc>.age``. Inside, a manifest lists every file
with its SHA-256, the files deleted since the parent backup, and the parent's
id, so ``restore`` can rebuild any point from the chain. SQLite databases are
copied with SQLite's own backup API, so a backup taken while Sergio runs is
still consistent. Caches, logs, models and downloaded programs are left out.
"""

from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from openjarvis.backup.age import AgeError, decrypt_bytes, encrypt_bytes
from openjarvis.backup.targets import Target

MANIFEST = "__sergio_backup__.json"
FULL_EVERY = 8  # a new full backup after 7 incrementals
MAX_FILE = 512 * 1024 * 1024
NAME_RE = re.compile(r"^sergio-backup-(\d{8}-\d{6}(?:-\d{3})?)-(full|inc)\.age$")
EXCLUDE = (
    "backup/*",
    "cache/*",
    "*/cache/*",
    "skill-cache/*",
    "logs/*",
    "*.log",
    "*.pid",
    "runtime/*",
    "models/*",
    "bin/*",
    "tmp/*",
    "*.tmp",
    "*.partial",
    "*/__pycache__/*",
    "*/node_modules/*",
    "*/.venv/*",
    "plugins/.tmp-*",
    "plugins/.old-*",
    "version-check.json",
)
SECRETS = (
    "sergio.env",
    "cloud-keys.env",
    "credentials.toml",
    ".vault_key",
    "connectors/*",
)


def _backup_id(stamp: float) -> str:
    total = int(stamp * 1000)
    seconds, millis = divmod(total, 1000)
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(seconds)) + f"-{millis:03d}"


def home() -> Path:
    return Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")


def _work() -> int:
    """scrypt work factor (tests and slow machines may lower it)."""
    try:
        return max(10, min(22, int(os.environ.get("SERGIO_AGE_WORK", "18"))))
    except ValueError:
        return 18


@dataclass
class BackupInfo:
    id: str
    kind: str  # full | inc
    name: str
    size: int = 0
    parent: str = ""
    files: int = 0
    deleted: int = 0
    created: str = ""


@dataclass
class Plan:
    kind: str
    parent: str
    changed: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    index: Dict[str, List] = field(
        default_factory=dict
    )  # rel -> [size, mtime_ns, sha256]


def _excluded(rel: str, patterns: Iterable[str]) -> bool:
    return any(
        fnmatch.fnmatch(rel, p) or fnmatch.fnmatch("/" + rel, "*/" + p)
        for p in patterns
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def scan(
    root: Path, *, with_secrets: bool = True, previous: Optional[Dict[str, List]] = None
) -> Dict[str, List]:
    """{relative path: [size, mtime_ns, sha256]} for every file to back up.

    Files whose size and modification time did not change reuse the previous
    hash, so an incremental backup does not re-read the whole folder."""
    previous = previous or {}
    patterns = EXCLUDE + (() if with_secrets else SECRETS)
    index: Dict[str, List] = {}
    if not root.is_dir():
        return index
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if _excluded(rel, patterns):
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        if st.st_size > MAX_FILE:
            continue
        old = previous.get(rel)
        if old and old[0] == st.st_size and old[1] == st.st_mtime_ns:
            index[rel] = [st.st_size, st.st_mtime_ns, old[2]]
        else:
            index[rel] = [st.st_size, st.st_mtime_ns, _sha256(path)]
    return index


def _state_path() -> Path:
    return home() / "backup" / "state.json"


def load_state() -> Dict:
    try:
        return json.loads(_state_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: Dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), "utf-8")
    tmp.replace(path)


def plan(
    root: Path, target_url: str, *, full: bool = False, with_secrets: bool = True
) -> Plan:
    state = load_state()
    same_target = state.get("target") == target_url and state.get("last_id")
    previous = state.get("files", {}) if same_target else {}
    index = scan(root, with_secrets=with_secrets, previous=previous)
    chain = int(state.get("chain", 0)) if same_target else 0
    if (
        full
        or not same_target
        or chain + 1 >= FULL_EVERY
        or bool(state.get("with_secrets", True)) != with_secrets
    ):
        return Plan("full", "", sorted(index), [], index)
    changed = sorted(
        rel
        for rel, meta in index.items()
        if previous.get(rel, [None, None, None])[2] != meta[2]
    )
    deleted = sorted(set(previous) - set(index))
    return Plan("inc", str(state["last_id"]), changed, deleted, index)


def _add_file(tar: tarfile.TarFile, root: Path, rel: str) -> str:
    """Add one file; returns the SHA-256 of the bytes that went in."""
    path = root / rel
    if path.suffix == ".db":
        # A consistent copy even while Sergio writes to it.
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy.db"
            try:
                src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                dst = sqlite3.connect(copy)
                with dst:
                    src.backup(dst)
                src.close()
                dst.close()
                tar.add(copy, arcname=rel, recursive=False)
                return _sha256(copy)
            except sqlite3.Error:
                pass  # not a SQLite file after all: copy the bytes
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "snap"
        shutil.copy2(path, snapshot)  # the hash and the archive see the same bytes
        tar.add(snapshot, arcname=rel, recursive=False)
        return _sha256(snapshot)


def create(
    target: Target,
    passphrase: str,
    *,
    root: Optional[Path] = None,
    full: bool = False,
    with_secrets: bool = True,
    progress: Callable[[str], None] = lambda _msg: None,
) -> BackupInfo:
    root = root or home()
    the_plan = plan(root, target.describe(), full=full, with_secrets=with_secrets)
    # Fixed-width ids (milliseconds) so text order is time order.
    existing = {i.id for i in list_backups(target)}
    stamp = time.time()
    backup_id = _backup_id(stamp)
    while backup_id in existing:
        stamp += 0.001
        backup_id = _backup_id(stamp)
    progress(
        f"{'Copia completa' if the_plan.kind == 'full' else 'Copia incremental'}: "
        f"{len(the_plan.changed)} archivos nuevos o cambiados, {len(the_plan.deleted)} borrados."
    )
    manifest = {
        "version": 1,
        "id": backup_id,
        "kind": the_plan.kind,
        "parent": the_plan.parent,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "with_secrets": with_secrets,
        "files": {
            rel: {"size": the_plan.index[rel][0], "sha256": the_plan.index[rel][2]}
            for rel in the_plan.changed
        },
        "all": {rel: meta[2] for rel, meta in the_plan.index.items()},
        "deleted": the_plan.deleted,
    }
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for rel in the_plan.changed:
            try:
                manifest["files"][rel]["sha256"] = _add_file(tar, root, rel)
            except OSError:  # vanished while backing up
                manifest["files"].pop(rel, None)
                manifest["all"].pop(rel, None)
        data = json.dumps(manifest, ensure_ascii=False).encode()
        info = tarfile.TarInfo(MANIFEST)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    progress("Cifrando…")
    sealed = encrypt_bytes(buffer.getvalue(), passphrase, work=_work())
    name = f"sergio-backup-{backup_id}-{the_plan.kind}.age"
    progress(f"Subiendo a {target.describe()} ({len(sealed) / 1e6:.1f} MB)…")
    target.put(name, sealed)
    state = load_state() if the_plan.kind == "inc" else {}
    _save_state(
        {
            "target": target.describe(),
            "last_id": backup_id,
            "chain": (int(state.get("chain", 0)) + 1) if the_plan.kind == "inc" else 0,
            "with_secrets": with_secrets,
            "files": the_plan.index,
        }
    )
    return BackupInfo(
        backup_id,
        the_plan.kind,
        name,
        len(sealed),
        the_plan.parent,
        len(the_plan.changed),
        len(the_plan.deleted),
        manifest["created"],
    )


def list_backups(target: Target) -> List[BackupInfo]:
    out = []
    for name in target.list(""):
        m = NAME_RE.match(PurePosixPath(name).name)
        if m:
            out.append(BackupInfo(m.group(1), m.group(2), name))
    return sorted(out, key=lambda b: b.id)


def _open(
    target: Target, info: BackupInfo, passphrase: str
) -> Tuple[Dict, tarfile.TarFile]:
    try:
        plain = decrypt_bytes(target.get(info.name), passphrase)
    except AgeError as exc:
        raise AgeError(f"{info.id}: {exc}") from exc
    tar = tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz")
    member = tar.getmember(MANIFEST)
    manifest = json.loads(tar.extractfile(member).read())  # type: ignore[union-attr]
    return manifest, tar


def chain_for(
    target: Target, backup_id: str, passphrase: str
) -> List[Tuple[Dict, tarfile.TarFile]]:
    """The backups needed to rebuild *backup_id*, oldest (the full one) first."""
    by_id = {b.id: b for b in list_backups(target)}
    chain: List[Tuple[Dict, tarfile.TarFile]] = []
    current = backup_id
    while current:
        info = by_id.get(current)
        if info is None:
            raise FileNotFoundError(f"falta la copia {current} en el destino")
        manifest, tar = _open(target, info, passphrase)
        chain.append((manifest, tar))
        current = manifest.get("parent", "") if manifest.get("kind") == "inc" else ""
        if len(chain) > 64:
            raise RuntimeError("cadena de copias demasiado larga")
    return list(reversed(chain))


def _safe_extract(tar: tarfile.TarFile, rel: str, dest: Path) -> None:
    posix = PurePosixPath(rel)
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"ruta peligrosa en la copia: {rel}")
    member = tar.getmember(rel)
    if not member.isfile():
        return
    target = (dest / rel).resolve()
    if dest.resolve() not in target.parents:
        raise ValueError(f"ruta fuera del destino: {rel}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tar.extractfile(member) as src, target.open("wb") as out:  # type: ignore[union-attr]
        shutil.copyfileobj(src, out)


def restore(
    target: Target,
    passphrase: str,
    dest: Path,
    *,
    backup_id: str = "",
    progress: Callable[[str], None] = lambda _msg: None,
) -> Dict[str, int]:
    """Rebuild a backup (the latest by default) into *dest*; verifies hashes."""
    backups = list_backups(target)
    if not backups:
        raise FileNotFoundError("no hay copias en el destino")
    backup_id = backup_id or backups[-1].id
    chain = chain_for(target, backup_id, passphrase)
    final = chain[-1][0]
    wanted: Dict[str, str] = dict(final.get("all", {}))
    source: Dict[
        str, int
    ] = {}  # file -> index of the backup that holds its latest copy
    for i, (manifest, _) in enumerate(chain):
        for rel in manifest.get("files", {}):
            source[rel] = i
    dest.mkdir(parents=True, exist_ok=True)
    restored = 0
    for rel in sorted(wanted):
        index = source.get(rel)
        if index is None:
            raise RuntimeError(f"la cadena no contiene {rel}")
        _safe_extract(chain[index][1], rel, dest)
        if _sha256(dest / rel) != chain[index][0]["files"][rel]["sha256"]:
            raise RuntimeError(f"{rel} no coincide con su huella: la copia está dañada")
        restored += 1
    for _, tar in chain:
        tar.close()
    progress(f"Restaurados {restored} archivos de la copia {backup_id}.")
    return {"files": restored, "backups_used": len(chain)}


def verify(target: Target, passphrase: str, backup_id: str = "") -> Dict[str, int]:
    """Decrypt the chain and check every file's hash, without writing anything."""
    with tempfile.TemporaryDirectory() as tmp:
        return restore(target, passphrase, Path(tmp) / "check", backup_id=backup_id)


def prune(target: Target, keep_full: int = 4) -> List[str]:
    """Delete chains older than the *keep_full* most recent full backups."""
    backups = list_backups(target)
    fulls = [b for b in backups if b.kind == "full"]
    if len(fulls) <= keep_full:
        return []
    cutoff = fulls[-keep_full].id
    gone = [b.name for b in backups if b.id < cutoff]
    for name in gone:
        target.delete(name)
    return gone


__all__ = [
    "BackupInfo",
    "EXCLUDE",
    "SECRETS",
    "chain_for",
    "create",
    "home",
    "list_backups",
    "load_state",
    "plan",
    "prune",
    "restore",
    "scan",
    "verify",
]
