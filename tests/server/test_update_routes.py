"""«Actualizar» runs the owner's universal command, detached, local only."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server import update_routes


def test_runs_the_universal_command_once(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    calls = []
    out = update_routes.start(popen=lambda cmd, **kw: calls.append((cmd, kw)))
    assert out == {"started": True, "running": True}
    cmd, kw = calls[0]
    script = cmd[-1]
    assert (
        "git fetch origin main && git checkout -B main origin/main && bash scripts/actualizar-sergio.sh main"
        in script
    )
    assert kw["start_new_session"] is True
    (tmp_path / "actualizando").write_text("9999999999")  # still running
    assert update_routes.start(popen=lambda *a, **k: calls.append(a)) == {
        "started": False,
        "running": True,
    }
    assert len(calls) == 1
    (tmp_path / "actualizando").write_text("1")  # an hour-old lock is stale
    assert not update_routes.running()


def test_only_from_this_computer(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    app = FastAPI()
    app.include_router(update_routes.router)
    remote = TestClient(app, client=("203.0.113.9", 5000))
    assert remote.post("/v1/sistema/actualizar").status_code == 403
    local = TestClient(app, client=("127.0.0.1", 5000))
    assert local.get("/v1/sistema/actualizar").json()["running"] is False
    tunnelled = local.get(
        "/v1/sistema/actualizar", headers={"X-Forwarded-For": "1.2.3.4"}
    )
    assert tunnelled.status_code == 403
