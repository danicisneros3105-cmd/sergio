"""Sergio's keys: AES-256-GCM for secrets at rest, HMAC for the ledger.

The **keyring** (``~/.openjarvis/clave_maestra``, 0600) holds one or more
32-byte keys, each with a short id (``kid``); the newest is the active one.
From each key, independent keys are derived per purpose (HKDF-SHA256):
``salud``, ``memoria``, ``nodes``, ``cifrar``… and ``libro`` for the ledger.

* **Versions and rotation** (like a bank's key-management service): a value
  is sealed as ``v2:<kid>:`` + base64(nonce ‖ ciphertext ‖ tag), so after
  :func:`rotate` new values use the new key and older ones still open with
  theirs. Values from before the keyring (``v1:``) open with the original key.
  The ledger is always signed with the **first** key, so its chain stays
  verifiable after a rotation.
* **Protected with a passphrase** (:func:`protect`): the keyring itself is then
  encrypted (AES-256-GCM) with a key made from the passphrase by scrypt
  (N=2^17, r=8, p=1: ~128 MB and a fraction of a second per try, so guessing
  is slow). The disk then holds no usable key; the server needs the phrase in
  ``SERGIO_FRASE_MAESTRA`` to start. Kept next to the data, the phrase adds
  little: it belongs in a secret manager or typed at start.
* ``SERGIO_CLAVE_MAESTRA`` (base64, one key): for a server whose disk must not
  hold any key; rotation then happens in the secret manager.

Every value is tied to what it belongs to (``aad``, e.g. the customer's id): a
sealed value copied elsewhere does not open. Losing the keyring (or the
phrase) loses what it sealed; never commit or share it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PREFIX = "v1:"  # before the keyring: sealed with the single original key
PREFIX2 = "v2:"  # v2:<kid>:<base64>
PREFIXES = (PREFIX, PREFIX2)
FORMAT = "sergio-llavero-1"
SCRYPT = {"n": 2**17, "r": 8, "p": 1}
MIN_PHRASE = 12

_LOCK = threading.Lock()
_CACHE: Dict[str, "Keyring"] = {}
_DERIVED: Dict[tuple, bytes] = {}


class SealError(ValueError):
    pass


@dataclass
class Keyring:
    keys: List[Dict[str, Any]] = field(default_factory=list)  # {kid, key, creada}
    active: str = ""
    source: str = "archivo"  # archivo | entorno
    protected: bool = False

    def key(self, kid: str) -> bytes:
        for k in self.keys:
            if k["kid"] == kid:
                return k["key"]
        raise SealError(f"la clave {kid} no está en el llavero")

    @property
    def first(self) -> bytes:
        return self.keys[0]["key"]


def _home(home: Any = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = get_config_dir()
    return Path(home)


def kid_of(key: bytes) -> str:
    return hashlib.sha256(b"sergio-kid|" + key).hexdigest()[:8]


def _phrase() -> str:
    return os.environ.get("SERGIO_FRASE_MAESTRA", "")


def _kek(phrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(phrase.encode())


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _inner(ring: Keyring) -> Dict[str, Any]:
    return {
        "activa": ring.active,
        "claves": [
            {"kid": k["kid"], "clave": _b64(k["key"]), "creada": k.get("creada", 0)}
            for k in ring.keys
        ],
    }


def _from_inner(data: Dict[str, Any]) -> Keyring:
    keys = []
    for k in data.get("claves", []):
        key = base64.b64decode(k["clave"])
        if len(key) != 32 or kid_of(key) != k["kid"]:
            raise SealError("el llavero está dañado")
        keys.append({"kid": k["kid"], "key": key, "creada": k.get("creada", 0)})
    if not keys:
        raise SealError("el llavero está vacío")
    active = data.get("activa") or keys[-1]["kid"]
    return Keyring(keys=keys, active=active)


def _write(path: Path, ring: Keyring, phrase: str = "") -> None:
    """Writes the keyring atomically (0600), wrapped if there is a phrase."""
    body: Dict[str, Any] = {"formato": FORMAT}
    inner = json.dumps(_inner(ring)).encode()
    if phrase:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        kek = _kek(phrase, salt, **SCRYPT)
        body["envuelta"] = {
            "kdf": "scrypt",
            **SCRYPT,
            "sal": _b64(salt),
            "nonce": _b64(nonce),
            "datos": _b64(AESGCM(kek).encrypt(nonce, inner, FORMAT.encode())),
        }
    else:
        body.update(_inner(ring))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(body, fh)
    os.replace(tmp, path)


def _read(path: Path, phrase: str) -> Keyring:
    raw = path.read_bytes().strip()
    if not raw.startswith(b"{"):  # the single key of before
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise SealError("la clave maestra está dañada")
        kid = kid_of(key)
        return Keyring(keys=[{"kid": kid, "key": key, "creada": 0}], active=kid)
    data = json.loads(raw)
    wrapped = data.get("envuelta")
    if not wrapped:
        return _from_inner(data)
    if not phrase:
        raise SealError(
            "el llavero está protegido con frase: falta SERGIO_FRASE_MAESTRA"
        )
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    kek = _kek(
        phrase,
        base64.b64decode(wrapped["sal"]),
        int(wrapped["n"]),
        int(wrapped["r"]),
        int(wrapped["p"]),
    )
    try:
        inner = AESGCM(kek).decrypt(
            base64.b64decode(wrapped["nonce"]),
            base64.b64decode(wrapped["datos"]),
            FORMAT.encode(),
        )
    except InvalidTag as exc:
        raise SealError("la frase no abre el llavero") from exc
    ring = _from_inner(json.loads(inner))
    ring.protected = True
    return ring


def keyring(home: Any = None) -> Keyring:
    raw = os.environ.get("SERGIO_CLAVE_MAESTRA", "").strip()
    if raw:
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise SealError("SERGIO_CLAVE_MAESTRA debe tener 32 bytes en base64")
        kid = kid_of(key)
        return Keyring([{"kid": kid, "key": key, "creada": 0}], kid, "entorno")
    path = _home(home) / "clave_maestra"
    cached = _CACHE.get(str(path))
    if cached:
        return cached
    with _LOCK:
        if not path.exists():
            key = secrets.token_bytes(32)
            ring = Keyring([{"kid": kid_of(key), "key": key, "creada": time.time()}])
            ring.active = ring.keys[0]["kid"]
            _write(path, ring, _phrase())
            ring.protected = bool(_phrase())
        else:
            ring = _read(path, _phrase())
        _CACHE[str(path)] = ring
        return ring


def _forget(home: Any = None) -> None:
    _CACHE.pop(str(_home(home) / "clave_maestra"), None)


def master_key(home: Any = None) -> bytes:
    """The active key (kept for callers of before the keyring)."""
    ring = keyring(home)
    return ring.key(ring.active)


def _derive(purpose: str, key: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    tag = (purpose, hashlib.sha256(key).digest())
    cached = _DERIVED.get(tag)
    if cached is None:
        cached = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"sergio-pagos",
            info=purpose.encode(),
        ).derive(key)
        _DERIVED[tag] = cached
    return cached


def is_sealed(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIXES)


def seal(text: str, aad: str = "", home: Any = None, purpose: str = "cifrar") -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ring = keyring(home)
    nonce = secrets.token_bytes(12)
    box = AESGCM(_derive(purpose, ring.key(ring.active))).encrypt(
        nonce, text.encode(), aad.encode()
    )
    return f"{PREFIX2}{ring.active}:" + base64.urlsafe_b64encode(nonce + box).decode()


def _open(blob: bytes, key: bytes, aad: str, purpose: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return (
        AESGCM(_derive(purpose, key))
        .decrypt(blob[:12], blob[12:], aad.encode())
        .decode()
    )


def unseal(token: str, aad: str = "", home: Any = None, purpose: str = "cifrar") -> str:
    from cryptography.exceptions import InvalidTag

    ring = keyring(home)
    try:
        if token.startswith(PREFIX2):
            kid, _, body = token[len(PREFIX2) :].partition(":")
            return _open(base64.urlsafe_b64decode(body), ring.key(kid), aad, purpose)
        if token.startswith(PREFIX):
            blob = base64.urlsafe_b64decode(token[len(PREFIX) :])
            for k in ring.keys:  # sealed before versions: the original key
                try:
                    return _open(blob, k["key"], aad, purpose)
                except InvalidTag:
                    continue
            raise InvalidTag()
    except InvalidTag as exc:
        raise SealError("no se puede abrir: otra clave o datos alterados") from exc
    raise SealError("no está cifrado")


def needs_reseal(token: str, home: Any = None) -> bool:
    """True when a sealed value is not under the active key (after a rotation)."""
    ring = keyring(home)
    return not token.startswith(f"{PREFIX2}{ring.active}:")


def sign(text: str, home: Any = None) -> str:
    # always the first key: the ledger chain stays verifiable after a rotation
    return hmac.new(
        _derive("libro", keyring(home).first), text.encode(), hashlib.sha256
    ).hexdigest()


def same(a: str, b: Optional[str]) -> bool:
    return bool(b) and hmac.compare_digest(a, b or "")


# -- managing the keyring (``sergio boveda``) ------------------------------------


def _own_file(home: Any) -> Path:
    if os.environ.get("SERGIO_CLAVE_MAESTRA", "").strip():
        raise SealError(
            "la clave viene de SERGIO_CLAVE_MAESTRA: se cambia en el gestor de secretos"
        )
    path = _home(home) / "clave_maestra"
    keyring(home)  # created if missing, and readable with the current phrase
    return path


def rotate(home: Any = None) -> str:
    """A new active key; the older ones stay to open what they sealed."""
    path = _own_file(home)
    with _LOCK:
        ring = _read(path, _phrase())
        key = secrets.token_bytes(32)
        ring.keys.append({"kid": kid_of(key), "key": key, "creada": time.time()})
        ring.active = ring.keys[-1]["kid"]
        _write(path, ring, _phrase() if ring.protected else "")
        _forget(home)
    return ring.active


def protect(phrase: str, home: Any = None) -> None:
    """Encrypts the keyring with a passphrase (the server then needs it)."""
    if len(phrase) < MIN_PHRASE:
        raise SealError(f"la frase debe tener al menos {MIN_PHRASE} caracteres")
    path = _own_file(home)
    with _LOCK:
        ring = _read(path, _phrase())
        _write(path, ring, phrase)
        _forget(home)


def unprotect(phrase: str, home: Any = None) -> None:
    path = _own_file(home)
    with _LOCK:
        ring = _read(path, phrase)
        _write(path, ring, "")
        _forget(home)


def status(home: Any = None) -> Dict[str, Any]:
    ring = keyring(home)
    return {
        "algoritmo": "AES-256-GCM, una clave por propósito (HKDF-SHA256)",
        "origen": ring.source,
        "protegida_con_frase": ring.protected,
        "activa": ring.active,
        "claves": [{"id": k["kid"], "creada": k.get("creada", 0)} for k in ring.keys],
    }


__all__ = [
    "PREFIX",
    "PREFIX2",
    "SealError",
    "is_sealed",
    "keyring",
    "master_key",
    "needs_reseal",
    "protect",
    "rotate",
    "same",
    "seal",
    "sign",
    "status",
    "unprotect",
    "unseal",
]
