"""The audit of 27 Oct 2026: customers fenced in, paid plans that unlock,
payments that survive a crash, voice for customers, OpenRouter's own ids,
Cowork keeping who asked, and a ledger whose newest lines cannot vanish."""

import contextvars
import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from openjarvis import quota, tiers
from openjarvis.accounts import provision
from openjarvis.accounts.store import AccountStore
from openjarvis.pagos import gateways, ledger, service
from openjarvis.server.customer_gate import allowed


# 1 -- a customer cannot touch the owner's things ---------------------------------
def test_the_gate_denies_by_default():
    assert allowed("POST", "/v1/chat/completions")
    assert allowed("GET", "/v1/pagos/pedido/pd_1")
    assert allowed("GET", "/assets/app.js")
    for method, path in [
        ("POST", "/v1/personal/perfil"),
        ("GET", "/v1/connectors"),
        ("GET", "/v1/healthdata/summary"),
        ("GET", "/v1/nodes"),
        ("GET", "/v1/pagos/resumen"),
        ("POST", "/v1/pagos/pedido/pd_1/devolver"),
    ]:
        assert not allowed(method, path), path


@pytest.fixture
def server(tmp_path, monkeypatch):
    from openjarvis.server import accounts_routes
    from openjarvis.server.app import create_app

    store = AccountStore(tmp_path / "c.db")
    monkeypatch.setattr(accounts_routes, "_store", lambda: store)
    owner = store.create(
        email="d@x.ec", canonical="d@x.ec", role="dueño", email_ok=True
    )
    ana = store.create(
        email="a@x.ec", canonical="a@x.ec", role="aprobado", email_ok=True
    )
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["m"]
    client = TestClient(create_app(engine, "m"), raise_server_exceptions=False)
    return (
        client,
        store.open_session(owner["id"], "d"),
        store.open_session(ana["id"], "d"),
    )


def test_a_customer_session_is_fenced_in(server):
    client, _owner, ana = server
    me = {"Authorization": f"Bearer {ana}"}
    assert client.get("/v1/personal/perfil", headers=me).status_code == 403
    assert (
        client.post("/v1/personal/perfil", json={"trato": "tú"}, headers=me).status_code
        == 403
    )
    assert client.get("/v1/connectors", headers=me).status_code == 403
    assert client.get("/v1/models", headers=me).status_code != 403


# 2 -- a paid plan unlocks, with the customer's own limits -----------------------
def test_a_customers_plan_and_limits_are_their_own(monkeypatch):
    monkeypatch.delenv("SERGIO_PLANES_ACTIVOS", raising=False)
    owner_day = quota.today()
    who = provision.CUSTOMER.set("ana")
    plan = provision.CUSTOMER_PLAN.set("dev")
    try:
        assert tiers.current()["plan"] == "dev"
        assert quota.today() != owner_day and quota.today().endswith("|ana")
        assert quota.enforcing()
    finally:
        provision.CUSTOMER_PLAN.reset(plan)
        provision.CUSTOMER.reset(who)
    assert not quota.enforcing()


def test_the_plan_comes_from_the_paid_month(tmp_path, monkeypatch):
    from openjarvis.server import customer_gate

    monkeypatch.setattr(ledger, "_path", lambda home=None: tmp_path / "pagos.db")
    order = ledger.new_order("ana", "dev", 15, 75.0, "stripe")
    ledger.settle_paid("stripe", "e1", order["id"], 9e12, {"ingreso": 75.0})
    assert customer_gate.plan_of("ana") == "dev"


# 3 -- a crash never loses a payment ---------------------------------------------
def test_a_crash_while_recording_leaves_nothing_half_done(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "_activate", lambda *a: True)
    order = ledger.new_order("ana", "go", 0, 5.0, "stripe", tmp_path)
    paid = gateways.Paid(order=order["id"], usd=5.0, event="evt_1")
    real = ledger._write_lines

    def boom(*a, **k):
        raise RuntimeError("se fue la luz")

    monkeypatch.setattr(ledger, "_write_lines", boom)
    with pytest.raises(RuntimeError):
        service.settle(paid, "stripe", home=tmp_path)
    assert ledger.get(order["id"], tmp_path)["status"] == "abierto"
    monkeypatch.setattr(ledger, "_write_lines", real)
    out = service.settle(paid, "stripe", home=tmp_path)  # the processor retries
    assert out["ok"] and not out.get("repetido") and out["recibo"]


def test_a_crash_after_recording_still_switches_the_plan_on(tmp_path, monkeypatch):
    calls = []

    def flaky(uid, plan, usd):
        calls.append(plan)
        if len(calls) == 1:
            raise RuntimeError("OpenRouter no respondió")
        return True

    monkeypatch.setattr(service, "_activate", flaky)
    order = ledger.new_order("ana", "go", 0, 5.0, "stripe", tmp_path)
    paid = gateways.Paid(order=order["id"], usd=5.0, event="evt_2")
    with pytest.raises(RuntimeError):
        service.settle(paid, "stripe", home=tmp_path)
    again = service.settle(paid, "stripe", home=tmp_path)
    assert again["repetido"] and calls == ["go", "go"]
    assert ledger.totals(home=tmp_path)["ingreso"] == 5.0  # recorded once


# 4 -- a customer's session opens the voice --------------------------------------
def test_voice_accepts_a_customers_session(monkeypatch):
    from openjarvis.server import auth_middleware

    monkeypatch.setattr(auth_middleware, "_account_token", lambda t: t == "sg_ana")
    ws = SimpleNamespace(headers={"authorization": "Bearer sg_ana"})
    monkeypatch.setattr(
        auth_middleware, "_offered_websocket_auth", lambda w: ("", None)
    )
    assert auth_middleware.authenticate_websocket(ws, "oj_sk_owner")[0]
    assert auth_middleware.websocket_session_token(ws) == "sg_ana"
    ws.headers = {"authorization": "Bearer sg_otro"}
    assert not auth_middleware.authenticate_websocket(ws, "oj_sk_owner")[0]


# 5 -- OpenRouter's own router keeps its name ------------------------------------
def test_openrouter_ids():
    from openjarvis.engine.cloud import _openrouter_id

    assert _openrouter_id("openrouter/auto") == "openrouter/auto"
    assert (
        _openrouter_id("openrouter/anthropic/claude-sonnet-5-5")
        == "anthropic/claude-sonnet-5-5"
    )


# 6 -- Cowork's worker keeps who asked -------------------------------------------
def test_cowork_thread_keeps_the_customers_key():
    import inspect

    from openjarvis.cowork import session

    src = inspect.getsource(session)
    assert "contextvars.copy_context()" in src
    seen = []
    token = provision.CUSTOMER_KEY.set("sk-or-ana")
    try:
        ctx = contextvars.copy_context()
        t = threading.Thread(
            target=ctx.run, args=(lambda: seen.append(provision.CUSTOMER_KEY.get()),)
        )
        t.start()
        t.join()
    finally:
        provision.CUSTOMER_KEY.reset(token)
    assert seen == ["sk-or-ana"]


# 7 -- removing the newest ledger line is noticed --------------------------------
def test_removing_the_last_line_breaks_the_seal(tmp_path):
    order = ledger.new_order("ana", "go", 0, 5.0, "stripe", tmp_path)
    ledger.settle_paid(
        "stripe", "e", order["id"], 9e12, {"ingreso": 5.0, "margen": 2.0}, tmp_path
    )
    assert ledger.verify(tmp_path)["integro"]
    with sqlite3.connect(tmp_path / "pagos.db") as db:
        db.execute("DELETE FROM entries WHERE rowid = (SELECT MAX(rowid) FROM entries)")
    assert not ledger.verify(tmp_path)["integro"]
    with sqlite3.connect(tmp_path / "pagos.db") as db:
        db.execute("DELETE FROM meta")
    assert not ledger.verify(tmp_path)["integro"]
