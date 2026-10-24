"""Passwords, codes and tokens: nothing secret is stored as written."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Tuple

SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
MIN_PASSWORD = 10
_COMMON = frozenset(
    """
123456 123456789 12345678 password qwerty 111111 123123 1234567890 1234567 qwerty123
000000 1q2w3e abc123 password1 iloveyou 123321 654321 qwertyuiop 123qwe contraseña
contrasena teamo 12345678910 superman dragon monkey letmein football admin welcome
""".split()
)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${key.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        kind, salt, key = stored.split("$")
    except ValueError:
        return False
    if kind != "scrypt":
        return False
    got = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), **SCRYPT)
    return hmac.compare_digest(got.hex(), key)


def password_problem(password: str, email: str = "") -> str:
    """Why a password is not good enough ('' when it is)."""
    p = password or ""
    if len(p) < MIN_PASSWORD:
        return f"Use al menos {MIN_PASSWORD} caracteres."
    if p.lower() in _COMMON or len(set(p)) < 4:
        return "Esa contraseña es de las más usadas; elija otra."
    local = (email or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in p.lower():
        return "No use su correo dentro de la contraseña."
    return ""


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def digest(value: str, pepper: str) -> str:
    """Keyed hash for codes and session tokens (the raw value is never kept)."""
    return hmac.new(
        pepper.encode("utf-8"), value.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def new_token() -> Tuple[str, str]:
    """(the token given to the browser, a short visible id)."""
    raw = "sg_" + secrets.token_urlsafe(32)
    return raw, raw[3:11]


__all__ = [
    "MIN_PASSWORD",
    "check_password",
    "digest",
    "hash_password",
    "new_code",
    "new_token",
    "password_problem",
]
