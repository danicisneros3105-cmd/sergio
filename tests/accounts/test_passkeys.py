"""Signing in with the device's own face, finger or PIN (passkeys), end to end
with a real P-256 key standing in for the phone."""

from __future__ import annotations

import hashlib
import json
import struct

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.accounts import passkeys
from openjarvis.accounts.passkeys import b64u
from openjarvis.accounts.store import AccountStore

ORIGIN = "https://sergio.example"
HOST = "sergio.example"


def cbor_encode(value) -> bytes:
    """Just enough CBOR to play an authenticator."""

    def head(major: int, n: int) -> bytes:
        if n < 24:
            return bytes([major << 5 | n])
        if n < 256:
            return bytes([major << 5 | 24, n])
        return bytes([major << 5 | 25]) + n.to_bytes(2, "big")

    if isinstance(value, bool):
        return bytes([0xF5 if value else 0xF4])
    if isinstance(value, int):
        return head(0, value) if value >= 0 else head(1, -1 - value)
    if isinstance(value, bytes):
        return head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode()
        return head(3, len(raw)) + raw
    if isinstance(value, dict):
        return head(5, len(value)) + b"".join(
            cbor_encode(k) + cbor_encode(v) for k, v in value.items()
        )
    raise TypeError(value)


class Phone:
    """A fake platform authenticator: a P-256 key, Face ID always passes."""

    def __init__(self, rp_id: str = HOST, verified: bool = True):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = b"phone-credential-1"
        self.rp_id = rp_id
        self.verified = verified
        self.count = 0

    def _auth(self, attested: bool) -> bytes:
        flags = 0x01 | (0x04 if self.verified else 0) | (0x40 if attested else 0)
        data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([flags])
            + struct.pack(">I", self.count)
        )
        if attested:
            nums = self.key.public_key().public_numbers()
            cose = {
                1: 2,
                3: -7,
                -1: 1,
                -2: nums.x.to_bytes(32, "big"),
                -3: nums.y.to_bytes(32, "big"),
            }
            data += (
                b"\x00" * 16
                + struct.pack(">H", len(self.cred_id))
                + self.cred_id
                + cbor_encode(cose)
            )
        return data

    def create(self, challenge: str, origin: str = ORIGIN) -> dict:
        client = json.dumps(
            {"type": "webauthn.create", "challenge": challenge, "origin": origin}
        ).encode()
        att = cbor_encode({"fmt": "none", "attStmt": {}, "authData": self._auth(True)})
        return {
            "clientDataJSON": b64u(client),
            "attestationObject": b64u(att),
            "name": "Teléfono",
        }

    def get(self, challenge: str, origin: str = ORIGIN) -> dict:
        self.count += 1
        client = json.dumps(
            {"type": "webauthn.get", "challenge": challenge, "origin": origin}
        ).encode()
        auth = self._auth(False)
        sig = self.key.sign(
            auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64u(self.cred_id),
            "clientDataJSON": b64u(client),
            "authenticatorData": b64u(auth),
            "signature": b64u(sig),
            "device": "telefono-1",
        }


@pytest.fixture
def store(tmp_path):
    return AccountStore(tmp_path / "c.db")


@pytest.fixture
def client(store, monkeypatch):
    from openjarvis.server import accounts_routes

    monkeypatch.setattr(accounts_routes, "_store", lambda: store)
    accounts_routes._hits.clear()
    app = FastAPI()
    app.include_router(accounts_routes.router)
    c = TestClient(app, base_url=f"https://{HOST}")
    c.headers.update({"origin": ORIGIN})
    return c


def owner(store) -> dict:
    return store.create(
        email="duenio@example.com", canonical="duenio@example.com", role="dueño"
    )


def register(client, phone: Phone, token: str = "") -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    opts = client.post("/v1/cuentas/llave/opciones-registro", headers=headers).json()
    assert opts["authenticatorSelection"]["userVerification"] == "required"
    assert opts["rp"]["id"] == HOST
    return client.post(
        "/v1/cuentas/llave/registrar",
        json=phone.create(opts["challenge"]),
        headers=headers,
    )


def sign_in(client, phone: Phone, origin: str = ORIGIN):
    opts = client.post("/v1/cuentas/llave/opciones").json()
    return client.post(
        "/v1/cuentas/llave/entrar", json=phone.get(opts["challenge"], origin)
    )


def test_the_phone_face_signs_in_without_a_password(client, store):
    me = owner(store)
    token = store.open_session(me["id"])
    phone = Phone()
    r = register(client, phone, token)
    assert r.status_code == 200, r.text
    stored = store.passkey(b64u(phone.cred_id))
    assert stored and stored["user"] == me["id"] and "PRIVATE" not in stored["public"]
    r = sign_in(client, phone)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "dentro" and body["token"].startswith("sg_")
    assert store.session_user(body["token"])["id"] == me["id"]


def test_a_fake_site_cannot_use_the_key(client, store):
    me = owner(store)
    phone = Phone()
    assert register(client, phone, store.open_session(me["id"])).status_code == 200
    # the browser signs the address it really was on: another site fails
    r = sign_in(client, phone, origin="https://sergio-login.example")
    assert r.status_code == 401
    # and a key made for another site is refused at once
    other = Phone(rp_id="evil.example")
    other.cred_id = b"other"
    assert register(client, other, store.open_session(me["id"])).status_code == 400


def test_the_device_must_check_the_person(client, store):
    me = owner(store)
    lazy = Phone(verified=False)
    r = register(client, lazy, store.open_session(me["id"]))
    assert r.status_code == 400 and "cara, huella o PIN" in r.json()["detail"]


def test_a_challenge_works_once_and_a_copied_key_is_caught(client, store):
    me = owner(store)
    phone = Phone()
    assert register(client, phone, store.open_session(me["id"])).status_code == 200
    opts = client.post("/v1/cuentas/llave/opciones").json()
    signed = phone.get(opts["challenge"])
    assert client.post("/v1/cuentas/llave/entrar", json=signed).status_code == 200
    assert (
        client.post("/v1/cuentas/llave/entrar", json=signed).status_code == 401
    )  # replay
    phone.count = 0  # a clone with an older counter
    assert sign_in(client, phone).status_code == 401


def test_a_wrong_signature_is_refused(client, store):
    me = owner(store)
    phone = Phone()
    assert register(client, phone, store.open_session(me["id"])).status_code == 200
    opts = client.post("/v1/cuentas/llave/opciones").json()
    signed = phone.get(opts["challenge"])
    signed["signature"] = b64u(Phone().key.sign(b"x", ec.ECDSA(hashes.SHA256())))
    assert client.post("/v1/cuentas/llave/entrar", json=signed).status_code == 401


def test_pending_accounts_still_wait_and_keys_can_be_removed(client, store):
    owner(store)
    uid = store.create(
        email="otra@example.com", canonical="otra@example.com", role="aprobado"
    )["id"]
    token = store.open_session(uid)
    phone = Phone()
    assert register(client, phone, token).status_code == 200
    store.set(uid, role="pendiente")
    assert sign_in(client, phone).json()["status"] == "pendiente"
    store.set(uid, role="aprobado")
    token = store.open_session(uid)
    keys = client.get(
        "/v1/cuentas/llave/lista", headers={"Authorization": f"Bearer {token}"}
    ).json()["llaves"]
    assert len(keys) == 1
    gone = client.delete(
        f"/v1/cuentas/llave/{keys[0]['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gone.json()["llaves"] == []
    assert sign_in(client, phone).status_code == 401


def test_only_https_or_localhost_and_only_this_address():
    assert (
        passkeys.rp_from_origin("https://sergio.example", "sergio.example")
        == "sergio.example"
    )
    assert (
        passkeys.rp_from_origin("http://localhost:8000", "localhost:8000")
        == "localhost"
    )
    assert (
        passkeys.rp_from_origin("http://192.168.1.5:8000", "192.168.1.5:8000") is None
    )
    assert passkeys.rp_from_origin("https://otro.example", "sergio.example") is None
    assert passkeys.rp_from_origin("", "sergio.example") is None


def test_cbor_reader_handles_what_authenticators_send():
    value = {1: 2, 3: -7, -1: 1, "fmt": "none", "ok": True, "list": b"\x00\x01"}
    decoded, end = passkeys.cbor(cbor_encode(value))
    assert decoded == value and end == len(cbor_encode(value))
    with pytest.raises(passkeys.PasskeyError):
        passkeys.cbor(b"\x5a\xff")  # a byte string longer than the data
