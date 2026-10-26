"""Credits: more use today without changing plan (owner, 26 Oct 2026:
«comprar créditos»).

A credit is one message beyond the day's limit; bigger things cost more
(:data:`COST`). Credits are bought like plans: Sergio never asks for card
details — the pack opens the payment processor's page
(``SERGIO_CHECKOUT_CREDITOS_<PACK>``) and the seller sends back a signed code
that is pasted here. The code is signed with the same Ed25519 key as the
licenses (``tiers.py``) and each one counts once on this computer.

The packs and their prices live in :data:`PACKS` (the seller sets the margin
there); the page shows them in the person's currency, never below the dollar
price (``pricing.py``).
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openjarvis import tiers

PREFIX = "sergio-cred-v1"
# (id, credits, price in dollars) — change them here; the page follows.
PACKS: Tuple[Tuple[str, int, float], ...] = (
    ("c100", 100, 3.0),
    ("c300", 300, 8.0),
    ("c1000", 1000, 22.0),
)
# What one use beyond today's limit costs, in credits (quota.BASE_DAILY kinds).
COST: Dict[str, int] = {"mensajes": 1, "voz": 2, "nodes": 1, "swarm": 25, "cowork": 5}
_LOCK = threading.Lock()


def _path() -> Path:
    return (
        Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")
        / "creditos.json"
    )


def _load() -> Dict[str, Any]:
    try:
        data = json.loads(_path().read_text("utf-8"))
        if isinstance(data, dict):
            return {
                "saldo": int(data.get("saldo", 0)),
                "usados": list(data.get("usados") or []),
            }
    except (OSError, ValueError, TypeError):
        pass
    return {"saldo": 0, "usados": []}


def _save(data: Dict[str, Any]) -> None:
    tiers.write_private(_path(), json.dumps(data))


def balance() -> int:
    return _load()["saldo"]


def pack(pack_id: str) -> Optional[Tuple[str, int, float]]:
    return next((p for p in PACKS if p[0] == pack_id), None)


def checkout_url(pack_id: str) -> str:
    return os.environ.get(f"SERGIO_CHECKOUT_CREDITOS_{pack_id.upper()}", "").strip()


# -- the seller's side ----------------------------------------------------------


def issue(
    private_key_b64: str, credits: int, *, holder: str = "", now: Optional[float] = None
) -> str:
    """Sign a credit code (run by the seller after a payment)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if int(credits) <= 0:
        raise tiers.LicenseError("créditos inválidos")
    payload = {
        "creditos": int(credits),
        "id": secrets.token_hex(8),
        "holder": holder[:120],
        "issued": int(now or time.time()),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    return f"{PREFIX}.{tiers._b64e(body)}.{tiers._b64e(key.sign(body))}"


# -- every install --------------------------------------------------------------


def verify(token: str, *, pubkey_b64: Optional[str] = None) -> Dict[str, Any]:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    pubkey_b64 = pubkey_b64 if pubkey_b64 is not None else tiers.public_key()
    if not pubkey_b64:
        raise tiers.LicenseError(
            "esta instalación no puede comprobar códigos de créditos"
        )
    try:
        prefix, body64, sig64 = tiers.clean(token).split(".")
        if prefix != PREFIX:
            raise ValueError
        body = tiers._b64d(body64)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pubkey_b64)).verify(
            tiers._b64d(sig64), body
        )
        payload = json.loads(body)
        if (
            not isinstance(payload, dict)
            or int(payload.get("creditos", 0)) <= 0
            or not payload.get("id")
        ):
            raise ValueError
    except InvalidSignature:
        raise tiers.LicenseError("el código de créditos no es auténtico") from None
    except (ValueError, TypeError):
        raise tiers.LicenseError("el código de créditos está mal formado") from None
    return payload


def redeem(token: str, *, pubkey_b64: Optional[str] = None) -> int:
    """Add a code's credits; the new balance. A code counts once."""
    payload = verify(token, pubkey_b64=pubkey_b64)
    with _LOCK:
        data = _load()
        if payload["id"] in data["usados"]:
            raise tiers.LicenseError("ese código ya se usó")
        data["saldo"] += int(payload["creditos"])
        data["usados"] = (data["usados"] + [payload["id"]])[-500:]
        _save(data)
        return data["saldo"]


def spend(kind: str) -> bool:
    """Pay one use of *kind* beyond today's limit; False if there are not enough."""
    cost = COST.get(kind, 1)
    with _LOCK:
        data = _load()
        if data["saldo"] < cost:
            return False
        data["saldo"] -= cost
        _save(data)
        return True


def packs(
    country: str = "EC", rates: Optional[Dict[str, float]] = None
) -> List[Dict[str, Any]]:
    from openjarvis import pricing

    return [
        {
            "id": pid,
            "creditos": n,
            "precio": pricing.price_for(usd, country, rates),
            "pago": bool(checkout_url(pid)),
        }
        for pid, n, usd in PACKS
    ]


__all__ = [
    "COST",
    "PACKS",
    "balance",
    "checkout_url",
    "issue",
    "pack",
    "packs",
    "redeem",
    "spend",
    "verify",
]
