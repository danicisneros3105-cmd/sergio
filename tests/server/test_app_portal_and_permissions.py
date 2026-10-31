"""Tests for the Plug-and-Play Downloadable App Portal, Permission Gateway, and Account Deletion."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from openjarvis.core.config import JarvisConfig
from openjarvis.server.app import create_app
from openjarvis.server.permission_gateway import (
    PermissionGatewayStore,
    PermissionStatus,
    RiskLevel,
    get_permission_gateway_store,
)


def _make_engine():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    return engine


def _test_config():
    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    return cfg


@pytest.fixture
def client():
    engine = _make_engine()
    app = create_app(engine, "test-model", config=_test_config())
    return TestClient(app)


def test_download_windows_launcher(client: TestClient):
    response = client.get("/descargar/windows")
    assert response.status_code == 200
    assert (
        'attachment; filename="Iniciar_Sergio_AI.bat"'
        in response.headers["content-disposition"]
    )
    text = response.text
    assert "@echo off" in text
    assert "msedge.exe" in text
    assert "/portal" in text


def test_download_macos_launcher(client: TestClient):
    response = client.get("/descargar/macos")
    assert response.status_code == 200
    assert (
        'attachment; filename="Iniciar_Sergio_AI.command"'
        in response.headers["content-disposition"]
    )
    assert "#!/bin/bash" in response.text
    assert "/portal" in response.text


def test_download_linux_launcher(client: TestClient):
    response = client.get("/descargar/linux")
    assert response.status_code == 200
    assert (
        'attachment; filename="Iniciar_Sergio_AI.sh"'
        in response.headers["content-disposition"]
    )
    assert "#!/bin/bash" in response.text
    assert "/portal" in response.text


def test_download_info_endpoint(client: TestClient):
    response = client.get("/descargar/info")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "/portal" in data["portales"]["web_portal"]
    assert "/descargar/windows" in data["descargas_directas"]["windows"]


def test_portal_html_serving(client: TestClient):
    res_portal = client.get("/portal")
    assert res_portal.status_code == 200
    assert "text/html" in res_portal.headers["content-type"]
    assert "Sergio" in res_portal.text
    assert (
        "Conceder Permiso" in res_portal.text or "Centro de Permisos" in res_portal.text
    )

    res_app = client.get("/app")
    assert res_app.status_code == 200
    assert "text/html" in res_app.headers["content-type"]


def test_permission_gateway_lifecycle():
    store = PermissionGatewayStore()
    req = store.create_request(
        title="Actualizar Dependencias del Sistema",
        command="winget upgrade --all --accept-source-agreements",
        system_target="windows",
        explanation="Sergio ejecutará winget upgrade silencioso.",
        risk_level=RiskLevel.MEDIUM,
    )
    assert req.status == PermissionStatus.PENDING

    pending = store.get_pending()
    assert len(pending) == 1
    assert pending[0]["request_id"] == req.request_id

    # Test approve
    approved = store.grant_permission(req.request_id, resolved_by="user_test")
    assert approved is True

    # Pending list should be empty
    assert len(store.get_pending()) == 0

    # Test deny on new request
    req2 = store.create_request(
        title="Limpieza de temporales",
        command="rm -rf /tmp/sergio_*",
        system_target="linux",
        explanation="Eliminar carpetas temporales",
        risk_level=RiskLevel.HIGH,
    )
    denied = store.deny_permission(req2.request_id, resolved_by="user_test")
    assert denied is True
    assert store._requests[req2.request_id].status == PermissionStatus.DENIED


def test_permission_routes(client: TestClient):
    # Create request directly in store
    store = get_permission_gateway_store()
    req = store.create_request(
        title="Accion de Prueba",
        command="dir",
        system_target="windows",
        explanation="Listado de directorio de trabajo",
        risk_level=RiskLevel.MEDIUM,
    )

    # Get pending via endpoint
    res = client.get("/v1/permisos/pendientes")
    assert res.status_code == 200
    pendings = res.json()["pendientes"]
    assert any(p["request_id"] == req.request_id for p in pendings)

    # Grant permission via endpoint
    res_grant = client.post(f"/v1/permisos/{req.request_id}/conceder")
    assert res_grant.status_code == 200
    assert res_grant.json()["estado"] == PermissionStatus.GRANTED.value


def test_eliminar_mi_cuenta_validation(client: TestClient):
    # Without typing 'eliminar', must fail with 400
    res = client.post("/v1/cuentas/eliminar-mi-cuenta", json={"confirmacion": "no"})
    assert res.status_code == 400
    assert "eliminar" in res.json()["detail"].lower()

    # With proper confirmation 'eliminar'
    res_ok = client.post(
        "/v1/cuentas/eliminar-mi-cuenta",
        json={"confirmacion": "eliminar", "purgar_datos_locales": False},
    )
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert data["ok"] is True
    assert data["sesion_cerrada"] is True
