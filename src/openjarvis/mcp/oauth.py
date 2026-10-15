"""Signing in to a remote MCP server, as the MCP authorization spec asks.

The flow a remote connector (Notion, Linear, Higgsfield…) expects:

1. ``discover(url)`` — call the server without a token; a protected one
   answers 401 with ``WWW-Authenticate: Bearer resource_metadata="…"``.
   Read that Protected Resource Metadata (RFC 9728), then the authorization
   server's metadata (RFC 8414, or OpenID discovery). Servers from before
   2025-06 that publish no resource metadata get the 2025-03 fallback
   (metadata or ``/authorize``, ``/token``, ``/register`` on the origin).
2. ``register(...)`` — dynamic client registration (RFC 7591) as «Sergio»,
   unless the owner typed a client ID of their own (Advanced settings).
3. ``start(...)`` — PKCE S256 + state + the RFC 8707 ``resource``; the
   owner signs in on the service's own page in the browser.
4. ``finish(...)`` — the browser comes back to Sergio with ``code``; it is
   exchanged for tokens. ``refresh(...)`` renews them before they expire.

Everything takes an ``httpx.Client`` so tests can drive a real server.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse

PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "Sergio"


class OAuthError(RuntimeError):
    """Signing in could not be completed; the message is for the owner."""


@dataclass
class AuthServer:
    """What a protected MCP server needs to sign in."""

    resource: str
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str = ""
    scopes: List[str] = field(default_factory=list)
    code_challenge_methods: List[str] = field(default_factory=list)
    token_auth_methods: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthServer":
        fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**fields)


@dataclass
class Tokens:
    access_token: str
    token_type: str = "Bearer"
    refresh_token: str = ""
    expires_at: float = 0.0  # 0 = unknown / does not expire
    scope: str = ""

    def expired(self, margin: float = 60.0) -> bool:
        return bool(self.expires_at) and time.time() > self.expires_at - margin

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_response(
        cls, data: Dict[str, Any], old: Optional["Tokens"] = None
    ) -> "Tokens":
        token = str(data.get("access_token") or "")
        if not token:
            raise OAuthError("El servicio no devolvió un token de acceso.")
        expires = data.get("expires_in")
        return cls(
            access_token=token,
            token_type=str(data.get("token_type") or "Bearer"),
            # A refresh response may omit the refresh token: keep the old one.
            refresh_token=str(
                data.get("refresh_token") or (old.refresh_token if old else "")
            ),
            expires_at=time.time() + float(expires) if expires else 0.0,
            scope=str(data.get("scope") or (old.scope if old else "")),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Tokens":
        fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**fields)


# -- discovery --------------------------------------------------------------
_PARAM = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|([^\s,]+))')


def parse_www_authenticate(header: str) -> Dict[str, str]:
    """``Bearer resource_metadata="…", scope="a b"`` → ``{"resource_metadata": …}``."""
    if not header:
        return {}
    body = header.split(" ", 1)[1] if header.lower().startswith("bearer") else header
    return {
        m.group(1): m.group(2) if m.group(2) is not None else m.group(3)
        for m in _PARAM.finditer(body)
    }


def _origin(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"


def _well_known(url: str, name: str) -> List[str]:
    """RFC 8414 path insertion first, then the root (what servers really use)."""
    parts = urlparse(url)
    path = parts.path.rstrip("/")
    base = f"{parts.scheme}://{parts.netloc}/.well-known/{name}"
    return [base + path, base] if path else [base]


def probe(http: Any, url: str) -> Optional[Dict[str, str]]:
    """``None`` when the server answers without a token; else the challenge."""
    body = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME, "version": "1"},
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    try:
        response = http.post(url, json=body, headers=headers)
    except Exception as exc:  # noqa: BLE001 - the message goes to the owner
        raise OAuthError(f"No pude llegar al servidor: {exc}") from exc
    if response.status_code in (401, 403):
        return parse_www_authenticate(response.headers.get("www-authenticate", ""))
    if response.status_code == 405 and url.rstrip("/").endswith("/sse"):
        return None  # an old SSE endpoint: GET only; no token needed to try
    if response.status_code >= 400:
        raise OAuthError(f"El servidor respondió {response.status_code}.")
    return None


def _get_json(http: Any, url: str) -> Optional[Dict[str, Any]]:
    try:
        response = http.get(
            url,
            headers={
                "Accept": "application/json",
                "MCP-Protocol-Version": PROTOCOL_VERSION,
            },
        )
    except Exception:  # noqa: BLE001 - try the next candidate
        return None
    if response.status_code != 200:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def discover(
    http: Any, url: str, challenge: Optional[Dict[str, str]] = None
) -> AuthServer:
    """Where and how to sign in for the MCP server at *url*."""
    challenge = challenge if challenge is not None else (probe(http, url) or {})
    resource_meta: Optional[Dict[str, Any]] = None
    candidates = (
        [challenge["resource_metadata"]] if challenge.get("resource_metadata") else []
    )
    candidates += _well_known(url, "oauth-protected-resource")
    for candidate in candidates:
        resource_meta = _get_json(http, candidate)
        if resource_meta and resource_meta.get("authorization_servers"):
            break
        resource_meta = None

    issuer = str((resource_meta or {}).get("authorization_servers", [_origin(url)])[0])
    resource = str((resource_meta or {}).get("resource") or url)
    auth_meta: Optional[Dict[str, Any]] = None
    for candidate in _well_known(issuer, "oauth-authorization-server") + _well_known(
        issuer, "openid-configuration"
    ):
        auth_meta = _get_json(http, candidate)
        if auth_meta and auth_meta.get("authorization_endpoint"):
            break
        auth_meta = None
    if auth_meta is None:
        # 2025-03-26 fallback: the default endpoints on the server's origin.
        origin = _origin(issuer)
        auth_meta = {
            "issuer": origin,
            "authorization_endpoint": f"{origin}/authorize",
            "token_endpoint": f"{origin}/token",
            "registration_endpoint": f"{origin}/register",
        }
    scopes = challenge.get("scope", "").split() or list(
        (resource_meta or {}).get("scopes_supported") or []
    )
    methods = list(auth_meta.get("code_challenge_methods_supported") or [])
    if methods and "S256" not in methods:
        raise OAuthError(
            "El servicio no admite PKCE con S256; no es seguro conectarse."
        )
    return AuthServer(
        resource=resource,
        issuer=str(auth_meta.get("issuer") or issuer),
        authorization_endpoint=str(auth_meta["authorization_endpoint"]),
        token_endpoint=str(auth_meta["token_endpoint"]),
        registration_endpoint=str(auth_meta.get("registration_endpoint") or ""),
        scopes=[str(s) for s in scopes],
        code_challenge_methods=methods,
        token_auth_methods=list(
            auth_meta.get("token_endpoint_auth_methods_supported") or []
        ),
    )


# -- registration -----------------------------------------------------------
def register(http: Any, server: AuthServer, redirect_uri: str) -> Dict[str, str]:
    """Dynamic client registration: Sergio introduces itself to the service."""
    if not server.registration_endpoint:
        raise OAuthError(
            "Este servicio no permite registrarse solo: añada un Client ID (y su secreto, si lo tiene) "
            "en «Opciones avanzadas»."
        )
    body = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if server.scopes:
        body["scope"] = " ".join(server.scopes)
    response = http.post(
        server.registration_endpoint, json=body, headers={"Accept": "application/json"}
    )
    if response.status_code not in (200, 201):
        raise OAuthError(
            f"El servicio no aceptó a Sergio como cliente ({response.status_code})."
        )
    data = response.json()
    if not data.get("client_id"):
        raise OAuthError("El registro no devolvió un Client ID.")
    return {
        "client_id": str(data["client_id"]),
        "client_secret": str(data.get("client_secret") or ""),
    }


# -- authorization ----------------------------------------------------------
def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


@dataclass
class Pending:
    """A sign-in in progress: what ``finish`` needs when the browser returns."""

    state: str
    verifier: str
    redirect_uri: str
    server_id: str
    created: float = field(default_factory=time.time)


def authorize_url(
    server: AuthServer, client_id: str, redirect_uri: str, server_id: str
) -> tuple[str, Pending]:
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": server.resource,
    }
    if server.scopes:
        query["scope"] = " ".join(server.scopes)
    sep = "&" if "?" in server.authorization_endpoint else "?"
    return f"{server.authorization_endpoint}{sep}{urlencode(query)}", Pending(
        state, verifier, redirect_uri, server_id
    )


def _token_request(
    http: Any, server: AuthServer, client: Dict[str, str], form: Dict[str, str]
) -> Dict[str, Any]:
    form = {**form, "client_id": client["client_id"], "resource": server.resource}
    auth = None
    if client.get("client_secret"):
        if (
            "client_secret_basic" in server.token_auth_methods
            and "client_secret_post" not in server.token_auth_methods
        ):
            auth = (client["client_id"], client["client_secret"])
        else:
            form["client_secret"] = client["client_secret"]
    response = http.post(
        server.token_endpoint,
        data=form,
        auth=auth,
        headers={"Accept": "application/json"},
    )
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code != 200:
        why = data.get("error_description") or data.get("error") or response.status_code
        raise OAuthError(f"El servicio rechazó el inicio de sesión: {why}.")
    return data


def exchange(
    http: Any, server: AuthServer, client: Dict[str, str], pending: Pending, code: str
) -> Tokens:
    data = _token_request(
        http,
        server,
        client,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending.redirect_uri,
            "code_verifier": pending.verifier,
        },
    )
    return Tokens.from_response(data)


def refresh(
    http: Any, server: AuthServer, client: Dict[str, str], tokens: Tokens
) -> Tokens:
    if not tokens.refresh_token:
        raise OAuthError("La sesión caducó: vuelva a conectar.")
    data = _token_request(
        http,
        server,
        client,
        {"grant_type": "refresh_token", "refresh_token": tokens.refresh_token},
    )
    return Tokens.from_response(data, old=tokens)


__all__ = [
    "AuthServer",
    "OAuthError",
    "Pending",
    "Tokens",
    "authorize_url",
    "discover",
    "exchange",
    "parse_www_authenticate",
    "pkce_pair",
    "probe",
    "refresh",
    "register",
]
