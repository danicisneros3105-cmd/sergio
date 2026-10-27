"""The automation routes are the owner's alone; a tunnel or a customer gets 403."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from openjarvis.accounts.store import AccountStore


@pytest.fixture
def server(tmp_path, monkeypatch):
    from openjarvis.server import accounts_routes
    from openjarvis.server.app import create_app

    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
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


def test_only_the_owner_reaches_automation(server):
    client, owner, ana = server
    far = {"X-Forwarded-For": "8.8.8.8"}
    assert client.get("/v1/automatiza/estabilidad").status_code == 200  # his computer
    assert client.get("/v1/automatiza/estabilidad", headers=far).status_code in (
        401,
        403,
    )
    customer = {**far, "Authorization": f"Bearer {ana}"}
    for method, path in [("GET", "/v1/automatiza"), ("POST", "/v1/automatiza/trading/detener"),
                         ("POST", "/v1/automatiza/respuestas/enviar"), ("POST", "/v1/automatiza/canal")]:  # fmt: skip
        assert client.request(
            method, path, headers=customer, json={"ids": []}
        ).status_code in (401, 403), path
    # From outside even his session is fenced like Pagos (docs/SEGURIDAD.md:
    # «desde fuera, todo es 403 salvo cuentas y avisos firmados»).
    mine = {**far, "Authorization": f"Bearer {owner}"}
    assert client.get("/v1/automatiza/estabilidad", headers=mine).status_code == 403


def test_a_shared_file_link_works_once_and_guesses_fail(server, tmp_path, monkeypatch):
    from openjarvis.automatiza import canales

    client, _, _ = server
    monkeypatch.setenv("SERGIO_PUBLIC_URL", "https://s.example")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00\x01")
    token = canales.share_once(video).rsplit("/", 1)[1]
    assert client.get(f"/v1/automatiza/archivo/{token}").status_code == 200
    assert client.get(f"/v1/automatiza/archivo/{token}").status_code == 404
    assert client.get("/v1/automatiza/archivo/adivinado").status_code == 404
