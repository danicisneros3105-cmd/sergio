"""What happens around a payment, the same for every processor.

``checkout`` opens an order and the processor's hosted page; ``settle`` takes
a payment the processor confirmed (a signed notice or PayPal's capture) and
does the rest on its own: checks the amount, records the ledger, switches on
the customer's plan and their AI budget at OpenRouter
(:mod:`openjarvis.accounts.provision`). ``expire`` puts back on Free whoever's
paid month ran out without a renewal. ``summary`` is the owner's view: money
in, fees, what the AI may cost, margin, and whether his OpenRouter balance
covers what his customers may still spend.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from openjarvis.pagos import ledger
from openjarvis.pagos.gateways import GATEWAYS, Gateway, GatewayError, Paid, get

MONTH = 31 * 86400
EXPIRY_EVERY = 3600
log = logging.getLogger(__name__)


class PaymentError(ValueError):
    pass


def methods(http: Any = None) -> List[Dict[str, str]]:
    """The ways to pay that are switched on (their keys are in sergio.env)."""
    out = []
    for key in GATEWAYS:
        gw = get(key, http)
        if gw is not None and gw.ready():
            out.append({"id": gw.key, "nombre": gw.label, "detalle": gw.detail})
    return out


def _gateway(method: str, http: Any = None) -> Gateway:
    gw = get(method, http)
    if gw is None or not gw.ready():
        raise PaymentError("Esa forma de pago no está activada.")
    return gw


def price(plan: str, mult: int = 0) -> Dict[str, Any]:
    from openjarvis import tiers

    plan = tiers.plan_id(plan)
    if plan not in tiers.PLANS or plan == "free":
        raise PaymentError("Ese plan no se paga.")
    info = tiers.PLAN_INFO[plan]
    mult = max(info.mult, min(info.mult_max or info.mult, int(mult or info.mult)))
    return {
        "plan": plan,
        "nombre": info.name,
        "mult": mult,
        "usd": float(tiers.stretch_usd(plan, mult)),
        "incluye": list(info.includes),
    }


def checkout(
    uid: str,
    plan: str,
    mult: int,
    method: str,
    base: str,
    *,
    http: Any = None,
    home: Any = None,
) -> Dict[str, str]:
    """Open an order and the processor's page. Returns ``{url, pedido}``."""
    if not uid:
        raise PaymentError("Entre con su cuenta para pagar.")
    p = price(plan, mult)
    gw = _gateway(method, http)
    order = ledger.new_order(uid, p["plan"], p["mult"], p["usd"], gw.key, home)
    base = base.rstrip("/")
    back = f"{base}/v1/pagos/vuelta/{gw.key}?pedido={order['id']}"
    cancel = f"{base}/pagar?plan={p['plan']}&mult={p['mult']}&cancelado=1"
    try:
        page = gw.start(order, f"Sergio {p['nombre']} (1 mes)", back, cancel)
    except (GatewayError, KeyError, ValueError) as exc:
        ledger.mark(order["id"], "fallido", home)
        log.warning("checkout not opened: %s", exc)
        raise PaymentError(
            "El procesador de pagos no respondió. Inténtelo otra vez."
        ) from exc
    ledger.set_ext(order["id"], page.get("ext", ""), home)
    return {"url": page["url"], "pedido": order["id"]}


def _activate(uid: str, plan: str, usd: float) -> bool:
    from openjarvis.accounts import provision

    if not provision.enabled():
        return False
    if provision.key_for(uid):
        return provision.set_plan(uid, plan, usd=usd)
    return provision.ensure(uid, plan, usd=usd)


def settle(paid: Paid, method: str, *, home: Any = None) -> Dict[str, Any]:
    """Apply one confirmed payment (or cancellation). Safe to call twice."""
    from openjarvis.accounts import provision

    order = ledger.get(paid.order, home) if paid.order else None
    if order is None or order["method"] != method:
        return {"ok": False, "motivo": "pedido desconocido"}
    if not ledger.first_time(method, paid.event, home):
        return {"ok": True, "repetido": True, "pedido": order["id"]}
    if paid.kind == "baja":
        ledger.end_now(order["uid"], home)
        return {"ok": True, "baja": True, "pedido": order["id"]}
    if paid.usd + 0.01 < float(order["usd"]):
        ledger.mark(order["id"], "importe_incorrecto", home)
        log.warning(
            "order %s paid %.2f, expected %.2f", order["id"], paid.usd, order["usd"]
        )
        return {"ok": False, "motivo": "importe incorrecto"}
    if paid.kind == "renovacion" or order["status"] == "pagado":
        order = ledger.new_order(
            order["uid"], order["plan"], order["mult"], order["usd"], method, home
        )
        ledger.set_ext(order["id"], paid.ext, home)
    gw = get(method)
    usd = float(order["usd"])
    fee = gw.fee(usd) if gw else 0.0
    ai = provision.budget(order["plan"], usd)
    start = max(time.time(), ledger.paid_until(order["uid"], home))
    ledger.mark_paid(
        order["id"],
        start + MONTH * (gw.months_per_payment if gw else 1),
        {
            "ingreso": usd,
            "comision": fee,
            "proveedor": ai,
            "margen": usd - fee - ai,
        },
        home,
    )
    active = _activate(order["uid"], order["plan"], usd)
    return {"ok": True, "pedido": order["id"], "clave_ia": active}


def notice(
    method: str, headers: Any, body: bytes, *, http: Any = None, home: Any = None
) -> List[Dict[str, Any]]:
    gw = get(method, http)
    if gw is None or not gw.ready():
        raise PaymentError("Esa forma de pago no está activada.")
    return [settle(p, method, home=home) for p in gw.notice(headers, body)]


def come_back(
    method: str, order_id: str, query: Any, *, http: Any = None, home: Any = None
) -> Dict[str, Any]:
    """The customer is back from the processor's page."""
    order = ledger.get(order_id, home)
    if order is None or order["method"] != method:
        return {"ok": False}
    if order["status"] == "pagado":
        return {"ok": True, "pedido": order_id}
    gw = get(method, http)
    if gw is None or not gw.ready():
        return {"ok": False}
    try:
        paid = gw.finish(order, query)
    except GatewayError as exc:
        log.warning("payment not finished: %s", exc)
        return {"ok": False, "pedido": order_id}
    if paid is None:  # paid by notice (Stripe, Hyperswitch): it arrives on its own
        return {"ok": True, "pedido": order_id, "esperando": True}
    return settle(paid, method, home=home)


def order(
    order_id: str, uid: str = "", *, home: Any = None
) -> Optional[Dict[str, Any]]:
    o = ledger.get(order_id, home)
    if o is None or (uid and o["uid"] != uid):
        return None
    return {
        "pedido": o["id"],
        "plan": o["plan"],
        "usd": o["usd"],
        "estado": o["status"],
        "hasta": o["until"],
    }


def expire(*, now: Optional[float] = None, home: Any = None) -> List[str]:
    """Customers whose paid month ended without renewal go back to Free."""
    from openjarvis.accounts import provision

    now = time.time() if now is None else now
    done = []
    for o in ledger.latest_paid(home):
        if o["until"] and o["until"] < now:
            ledger.mark(o["id"], "vencido", home)
            if provision.key_for(o["uid"]):
                provision.set_plan(o["uid"], "free")
            done.append(o["uid"])
    return done


def _openrouter_balance(http: Any = None) -> Optional[float]:
    from openjarvis.accounts import provision

    if not provision.enabled():
        return None
    try:
        client = http or __import__("httpx").Client(timeout=10)
        resp = client.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {provision.management_key()}"},
        )
        data = resp.json().get("data") or {}
        return round(
            float(data.get("total_credits", 0)) - float(data.get("total_usage", 0)), 2
        )
    except Exception:  # noqa: BLE001 — the summary still shows the rest
        return None


def summary(*, http: Any = None, home: Any = None) -> Dict[str, Any]:
    month = time.time() - 30 * 86400
    now = time.time()
    active = [o for o in ledger.latest_paid(home) if (o["until"] or 0) > now]
    from openjarvis.accounts import provision

    owed = round(sum(provision.budget(o["plan"], o["usd"]) for o in active), 2)
    balance = _openrouter_balance(http)
    return {
        "metodos": methods(http),
        "mes": ledger.totals(month, home),
        "total": ledger.totals(0.0, home),
        "clientes_activos": len(active),
        "ia_comprometida_usd": owed,
        "saldo_openrouter_usd": balance,
        "falta_saldo": balance is not None and balance < owed,
        "claves_ia": provision.enabled(),
        "ultimos": [
            {k: o[k] for k in ("id", "plan", "usd", "method", "status", "created")}
            for o in ledger.recent(10, home)
        ],
    }


_LOOP: Optional[threading.Thread] = None


def start_expiry_loop() -> None:
    global _LOOP
    if _LOOP is not None:
        return

    def run() -> None:
        while True:
            try:
                expire()
            except Exception as exc:  # noqa: BLE001
                log.warning("expiry check failed: %s", exc)
            time.sleep(EXPIRY_EVERY)

    _LOOP = threading.Thread(target=run, name="sergio-pagos", daemon=True)
    _LOOP.start()


__all__ = [
    "PaymentError",
    "checkout",
    "come_back",
    "expire",
    "methods",
    "notice",
    "order",
    "price",
    "settle",
    "start_expiry_loop",
    "summary",
]
