"""External-app boundaries: allowlisted installs, real REST and honest model state."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from openjarvis.professional.catalog import BY_ID, catalog, installer
from openjarvis.professional.kronos import forecast, validate
from openjarvis.professional.opendesign import endpoint, request


def candles():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "timestamp": (start + timedelta(days=i)).isoformat(),
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1000,
        }
        for i in range(16)
    ]


def test_complete_app_families_and_host_scope(monkeypatch):
    monkeypatch.setattr(
        "shutil.which", lambda value: "/bin/git" if value == "git" else None
    )
    data = catalog()
    assert data["scope"] == "server_path"
    assert {
        "freecad",
        "blender",
        "bonsai",
        "librecad",
        "codium",
        "kdenlive",
        "opendesign",
        "kronos",
        "artcraft",
    }.issubset(BY_ID)
    assert sum(p.repository.startswith("storytold/") for p in BY_ID.values()) == 13
    assert next(p for p in data["programs"] if p["id"] == "git")["detected"]
    assert not next(p for p in data["programs"] if p["id"] == "bonsai")["detected"]
    assert not BY_ID["lidojs"].winget


@pytest.mark.parametrize(
    "ids", [[], ["not-an-app"], ["git; Remove-Item"], ["lidojs"], ["opendesign"]]
)
def test_installer_rejects_unreviewed_or_injected_ids(ids):
    with pytest.raises(ValueError):
        installer(ids)


def test_installer_contains_only_the_selection_once():
    script = installer(["codium", "codium", "freecad"])
    assert "$packages = @('VSCodium.VSCodium', 'FreeCAD.FreeCAD')" in script
    assert "KDE.Kdenlive" not in script
    assert "--exact --id $package" in script and "$LASTEXITCODE -ne 0" in script


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://169.254.169.254",
        "http://localhost@evil.test",
        "http://127.0.0.1/api",
        "http://127.0.0.1?x=1",
        "http://127.0.0.1#fragment",
    ],
)
def test_opendesign_cannot_exfiltrate_to_external_servers(monkeypatch, url):
    monkeypatch.setenv("SERGIO_OPENDESIGN_URL", url)
    with pytest.raises(ValueError):
        endpoint()


def test_real_opendesign_create_and_template_fill_contract(monkeypatch):
    monkeypatch.setenv("SERGIO_OPENDESIGN_URL", "http://localhost:8787")
    seen = []

    def serve(req):
        seen.append((req.method, req.url.path, json.loads(req.content)))
        return httpx.Response(200, json={"id": "design-1", "filled": ["title"]})

    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        request(
            "create", {"name": "Mi marca", "width": 1080, "height": 1080}, client=client
        )
        request(
            "fill",
            {"id": "design-1", "values": {"title": "Hola"}, "save": True},
            client=client,
        )
    assert seen[0] == (
        "POST",
        "/api/designs",
        {"name": "Mi marca", "width": 1080, "height": 1080},
    )
    assert seen[1] == (
        "POST",
        "/api/designs/design-1/fill",
        {"values": {"title": "Hola"}, "save": True},
    )


@pytest.mark.parametrize(
    "op,payload",
    [
        ("delete", {}),
        ("get", {"id": "../../tokens"}),
        ("create", {"width": -1}),
        ("create", {"admin": True}),
    ],
)
def test_opendesign_rejects_bad_operations_before_network(op, payload):
    with pytest.raises(ValueError):
        request(op, payload)


def test_kronos_rejects_data_leaks_nan_bad_candles_and_unknown_state(
    tmp_path, monkeypatch
):
    future = ["2026-01-17T00:00:00+00:00"]
    assert validate(candles(), future)["rows"][-1]["close"] == 105
    for key, value in [
        ("low", 106),
        ("high", 99),
        ("close", float("nan")),
        ("open", -1),
        ("volume", True),
    ]:
        data = candles()
        data[0][key] = value
        with pytest.raises(ValueError):
            validate(data, future)
    for invalid in [
        [candles()[0]["timestamp"]],
        [future[0], future[0]],
        ["2026-01-17"],
    ]:
        with pytest.raises(ValueError):
            validate(candles(), invalid)
    monkeypatch.setenv("SERGIO_KRONOS_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="No descargué modelos ni inventé"):
        forecast(candles(), future)


def test_program_routes_do_not_install_on_server():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.professional.routes import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/v1/programs").json()["scope"] == "server_path"
        res = client.post("/v1/programs/installer", json={"ids": ["codium"]})
        assert res.status_code == 200 and res.content.startswith(b"\xef\xbb\xbf")
        assert "Sergio-Programas.ps1" in res.headers["Content-Disposition"]
        assert (
            client.post(
                "/v1/programs/installer", json={"ids": ["opendesign"]}
            ).status_code
            == 400
        )
        assert client.post("/v1/programs/bonsai/open").status_code == 400
