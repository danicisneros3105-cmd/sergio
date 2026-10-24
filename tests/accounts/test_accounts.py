"""Sign in and sign up: passwords, codes, temp mail, multi-account, providers."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.accounts import disposable, fraud, oauth, security
from openjarvis.accounts import email as mail
from openjarvis.accounts.store import AccountStore


@pytest.fixture
def store(tmp_path):
    return AccountStore(tmp_path / "c.db")


@pytest.fixture
def app(store, monkeypatch):
    from openjarvis.server import accounts_routes

    monkeypatch.setattr(accounts_routes, "_store", lambda: store)
    accounts_routes._hits.clear()
    a = FastAPI()
    a.include_router(accounts_routes.router)
    return a


def test_passwords_are_stretched_and_weak_ones_refused():
    h = security.hash_password("una frase larga y mía")
    assert h.startswith("scrypt$") and "una frase" not in h
    assert security.check_password("una frase larga y mía", h)
    assert not security.check_password("otra cosa", h)
    assert security.password_problem("corta")
    assert security.password_problem("1234567890")
    assert security.password_problem("pedroperez99!", "pedroperez@gmail.com")
    assert security.password_problem("caballo-bateria-grapa") == ""


def test_the_same_inbox_written_another_way_is_the_same_person():
    assert mail.canonical("Pe.Dro+compras@GoogleMail.com") == "pedro@gmail.com"
    assert mail.canonical("ana+x@outlook.com") == "ana@outlook.com"
    assert mail.canonical("a.b@empresa.ec") == "a.b@empresa.ec"
    assert (
        mail.valid("ana@empresa.ec")
        and not mail.valid("ana@")
        and not mail.valid("a b@x.com")
    )


def test_temp_mail_is_refused_including_subdomains(tmp_path, monkeypatch):
    assert disposable.is_disposable("mailinator.com")
    assert disposable.is_disposable("xyz.yopmail.com")
    assert not disposable.is_disposable("gmail.com")
    monkeypatch.setattr(disposable, "list_path", lambda: tmp_path / "list.txt")
    disposable._domains.cache_clear()
    n = disposable.update_list(
        fetch=lambda url: "\n".join(f"tmp{i}.example" for i in range(150))
    )
    assert n == 150 and disposable.is_disposable("tmp7.example")
    with pytest.raises(ValueError):
        disposable.update_list(fetch=lambda url: "")
    disposable._domains.cache_clear()


def test_fraud_checks(store):
    assert fraud.check(store, email="ana@mailinator.com")["action"] == "block"
    store.create(
        email="pedro@gmail.com", canonical="pedro@gmail.com", phone="+593991234567"
    )
    assert fraud.check(store, email="p.e.d.r.o+2@gmail.com")["action"] == "block"
    assert fraud.check(store, phone="+593991234567")["action"] == "block"
    for i in range(2):
        store.note_signup(f"u{i}", "dev-1", "10.0.0.0/24")
    assert "dispositivo" in " ".join(
        fraud.check(store, email="nueva@empresa.ec", device="dev-1")["reasons"]
    )
    for i in range(4):
        store.note_signup(f"v{i}", f"d{i}", "192.168.1.0/24")
    v = fraud.check(store, email="otra@empresa.ec", device="d9", ip="192.168.1.77")
    assert v["action"] == "review" and v["network"] == "192.168.1.0/24"
    assert (
        fraud.check(store, email="limpia@empresa.ec", device="d10", ip="8.8.8.8")[
            "action"
        ]
        == "allow"
    )


def test_secure_providers_only_when_asked(store, monkeypatch):
    assert fraud.check(store, email="ana@empresa.ec")["action"] == "allow"
    monkeypatch.setenv("SERGIO_EMAIL_SOLO_SEGUROS", "1")
    assert fraud.check(store, email="ana@empresa.ec")["action"] == "block"
    assert fraud.check(store, email="ana@proton.me")["action"] == "allow"


def test_codes_expire_and_allow_few_tries(store):
    code = store.put_code("ana@empresa.ec", "correo")
    assert len(code) == 6 and code.isdigit()
    assert not store.check_code("ana@empresa.ec", code, "telefono")
    for _ in range(5):
        store.check_code(
            "ana@empresa.ec", "000000" if code != "000000" else "111111", "correo"
        )
    assert not store.check_code("ana@empresa.ec", code, "correo")  # too many tries


def test_the_owner_signs_up_on_the_computer_and_others_wait(app, store):
    local = TestClient(app)  # the test client counts as the computer itself
    first = local.post(
        "/v1/cuentas/registro",
        json={"email": "dueno@gmail.com", "password": "caballo-bateria-grapa"},
    )
    assert first.status_code == 200 and first.json()["status"] == "dentro"
    token = first.json()["token"]
    assert (
        local.get(
            "/v1/cuentas/estado", headers={"Authorization": f"Bearer {token}"}
        ).json()["me"]["role"]
        == "dueño"
    )
    other = TestClient(
        app, headers={"X-Forwarded-For": "200.1.2.3"}
    )  # through a tunnel
    second = other.post(
        "/v1/cuentas/registro",
        json={"email": "amigo@empresa.ec", "password": "otra-frase-larga-9"},
    )
    assert second.json()["status"] == "pendiente"
    login = other.post(
        "/v1/cuentas/entrar",
        json={"email": "amigo@empresa.ec", "password": "otra-frase-larga-9"},
    )
    assert login.json()["status"] == "codigo"  # email not confirmed and no mail server
    assert other.get("/v1/cuentas/lista").status_code == 403
    users = local.get("/v1/cuentas/lista").json()["accounts"]
    friend = next(u for u in users if u["email"] == "amigo@empresa.ec")
    assert "password" not in friend
    assert local.post(
        f"/v1/cuentas/{friend['id']}/rol", json={"role": "aprobado"}
    ).json()["ok"]
    store.set(friend["id"], email_ok=1)
    ok = other.post(
        "/v1/cuentas/entrar",
        json={"email": "amigo@empresa.ec", "password": "otra-frase-larga-9"},
    )
    assert ok.json()["status"] == "dentro"
    assert (
        local.post(
            f"/v1/cuentas/{users[0]['id']}/rol", json={"role": "bloqueado"}
        ).status_code
        == 400
    )


def test_wrong_passwords_lock_the_account(app, store):
    c = TestClient(app)
    c.post(
        "/v1/cuentas/registro",
        json={"email": "yo@gmail.com", "password": "caballo-bateria-grapa"},
    )
    from openjarvis.server import accounts_routes

    for _ in range(5):
        accounts_routes._hits.clear()
        assert (
            c.post(
                "/v1/cuentas/entrar",
                json={"email": "yo@gmail.com", "password": "mala-mala-mala"},
            ).status_code
            == 401
        )
    accounts_routes._hits.clear()
    r = c.post(
        "/v1/cuentas/entrar",
        json={"email": "yo@gmail.com", "password": "caballo-bateria-grapa"},
    )
    assert r.status_code == 429


def test_temp_mail_cannot_sign_up(app):
    r = TestClient(app).post(
        "/v1/cuentas/registro",
        json={"email": "x@yopmail.com", "password": "caballo-bateria-grapa"},
    )
    assert r.status_code == 403 and "temporal" in r.json()["detail"]


def test_sign_in_with_a_provider_checks_the_nonce(monkeypatch):
    monkeypatch.setenv("SERGIO_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("SERGIO_GOOGLE_CLIENT_SECRET", "sec")
    url = oauth.start(
        "google", "http://127.0.0.1:8000/v1/cuentas/oauth/google/vuelta", "dev"
    )
    assert "code_challenge_method=S256" in url and "client_id=cid" in url
    state = next(
        p.split("=", 1)[1]
        for p in url.split("?", 1)[1].split("&")
        if p.startswith("state=")
    )
    nonce = oauth._pending[state]["nonce"]
    seen = {}

    def post(url, form):
        seen.update(form)
        return {"id_token": "x"}

    good = {"sub": "1", "email": "a@gmail.com", "email_verified": True, "nonce": nonce}
    claims = oauth.finish(
        "google", "the-code", state, post=post, verify=lambda p, t: good
    )
    assert (
        claims["email_ok"] and seen["code_verifier"] and seen["client_secret"] == "sec"
    )
    with pytest.raises(ValueError):
        oauth.finish(
            "google", "again", state, post=post, verify=lambda p, t: {}
        )  # state used once


def test_the_api_guard_accepts_only_approved_sessions(tmp_path, monkeypatch):
    from openjarvis.server import accounts_routes
    from openjarvis.server.auth_middleware import AuthMiddleware

    st = AccountStore(tmp_path / "c.db")
    monkeypatch.setattr(accounts_routes, "_store", lambda: st)
    owner = st.create(
        email="d@gmail.com", canonical="d@gmail.com", role="dueño", email_ok=True
    )
    waiting = st.create(
        email="w@gmail.com", canonical="w@gmail.com", role="pendiente", email_ok=True
    )
    a = FastAPI()
    a.add_middleware(AuthMiddleware, api_key="clave-del-dueno")

    @a.get("/v1/algo")
    def algo():
        return {"ok": True}

    a.include_router(accounts_routes.router)
    c = TestClient(a)
    assert c.get("/v1/algo").status_code == 401
    assert (
        c.get(
            "/v1/algo",
            headers={"Authorization": f"Bearer {st.open_session(owner['id'])}"},
        ).status_code
        == 200
    )
    assert (
        c.get(
            "/v1/algo",
            headers={"Authorization": f"Bearer {st.open_session(waiting['id'])}"},
        ).status_code
        == 401
    )
    assert c.get("/v1/cuentas/estado").status_code == 200  # signing in needs no key
