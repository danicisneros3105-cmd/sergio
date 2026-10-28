"""«En marcha» lists channels and the trading robot, each with a way to stop."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    from openjarvis.server.app import create_app

    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["m"]
    return TestClient(create_app(engine, "m"), raise_server_exceptions=False)


def test_a_channel_and_paper_trading_show_up_and_can_be_stopped(tmp_path, monkeypatch):
    from openjarvis.automatiza import trading
    from openjarvis.video_essay import schedule

    item = schedule.add(
        "datos curiosos", every_hours=6, publish_to=["youtube"], auto=True
    )
    trading.save_settings({"activo": True})
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/v1/personal/en-marcha")
    rows = resp.json()["en_marcha"]
    kinds = {r["tipo"]: r for r in rows}
    assert {"canal", "trading"} <= set(kinds)
    assert "papel" in kinds["trading"]["que"].lower()

    assert client.post(kinds["canal"]["detener"]).status_code == 200
    assert client.post(kinds["trading"]["detener"]).status_code == 200
    rows = client.get("/v1/personal/en-marcha").json()["en_marcha"]
    assert not [r for r in rows if r["tipo"] in ("canal", "trading")]
    assert item["id"]
