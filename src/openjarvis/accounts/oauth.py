"""Sign in with Google, Microsoft or Apple (OpenID Connect + PKCE).

Each provider needs its client id (and secret) in ``~/.openjarvis/sergio.env``:
``SERGIO_GOOGLE_CLIENT_ID`` / ``_SECRET``, ``SERGIO_MICROSOFT_CLIENT_ID`` /
``_SECRET``, ``SERGIO_APPLE_CLIENT_ID`` / ``SERGIO_APPLE_CLIENT_SECRET`` (Apple's
secret is the signed JWT made from its key; it lasts up to six months). The
return address to register with the provider is
``<address of Sergio>/v1/cuentas/oauth/<provider>/vuelta``.

The id_token is checked like a bank would: signature against the provider's
published keys, audience, issuer, expiry and the nonce of this very sign-in.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode

STATE_TTL_S = 600


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    auth: str
    token: str
    jwks: str
    issuer: str  # a regex
    scope: str = "openid email profile"
    form_post: bool = False

    @property
    def client_id(self) -> str:
        return os.environ.get(f"SERGIO_{self.key.upper()}_CLIENT_ID", "")

    @property
    def client_secret(self) -> str:
        return os.environ.get(f"SERGIO_{self.key.upper()}_CLIENT_SECRET", "")

    @property
    def ready(self) -> bool:
        return bool(self.client_id and self.client_secret)


PROVIDERS: Dict[str, Provider] = {
    "google": Provider("google", "Google", "https://accounts.google.com/o/oauth2/v2/auth",
                       "https://oauth2.googleapis.com/token", "https://www.googleapis.com/oauth2/v3/certs",
                       r"^https://accounts\.google\.com$|^accounts\.google\.com$"),
    "microsoft": Provider("microsoft", "Microsoft",
                          "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                          "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                          "https://login.microsoftonline.com/common/discovery/v2.0/keys",
                          r"^https://login\.microsoftonline\.com/[0-9a-f\-]{36}/v2\.0$"),
    "apple": Provider("apple", "Apple", "https://appleid.apple.com/auth/authorize",
                      "https://appleid.apple.com/auth/token", "https://appleid.apple.com/auth/keys",
                      r"^https://appleid\.apple\.com$", scope="openid email name", form_post=True),
}  # fmt: skip

_pending: Dict[str, Dict[str, Any]] = {}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def start(key: str, redirect_uri: str, device: str = "") -> str:
    p = PROVIDERS[key]
    if not p.ready:
        raise RuntimeError(f"{p.label} no está configurado.")
    now = time.time()
    for k in [k for k, v in _pending.items() if now - v["at"] > STATE_TTL_S]:
        _pending.pop(k, None)
    state, nonce, verifier = (
        secrets.token_urlsafe(24),
        secrets.token_urlsafe(24),
        secrets.token_urlsafe(48),
    )
    _pending[state] = {"provider": key, "nonce": nonce, "verifier": verifier, "device": device[:64],
                       "redirect": redirect_uri, "at": now}  # fmt: skip
    params = {
        "client_id": p.client_id, "response_type": "code", "redirect_uri": redirect_uri, "scope": p.scope,
        "state": state, "nonce": nonce, "code_challenge_method": "S256",
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
    }  # fmt: skip
    if p.form_post:
        params["response_mode"] = "form_post"
    if key == "google":
        params["prompt"] = "select_account"
    return f"{p.auth}?{urlencode(params)}"


def finish(
    key: str, code: str, state: str, *, post=None, verify=None
) -> Dict[str, Any]:
    """Exchange the code and check the id_token. Returns the person's claims."""
    pend = _pending.pop(state or "", None)
    if not pend or pend["provider"] != key or time.time() - pend["at"] > STATE_TTL_S:
        raise ValueError(
            "El inicio de sesión caducó o no es de aquí; vuelva a intentarlo."
        )
    p = PROVIDERS[key]
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": pend["redirect"],
            "client_id": p.client_id, "client_secret": p.client_secret, "code_verifier": pend["verifier"]}  # fmt: skip
    if post is None:
        import httpx

        def post(url: str, form: dict) -> dict:
            with httpx.Client(timeout=20) as c:
                r = c.post(url, data=form, headers={"Accept": "application/json"})
                r.raise_for_status()
                return r.json()

    tokens = post(p.token, data)
    claims = (verify or verify_id_token)(p, str(tokens.get("id_token") or ""))
    if claims.get("nonce") != pend["nonce"]:
        raise ValueError("La respuesta no corresponde a este inicio de sesión.")
    email = str(claims.get("email") or "")
    verified = claims.get("email_verified") in (True, "true") or (
        key == "microsoft" and bool(email)
    )
    return {"subject": str(claims["sub"]), "email": email, "email_ok": bool(email and verified),
            "name": str(claims.get("name") or ""), "device": pend["device"]}  # fmt: skip


def verify_id_token(p: Provider, id_token: str) -> Dict[str, Any]:
    import jwt

    key = jwt.PyJWKClient(p.jwks).get_signing_key_from_jwt(id_token)
    claims = jwt.decode(id_token, key.key, algorithms=["RS256", "ES256"], audience=p.client_id,
                        options={"require": ["exp", "iat", "sub", "aud", "iss"]})  # fmt: skip
    if not re.match(p.issuer, str(claims.get("iss") or "")):
        raise ValueError("Emisor no válido.")
    return claims


def available() -> Dict[str, bool]:
    return {k: p.ready for k, p in PROVIDERS.items()}


def pending_state(state: str) -> Optional[Dict[str, Any]]:
    return _pending.get(state)


__all__ = ["PROVIDERS", "Provider", "available", "finish", "start", "verify_id_token"]
