"""Sergio Pagos: orders, signed notices, ledger and plan activation."""

import hashlib
import hmac
import json
import time

import pytest

from openjarvis.accounts import provision
from openjarvis.pagos import gateways, ledger, service


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


class _Http:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        for part, data in self.answers.items():
            if part in url:
                return _Resp(data)
        return _Resp({}, 404)

    def get(self, url, **kw):
        return self.post(url, **kw)


@pytest.fixture
def stripe_on(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")


@pytest.fixture
def activations(monkeypatch):
    seen = []
    monkeypatch.setattr(
        service,
        "_activate",
        lambda uid, plan, usd: seen.append((uid, plan, usd)) or True,
    )
    return seen


def _signed(body: bytes, secret=b"whsec_test", stamp=None):
    stamp = str(int(stamp or time.time()))
    sig = hmac.new(secret, stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={stamp},v1={sig}"}


def _stripe_checkout(tmp_path, plan="go"):
    http = _Http(
        {"checkout/sessions": {"id": "cs_1", "url": "https://checkout.stripe.com/x"}}
    )
    out = service.checkout(
        "u1", plan, 0, "stripe", "https://sergio.test", http=http, home=tmp_path
    )
    return out, http


def test_only_switched_on_methods_are_offered(monkeypatch, stripe_on):
    for name in ("PAYPAL_CLIENT_ID", "HYPERSWITCH_URL"):
        monkeypatch.delenv(name, raising=False)
    assert [m["id"] for m in service.methods()] == ["stripe"]


def test_free_is_never_charged_and_needs_an_account(tmp_path, stripe_on):
    with pytest.raises(service.PaymentError):
        service.checkout("u1", "free", 0, "stripe", "https://s", home=tmp_path)
    with pytest.raises(service.PaymentError):
        service.checkout("", "go", 0, "stripe", "https://s", home=tmp_path)


def test_checkout_opens_the_processors_page(tmp_path, stripe_on):
    out, http = _stripe_checkout(tmp_path)
    assert out["url"].startswith("https://checkout.stripe.com/")
    url, kw = http.calls[0]
    form = kw["data"]
    assert form["line_items[0][price_data][unit_amount]"] == "500"
    assert form["client_reference_id"] == out["pedido"]
    assert "/v1/pagos/vuelta/stripe?pedido=" in form["success_url"]
    assert ledger.get(out["pedido"], tmp_path)["ext"] == "cs_1"


def test_a_signed_payment_switches_the_plan_on_and_fills_the_ledger(
    tmp_path, stripe_on, activations, monkeypatch
):
    monkeypatch.setenv("SERGIO_MARGEN", "0.4")
    out, _ = _stripe_checkout(tmp_path)
    body = json.dumps(
        {
            "id": "evt_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": out["pedido"],
                    "amount_total": 500,
                    "payment_status": "paid",
                    "subscription": "sub_1",
                }
            },
        }
    ).encode()
    done = service.notice("stripe", _signed(body), body, home=tmp_path)
    assert done[0]["ok"] and activations == [("u1", "go", 5.0)]
    # The same notice twice counts once.
    again = service.notice("stripe", _signed(body), body, home=tmp_path)
    assert again[0].get("repetido") and len(activations) == 1
    t = ledger.totals(home=tmp_path)
    assert t["ingreso"] == 5.0 and t["proveedor"] == 3.0
    assert t["comision"] == round(5 * 0.029 + 0.30, 2)
    assert t["margen"] == round(5 - t["comision"] - 3.0, 2)
    assert service.order(out["pedido"], "u1", home=tmp_path)["estado"] == "pagado"
    assert service.order(out["pedido"], "otro", home=tmp_path) is None


def test_forged_old_or_short_notices_do_nothing(tmp_path, stripe_on, activations):
    out, _ = _stripe_checkout(tmp_path)
    good = {
        "id": "e",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": out["pedido"],
                "amount_total": 500,
                "payment_status": "paid",
            }
        },
    }
    body = json.dumps(good).encode()
    with pytest.raises(gateways.GatewayError):
        service.notice("stripe", _signed(body, secret=b"otra"), body, home=tmp_path)
    with pytest.raises(gateways.GatewayError):
        service.notice(
            "stripe", _signed(body, stamp=time.time() - 3600), body, home=tmp_path
        )
    good["data"]["object"]["amount_total"] = 1
    cheap = json.dumps(good).encode()
    assert not service.notice("stripe", _signed(cheap), cheap, home=tmp_path)[0]["ok"]
    assert activations == []


def test_a_month_without_renewal_goes_back_to_free(
    tmp_path, stripe_on, activations, monkeypatch
):
    out, _ = _stripe_checkout(tmp_path)
    paid = gateways.Paid(order=out["pedido"], usd=5.0, event="e1")
    service.settle(paid, "stripe", home=tmp_path)
    downgraded = []
    monkeypatch.setattr(provision, "key_for", lambda uid: "sk")
    monkeypatch.setattr(
        provision, "set_plan", lambda uid, plan, **k: downgraded.append((uid, plan))
    )
    assert service.expire(now=time.time() + 10 * 86400, home=tmp_path) == []
    renew = gateways.Paid(order=out["pedido"], usd=5.0, event="e2", kind="renovacion")
    service.settle(renew, "stripe", home=tmp_path)
    # A renewal adds a month after the one already paid.
    assert service.expire(now=time.time() + 40 * 86400, home=tmp_path) == []
    assert service.expire(now=time.time() + 70 * 86400, home=tmp_path) == ["u1"]
    assert downgraded == [("u1", "free")]


def test_paypal_is_captured_on_return(tmp_path, monkeypatch, activations):
    for name, v in (
        ("PAYPAL_CLIENT_ID", "id"),
        ("PAYPAL_SECRET", "s"),
        ("PAYPAL_WEBHOOK_ID", "wh"),
    ):
        monkeypatch.setenv(name, v)
    http = _Http(
        {
            "oauth2/token": {"access_token": "tok"},
            "/capture": None,
            "checkout/orders": {
                "id": "PP1",
                "links": [{"rel": "payer-action", "href": "https://paypal.test/pay"}],
            },
        }
    )
    out = service.checkout(
        "u1", "work", 0, "paypal", "https://s", http=http, home=tmp_path
    )
    assert out["url"] == "https://paypal.test/pay"
    http.answers["/capture"] = {
        "id": "PP1",
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {
                            "id": "CAP1",
                            "status": "COMPLETED",
                            "custom_id": out["pedido"],
                            "amount": {"value": "21.00"},
                        }
                    ]
                }
            }
        ],
    }
    # Wrong processor id: nothing is captured.
    assert not service.come_back(
        "paypal", out["pedido"], {"token": "PP9"}, http=http, home=tmp_path
    ).get("clave_ia")
    done = service.come_back(
        "paypal", out["pedido"], {"token": "PP1"}, http=http, home=tmp_path
    )
    assert done["ok"] and activations == [("u1", "work", 21.0)]


def test_hyperswitch_notice_signature(tmp_path, monkeypatch, activations):
    for name, v in (
        ("HYPERSWITCH_URL", "https://hs.test"),
        ("HYPERSWITCH_API_KEY", "k"),
        ("HYPERSWITCH_HASH_KEY", "hash"),
    ):
        monkeypatch.setenv(name, v)
    http = _Http(
        {
            "/payments": {
                "payment_id": "pay_1",
                "payment_link": {"link": "https://hs.test/link"},
            }
        }
    )
    out = service.checkout(
        "u1", "go", 0, "hyperswitch", "https://s", http=http, home=tmp_path
    )
    body = json.dumps(
        {
            "event_id": "ev",
            "event_type": "payment_succeeded",
            "content": {
                "object": {
                    "status": "succeeded",
                    "amount": 500,
                    "metadata": {"pedido": out["pedido"]},
                }
            },
        }
    ).encode()
    sig = hmac.new(b"hash", body, hashlib.sha512).hexdigest()
    with pytest.raises(gateways.GatewayError):
        service.notice(
            "hyperswitch", {"x-webhook-signature-512": "0" * 128}, body, home=tmp_path
        )
    assert service.notice(
        "hyperswitch", {"x-webhook-signature-512": sig}, body, home=tmp_path
    )[0]["ok"]
    assert activations == [("u1", "go", 5.0)]


def test_webhook_routes_are_open_but_the_rest_is_not():
    from openjarvis.server.auth_middleware import AuthMiddleware

    assert not AuthMiddleware._requires_auth("/v1/pagos/aviso/stripe")
    assert not AuthMiddleware._requires_auth("/v1/pagos/vuelta/paypal")
    assert AuthMiddleware._requires_auth("/v1/pagos/resumen")
    assert AuthMiddleware._requires_auth("/v1/pagos/checkout")
