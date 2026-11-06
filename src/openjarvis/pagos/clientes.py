"""What each customer pays, what their AI really costs, and what is left.

The owner (2 Nov 2026): «los planes necesitan una buena gestión con las
ganancias para mí, acceso a modelos y el costo de API». Each paying customer
has a capped key inside the owner's OpenRouter account
(:mod:`openjarvis.accounts.provision`); OpenRouter says how much that key spent
(``GET /api/v1/keys/{hash}``: ``usage_monthly``, or ``usage`` on older
answers). So the margin shown is real: price paid, minus the processor's fee,
minus the AI actually used this month. When OpenRouter cannot be asked, the
cost is ``None`` and the page says so; nothing is guessed.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# The most expensive model class (quota.model_weight) each plan may use. A
# request above it goes to the cheap model (SERGIO_MODELO_BARATO). The key's
# monthly cap stays the hard stop either way.
MODEL_ACCESS: Dict[str, int] = {
    "free": 1,
    "go": 1,
    "work": 3,
    "dev": 99,
    "founders": 99,
}
ACCESS_WORDS: Dict[int, str] = {
    1: "Modelos rápidos (Flash, Mini, Haiku…)",
    3: "Hasta nivel medio (Sonnet, GPT-5…)",
    99: "Todos, también los más avanzados (Opus, o3…)",
}
CHEAP_DEFAULT = "openrouter/google/gemini-2.5-flash"


def max_weight(plan: str) -> int:
    return MODEL_ACCESS.get(plan, 1)


def cheap_model() -> str:
    import os

    return os.environ.get("SERGIO_MODELO_BARATO", "").strip() or CHEAP_DEFAULT


def allowed(model: str, plan: str) -> bool:
    """Whether a customer of *plan* may use *model*. ``openrouter/auto`` can
    choose an expensive model, so only plans with every model get it."""
    from openjarvis.quota import model_weight

    name = (model or "").strip().lower()
    if not name or name.endswith("/auto"):
        return max_weight(plan) >= 99
    return model_weight(name) <= max_weight(plan)


def key_usage(hash_: str, http: Any = None) -> Optional[float]:
    """USD this month on one customer key, as OpenRouter reports it."""
    from openjarvis.accounts import provision

    if not hash_ or not provision.enabled():
        return None
    try:
        client = http or provision._http()
        resp = client.get(
            f"{provision.API}/{hash_}",
            headers={"Authorization": f"Bearer {provision.management_key()}"},
        )
        if resp.status_code >= 400:
            return None
        data = resp.json().get("data") or {}
    except Exception:  # noqa: BLE001 — the row says «no se pudo leer»
        return None
    value = data.get("usage_monthly", data.get("usage"))
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _label(uid: str) -> str:
    """The customer's name, or their e-mail with the middle hidden."""
    try:
        from openjarvis.accounts import get_store

        user = get_store().get(uid) or {}
    except Exception:  # noqa: BLE001
        user = {}
    if user.get("name"):
        return str(user["name"])[:40]
    email = str(user.get("email") or "")
    if "@" in email:
        local, _, domain = email.partition("@")
        return f"{local[:2]}…@{domain}"
    return f"Cliente {uid[:6]}"


def report(*, http: Any = None, home: Any = None, limit: int = 60) -> Dict[str, Any]:
    from openjarvis.accounts import provision
    from openjarvis.pagos import ledger

    now = time.time()
    keys = provision._load(Path(home) if home else None)
    rows: List[Dict[str, Any]] = []
    for o in ledger.latest_paid(home):
        if (o.get("until") or 0) <= now:
            continue
        uid = o["uid"]
        entry = keys.get(uid) or {}
        cost = (
            key_usage(str(entry.get("hash") or ""), http) if len(rows) < limit else None
        )
        fee = ledger.order_fee(o["id"], home)
        price = round(float(o["usd"] or 0), 2)
        cap = provision.budget(o["plan"], o.get("list_usd") or o["usd"])
        rows.append(
            {
                "cliente": _label(uid),
                "plan": o["plan"],
                "paga": price,
                "comision": fee,
                "tope_ia": cap,
                "gasto_ia": cost,
                "ganancia": None if cost is None else round(price - fee - cost, 2),
                "uso": None
                if cost is None or not cap
                else round(min(1.0, cost / cap), 3),
                "modelos": ACCESS_WORDS[max_weight(o["plan"])],
                "hasta": o.get("until"),
            }
        )
    rows.sort(key=lambda r: (r["ganancia"] is None, r["ganancia"] or 0))  # worst first
    known = [r for r in rows if r["gasto_ia"] is not None]
    return {
        "clientes": rows,
        "totales": {
            "paga": round(sum(r["paga"] for r in rows), 2),
            "comision": round(sum(r["comision"] for r in rows), 2),
            "gasto_ia": round(sum(r["gasto_ia"] for r in known), 2),
            "ganancia": round(sum(r["ganancia"] for r in known), 2),
            "sin_dato": len(rows) - len(known),
        },
        "acceso": {plan: ACCESS_WORDS[w] for plan, w in MODEL_ACCESS.items()},
        "claves_ia": provision.enabled(),
    }


__all__ = [
    "MODEL_ACCESS",
    "allowed",
    "cheap_model",
    "key_usage",
    "max_weight",
    "report",
]
