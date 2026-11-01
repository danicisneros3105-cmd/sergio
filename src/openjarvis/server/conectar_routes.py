"""Conectar la IA con un clic (OpenRouter, OAuth PKCE): sin copiar ni pegar claves.

The owner (2 Nov 2026): «aún sigue con configuración manual de API». OpenRouter
lets an app ask for a key with its own sign-in page (PKCE): the owner taps
«Conectar», signs in at openrouter.ai and approves; OpenRouter sends back a
one-time code that Sergio swaps for the key and saves where every key lives
(``cloud-keys.env``, 0600; never in a log). One key gives every model there.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any, Dict
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/v1/conectar", tags=["conectar"])

AUTH = "https://openrouter.ai/auth"
EXCHANGE = "https://openrouter.ai/api/v1/auth/keys"
TTL = 15 * 60
_PENDING: Dict[str, Dict[str, Any]] = {}  # state -> verifier, when, where to go back


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _local(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in ("127.0.0.1", "::1", "localhost", "testclient")


@router.get("/openrouter")
def start(request: Request, vuelta: str = "/") -> Dict[str, str]:
    """The sign-in page to open (only from this computer)."""
    if not _local(request):
        raise HTTPException(403, "Conecte la IA desde el propio equipo de Sergio.")
    now = time.time()
    for k in [k for k, v in _PENDING.items() if now - v["when"] > TTL]:
        _PENDING.pop(k, None)
    state = secrets.token_urlsafe(18)
    verifier = secrets.token_urlsafe(48)
    back = vuelta if vuelta.startswith("/") and not vuelta.startswith("//") else "/"
    _PENDING[state] = {"verifier": verifier, "when": now, "back": back}
    callback = (
        str(request.base_url).rstrip("/")
        + f"/v1/conectar/openrouter/vuelta?state={state}"
    )
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    url = (
        AUTH
        + "?"
        + urlencode(
            {
                "callback_url": callback,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )
    return {"url": url}


def exchange(code: str, verifier: str, http: Any = None) -> str:
    import httpx

    client = http or httpx.Client(timeout=30)
    r = client.post(
        EXCHANGE,
        json={"code": code, "code_verifier": verifier, "code_challenge_method": "S256"},
    )
    r.raise_for_status()
    key = str((r.json() or {}).get("key") or "")
    if not key.startswith("sk-"):
        raise RuntimeError("OpenRouter no devolvió una clave.")
    return key


@router.get("/openrouter/vuelta")
def back(request: Request, state: str = "", code: str = "") -> RedirectResponse:
    """OpenRouter sends the browser here with the one-time code."""
    pending = _PENDING.pop(state, None)
    if not pending or not code or time.time() - pending["when"] > TTL:
        return RedirectResponse("/?ia=caducado", status_code=303)
    try:
        key = exchange(code, pending["verifier"])
    except Exception:  # noqa: BLE001 — never the code or the key in a log
        return RedirectResponse(f"{pending['back']}?ia=error", status_code=303)
    from openjarvis.accounts.autoconfig import _save_env

    _save_env("OPENROUTER_API_KEY", key)
    try:  # the model list and the engines see the new key at once
        from openjarvis.server.cloud_router import _load_keys

        _load_keys()
    except Exception:  # noqa: BLE001
        pass
    sep = "&" if "?" in pending["back"] else "?"
    return RedirectResponse(f"{pending['back']}{sep}ia=conectada", status_code=303)


__all__ = ["exchange", "router"]
