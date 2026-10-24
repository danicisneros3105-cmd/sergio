"""Multi-account and throwaway-mail checks at sign-up.

Signals (all local; nothing is sent anywhere):

* the address is a throwaway domain → **block**;
* the same inbox written another way (dots, +tags, googlemail) → **block**
  (it is the same person);
* a phone already used by another account → **block**;
* more than 2 accounts from this device in 30 days → **block**;
* more than 4 accounts from this network (/24, or /48 for IPv6) in a day →
  **review** (the owner decides);
* no email confirmation and no phone → **verify** before using it.

It is a set of honest heuristics, not a commercial fraud service.
"""

from __future__ import annotations

import ipaddress
from typing import Any, Dict, List

from openjarvis.accounts import disposable
from openjarvis.accounts import email as mail

DEVICE_LIMIT = 2
DEVICE_WINDOW_S = 30 * 86400
NETWORK_LIMIT = 4
NETWORK_WINDOW_S = 86400


def network_of(ip: str) -> str:
    try:
        addr = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return "?"
    if addr.version == 4:
        return str(ipaddress.ip_network(f"{addr}/24", strict=False))
    return str(ipaddress.ip_network(f"{addr}/48", strict=False))


def check(
    store: Any, *, email: str = "", phone: str = "", device: str = "", ip: str = ""
) -> Dict[str, Any]:
    reasons: List[str] = []
    action = "allow"

    def worst(a: str) -> None:
        nonlocal action
        order = ["allow", "verify", "review", "block"]
        if order.index(a) > order.index(action):
            action = a

    if email:
        _local, domain = mail.split(email)
        if disposable.is_disposable(domain):
            reasons.append("correo temporal")
            worst("block")
        if not mail.provider_ok(email):
            reasons.append("proveedor de correo no admitido")
            worst("block")
        if store.find(canonical=mail.canonical(email)):
            reasons.append("ese correo ya tiene cuenta")
            worst("block")
    if phone and store.find(phone=phone):
        reasons.append("ese teléfono ya tiene cuenta")
        worst("block")
    if device and store.signups_since(DEVICE_WINDOW_S, device=device) >= DEVICE_LIMIT:
        reasons.append("demasiadas cuentas desde este dispositivo")
        worst("block")
    net = network_of(ip)
    if (
        net != "?"
        and store.signups_since(NETWORK_WINDOW_S, network=net) >= NETWORK_LIMIT
    ):
        reasons.append("muchas cuentas desde esta red hoy")
        worst("review")
    if not email and not phone:
        worst("verify")
    score = {"allow": 0, "verify": 30, "review": 60, "block": 100}[action]
    return {"action": action, "score": score, "reasons": reasons, "network": net}


__all__ = ["check", "network_of"]
