"""The whole road through the real routes: a customer pays, the processor's
signed notice arrives, the plan and the customer's AI key switch on, the
owner sees it in his ledger. Stripe and OpenRouter are stand-ins that answer
like their published APIs; no card and no real money are involved."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.accounts import provision
from openjarvis.accounts.store import AccountStore
from openjarvis.pagos import gateways, ledger


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


class _World:
    """Stripe and OpenRouter as seen from Sergio."""

    def __init__(self):
        self.stripe_form = None
        self.keys = []

    def post(self, url, data=None, json=None, headers=None, **kw):
        assert url == "https://api.stripe.com/v1/checkout/sessions"
        assert headers["Authorization"] == "Bearer sk_test_sergio"
        self.stripe_form = data
        return _Resp(
            {"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"}
        )

    def request(self, method, url, json=None, headers=None):
        self.keys.append((method, url, json))
        if method == "POST":
            return _Resp({"key": "sk-or-cliente", "data": {"hash": "h1"}})
        return _Resp({"data": {}})


@pytest.fixture
def road(tmp_path, monkeypatch):
    from openjarvis.server import accounts_routes, pagos_routes

    store = AccountStore(tmp_path / "c.db")
    monkeypatch.setattr(accounts_routes, "_store", lambda: store)
    monkeypatch.setattr(ledger, "_path", lambda home=None: tmp_path / "pagos.db")
    monkeypatch.setattr(provision, "_path", lambda home=None: tmp_path / "claves.json")
    world = _World()
    monkeypatch.setattr(gateways, "_http", lambda: world)
    monkeypatch.setattr(provision, "_http", lambda: world)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_sergio")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_sergio")
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "mgmt")
    monkeypatch.setenv("SERGIO_MARGEN", "0.4")
    monkeypatch.setenv("SERGIO_PUBLIC_URL", "https://sergio.example")
    app = FastAPI()
    app.include_router(accounts_routes.router)
    app.include_router(pagos_routes.router)
    store.create(
        email="d@gmail.com", canonical="d@gmail.com", role="dueño", email_ok=True
    )
    ana = store.create(
        email="a@gmail.com", canonical="a@gmail.com", role="aprobado", email_ok=True
    )
    token = store.open_session(ana["id"], "dev")
    return TestClient(app), world, ana, token


def _notice(event: dict, secret=b"whsec_sergio"):
    body = json.dumps(event).encode()
    stamp = str(int(time.time()))
    sig = hmac.new(secret, stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return body, {
        "Stripe-Signature": f"t={stamp},v1={sig}",
        "Content-Type": "application/json",
    }


def test_a_customer_pays_and_everything_switches_on_by_itself(road):
    client, world, ana, token = road
    me = {"Authorization": f"Bearer {token}"}

    # 1. Without an account nobody pays; with hers, the processor's page opens.
    assert (
        client.post(
            "/v1/pagos/checkout", json={"plan": "work", "metodo": "stripe"}
        ).status_code
        == 401
    )
    out = client.post(
        "/v1/pagos/checkout", json={"plan": "work", "metodo": "stripe"}, headers=me
    )
    assert out.status_code == 200, out.text
    order = out.json()["pedido"]
    assert out.json()["url"].startswith("https://checkout.stripe.com/")
    assert world.stripe_form["line_items[0][price_data][unit_amount]"] == "2100"
    assert (
        world.stripe_form["success_url"]
        == f"https://sergio.example/v1/pagos/vuelta/stripe?pedido={order}"
    )

    # 2. Back from Stripe before its notice: «confirmando», nothing switched on yet.
    back = client.get(f"/v1/pagos/vuelta/stripe?pedido={order}", follow_redirects=False)
    assert (
        back.status_code == 303
        and back.headers["location"] == f"/pagar/listo?pedido={order}"
    )
    assert (
        client.get(f"/v1/pagos/pedido/{order}", headers=me).json()["estado"]
        == "abierto"
    )
    assert world.keys == []

    # 3. A forged notice is refused and changes nothing.
    paid = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": order,
                "amount_total": 2100,
                "payment_status": "paid",
                "subscription": "sub_1",
            }
        },
    }
    body, headers = _notice(paid, secret=b"falso")
    assert (
        client.post("/v1/pagos/aviso/stripe", content=body, headers=headers).status_code
        == 400
    )
    assert (
        client.get(f"/v1/pagos/pedido/{order}", headers=me).json()["estado"]
        == "abierto"
    )

    # 4. Stripe's real notice: paid, the plan and her AI key switch on.
    body, headers = _notice(paid)
    assert (
        client.post("/v1/pagos/aviso/stripe", content=body, headers=headers).json()[
            "aplicados"
        ]
        == 1
    )
    state = client.get(f"/v1/pagos/pedido/{order}", headers=me).json()
    assert state["estado"] == "pagado" and state["hasta"] > time.time() + 30 * 86400
    method, url, created = world.keys[0]
    assert (
        method == "POST"
        and created["limit"] == 12.6
        and created["limit_reset"] == "monthly"
    )
    assert provision.status(ana["id"])["plan"] == "work"

    # 5. Stripe retries the same notice: nothing is charged or created twice.
    client.post("/v1/pagos/aviso/stripe", content=body, headers=headers)
    assert len(world.keys) == 1

    # 6. The owner's ledger.
    money = client.get("/v1/pagos/resumen").json()["mes"]
    assert money["ingreso"] == 21.0 and money["proveedor"] == 12.6
    assert money["comision"] == round(21 * 0.029 + 0.30, 2)
    assert money["margen"] == round(21 - money["comision"] - 12.6, 2)

    # 7. Another customer, from outside (through the tunnel), cannot see it.
    assert client.get(
        f"/v1/pagos/pedido/{order}",
        headers={"Authorization": "Bearer sg_otro", "X-Forwarded-For": "1.2.3.4"},
    ).status_code in (403, 404)
