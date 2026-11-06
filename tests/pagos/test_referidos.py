"""Exercise signed settlement, delayed rewards and the hosted Stripe discount."""

import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.accounts import provision
from openjarvis.pagos import ledger, referidos, service
from openjarvis.pagos.gateways import Paid
from openjarvis.server import customer_gate, pagos_routes


class StripeHTTP:
    def __init__(self):
        self.requests = []

    def post(self, url, *, data, headers):
        self.requests.append((url, data, headers))
        self.status_code = 200
        self.body = (
            {"id": "coupon-test"}
            if url.endswith("/coupons")
            else {"id": "cs_mock", "url": "https://checkout.stripe.com/c/pay/mock"}
        )
        return self

    def json(self):
        return self.body


def _notice(home, oid, event, kind, amount=2100):
    body = json.dumps(
        {
            "id": event,
            "type": kind,
            "data": {
                "object": {
                    "client_reference_id": oid,
                    "currency": "usd",
                    "amount_total": amount,
                    "payment_status": "paid",
                }
            },
        }
    ).encode()
    stamp = str(int(time.time()))
    sig = hmac.new(
        b"webhook-key", stamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return service.notice(
        "stripe", {"stripe-signature": f"t={stamp},v1={sig}"}, body, home=home
    )[0]


def _setup(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "webhook-key")
    monkeypatch.setenv("SERGIO_REFERIDOS", "1")
    monkeypatch.setenv("SERGIO_MARGEN", "0.4")
    monkeypatch.setattr(provision, "enabled", lambda: False)
    monkeypatch.setattr(provision, "key_for", lambda *_: "")


def _purchase(home, uid, *, plan="work", usd=21):
    return ledger.new_order(uid, plan, 5, usd, "stripe", home)["id"]


def test_signed_referral_to_hosted_coupon_and_renewal(tmp_path, monkeypatch):
    _setup(monkeypatch)
    host = _purchase(tmp_path, "host")
    _notice(tmp_path, host, "host-paid", "checkout.session.completed")
    code = referidos.status("host", tmp_path)["codigo"]
    assert not referidos.link("host", code, tmp_path)
    assert referidos.link("guest", code.lower(), tmp_path)
    assert not referidos.link("guest", code, tmp_path)
    order = _purchase(tmp_path, "guest")
    assert referidos.status("host", tmp_path)["en_revision"] == 0
    paid = _notice(
        tmp_path, order, "guest-paid", "checkout.session.async_payment_succeeded"
    )
    assert paid["ok"] and paid["recibo"]
    again = _notice(tmp_path, order, "also-paid", "checkout.session.completed")
    assert again["repetido"]
    assert ledger.totals(home=tmp_path)["ingreso"] == 42
    for uid in ("host", "guest"):
        assert referidos.status(uid, tmp_path)["en_revision"] == 1
    monkeypatch.setattr(referidos, "WAIT_SECONDS", 0)
    for uid in ("host", "guest"):
        assert referidos.status(uid, tmp_path)["disponibles"] == 1
    with ledger._db(tmp_path) as db:
        db.execute("UPDATE orders SET until=0 WHERE id=?", (host,))
    http = StripeHTTP()
    new = service.checkout(
        "host", "dev", 10, "stripe", "https://app.example", http=http, home=tmp_path
    )
    assert (
        http.requests[0][1]["amount_off"] == "105"
    )  # capped at 5% of the source purchase
    assert http.requests[0][1]["duration"] == "once"
    assert http.requests[1][1]["discounts[0][coupon]"] == "coupon-test"
    assert http.requests[1][1]["line_items[0][price_data][unit_amount]"] == "5000"
    order = ledger.get(new["pedido"], tmp_path)
    assert order["usd"] == 48.95 and order["list_usd"] == 50
    assert _notice(
        tmp_path, order["id"], "new-paid", "checkout.session.completed", 4895
    )["ok"]
    assert service.settle(
        Paid(order["id"], 50, event="invoice-2", kind="renovacion"),
        "stripe",
        home=tmp_path,
    )["ok"]
    assert service.settle(
        Paid(order["id"], 50, event="invoice-2", kind="renovacion"),
        "stripe",
        home=tmp_path,
    )["repetido"]
    assert ledger.totals(home=tmp_path)["ingreso"] == 140.95


def test_refunded_invitation_cannot_be_spent_and_small_plan_is_not_subsidized(
    tmp_path, monkeypatch
):
    _setup(monkeypatch)
    host = _purchase(tmp_path, "host")
    _notice(tmp_path, host, "host-paid", "checkout.session.completed")
    code = referidos.status("host", tmp_path)["codigo"]
    assert referidos.link("guest", code, tmp_path)
    order = _purchase(tmp_path, "guest")
    _notice(tmp_path, order, "guest-paid", "checkout.session.completed")
    service.revoke(order, home=tmp_path)
    monkeypatch.setattr(referidos, "WAIT_SECONDS", 0)
    assert referidos.status("host", tmp_path)["disponibles"] == 0
    assert referidos.status("guest", tmp_path)["disponibles"] == 0
    assert referidos.discount("go", 5, 10) == 0


def test_concurrent_checkouts_cannot_reserve_the_same_award(tmp_path, monkeypatch):
    _setup(monkeypatch)
    monkeypatch.setattr(referidos, "WAIT_SECONDS", 0)
    order = _purchase(tmp_path, "host")
    _notice(tmp_path, order, "host-paid", "checkout.session.completed")
    code = referidos.status("host", tmp_path)["codigo"]
    assert referidos.link("guest", code, tmp_path)
    order = _purchase(tmp_path, "guest")
    _notice(tmp_path, order, "guest-paid", "checkout.session.completed")

    def checkout(_):
        return ledger.new_order(
            "host", "work", 5, 21, "stripe", tmp_path, referral_fee=1.0
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        orders = list(pool.map(checkout, range(4)))
    discounted = [o for o in orders if o["list_usd"]]
    assert len(discounted) == 1
    _notice(tmp_path, discounted[0]["id"], "closed", "checkout.session.expired", 0)
    assert referidos.status("host", tmp_path)["disponibles"] == 1


def test_referral_routes_are_explicitly_allowed_and_deny_owner(monkeypatch):
    _setup(monkeypatch)
    app = FastAPI()
    app.include_router(pagos_routes.router)
    monkeypatch.setattr(
        pagos_routes, "_payer", lambda _: {"id": "owner", "owner": True}
    )
    client = TestClient(app)
    path = "/v1/pagos/referidos"
    assert customer_gate.allowed("GET", path) and customer_gate.allowed("POST", path)
    assert not customer_gate.allowed("DELETE", path)
    assert client.get(path).json() == {"activo": False}
    assert client.post(path, json={"codigo": "A" * 16}).status_code == 404


def test_billing_portal_only_uses_the_signed_in_customers_checkout(
    tmp_path, monkeypatch
):
    import pytest

    _setup(monkeypatch)
    oid = _purchase(tmp_path, "owner-of-subscription")
    ledger.set_ext(oid, "cs_mock", tmp_path)
    _notice(tmp_path, oid, "stripe-paid", "checkout.session.completed")

    class PortalHTTP(StripeHTTP):
        def get(self, url, *, headers):
            assert url.endswith("/checkout/sessions/cs_mock")
            self.status_code = 200
            self.body = {"customer": "cus_owned"}
            return self

        def post(self, url, *, data, headers):
            assert url.endswith("/billing_portal/sessions")
            assert data == {
                "customer": "cus_owned",
                "return_url": "https://app.example/planes",
            }
            self.status_code = 200
            self.body = {"url": "https://billing.stripe.com/p/session/mock"}
            return self

    with pytest.raises(service.PaymentError, match="no tiene un pago"):
        service.billing_portal(
            "other-account", "https://app.example", http=PortalHTTP(), home=tmp_path
        )
    assert service.billing_portal(
        "owner-of-subscription", "https://app.example", http=PortalHTTP(), home=tmp_path
    ).startswith("https://billing.stripe.com/")


def test_paypal_can_charge_the_referral_price_without_stripe(tmp_path, monkeypatch):
    _setup(monkeypatch)
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "fake-client")
    monkeypatch.setenv("PAYPAL_SECRET", "fake-secret")
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "fake-webhook")
    monkeypatch.delenv("PAYPAL_MODO", raising=False)
    monkeypatch.setattr(referidos, "WAIT_SECONDS", 0)
    for uid in ("host", "guest"):
        if uid == "guest":
            assert referidos.link(
                "guest", referidos.status("host", tmp_path)["codigo"], tmp_path
            )
        oid = ledger.new_order(uid, "work", 5, 21, "paypal", tmp_path)["id"]
        assert service.settle(
            Paid(oid, 21, event=f"capture-{uid}"), "paypal", home=tmp_path
        )["ok"]

    class PayPalHTTP:
        def post(self, url, **kw):
            self.status_code = 200
            if url.endswith("/oauth2/token"):
                self.body = {"access_token": "oauth-test"}
            else:
                assert url.endswith("/v2/checkout/orders")
                assert kw["json"]["purchase_units"][0]["amount"]["value"] == "19.95"
                self.body = {
                    "id": "order-paypal",
                    "links": [
                        {
                            "rel": "payer-action",
                            "href": "https://www.paypal.com/checkoutnow",
                        }
                    ],
                }
            return self

        def json(self):
            return self.body

    discounted = service.checkout(
        "guest",
        "work",
        5,
        "paypal",
        "https://app.example",
        http=PayPalHTTP(),
        home=tmp_path,
    )
    assert service.settle(
        Paid(discounted["pedido"], 19.95, event="discount-paid"),
        "paypal",
        home=tmp_path,
    )["ok"]
    assert ledger.totals(home=tmp_path)["ingreso"] == 61.95


def test_reconciled_refund_does_not_debit_twice(tmp_path, monkeypatch):
    _setup(monkeypatch)
    oid = _purchase(tmp_path, "host")
    _notice(tmp_path, oid, "paid", "checkout.session.completed")
    service.revoke(oid, home=tmp_path)
    other = Paid(oid, 21, event="late-provider-refund", kind="reembolso")
    assert service.settle(other, "stripe", home=tmp_path)["repetido"]
    assert ledger.totals(home=tmp_path)["ingreso"] == 0
