"""Prices in local currency (never below the dollar price), limits per plan,
and the /v1/plans routes."""

from __future__ import annotations

import pytest

from openjarvis import pricing, quota, tiers


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    monkeypatch.delenv("SERGIO_PLANES_ACTIVOS", raising=False)
    monkeypatch.delenv("SERGIO_LICENSE_PUBKEY", raising=False)
    return tmp_path


def test_go_is_five_in_dollars_and_euros_never_less():
    assert pricing.price_for(5, "EC")["amount"] == 5  # Ecuador pays dollars
    assert pricing.price_for(5, "US")["currency"] == "USD"
    for country in ("ES", "FR", "DE", "IT", "PT"):
        euro = pricing.price_for(5, country)
        assert euro["currency"] == "EUR" and euro["amount"] == 5
    assert pricing.price_for(5, "GB")["amount"] == 5  # pounds: the same number
    assert pricing.price_for(5, "CH")["currency"] == "CHF"


def test_no_country_ever_pays_less_than_the_dollar_price():
    for country in list(pricing.COUNTRY_NAMES) + ["XX"]:
        for usd in (5, 21, 50, 99, 115, 235):
            price = pricing.price_for(usd, country)
            rate = pricing.RATES[price["currency"]]
            assert price["amount"] / rate >= usd - 1e-9, (country, usd, price)


def test_weaker_currencies_round_up_to_clean_amounts():
    assert pricing.price_for(5, "MX")["amount"] == 95  # 91.5 -> clean 95
    assert pricing.price_for(5, "CO")["amount"] % 100 == 0
    assert pricing.price_for(0, "MX")["amount"] == 0
    assert pricing.format_amount(5, "EUR") == "5 €"
    assert pricing.format_amount(5, "USD") == "$5"


def test_free_is_the_base_and_each_plan_multiplies_it(home):
    assert quota.limits(1)["mensajes"] == quota.BASE_DAILY["mensajes"]
    assert quota.multiplier() == 1
    assert quota.limits(2)["mensajes"] == 2 * quota.BASE_DAILY["mensajes"]
    assert [tiers.PLAN_INFO[p].mult for p in tiers.PLANS] == [1, 2, 5, 10, 25]


def test_use_is_counted_but_only_blocks_when_the_service_asks(home, monkeypatch):
    for _ in range(quota.BASE_DAILY["swarm"] + 3):
        quota.take("swarm")  # personal install: counted, never blocked
    assert quota.used()["swarm"] == quota.BASE_DAILY["swarm"] + 3

    monkeypatch.setenv("SERGIO_PLANES_ACTIVOS", "1")
    with pytest.raises(quota.QuotaExceeded, match="Free"):
        quota.check("swarm")
    quota.check("cowork")  # a different limit is still open
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as err:
        quota.guard("swarm")
    assert err.value.status_code == 402


def test_a_bigger_plan_has_more_room(home, monkeypatch):
    pair = tiers.generate_keypair()
    monkeypatch.setenv("SERGIO_LICENSE_PUBKEY", pair["public"])
    monkeypatch.setenv("SERGIO_PLANES_ACTIVOS", "1")
    for _ in range(quota.BASE_DAILY["swarm"]):
        quota.count("swarm")
    with pytest.raises(quota.QuotaExceeded):
        quota.check("swarm")
    tiers.activate(tiers.issue(pair["private"], "go", holder="Ana"))
    assert quota.multiplier() == 2
    quota.check("swarm")  # x2 leaves room
    tiers.activate(tiers.issue(pair["private"], "dev", holder="Ana", mult=15))
    assert quota.multiplier() == 15
    assert quota.limits()["swarm"] == 15 * quota.BASE_DAILY["swarm"]


def test_plans_routes(home, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server.plans_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    plans = client.get("/v1/plans?country=ES").json()
    assert plans["currency"] == "EUR"
    by_id = {p["id"]: p for p in plans["plans"]}
    assert list(by_id) == ["free", "go", "work", "dev", "founders"]
    assert by_id["go"]["price"]["amount"] == 5 and by_id["go"]["price"]["text"] == "5 €"
    assert by_id["work"]["price"]["amount"] == 19  # 21 dollars, exact, rounded up
    assert (
        by_id["dev"]["stretch"]["mult_min"] == 10
        and by_id["dev"]["stretch"]["mult_max"] == 23
    )
    assert by_id["founders"]["stretch"]["usd_min"] == 99
    assert by_id["founders"]["stretch"]["usd_max"] == 235
    stretched = client.get("/v1/plans?country=US&mult_dev=20").json()["plans"][3]
    assert stretched["mult"] == 20 and stretched["usd"] == round(50 + 65 * 10 / 13)

    me = client.get("/v1/plans/me").json()
    assert me["account"]["plan"] == "free" and me["usage"]["blocking"] is False
    assert {i["kind"] for i in me["usage"]["items"]} == set(quota.BASE_DAILY)

    assert client.post("/v1/plans/checkout", json={"plan": "free"}).status_code == 400
    no_link = client.post("/v1/plans/checkout", json={"plan": "go"})
    assert no_link.status_code == 409 and "pagos" in no_link.json()["detail"]
    monkeypatch.setenv("SERGIO_CHECKOUT_GO", "https://pay.example/go")
    assert client.post("/v1/plans/checkout", json={"plan": "go"}).json() == {
        "url": "https://pay.example/go"
    }
    bad = client.post("/v1/plans/license", json={"key": "sergio-lic-v1.x.y"})
    assert bad.status_code == 400
