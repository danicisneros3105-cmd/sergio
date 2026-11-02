"""One AI key per customer, created in the background inside the owner's account.

The owner (27 Oct 2026): «el cliente paga un plan → el dinero llega a mi cuenta
→ un software paga al proveedor → nos quedamos con la ganancia; las claves se
crean por ellos en segundo plano». This is how it works without breaking the
AI companies' terms:

* The owner has **one business account** at OpenRouter (one key reaches the
  models of every lab) and creates, once, a *management key*
  (``OPENROUTER_MANAGEMENT_KEY`` in ``~/.openjarvis/sergio.env``). In its
  dashboard he turns on automatic top-up from his card: that is the
  «software that pays the provider automatically».
* When a customer's account is approved, Sergio creates **a sub-key for that
  customer inside the owner's account** (``POST /api/v1/keys``) with a monthly
  spending limit: what the plan costs minus the owner's margin
  (``SERGIO_MARGEN``, 0.40 by default). The customer never sees it, never
  creates anything and never gives a card to anyone but the owner's checkout.
* That customer's chats use their sub-key (:data:`CUSTOMER_KEY`), so OpenRouter
  itself stops a customer who used up their budget and the owner's margin is
  never spent. Blocking or deleting the account disables the key.

What is NOT done, ever: accounts at OpenAI, Google or Anthropic opened in the
customers' names, or keys taken from their accounts (against the providers'
terms and the customers' own security).

The plaintext key only exists in the create answer; it is kept in
``~/.openjarvis/cuentas_claves.json`` (0600) sealed with AES-256-GCM under
Sergio's master key and tied to the customer (:mod:`openjarvis.pagos.cifrado`),
and never logged. Files from before the sealing are sealed on first read.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

API = "https://openrouter.ai/api/v1/keys"
MARGIN = 0.40
FREE_BUDGET_USD = 0.50  # a Free customer's monthly allowance
log = logging.getLogger(__name__)
_LOCK = threading.Lock()

# The customer key for the request being served (set by the server from the
# customer's session); the engines use it instead of the owner's key.
CUSTOMER_KEY: contextvars.ContextVar[str] = contextvars.ContextVar(
    "sergio_customer_key", default=""
)
# Who is asking, when it is a customer (not the owner): their id and the plan
# they paid for. Empty for the owner. tiers.current() and quota read them so
# features and daily limits follow the customer, never the owner's licence.
CUSTOMER: contextvars.ContextVar[str] = contextvars.ContextVar(
    "sergio_customer", default=""
)
CUSTOMER_PLAN: contextvars.ContextVar[str] = contextvars.ContextVar(
    "sergio_customer_plan", default="free"
)


def management_key() -> str:
    return os.environ.get("OPENROUTER_MANAGEMENT_KEY", "").strip()


def enabled() -> bool:
    return bool(management_key())


def margin() -> float:
    try:
        value = float(os.environ.get("SERGIO_MARGEN", MARGIN))
    except ValueError:
        value = MARGIN
    return min(0.95, max(0.0, value))


def budget(plan: str, usd: Optional[float] = None) -> float:
    """Monthly USD a customer of *plan* may spend at the provider: the plan's
    price minus the owner's margin (Free gets a small allowance)."""
    if usd is None:
        from openjarvis import tiers

        info = tiers.PLAN_INFO.get(plan) or tiers.PLAN_INFO["free"]
        usd = float(info.usd)
    if usd <= 0:
        return FREE_BUDGET_USD
    return round(usd * (1.0 - margin()), 2)


def _path(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = Path(get_config_dir())
    return Path(home) / "cuentas_claves.json"


def _load(home: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    try:
        data = json.loads(_path(home).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    plain = [uid for uid, e in data.items() if isinstance(e, dict) and e.get("key")]
    if plain:  # written before keys were sealed: seal them now
        for uid in plain:
            data[uid]["sealed"] = _seal(uid, data[uid].pop("key"), home)
        _save(data, home)
    return data


def _seal(uid: str, key: str, home: Optional[Path] = None) -> str:
    from openjarvis.pagos import cifrado

    return cifrado.seal(key, aad=f"subclave:{uid}", home=_path(home).parent)


def _open(uid: str, sealed: str, home: Optional[Path] = None) -> str:
    from openjarvis.pagos import cifrado

    try:
        return cifrado.unseal(sealed, aad=f"subclave:{uid}", home=_path(home).parent)
    except (cifrado.SealError, ValueError):
        log.warning("customer key cannot be opened (master key changed?)")
        return ""


def _save(data: Dict[str, Dict[str, Any]], home: Optional[Path] = None) -> None:
    path = _path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def _http() -> Any:
    import httpx

    return httpx.Client(timeout=20)


def _call(
    method: str, url: str, body: Dict[str, Any], http: Any = None
) -> Dict[str, Any]:
    client = http or _http()
    resp = client.request(
        method,
        url,
        json=body,
        headers={"Authorization": f"Bearer {management_key()}"},
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenRouter respondió {resp.status_code}")
    return resp.json()


def key_for(uid: str, home: Optional[Path] = None) -> str:
    entry = _load(home).get(uid) or {}
    if entry.get("off") or not entry.get("sealed"):
        return ""
    return _open(uid, entry["sealed"], home)


def status(uid: str, home: Optional[Path] = None) -> Dict[str, Any]:
    entry = _load(home).get(uid) or {}
    return {
        "activa": bool(entry.get("sealed")) and not entry.get("off"),
        "plan": entry.get("plan", "free"),
        "tope_usd": entry.get("limit"),
    }


def ensure(
    uid: str,
    plan: str = "free",
    *,
    usd: Optional[float] = None,
    http: Any = None,
    home: Optional[Path] = None,
) -> bool:
    """Create the customer's sub-key if there is none yet. False if provisioning
    is not set up (no management key) or OpenRouter refused."""
    if not enabled():
        return False
    with _LOCK:
        data = _load(home)
        if data.get(uid, {}).get("sealed"):
            return True
        limit = budget(plan, usd)
        try:
            out = _call(
                "POST",
                API,
                {"name": f"sergio-{uid}", "limit": limit, "limit_reset": "monthly"},
                http,
            )
        except Exception as exc:  # noqa: BLE001 — never block a sign-in
            log.warning("customer key not created: %s", exc)
            return False
        info = out.get("data") or {}
        key = str(out.get("key") or "")
        if not key:
            return False
        data[uid] = {
            "sealed": _seal(uid, key, home),
            "hash": info.get("hash", ""),
            "limit": limit,
            "plan": plan,
            "usd": usd,  # what they pay: the multiplier of a plan that stretches
        }
        _save(data, home)
        return True


def set_plan(
    uid: str,
    plan: str,
    *,
    usd: Optional[float] = None,
    http: Any = None,
    home: Optional[Path] = None,
) -> bool:
    """The customer changed plan (``usd``: what they pay, for plans that
    stretch): their monthly limit follows."""
    with _LOCK:
        data = _load(home)
        entry = data.get(uid)
        if not entry or not entry.get("hash") or not enabled():
            return False
        limit = budget(plan, usd)
        if entry.get("plan") == plan and entry.get("limit") == limit:
            if entry.get("usd") != usd:
                entry["usd"] = usd
                _save(data, home)
            return True  # already so: nothing to send
        try:
            _call("PATCH", f"{API}/{entry['hash']}", {"limit": limit}, http)
        except Exception as exc:  # noqa: BLE001
            log.warning("customer limit not changed: %s", exc)
            return False
        entry.update(limit=limit, plan=plan, usd=usd)
        _save(data, home)
        return True


def plan_info(uid: str, home: Optional[Path] = None) -> Dict[str, Any]:
    """The customer's own plan and what they pay (``{"plan", "usd"}``)."""
    entry = _load(home).get(uid) or {}
    return {"plan": entry.get("plan") or "free", "usd": entry.get("usd")}


def disable(uid: str, *, http: Any = None, home: Optional[Path] = None) -> bool:
    """Blocked or deleted: the customer's key stops working at once."""
    with _LOCK:
        data = _load(home)
        entry = data.get(uid)
        if not entry:
            return False
        if entry.get("hash") and enabled():
            try:
                _call("PATCH", f"{API}/{entry['hash']}", {"disabled": True}, http)
            except Exception as exc:  # noqa: BLE001
                log.warning("customer key not disabled: %s", exc)
        entry["off"] = True
        _save(data, home)
        return True


def in_background(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


def customer_model(model: str, plan: Optional[str] = None) -> str:
    """A customer's request goes through their own key at OpenRouter, with
    the models their plan includes (``pagos.clientes.MODEL_ACCESS``; owner,
    2 Nov 2026: «acceso a modelos» por plan). An OpenRouter id the plan allows
    stays; any other becomes ``openrouter/auto`` on plans with every model and
    the cheap model on the rest. The key's monthly cap is the hard stop."""
    from openjarvis.pagos import clientes

    plan = plan or CUSTOMER_PLAN.get() or "free"
    if model.startswith("openrouter/") and clientes.allowed(model, plan):
        return model
    if clientes.max_weight(plan) >= 99:
        return "openrouter/auto"
    return clientes.cheap_model()


__all__ = [
    "CUSTOMER_KEY",
    "budget",
    "customer_model",
    "disable",
    "enabled",
    "ensure",
    "in_background",
    "key_for",
    "margin",
    "set_plan",
    "status",
]
