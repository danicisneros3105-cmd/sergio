"""Credits (creditos.py): signed codes that count once, spent past the limit."""

from __future__ import annotations

import pytest

from openjarvis import creditos, quota, tiers


@pytest.fixture
def keys(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    pair = tiers.generate_keypair()
    monkeypatch.setenv("SERGIO_LICENSE_PUBKEY", pair["public"])
    return pair


def test_a_code_adds_credits_once(keys):
    code = creditos.issue(keys["private"], 100, holder="Ana")
    assert creditos.balance() == 0
    assert creditos.redeem(code) == 100
    with pytest.raises(tiers.LicenseError, match="ya se usó"):
        creditos.redeem(code)
    assert creditos.balance() == 100


def test_forged_or_foreign_codes_are_refused(keys):
    other = tiers.generate_keypair()
    with pytest.raises(tiers.LicenseError, match="no es auténtico"):
        creditos.redeem(creditos.issue(other["private"], 1000))
    with pytest.raises(tiers.LicenseError, match="mal formado"):
        creditos.redeem("sergio-cred-v1.abc")
    # A license is not a credit code.
    with pytest.raises(tiers.LicenseError):
        creditos.redeem(tiers.issue(keys["private"], "work", holder="x"))
    assert creditos.balance() == 0


def test_credits_pay_past_todays_limit(keys, monkeypatch):
    monkeypatch.setenv("SERGIO_PLANES_ACTIVOS", "1")
    monkeypatch.setattr(
        quota, "limits", lambda mult=None: {k: 1 for k in quota.BASE_DAILY}
    )
    quota.take("cowork")  # the day's one
    with pytest.raises(quota.QuotaExceeded):
        quota.take("cowork")  # no credits yet
    creditos.redeem(creditos.issue(keys["private"], 7))
    quota.take("cowork")  # paid with 5 credits
    assert creditos.balance() == 2
    with pytest.raises(quota.QuotaExceeded, match="compre créditos"):
        quota.take("cowork")
    assert creditos.balance() == 2  # nothing taken when it cannot pay


def test_packs_show_local_prices_never_below_dollars(keys):
    packs = creditos.packs("MX", {"MXN": 18.3})
    assert [p["creditos"] for p in packs] == [n for _i, n, _u in creditos.PACKS]
    for p, (_i, _n, usd) in zip(packs, creditos.PACKS):
        assert p["precio"]["currency"] == "MXN" and p["precio"]["amount"] >= usd * 18.3
        assert p["pago"] is False  # no payment link set on this computer


def test_routes(keys):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server.plans_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/v1/plans/creditos?country=EC").json()["saldo"] == 0
    assert (
        client.post("/v1/plans/creditos/checkout", json={"pack": "c100"}).status_code
        == 409
    )
    assert (
        client.post("/v1/plans/creditos/checkout", json={"pack": "nada"}).status_code
        == 404
    )
    code = creditos.issue(keys["private"], 300)
    assert client.post("/v1/plans/creditos", json={"key": code}).json() == {
        "saldo": 300
    }
    assert client.post("/v1/plans/creditos", json={"key": code}).status_code == 400
