"""Sergio Pagos, the hardening: sealed AI keys, a sealed ledger, refunds,
currency, the owner's real test charge, live-mode guards and the checklist."""

import json
import sqlite3
import time

import pytest

from openjarvis.accounts import provision
from openjarvis.pagos import cifrado, gateways, ledger, service


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


class _Keys:
    def request(self, method, url, json, headers):
        if method == "POST":
            return _Resp({"key": "sk-or-secreta", "data": {"hash": "h1"}})
        return _Resp({"data": {}})


class _Stripe:
    def __init__(self):
        self.form = None
        self.headers = None

    def post(self, url, data=None, headers=None, **kw):
        self.form, self.headers = data, headers
        return _Resp({"id": "cs_1", "url": "https://checkout.stripe.com/x"})

    def get(self, url, headers=None, **kw):
        return _Resp({}, 200 if "sk_test_bueno" in headers["Authorization"] else 401)


@pytest.fixture
def stripe(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_bueno")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    for name in ("PAYPAL_CLIENT_ID", "HYPERSWITCH_URL"):
        monkeypatch.delenv(name, raising=False)
    return _Stripe()


@pytest.fixture
def no_activation(monkeypatch):
    seen = []
    monkeypatch.setattr(service, "_activate", lambda *a: seen.append(a) or True)
    return seen


# -- the customers' AI keys are sealed ----------------------------------------
def test_ai_keys_are_sealed_and_tied_to_their_customer(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "mgmt")
    monkeypatch.delenv("SERGIO_CLAVE_MAESTRA", raising=False)
    assert provision.ensure("ana", "go", http=_Keys(), home=tmp_path)
    raw = (tmp_path / "cuentas_claves.json").read_text()
    assert "sk-or-secreta" not in raw and '"sealed": "v2:' in raw
    assert provision.key_for("ana", home=tmp_path) == "sk-or-secreta"
    assert (tmp_path / "clave_maestra").stat().st_mode & 0o077 == 0
    # Copied to another customer, the sealed key does not open.
    data = json.loads(raw)
    data["luis"] = dict(data["ana"])
    (tmp_path / "cuentas_claves.json").write_text(json.dumps(data))
    assert provision.key_for("luis", home=tmp_path) == ""


def test_keys_saved_before_sealing_are_sealed_on_first_read(tmp_path):
    (tmp_path / "cuentas_claves.json").write_text(
        json.dumps({"ana": {"key": "sk-or-vieja", "hash": "h", "plan": "go"}})
    )
    assert provision.key_for("ana", home=tmp_path) == "sk-or-vieja"
    assert "sk-or-vieja" not in (tmp_path / "cuentas_claves.json").read_text()


def test_a_master_key_from_the_environment_and_wrong_ones(tmp_path, monkeypatch):
    import base64
    import secrets

    monkeypatch.setenv(
        "SERGIO_CLAVE_MAESTRA", base64.b64encode(secrets.token_bytes(32)).decode()
    )
    box = cifrado.seal("hola", aad="x", home=tmp_path)
    assert cifrado.unseal(box, aad="x", home=tmp_path) == "hola"
    assert not (tmp_path / "clave_maestra").exists()
    monkeypatch.setenv(
        "SERGIO_CLAVE_MAESTRA", base64.b64encode(secrets.token_bytes(32)).decode()
    )
    with pytest.raises(cifrado.SealError):
        cifrado.unseal(box, aad="x", home=tmp_path)


# -- the ledger is sealed -----------------------------------------------------
def _paid_order(tmp_path, stripe, plan="go", uid="ana"):
    out = service.checkout(
        uid,
        plan,
        0,
        "stripe",
        "https://s",
        owner=plan == "prueba",
        http=stripe,
        home=tmp_path,
    )
    usd = ledger.get(out["pedido"], tmp_path)["usd"]
    done = service.settle(
        gateways.Paid(order=out["pedido"], usd=usd, event=out["pedido"]),
        "stripe",
        home=tmp_path,
    )
    return out["pedido"], done


def test_the_ledger_detects_a_line_changed_by_hand(tmp_path, stripe, no_activation):
    _paid_order(tmp_path, stripe)
    _paid_order(tmp_path, stripe, plan="work", uid="luis")
    assert ledger.verify(tmp_path) == {"integro": True, "lineas": 8, "rota_en": None}
    with sqlite3.connect(tmp_path / "pagos.db") as db:
        db.execute("UPDATE entries SET usd = 999 WHERE rowid = 6")
    check = ledger.verify(tmp_path)
    assert not check["integro"] and check["rota_en"] == 6
    with sqlite3.connect(tmp_path / "pagos.db") as db:
        db.execute(
            "UPDATE entries SET usd = 0.3 WHERE rowid = 6"
        )  # put back… wrong value
        db.execute("DELETE FROM entries WHERE rowid = 2")
    assert not ledger.verify(tmp_path)["integro"]


def test_each_paid_order_gets_a_receipt_number(tmp_path, stripe, no_activation):
    year = time.strftime("%Y")
    _, first = _paid_order(tmp_path, stripe)
    _, second = _paid_order(tmp_path, stripe, uid="luis")
    assert (
        first["recibo"] == f"SG-{year}-000001"
        and second["recibo"] == f"SG-{year}-000002"
    )


# -- refunds, chargebacks and the wrong currency -------------------------------
def test_a_refund_is_new_lines_and_ends_the_plan(
    tmp_path, stripe, no_activation, monkeypatch
):
    downgraded = []
    monkeypatch.setattr(provision, "key_for", lambda uid: "sk")
    monkeypatch.setattr(
        provision, "set_plan", lambda uid, plan, **k: downgraded.append((uid, plan))
    )
    oid, _ = _paid_order(tmp_path, stripe)
    out = service.settle(
        gateways.Paid(order=oid, usd=5.0, event="re1", kind="reembolso"),
        "stripe",
        home=tmp_path,
    )
    assert out["reembolso"] == 5.0 and downgraded == [("ana", "free")]
    assert ledger.totals(home=tmp_path)["ingreso"] == 0.0
    assert ledger.get(oid, tmp_path)["status"] == "reembolsado"
    assert ledger.verify(tmp_path)["integro"]
    assert service.expire(now=time.time() + 5, home=tmp_path) == []


def test_the_owner_records_a_refund_made_in_the_dashboard(
    tmp_path, stripe, no_activation
):
    oid, _ = _paid_order(tmp_path, stripe)
    assert service.revoke(oid, home=tmp_path)["reembolso"] == 5.0
    with pytest.raises(service.PaymentError):
        service.revoke(oid, home=tmp_path)


def test_paypal_refund_and_chargeback_notices(monkeypatch):
    for name, v in (
        ("PAYPAL_CLIENT_ID", "i"),
        ("PAYPAL_SECRET", "s"),
        ("PAYPAL_WEBHOOK_ID", "w"),
    ):
        monkeypatch.setenv(name, v)
    gw = gateways.PayPal()
    monkeypatch.setattr(gw, "_call", lambda *a, **k: {"verification_status": "SUCCESS"})
    for kind in ("PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"):
        body = json.dumps(
            {
                "id": "WH",
                "event_type": kind,
                "resource": {
                    "id": "R1",
                    "custom_id": "pd_1",
                    "amount": {"value": "5.00", "currency_code": "USD"},
                },
            }
        ).encode()
        (paid,) = gw.notice({}, body)
        assert paid.kind == "reembolso" and paid.order == "pd_1" and paid.usd == 5.0


def test_money_in_another_currency_is_not_accepted(tmp_path, stripe, no_activation):
    out = service.checkout(
        "ana", "go", 0, "stripe", "https://s", http=stripe, home=tmp_path
    )
    done = service.settle(
        gateways.Paid(order=out["pedido"], usd=500, event="e", currency="COP"),
        "stripe",
        home=tmp_path,
    )
    assert not done["ok"] and no_activation == []


# -- the owner's real test charge ---------------------------------------------
def test_only_the_owner_makes_the_one_dollar_test(tmp_path, stripe, no_activation):
    with pytest.raises(service.PaymentError):
        service.checkout(
            "ana", "prueba", 0, "stripe", "https://s", http=stripe, home=tmp_path
        )
    with pytest.raises(service.PaymentError):
        service.checkout(
            "dueño",
            "go",
            0,
            "stripe",
            "https://s",
            owner=True,
            http=stripe,
            home=tmp_path,
        )
    oid, done = _paid_order(tmp_path, stripe, plan="prueba", uid="dueño")
    assert (
        stripe.form["mode"] == "payment"
        and stripe.form["line_items[0][price_data][unit_amount]"] == "100"
    )
    assert "recurring" not in json.dumps(stripe.form) and stripe.headers[
        "Idempotency-Key"
    ].startswith("sergio-pd_")
    assert done["ok"] and done["recibo"] and no_activation == []
    assert service.summary(home=tmp_path)["clientes_activos"] == 0
    assert service.expire(now=time.time() + 99 * 86400, home=tmp_path) == []


# -- guards ---------------------------------------------------------------------
def test_real_money_needs_https(tmp_path, stripe, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_x")
    with pytest.raises(service.PaymentError, match="https"):
        service.checkout(
            "ana",
            "go",
            0,
            "stripe",
            "http://192.168.1.5:8000",
            http=stripe,
            home=tmp_path,
        )
    assert service.methods()[0]["real"] is True


def test_too_many_attempts_are_slowed_down(tmp_path, stripe):
    for _ in range(service.MAX_OPEN):
        service.checkout(
            "ana", "go", 0, "stripe", "https://s", http=stripe, home=tmp_path
        )
    with pytest.raises(service.PaymentError, match="Demasiados"):
        service.checkout(
            "ana", "go", 0, "stripe", "https://s", http=stripe, home=tmp_path
        )


def test_the_owners_checklist(stripe, monkeypatch):
    monkeypatch.delenv("OPENROUTER_MANAGEMENT_KEY", raising=False)
    out = service.readiness("https://sergio.example", online=True, http=stripe)
    assert not out["listo"]
    steps = {s["paso"]: s for s in out["pasos"]}
    assert (
        steps["Tarjeta: claves puestas"]["ok"]
        and "prueba" in steps["Tarjeta: claves puestas"]["detalle"]
    )
    assert not steps["Claves de IA por cliente (OpenRouter)"]["ok"]
    assert out["avisos"]["stripe"] == "https://sergio.example/v1/pagos/aviso/stripe"
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_malo")
    assert not service.readiness("https://s", online=True, http=stripe)["pasos"][0][
        "ok"
    ]
