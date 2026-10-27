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
TEST_USD = 1.00  # the owner's real test charge, to refund afterwards
MAX_OPEN = 5  # orders one account may open in WINDOW seconds
WINDOW = 600
log = logging.getLogger(__name__)


class PaymentError(ValueError):
    pass


def _https(base: str) -> bool:
    return base.startswith("https://")


def methods(http: Any = None) -> List[Dict[str, Any]]:
    """The ways to pay that are switched on (their keys are in sergio.env)."""
    out = []
    for key in GATEWAYS:
        gw = get(key, http)
        if gw is not None and gw.ready():
            out.append(
                {
                    "id": gw.key,
                    "nombre": gw.label,
                    "detalle": gw.detail,
                    "real": gw.live(),
                }
            )
    return out


def _gateway(method: str, http: Any = None) -> Gateway:
    gw = get(method, http)
    if gw is None or not gw.ready():
        raise PaymentError("Esa forma de pago no está activada.")
    return gw


def price(plan: str, mult: int = 0) -> Dict[str, Any]:
    from openjarvis import tiers

    if plan == "prueba":
        return {
            "plan": "prueba",
            "nombre": "Prueba de cobro",
            "mult": 0,
            "usd": TEST_USD,
            "incluye": [
                "Un cobro real de $1 con su propia tarjeta",
                "Recorre todo: página segura, aviso firmado, recibo y libro",
                "Devuélvalo después desde el panel del procesador",
            ],
        }
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
    owner: bool = False,
    http: Any = None,
    home: Any = None,
) -> Dict[str, str]:
    """Open an order and the processor's page. Returns ``{url, pedido}``.
    The owner may only open the real test charge (``plan="prueba"``)."""
    if not uid:
        raise PaymentError("Entre con su cuenta para pagar.")
    if owner != (plan == "prueba"):
        raise PaymentError(
            "La prueba de cobro es solo para el dueño."
            if plan == "prueba"
            else "La cuenta del dueño no paga planes."
        )
    p = price(plan, mult)
    gw = _gateway(method, http)
    if gw.live() and not _https(base):
        raise PaymentError(
            "Para cobrar dinero real Sergio necesita una dirección https "
            "(SERGIO_PUBLIC_URL)."
        )
    if ledger.opened_since(uid, time.time() - WINDOW, home) >= MAX_OPEN:
        raise PaymentError("Demasiados intentos de pago. Espere unos minutos.")
    order = ledger.new_order(uid, p["plan"], p["mult"], p["usd"], gw.key, home)
    base = base.rstrip("/")
    back = f"{base}/v1/pagos/vuelta/{gw.key}?pedido={order['id']}"
    cancel = f"{base}/pagar?plan={p['plan']}&mult={p['mult']}&cancelado=1"
    try:
        title = (
            "Sergio · prueba de cobro"
            if p["plan"] == "prueba"
            else f"Sergio {p['nombre']} (1 mes)"
        )
        page = gw.start(order, title, back, cancel)
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
    if paid.currency and paid.currency.upper() != "USD":
        ledger.mark(order["id"], "moneda_incorrecta", home)
        log.warning("order %s paid in %s", order["id"], paid.currency)
        return {"ok": False, "motivo": "moneda incorrecta"}
    if paid.kind in ("baja", "reembolso") and not ledger.first_time(
        method, paid.event, home
    ):
        return {"ok": True, "repetido": True, "pedido": order["id"]}
    if paid.kind == "baja":
        ledger.end_now(order["uid"], home)
        return {"ok": True, "baja": True, "pedido": order["id"]}
    if paid.kind == "reembolso":
        return _give_back(order, paid.usd, home)
    done = ledger.event_order(method, paid.event, home)
    if done is not None:
        # Already recorded. Switch the plan on again (it is idempotent): a
        # crash right after recording must not leave the customer without it.
        first = ledger.get(done, home) if done else None
        if first and first["status"] == "pagado" and first["plan"] != "prueba":
            _activate(first["uid"], first["plan"], float(first["usd"]))
        return {"ok": True, "repetido": True, "pedido": done or order["id"]}
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
    test = order["plan"] == "prueba"
    ai = 0.0 if test else provision.budget(order["plan"], usd)
    start = max(time.time(), 0 if test else ledger.paid_until(order["uid"], home))
    receipt = ledger.settle_paid(
        method,
        paid.event,
        order["id"],
        time.time() if test else start + MONTH * (gw.months_per_payment if gw else 1),
        {
            "ingreso": usd,
            "comision": fee,
            "proveedor": ai,
            "margen": usd - fee - ai,
        },
        home,
    )
    if receipt is None:  # the same event, recorded meanwhile by another thread
        return {"ok": True, "repetido": True, "pedido": order["id"]}
    active = False if test else _activate(order["uid"], order["plan"], usd)
    return {"ok": True, "pedido": order["id"], "recibo": receipt, "clave_ia": active}


def _give_back(order: Dict[str, Any], usd: float, home: Any) -> Dict[str, Any]:
    """Money returned (refund or chargeback): the books say so with new lines
    and the customer's paid time ends now."""
    from openjarvis.accounts import provision

    usd = min(abs(usd) or float(order["usd"]), float(order["usd"]))
    ledger.add_lines(order["id"], {"ingreso": -usd, "margen": -usd}, home)
    ledger.mark(order["id"], "reembolsado", home)
    if order["plan"] != "prueba":
        ledger.end_now(order["uid"], home)
        if provision.key_for(order["uid"]):
            provision.set_plan(order["uid"], "free")
    return {"ok": True, "reembolso": usd, "pedido": order["id"]}


def revoke(order_id: str, *, home: Any = None) -> Dict[str, Any]:
    """The owner refunded in the processor's dashboard: record it here."""
    o = ledger.get(order_id, home)
    if o is None or o["status"] != "pagado":
        raise PaymentError("Solo se devuelve un pedido pagado.")
    return _give_back(o, float(o["usd"]), home)


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
        "recibo": o.get("recibo") or "",
        "metodo": o["method"],
        "pagado": o["paid"],
    }


def readiness(base: str, *, online: bool = False, http: Any = None) -> Dict[str, Any]:
    """What is set up and what is missing, in the owner's words."""
    from openjarvis.accounts import provision

    steps: List[Dict[str, Any]] = []
    on = []
    for key in GATEWAYS:
        gw = get(key, http)
        if gw is None or not gw.ready():
            continue
        problem = gw.check() if online else ""
        on.append(gw)
        steps.append(
            {
                "paso": f"{gw.label}: claves puestas",
                "ok": not problem,
                "detalle": problem
                or ("Cobra dinero real." if gw.live() else "Modo de prueba."),
            }
        )
    if not on:
        steps.append(
            {
                "paso": "Una forma de pago",
                "ok": False,
                "detalle": "Ponga las claves de Stripe o PayPal en sergio.env.",
            }
        )
    steps.append(
        {
            "paso": "Dirección pública https",
            "ok": _https(base),
            "detalle": base if _https(base) else "Falta SERGIO_PUBLIC_URL con https.",
        }
    )
    steps.append(
        {
            "paso": "Claves de IA por cliente (OpenRouter)",
            "ok": provision.enabled(),
            "detalle": "Lista."
            if provision.enabled()
            else "Falta OPENROUTER_MANAGEMENT_KEY.",
        }
    )
    return {
        "listo": all(x["ok"] for x in steps),
        "pasos": steps,
        "avisos": {gw.key: f"{base.rstrip('/')}/v1/pagos/aviso/{gw.key}" for gw in on},
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
        "libro": ledger.verify(home),
        "ultimos": [
            {
                k: o.get(k)
                for k in ("id", "plan", "usd", "method", "status", "created", "recibo")
            }
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
    "readiness",
    "revoke",
    "settle",
    "start_expiry_loop",
    "summary",
]
