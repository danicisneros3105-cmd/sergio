"""Passphrase encryption in the `age <https://age-encryption.org>`_ v1 format.

Files written here can be opened with the standard ``age -d`` tool (and
the other way round), so a backup never depends on Sergio being around to
read it. Only the passphrase recipient (``scrypt``) is implemented: the
passphrase is stretched with scrypt (N = 2^18 by default), wraps a random
16-byte file key, and the payload is ChaCha20-Poly1305 in 64 KiB chunks
(age's STREAM construction). Nothing about the content, not even its
size beyond the chunk count, is visible without the passphrase.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
from typing import BinaryIO, Iterator, List, Optional

INTRO = b"age-encryption.org/v1\n"
SCRYPT_LABEL = b"age-encryption.org/v1/scrypt"
CHUNK = 64 * 1024
TAG = 16
DEFAULT_WORK = 18  # log2(N): age's default; ~1 s and 256 MiB on a laptop
MAX_WORK = 22


class AgeError(ValueError):
    """Wrong passphrase, damaged file or not an age file."""


def _aead(key: bytes):  # noqa: ANN202
    try:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    except ImportError as exc:  # pragma: no cover - cryptography is a dependency
        raise RuntimeError(
            "Falta la librería 'cryptography' (pip install cryptography)"
        ) from exc
    return ChaCha20Poly1305(key)


def _b64(data: bytes) -> bytes:
    return base64.b64encode(data).rstrip(b"=")


def _unb64(text: bytes) -> bytes:
    if b"=" in text or b"\r" in text:
        raise AgeError("cabecera age inválida")
    return base64.b64decode(text + b"=" * (-len(text) % 4), validate=True)


def _hkdf(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    prk = hmac.new(salt or b"\x00" * 32, ikm, hashlib.sha256).digest()
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _scrypt(passphrase: str, salt: bytes, work: int) -> bytes:
    n = 1 << work
    return hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=SCRYPT_LABEL + salt,
        n=n,
        r=8,
        p=1,
        maxmem=128 * 8 * n + (1 << 24),
        dklen=32,
    )


def _wrap_lines(data: bytes) -> bytes:
    text = _b64(data)
    lines = [text[i : i + 64] for i in range(0, len(text), 64)] or [b""]
    if len(lines[-1]) == 64:
        lines.append(b"")
    return b"\n".join(lines) + b"\n"


def _nonce(counter: int, last: bool) -> bytes:
    return counter.to_bytes(11, "big") + (b"\x01" if last else b"\x00")


def encrypt_stream(
    source: BinaryIO, target: BinaryIO, passphrase: str, *, work: int = DEFAULT_WORK
) -> None:
    """Encrypt everything read from *source* into *target*."""
    if not passphrase:
        raise AgeError("la frase de paso no puede estar vacía")
    file_key = os.urandom(16)
    salt = os.urandom(16)
    wrap_key = _scrypt(passphrase, salt, work)
    body = _aead(wrap_key).encrypt(b"\x00" * 12, file_key, None)
    header = INTRO + b"-> scrypt " + _b64(salt) + b" " + str(work).encode() + b"\n"
    header += _wrap_lines(body) + b"---"
    mac = hmac.new(_hkdf(file_key, b"", b"header"), header, hashlib.sha256).digest()
    target.write(header + b" " + _b64(mac) + b"\n")
    nonce = os.urandom(16)
    target.write(nonce)
    aead = _aead(_hkdf(file_key, nonce, b"payload"))
    counter = 0
    chunk = source.read(CHUNK)
    while True:
        following = source.read(CHUNK) if len(chunk) == CHUNK else b""
        last = not following
        target.write(aead.encrypt(_nonce(counter, last), chunk, None))
        if last:
            return
        counter += 1
        chunk = following


def _read_header(source: BinaryIO) -> tuple[bytes, List[List[bytes]], bytes]:
    """(header bytes up to '---', stanzas [[args…], body], mac)."""
    raw = b""
    lines: List[bytes] = []
    while True:
        line = source.readline(4096)
        if not line:
            raise AgeError("no es un archivo age (cabecera incompleta)")
        raw += line
        if line.startswith(b"--- "):
            mac_text = line[4:].rstrip(b"\n")
            break
        lines.append(line.rstrip(b"\n"))
        if len(raw) > 64 * 1024:
            raise AgeError("cabecera age demasiado grande")
    if not lines or lines[0] + b"\n" != INTRO:
        raise AgeError("no es un archivo age v1")
    stanzas: List[List[bytes]] = []
    i = 1
    while i < len(lines):
        if not lines[i].startswith(b"-> "):
            raise AgeError("cabecera age inválida")
        args = lines[i][3:].split(b" ")
        body = b""
        i += 1
        while i < len(lines):
            body += lines[i]
            short = len(lines[i]) < 64
            i += 1
            if short:
                break
        stanzas.append(args + [body])
    header = raw[: raw.rindex(b"--- ") + 3]
    return header, stanzas, _unb64(mac_text)


def decrypt_stream(source: BinaryIO, target: BinaryIO, passphrase: str) -> None:
    """Decrypt an age file protected by *passphrase* into *target*."""
    header, stanzas, mac = _read_header(source)
    scrypts = [s for s in stanzas if s[0] == b"scrypt"]
    if len(stanzas) != 1 or not scrypts:
        raise AgeError("este archivo age no está protegido solo con frase de paso")
    args = scrypts[0]
    if len(args) != 4:
        raise AgeError("cabecera scrypt inválida")
    salt, work = _unb64(args[1]), int(args[2])
    if len(salt) != 16 or not 1 <= work <= MAX_WORK:
        raise AgeError("parámetros scrypt fuera de rango")
    try:
        file_key = _aead(_scrypt(passphrase, salt, work)).decrypt(
            b"\x00" * 12, _unb64(args[3]), None
        )
    except Exception as exc:  # cryptography raises InvalidTag
        raise AgeError("frase de paso incorrecta") from exc
    expected = hmac.new(
        _hkdf(file_key, b"", b"header"), header, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected, mac):
        raise AgeError("la cabecera fue alterada")
    nonce = source.read(16)
    if len(nonce) != 16:
        raise AgeError("archivo age truncado")
    aead = _aead(_hkdf(file_key, nonce, b"payload"))
    counter = 0
    sealed = source.read(CHUNK + TAG)
    while True:
        following = source.read(CHUNK + TAG) if len(sealed) == CHUNK + TAG else b""
        last = not following
        try:
            plain = aead.decrypt(_nonce(counter, last), sealed, None)
        except Exception as exc:
            raise AgeError("el archivo está dañado o fue alterado") from exc
        if last and not plain and counter > 0:
            raise AgeError("bloque final vacío no permitido")
        target.write(plain)
        if last:
            return
        counter += 1
        sealed = following


def encrypt_bytes(data: bytes, passphrase: str, *, work: int = DEFAULT_WORK) -> bytes:
    out = io.BytesIO()
    encrypt_stream(io.BytesIO(data), out, passphrase, work=work)
    return out.getvalue()


def decrypt_bytes(data: bytes, passphrase: str) -> bytes:
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(data), out, passphrase)
    return out.getvalue()


def chunks(data: bytes, size: int = CHUNK) -> Iterator[bytes]:
    for i in range(0, len(data), size):
        yield data[i : i + size]


def is_age(head: Optional[bytes]) -> bool:
    return bool(head) and head.startswith(INTRO)


__all__ = [
    "AgeError",
    "DEFAULT_WORK",
    "decrypt_bytes",
    "decrypt_stream",
    "encrypt_bytes",
    "encrypt_stream",
    "is_age",
]
