"""Exercise the account lifecycle through HTTP against a temporary SQLite store."""

from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from openjarvis.accounts import autoconfig, senders
from openjarvis.accounts.registro import TERMS_VERSION
from openjarvis.accounts.store import AccountStore
from openjarvis.server import accounts_routes
from openjarvis.server.auth_middleware import AuthMiddleware


def test_open_signup_verify_login_logout_and_replay(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(accounts_routes.router)
    app.add_middleware(AuthMiddleware, api_key="test-server-key")
    store = AccountStore(tmp_path / "account-journey.db")
    mailbox = []

    @app.get("/v1/test/private")
    def private(request: Request):
        return {"user": accounts_routes._me(request)["email"]}

    monkeypatch.setenv("SERGIO_REGISTRO", "abierto")
    monkeypatch.setattr(accounts_routes, "_store", lambda: store)
    monkeypatch.setattr(accounts_routes, "_hits", defaultdict(deque))
    monkeypatch.setattr(autoconfig, "in_background", lambda user: None)
    monkeypatch.setattr(senders, "smtp_ready", lambda: True)
    monkeypatch.setattr(
        senders, "send_email_code", lambda to, code: mailbox.append(code)
    )
    client = TestClient(app, client=("203.0.113.91", 10000))
    path = "/v1/cuentas"
    email = "mariela.pruebas@gmail.com"
    password = "una-frase-con-seguridad-2026"
    registration = {"email": email, "password": password, "device": "test-device"}
    assert client.get("/v1/test/private").status_code == 401
    assert client.post(f"{path}/registro", json=registration).status_code == 400
    signup = client.post(
        f"{path}/registro", json={**registration, "acepta": True, "mayor": True}
    )
    assert signup.status_code == 200 and signup.json()["status"] == "codigo"
    user = store.users()[0]
    assert store.consent_of(user["id"])["terms"] == TERMS_VERSION
    verification = {"email": email, "device": "test-device"}
    wrong = "000000" if mailbox[-1] != "000000" else "000001"
    assert (
        client.post(
            f"{path}/verificar", json={**verification, "code": wrong}
        ).status_code
        == 400
    )
    verified = client.post(
        f"{path}/verificar", json={**verification, "code": mailbox[-1]}
    )
    assert verified.json()["status"] == "dentro"
    assert "set-cookie" not in verified.headers
    assert (
        client.post(
            f"{path}/verificar", json={**verification, "code": mailbox[-1]}
        ).status_code
        == 400
    )
    login = client.post(f"{path}/entrar", json=registration)
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    assert client.get("/v1/test/private", headers=headers).json() == {"user": email}
    assert client.get(f"{path}/lista", headers=headers).status_code == 403
    assert client.post(f"{path}/salir", headers=headers).status_code == 200
    assert client.get("/v1/test/private", headers=headers).status_code == 401
    assert not client.cookies
