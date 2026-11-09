"""Open sign-up: terms and age, a clean sign-up, and the e-mail code."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.accounts import senders
from openjarvis.accounts import store as store_mod
from openjarvis.server import accounts_routes as R


@pytest.fixture()
def api(tmp_path, monkeypatch):
    st = store_mod.AccountStore(tmp_path / "cuentas.db")
    monkeypatch.setattr(R, "_store", lambda: st)
    sent = []
    monkeypatch.setattr(senders, "smtp_ready", lambda: True)
    monkeypatch.setattr(
        senders, "send_email_code", lambda to, code: sent.append((to, code))
    )
    monkeypatch.setattr(R, "_first_local", lambda request: False)
    monkeypatch.setattr(R, "_limit", lambda request: None)
    app = FastAPI()
    app.include_router(R.router)
    return TestClient(app), st, sent


GOOD = {
    "email": "ana.perez@gmail.com",
    "password": "una-clave-larga-y-buena-7",
    "device": "d1",
}


def test_closed_by_default_the_owner_still_approves(api, monkeypatch):
    client, st, _sent = api
    monkeypatch.delenv("SERGIO_REGISTRO", raising=False)
    r = client.post("/v1/cuentas/registro", json=GOOD)
    assert r.status_code == 200
    user = st.find(canonical="anaperez@gmail.com") or st.users()[0]
    assert user["role"] == "pendiente" and st.consent_of(user["id"]) is None


def test_open_needs_terms_and_age(api, monkeypatch):
    client, st, _ = api
    monkeypatch.setenv("SERGIO_REGISTRO", "abierto")
    assert client.get("/v1/cuentas/estado").json()["edad_minima"] == 18
    assert client.post("/v1/cuentas/registro", json=GOOD).status_code == 400
    assert (
        client.post("/v1/cuentas/registro", json={**GOOD, "acepta": True}).status_code
        == 400
    )
    assert st.users() == []  # nothing was created by the refused tries


def test_open_clean_signup_opens_only_after_the_email_code(api, monkeypatch):
    client, st, sent = api
    monkeypatch.setenv("SERGIO_REGISTRO", "abierto")
    r = client.post(
        "/v1/cuentas/registro", json={**GOOD, "acepta": True, "mayor": True}
    )
    assert r.json()["status"] == "codigo" and sent
    user = st.users()[0]
    assert user["role"] == "pendiente"  # no code yet, no access
    consent = st.consent_of(user["id"])
    assert (
        consent["terms"] == "2026-11-08"
        and consent["adult"] == 1
        and consent["auto"] == 1
    )
    bad = client.post(
        "/v1/cuentas/verificar",
        json={"email": GOOD["email"], "code": "000000", "device": "d1"},
    )
    assert bad.status_code == 400 and st.users()[0]["role"] == "pendiente"
    ok = client.post(
        "/v1/cuentas/verificar",
        json={"email": GOOD["email"], "code": sent[-1][1], "device": "d1"},
    )
    assert ok.status_code == 200 and ok.json()["status"] == "dentro"
    assert st.users()[0]["role"] == "aprobado" and st.users()[0]["email_ok"]


def test_open_doubtful_signup_still_waits_for_the_owner(api, monkeypatch):
    client, st, sent = api
    monkeypatch.setenv("SERGIO_REGISTRO", "abierto")
    from openjarvis.accounts import fraud

    monkeypatch.setattr(
        fraud,
        "check",
        lambda *a, **k: {
            "action": "review",
            "reasons": ["red repetida"],
            "network": "n",
        },
    )
    client.post("/v1/cuentas/registro", json={**GOOD, "acepta": True, "mayor": True})
    assert st.consent_of(st.users()[0]["id"])["auto"] == 0
    r = client.post(
        "/v1/cuentas/verificar",
        json={"email": GOOD["email"], "code": sent[-1][1], "device": "d1"},
    )
    assert st.users()[0]["role"] == "pendiente" and r.json()["status"] == "pendiente"


def test_open_without_a_way_to_send_the_code_is_refused_before_creating(
    api, monkeypatch
):
    client, st, _ = api
    monkeypatch.setenv("SERGIO_REGISTRO", "abierto")
    monkeypatch.setattr(senders, "smtp_ready", lambda: False)
    r = client.post(
        "/v1/cuentas/registro", json={**GOOD, "acepta": True, "mayor": True}
    )
    assert r.status_code == 503 and st.users() == []


def test_oauth_and_sms_cannot_create_public_accounts_without_consent(api, monkeypatch):
    from urllib.parse import unquote

    from openjarvis.accounts import oauth

    client, st, _ = api
    monkeypatch.setenv("SERGIO_REGISTRO", "abierto")
    monkeypatch.setattr(senders, "check_sms_code", lambda number, code: True)
    monkeypatch.setattr(
        oauth,
        "finish",
        lambda *args: {
            "subject": "testing-only",
            "email": GOOD["email"],
            "email_ok": True,
            "device": "d1",
        },
    )
    sms = client.post(
        "/v1/cuentas/telefono/entrar",
        json={"phone": "+593991234567", "code": "123456", "device": "d1"},
    )
    assert sms.status_code == 403
    callback = client.get("/v1/cuentas/oauth/google/vuelta", follow_redirects=False)
    assert callback.status_code == 303
    assert "Cree primero su cuenta por correo" in unquote(callback.headers["location"])
    assert st.users() == []
