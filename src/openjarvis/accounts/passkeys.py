"""Sign in with the face (or fingerprint) of the device itself: passkeys.

The phone's Face ID, the Mac's Touch ID, Windows Hello: the browser asks the
device to check the person (``userVerification: required``) and signs a fresh
challenge with a key that never leaves it. Sergio keeps only the public key.
That is the device's own biometric security, plus what a password never has:
the signature is bound to this site's address, so a fake page cannot use it,
and a cloned key shows up in the signature counter.

Only what WebAuthn needs is here: a small CBOR reader, the authenticator data,
and ES256 / RS256 / EdDSA signatures checked with ``cryptography``. Attestation
is ``none`` (the device is trusted to be a device; the person is checked by it).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import struct
import threading
import time
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

CHALLENGE_SECONDS = 120
ALGS = (-7, -8, -257)  # ES256, EdDSA, RS256

FLAG_UP = 0x01  # the person was present
FLAG_UV = 0x04  # the device verified them (face, finger, PIN)
FLAG_AT = 0x40  # credential data follows


class PasskeyError(ValueError):
    """The passkey could not be accepted (the message is safe to show)."""


# -- base64url ----------------------------------------------------------------
def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise PasskeyError("Datos de la llave dañados.") from exc


# -- CBOR (only what authenticators send) -----------------------------------------
def cbor(data: bytes, at: int = 0) -> Tuple[Any, int]:
    """Decode one CBOR item at *at*; returns (value, next offset)."""
    if at >= len(data):
        raise PasskeyError("Datos de la llave incompletos.")
    first = data[at]
    major, info = first >> 5, first & 0x1F
    at += 1
    if info < 24:
        arg = info
    elif info in (24, 25, 26, 27):
        size = 1 << (info - 24)
        if at + size > len(data):
            raise PasskeyError("Datos de la llave incompletos.")
        arg = int.from_bytes(data[at : at + size], "big")
        at += size
    else:
        raise PasskeyError("Formato de llave no admitido.")
    if major == 0:
        return arg, at
    if major == 1:
        return -1 - arg, at
    if major in (2, 3):
        if at + arg > len(data):
            raise PasskeyError("Datos de la llave incompletos.")
        raw = data[at : at + arg]
        return (raw if major == 2 else raw.decode("utf-8")), at + arg
    if major == 4:
        items = []
        for _ in range(arg):
            item, at = cbor(data, at)
            items.append(item)
        return items, at
    if major == 5:
        out: Dict[Any, Any] = {}
        for _ in range(arg):
            key, at = cbor(data, at)
            out[key], at = cbor(data, at)
        return out, at
    if major == 7 and info in (20, 21, 22):
        return {20: False, 21: True, 22: None}[info], at
    raise PasskeyError("Formato de llave no admitido.")


# -- authenticator data -----------------------------------------------------------
def auth_data(raw: bytes) -> Dict[str, Any]:
    if len(raw) < 37:
        raise PasskeyError("Datos de la llave incompletos.")
    out: Dict[str, Any] = {
        "rp_hash": raw[:32],
        "flags": raw[32],
        "count": struct.unpack(">I", raw[33:37])[0],
    }
    if out["flags"] & FLAG_AT:
        if len(raw) < 55:
            raise PasskeyError("Datos de la llave incompletos.")
        length = struct.unpack(">H", raw[53:55])[0]
        out["cred_id"] = raw[55 : 55 + length]
        out["cose"], _ = cbor(raw, 55 + length)
    return out


def public_key(cose: Dict[int, Any]) -> Tuple[Any, int]:
    """A COSE key → (cryptography public key, algorithm)."""
    kty, alg = cose.get(1), cose.get(3)
    if kty == 2 and alg == -7 and cose.get(-1) == 1:  # EC2, ES256, P-256
        x, y = cose.get(-2), cose.get(-3)
        if not (
            isinstance(x, bytes) and isinstance(y, bytes) and len(x) == len(y) == 32
        ):
            raise PasskeyError("Llave EC no válida.")
        point = b"\x04" + x + y
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point), -7
    if kty == 3 and alg == -257:  # RSA, RS256 (older Windows Hello)
        n, e = cose.get(-1), cose.get(-2)
        if not (isinstance(n, bytes) and isinstance(e, bytes)):
            raise PasskeyError("Llave RSA no válida.")
        numbers = rsa.RSAPublicNumbers(
            int.from_bytes(e, "big"), int.from_bytes(n, "big")
        )
        return numbers.public_key(), -257
    if kty == 1 and alg == -8 and cose.get(-1) == 6:  # OKP, EdDSA, Ed25519
        x = cose.get(-2)
        if not (isinstance(x, bytes) and len(x) == 32):
            raise PasskeyError("Llave Ed25519 no válida.")
        return ed25519.Ed25519PublicKey.from_public_bytes(x), -8
    raise PasskeyError("Este tipo de llave no se admite.")


def pem(key: Any) -> str:
    return key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def _check_signature(key_pem: str, alg: int, signature: bytes, signed: bytes) -> None:
    key = serialization.load_pem_public_key(key_pem.encode())
    try:
        if alg == -7 and isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(signature, signed, ec.ECDSA(hashes.SHA256()))
        elif alg == -257 and isinstance(key, rsa.RSAPublicKey):
            key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
        elif alg == -8 and isinstance(key, ed25519.Ed25519PublicKey):
            key.verify(signature, signed)
        else:
            raise PasskeyError("Tipo de llave inesperado.")
    except PasskeyError:
        raise
    except Exception as exc:  # noqa: BLE001 — InvalidSignature and malformed input alike
        raise PasskeyError("La firma de la llave no coincide.") from exc


# -- challenges (one use, two minutes) -----------------------------------------------
_challenges: Dict[str, Tuple[str, str, float]] = {}
_lock = threading.Lock()


def new_challenge(purpose: str, user: str = "") -> str:
    value = b64u(secrets.token_bytes(32))
    now = time.time()
    with _lock:
        for key in [k for k, (_, _, t) in _challenges.items() if t < now]:
            _challenges.pop(key, None)
        _challenges[value] = (purpose, user, now + CHALLENGE_SECONDS)
    return value


def take_challenge(value: str, purpose: str) -> str:
    """Use a challenge once; returns the user it was made for ('' for sign-in)."""
    with _lock:
        found = _challenges.pop(value, None)
    if not found or found[0] != purpose or found[2] < time.time():
        raise PasskeyError("La solicitud caducó. Inténtelo otra vez.")
    return found[1]


def _client_data(raw: bytes, kind: str, origin: str, purpose: str) -> str:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PasskeyError("Datos del navegador dañados.") from exc
    if data.get("type") != kind:
        raise PasskeyError("Tipo de solicitud inesperado.")
    if data.get("origin") != origin:
        raise PasskeyError("La llave se pidió desde otra dirección.")
    return take_challenge(str(data.get("challenge", "")), purpose)


def _flags_ok(parsed: Dict[str, Any], rp_id: str) -> None:
    if parsed["rp_hash"] != hashlib.sha256(rp_id.encode()).digest():
        raise PasskeyError("La llave es de otro sitio.")
    if not parsed["flags"] & FLAG_UP:
        raise PasskeyError("No se confirmó la presencia.")
    if not parsed["flags"] & FLAG_UV:
        raise PasskeyError(
            "El dispositivo no verificó a la persona (cara, huella o PIN)."
        )


def verify_registration(
    *, client_data: str, attestation: str, origin: str, rp_id: str
) -> Dict[str, Any]:
    """A new passkey → {user, id, public, alg, count} (raises PasskeyError)."""
    user = _client_data(unb64u(client_data), "webauthn.create", origin, "registro")
    obj, _ = cbor(unb64u(attestation))
    if not isinstance(obj, dict) or not isinstance(obj.get("authData"), bytes):
        raise PasskeyError("Datos de la llave dañados.")
    parsed = auth_data(obj["authData"])
    _flags_ok(parsed, rp_id)
    if "cose" not in parsed or not isinstance(parsed["cose"], dict):
        raise PasskeyError("La llave no trae su clave pública.")
    key, alg = public_key(parsed["cose"])
    return {
        "user": user,
        "id": b64u(parsed["cred_id"]),
        "public": pem(key),
        "alg": alg,
        "count": parsed["count"],
    }


def verify_assertion(
    *,
    stored: Dict[str, Any],
    client_data: str,
    authenticator_data: str,
    signature: str,
    origin: str,
    rp_id: str,
) -> int:
    """Check a sign-in with a stored passkey; returns the new signature counter."""
    raw_client = unb64u(client_data)
    _client_data(raw_client, "webauthn.get", origin, "entrar")
    raw_auth = unb64u(authenticator_data)
    parsed = auth_data(raw_auth)
    _flags_ok(parsed, rp_id)
    _check_signature(
        stored["public"],
        int(stored["alg"]),
        unb64u(signature),
        raw_auth + hashlib.sha256(raw_client).digest(),
    )
    old, new = int(stored.get("count") or 0), parsed["count"]
    if (old or new) and new <= old:
        raise PasskeyError("Esta llave parece copiada: la bloqueé por seguridad.")
    return new


def rp_from_origin(origin: str, host: str) -> Optional[str]:
    """The site id for an Origin header, only if it is this server's own address."""
    from urllib.parse import urlparse

    parsed = urlparse(origin or "")
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        return None
    if parsed.scheme == "http" and parsed.hostname != "localhost":
        return None  # browsers allow passkeys only on https or localhost (never an IP)
    own = (host or "").rsplit(":", 1)[0].strip("[]").lower()
    if parsed.hostname.lower() != own:
        return None
    return parsed.hostname.lower()


__all__ = [
    "PasskeyError",
    "auth_data",
    "b64u",
    "cbor",
    "new_challenge",
    "public_key",
    "rp_from_origin",
    "take_challenge",
    "unb64u",
    "verify_assertion",
    "verify_registration",
]
