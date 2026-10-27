"""The processors under Sergio Pagos, each behind the same small interface.

A :class:`Gateway` does three things: open a hosted payment page for an order
(:meth:`Gateway.start`), finish a payment when the customer comes back if the
processor needs it (:meth:`Gateway.finish`, PayPal's capture), and read a
notice (webhook) only after checking it really came from the processor
(:meth:`Gateway.notice`). Each returns :class:`Paid` facts or ``None``; what to
do with a payment is :mod:`.service`'s job, never the gateway's.

* **Stripe** — Checkout Session in subscription mode (renews monthly on its
  own); notices signed with HMAC-SHA256 (``Stripe-Signature``, 5 min window).
* **PayPal** — Orders v2 (one month per payment), captured on return;
  notices checked by PayPal itself (``verify-webhook-signature``).
* **Hyperswitch** — the owner's own, self-hosted payment orchestrator
  (Apache-2.0, juspay/hyperswitch), which reaches card and local processors
  from one place; payment links, notices signed with HMAC-SHA512
  (``x-webhook-signature-512``).

Keys come only from the environment (``~/.openjarvis/sergio.env``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

TOLERANCE = 300  # seconds a signed notice stays valid


@dataclass
class Paid:
    """A payment the processor confirmed. ``order`` is Sergio's order id."""

    order: str
    usd: float
    event: str = ""
    ext: str = ""
    kind: str = "pago"  # "pago", "renovacion" or "baja"


class GatewayError(RuntimeError):
    pass


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _http() -> Any:
    import httpx

    return httpx.Client(timeout=20)


class Gateway:
    key = ""
    label = ""
    detail = ""
    fee_rate = 0.0
    fee_fixed = 0.0
    months_per_payment = 1

    def __init__(self, http: Any = None) -> None:
        self._http_client = http

    @property
    def http(self) -> Any:
        if self._http_client is None:
            self._http_client = _http()
        return self._http_client

    def ready(self) -> bool:
        raise NotImplementedError

    def start(
        self, order: Mapping[str, Any], title: str, back: str, cancel: str
    ) -> Dict[str, str]:
        """Open the hosted page: ``{"url": …, "ext": processor's id}``."""
        raise NotImplementedError

    def finish(
        self, order: Mapping[str, Any], query: Mapping[str, str]
    ) -> Optional[Paid]:
        return None

    def notice(self, headers: Mapping[str, str], body: bytes) -> List[Paid]:
        raise NotImplementedError

    def fee(self, usd: float) -> float:
        rate = _env(f"SERGIO_COMISION_{self.key.upper()}")
        r, f = self.fee_rate, self.fee_fixed
        if rate:
            try:
                parts = rate.split("+")
                r = float(parts[0])
                f = float(parts[1]) if len(parts) > 1 else 0.0
            except ValueError:
                pass
        return round(usd * r + f, 2) if usd > 0 else 0.0


def _lower(headers: Mapping[str, str]) -> Dict[str, str]:
    return {k.lower(): v for k, v in headers.items()}


# -- Stripe -------------------------------------------------------------------
class Stripe(Gateway):
    key = "stripe"
    label = "Tarjeta"
    detail = "Visa, Mastercard, Apple Pay y Google Pay. Se renueva sola cada mes."
    fee_rate, fee_fixed = 0.029, 0.30
    API = "https://api.stripe.com/v1"

    def ready(self) -> bool:
        return bool(_env("STRIPE_SECRET_KEY") and _env("STRIPE_WEBHOOK_SECRET"))

    def start(self, order, title, back, cancel):  # noqa: ANN001, ANN201
        cents = int(round(float(order["usd"]) * 100))
        form = {
            "mode": "subscription",
            "client_reference_id": order["id"],
            "success_url": back,
            "cancel_url": cancel,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][unit_amount]": str(cents),
            "line_items[0][price_data][recurring][interval]": "month",
            "line_items[0][price_data][product_data][name]": title,
            "metadata[pedido]": order["id"],
            "subscription_data[metadata][pedido]": order["id"],
        }
        resp = self.http.post(
            f"{self.API}/checkout/sessions",
            data=form,
            headers={"Authorization": f"Bearer {_env('STRIPE_SECRET_KEY')}"},
        )
        if resp.status_code >= 400:
            raise GatewayError(f"Stripe respondió {resp.status_code}")
        out = resp.json()
        return {"url": out["url"], "ext": out.get("id", "")}

    def notice(self, headers, body):  # noqa: ANN001, ANN201
        sig = _lower(headers).get("stripe-signature", "")
        parts: Dict[str, List[str]] = {}
        for item in sig.split(","):
            k, _, v = item.strip().partition("=")
            parts.setdefault(k, []).append(v)
        stamp = (parts.get("t") or [""])[0]
        if not stamp.isdigit() or abs(time.time() - int(stamp)) > TOLERANCE:
            raise GatewayError("aviso de Stripe vencido o sin firma")
        secret = _env("STRIPE_WEBHOOK_SECRET").encode()
        want = hmac.new(
            secret, stamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        if not any(hmac.compare_digest(want, v) for v in parts.get("v1", [])):
            raise GatewayError("firma de Stripe incorrecta")
        event = json.loads(body)
        obj = (event.get("data") or {}).get("object") or {}
        kind = event.get("type", "")
        eid = event.get("id", "")
        if kind == "checkout.session.completed" and obj.get("payment_status") == "paid":
            return [
                Paid(
                    order=obj.get("client_reference_id")
                    or (obj.get("metadata") or {}).get("pedido", ""),
                    usd=(obj.get("amount_total") or 0) / 100,
                    event=eid,
                    ext=obj.get("subscription") or obj.get("id", ""),
                )
            ]
        if kind == "invoice.paid" and obj.get("billing_reason") == "subscription_cycle":
            meta = (
                ((obj.get("parent") or {}).get("subscription_details") or {}).get(
                    "metadata"
                )
                or (obj.get("subscription_details") or {}).get("metadata")
                or {}
            )
            return [
                Paid(
                    order=meta.get("pedido", ""),
                    usd=(obj.get("amount_paid") or 0) / 100,
                    event=eid,
                    kind="renovacion",
                )
            ]
        if kind == "customer.subscription.deleted":
            return [
                Paid(
                    order=(obj.get("metadata") or {}).get("pedido", ""),
                    usd=0.0,
                    event=eid,
                    kind="baja",
                )
            ]
        return []


# -- PayPal -------------------------------------------------------------------
class PayPal(Gateway):
    key = "paypal"
    label = "PayPal"
    detail = "Con su cuenta PayPal o tarjeta. Un mes por pago."
    fee_rate, fee_fixed = 0.0349, 0.49

    @property
    def api(self) -> str:
        if _env("PAYPAL_MODO").lower() == "sandbox":
            return "https://api-m.sandbox.paypal.com"
        return "https://api-m.paypal.com"

    def ready(self) -> bool:
        return all(
            _env(n) for n in ("PAYPAL_CLIENT_ID", "PAYPAL_SECRET", "PAYPAL_WEBHOOK_ID")
        )

    def _token(self) -> str:
        resp = self.http.post(
            f"{self.api}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(_env("PAYPAL_CLIENT_ID"), _env("PAYPAL_SECRET")),
        )
        if resp.status_code >= 400:
            raise GatewayError(f"PayPal respondió {resp.status_code}")
        return resp.json()["access_token"]

    def _call(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.http.post(
            f"{self.api}{path}",
            json=body,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            raise GatewayError(f"PayPal respondió {resp.status_code}")
        return resp.json()

    def start(self, order, title, back, cancel):  # noqa: ANN001, ANN201
        out = self._call(
            "/v2/checkout/orders",
            {
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "custom_id": order["id"],
                        "description": title[:127],
                        "amount": {
                            "currency_code": "USD",
                            "value": f"{float(order['usd']):.2f}",
                        },
                    }
                ],
                "payment_source": {
                    "paypal": {
                        "experience_context": {
                            "brand_name": "Sergio",
                            "user_action": "PAY_NOW",
                            "shipping_preference": "NO_SHIPPING",
                            "return_url": back,
                            "cancel_url": cancel,
                        }
                    }
                },
            },
        )
        link = next(
            (
                x["href"]
                for x in out.get("links", [])
                if x.get("rel") in ("payer-action", "approve")
            ),
            "",
        )
        if not link:
            raise GatewayError("PayPal no dio la página de pago")
        return {"url": link, "ext": out.get("id", "")}

    @staticmethod
    def _captured(out: Mapping[str, Any], event: str = "") -> List[Paid]:
        paid = []
        for unit in out.get("purchase_units") or []:
            for cap in (unit.get("payments") or {}).get("captures") or []:
                if cap.get("status") == "COMPLETED":
                    paid.append(
                        Paid(
                            order=cap.get("custom_id") or unit.get("custom_id", ""),
                            usd=float((cap.get("amount") or {}).get("value") or 0),
                            event=event or cap.get("id", ""),
                            ext=out.get("id", ""),
                        )
                    )
        return paid

    def finish(self, order, query):  # noqa: ANN001, ANN201
        ext = query.get("token") or order.get("ext", "")
        if not ext or ext != order.get("ext"):
            return None
        out = self._call(f"/v2/checkout/orders/{ext}/capture", {})
        paid = self._captured(out)
        return paid[0] if paid else None

    def notice(self, headers, body):  # noqa: ANN001, ANN201
        h = _lower(headers)
        event = json.loads(body)
        check = self._call(
            "/v1/notifications/verify-webhook-signature",
            {
                "auth_algo": h.get("paypal-auth-algo", ""),
                "cert_url": h.get("paypal-cert-url", ""),
                "transmission_id": h.get("paypal-transmission-id", ""),
                "transmission_sig": h.get("paypal-transmission-sig", ""),
                "transmission_time": h.get("paypal-transmission-time", ""),
                "webhook_id": _env("PAYPAL_WEBHOOK_ID"),
                "webhook_event": event,
            },
        )
        if check.get("verification_status") != "SUCCESS":
            raise GatewayError("PayPal no reconoce ese aviso")
        if event.get("event_type") != "PAYMENT.CAPTURE.COMPLETED":
            return []
        res = event.get("resource") or {}
        return [
            Paid(
                order=res.get("custom_id", ""),
                usd=float((res.get("amount") or {}).get("value") or 0),
                # The capture id, so the return and the notice count once.
                event=res.get("id", "") or event.get("id", ""),
            )
        ]


# -- Hyperswitch (open source, self-hosted) -----------------------------------
class Hyperswitch(Gateway):
    key = "hyperswitch"
    label = "Tarjeta y pagos locales"
    detail = "Por el orquestador propio de Sergio (bancos y pasarelas de su país)."
    fee_rate, fee_fixed = 0.03, 0.30

    def ready(self) -> bool:
        return all(
            _env(n)
            for n in ("HYPERSWITCH_URL", "HYPERSWITCH_API_KEY", "HYPERSWITCH_HASH_KEY")
        )

    def start(self, order, title, back, cancel):  # noqa: ANN001, ANN201
        resp = self.http.post(
            f"{_env('HYPERSWITCH_URL').rstrip('/')}/payments",
            json={
                "amount": int(round(float(order["usd"]) * 100)),
                "currency": "USD",
                "description": title,
                "return_url": back,
                "payment_link": True,
                "metadata": {"pedido": order["id"]},
            },
            headers={"api-key": _env("HYPERSWITCH_API_KEY")},
        )
        if resp.status_code >= 400:
            raise GatewayError(f"Hyperswitch respondió {resp.status_code}")
        out = resp.json()
        link = (out.get("payment_link") or {}).get("link", "")
        if not link:
            raise GatewayError("Hyperswitch no dio la página de pago")
        return {"url": link, "ext": out.get("payment_id", "")}

    def notice(self, headers, body):  # noqa: ANN001, ANN201
        sig = _lower(headers).get("x-webhook-signature-512", "")
        want = hmac.new(
            _env("HYPERSWITCH_HASH_KEY").encode(), body, hashlib.sha512
        ).hexdigest()
        if not sig or not hmac.compare_digest(want, sig.lower()):
            raise GatewayError("firma de Hyperswitch incorrecta")
        event = json.loads(body)
        obj = (event.get("content") or {}).get("object") or {}
        if (
            event.get("event_type") != "payment_succeeded"
            or obj.get("status") != "succeeded"
        ):
            return []
        return [
            Paid(
                order=(obj.get("metadata") or {}).get("pedido", ""),
                usd=(obj.get("amount_received") or obj.get("amount") or 0) / 100,
                event=event.get("event_id", "") or obj.get("payment_id", ""),
                ext=obj.get("payment_id", ""),
            )
        ]


GATEWAYS = {g.key: g for g in (Stripe, PayPal, Hyperswitch)}


def get(key: str, http: Any = None) -> Optional[Gateway]:
    cls = GATEWAYS.get(key)
    return cls(http) if cls else None


__all__ = ["GATEWAYS", "Gateway", "GatewayError", "Paid", "get"]
