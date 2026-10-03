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


def test_open_globe_starts_it(monkeypatch):
    from openjarvis.tools import live_world

    monkeypatch.setattr(
        live_world, "ensure_globe", lambda wait=90.0: (True, "http://127.0.0.1:4173/")
    )
    assert _client().post("/v1/world/open").json() == {"url": "http://127.0.0.1:4173/"}


def test_open_globe_explains_why_not(monkeypatch):
    from openjarvis.tools import live_world

    monkeypatch.setattr(
        live_world,
        "ensure_globe",
        lambda wait=90.0: (False, "El globo no arrancó: skipped: Node.js 24+ and npm"),
    )
    resp = _client().post("/v1/world/open")
    assert resp.status_code == 503 and "Node.js" in resp.json()["detail"]


def test_ensure_globe_reports_the_log(tmp_path, monkeypatch):
    from openjarvis.tools import live_world
    from openjarvis.unified import supervisor

    class Sup:
        def __init__(self, config):
            pass

        def get(self, name):
            return object()

        def start(self, svc, wait=90.0):
            return "exited early, see globe.log"

        def log_file(self, name):
            log = tmp_path / "globe.log"
            log.write_text("npm ERR! network timeout\n")
            return log

    monkeypatch.setattr(supervisor, "Supervisor", Sup)
    monkeypatch.setattr(supervisor, "port_open", lambda port: False)
    running, detail = live_world.ensure_globe()
    assert not running and "exited early" in detail and "network timeout" in detail
