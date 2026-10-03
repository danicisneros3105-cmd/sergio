"""Endpoints behind the notch's World and Guides tabs."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.core.types import ToolResult
from openjarvis.server import notch_routes


def _client():
    app = FastAPI()
    app.include_router(notch_routes.router)
    return TestClient(app)


def test_world_summary(monkeypatch):
    from openjarvis.tools import live_world

    def quakes(self, **kw):
        return ToolResult(
            "live_earthquakes", "Earthquakes:\n- M5.1 — Ambato\n- M4.7 — Fiji"
        )

    def launches(self, **kw):
        return ToolResult("upcoming_launches", "boom", success=False)

    monkeypatch.setattr(live_world.LiveEarthquakesTool, "execute", quakes)
    monkeypatch.setattr(live_world.UpcomingLaunchesTool, "execute", launches)
    monkeypatch.setattr(live_world, "read_globe_target", lambda: None)
    data = _client().get("/v1/world/summary").json()
    assert data["earthquakes"] == ["M5.1 — Ambato", "M4.7 — Fiji"]
    assert data["launches"] == [] and data["errors"] == ["boom"]


def test_goto(monkeypatch):
    from openjarvis.tools import live_world

    def run(self, **kw):
        assert kw == {"place": "Quito", "style": "thermal"}
        return ToolResult(
            "globe_view",
            "ok",
            metadata={"label": "Quito, Ecuador", "url": "http://127.0.0.1:4173/#x"},
        )

    monkeypatch.setattr(live_world.GlobeViewTool, "execute", run)
    resp = _client().post("/v1/world/goto", json={"place": "Quito", "style": "thermal"})
    assert resp.json() == {"label": "Quito, Ecuador", "url": "http://127.0.0.1:4173/#x"}


def test_goto_unknown_place(monkeypatch):
    from openjarvis.tools import live_world

    monkeypatch.setattr(
        live_world.GlobeViewTool,
        "execute",
        lambda self, **kw: ToolResult(
            "globe_view", "No encontré ese lugar", success=False
        ),
    )
    resp = _client().post("/v1/world/goto", json={"place": "zzz"})
    assert resp.status_code == 400 and "No encontré" in resp.json()["detail"]


def test_ecc_guides(tmp_path, monkeypatch):
    from openjarvis.unified import ecc

    skill = tmp_path / "skills" / "video-editing" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: video-editing\ndescription: Cut and pace videos\n---\nBody"
    )
    (tmp_path / "agents").mkdir()
    monkeypatch.setattr(ecc, "ecc_dir", lambda: tmp_path)
    data = _client().get("/v1/ecc/guides", params={"q": "video"}).json()
    assert data["installed"] and data["guides"][0]["name"] == "video-editing"
    assert _client().get("/v1/ecc/guides").json()["guides"][0]["kind"] == "skill"
