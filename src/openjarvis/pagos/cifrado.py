"""Sergio's master key: AES-256-GCM for secrets at rest, HMAC for the ledger.

One 32-byte key per computer. It comes from ``SERGIO_CLAVE_MAESTRA`` (base64,
for a server whose disk should not hold it) or from
``~/.openjarvis/clave_maestra`` (created on first use, 0600). From it two
independent keys are derived (HKDF-SHA256): one encrypts the customers' AI
sub-keys, the other signs each line of the ledger so a line changed or removed
by hand is detected (:func:`openjarvis.pagos.ledger.verify`).

A sealed value is ``v1:`` + base64(nonce ‖ ciphertext ‖ tag) and is tied to
what it belongs to (``aad``, e.g. the customer's id): a sealed key copied to
another customer does not open. Losing the master key loses only what it
sealed (the sub-keys are recreated at OpenRouter); never commit or share it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, Optional

PREFIX = "v1:"
_LOCK = threading.Lock()
_CACHE: Dict[str, bytes] = {}


class SealError(ValueError):
    pass


def _home(home: Any = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = get_config_dir()
    return Path(home)


def master_key(home: Any = None) -> bytes:
    raw = os.environ.get("SERGIO_CLAVE_MAESTRA", "").strip()
    if raw:
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise SealError("SERGIO_CLAVE_MAESTRA debe tener 32 bytes en base64")
        return key
    path = _home(home) / "clave_maestra"
    cached = _CACHE.get(str(path))
    if cached:
        return cached
    with _LOCK:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(base64.b64encode(secrets.token_bytes(32)))
        key = base64.b64decode(path.read_bytes().strip())
        if len(key) != 32:
            raise SealError("la clave maestra está dañada")
        _CACHE[str(path)] = key
        return key


_DERIVED: Dict[tuple, bytes] = {}


def _derive(purpose: str, home: Any = None) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    master = master_key(home)
    key = (purpose, hashlib.sha256(master).digest())  # one derivation per key
    cached = _DERIVED.get(key)
    if cached is None:
        cached = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"sergio-pagos",
            info=purpose.encode(),
        ).derive(master)
        _DERIVED[key] = cached
    return cached


def seal(text: str, aad: str = "", home: Any = None, purpose: str = "cifrar") -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    box = AESGCM(_derive(purpose, home)).encrypt(nonce, text.encode(), aad.encode())
    return PREFIX + base64.urlsafe_b64encode(nonce + box).decode()


def unseal(token: str, aad: str = "", home: Any = None, purpose: str = "cifrar") -> str:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not token.startswith(PREFIX):
        raise SealError("no está cifrado")
    blob = base64.urlsafe_b64decode(token[len(PREFIX) :])
    try:
        out = AESGCM(_derive(purpose, home)).decrypt(blob[:12], blob[12:], aad.encode())
    except InvalidTag as exc:
        raise SealError("no se puede abrir: otra clave o datos alterados") from exc
    return out.decode()


def sign(text: str, home: Any = None) -> str:
    return hmac.new(_derive("libro", home), text.encode(), hashlib.sha256).hexdigest()


def same(a: str, b: Optional[str]) -> bool:
    return bool(b) and hmac.compare_digest(a, b or "")


__all__ = ["SealError", "master_key", "same", "seal", "sign", "unseal"]
