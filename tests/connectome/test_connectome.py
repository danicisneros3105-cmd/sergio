"""Shortcuts wired like the fly brain: Kenyon codes, learning, the map and the escape reflex."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.connectome import memory as mb
from openjarvis.connectome.regions import REGIONS


def test_kenyon_code_is_sparse_and_shares_cells_between_related_words():
    a = mb.kenyon_code("presión arterial")
    b = mb.kenyon_code("presion")
    assert 0 < len(a) <= mb.MAX_ACTIVE and set(b) <= set(a)
    assert mb.kenyon_code("abre la") == []
    assert all(0 <= c < mb.KENYON_CELLS for c in a)


def test_dopamine_learns_and_dismissal_weakens(tmp_path):
    body = mb.MushroomBody(tmp_path / "m.json")
    for _ in range(3):
        assert body.reinforce("presión", "salud:explorar")
    top = body.predict("mi presión arterial")
    assert top and top[0][0] == "salud:explorar"
    before = top[0][1]
    body.reinforce("presión", "salud:explorar", -1)
    assert body.predict("presión")[0][1] < before
    # Saved and read back.
    again = mb.MushroomBody(tmp_path / "m.json")
    assert again.predict("presión")[0][0] == "salud:explorar"
    assert again.stats()["synapses"] > 0
    again.forget()
    assert again.predict("presión") == []


def test_bad_actions_are_refused_and_old_habits_fade(tmp_path):
    body = mb.MushroomBody(tmp_path / "m.json")
    assert not body.reinforce("hola", "../../etc")
    assert not body.reinforce("", "chat")
    body.reinforce("correo", "chat", now=0)
    w = body.predict("correo", threshold=0)[0][1]
    body._decayed_at = 0
    body.reinforce("otra cosa", "perfil", now=200 * 86400)
    assert body.predict("correo", threshold=0)[0][1] < w * 0.2


def test_regions_cover_the_fly_brain():
    keys = [r["key"] for r in REGIONS]
    assert keys == [
        "sentidos",
        "cuerpo_fungiforme",
        "cuerno_lateral",
        "complejo_central",
        "descendentes",
        "fibra_gigante",
        "club_rico",
    ]
    assert all(r["fly"] and r["job"] and r["sergio"] for r in REGIONS)


def _client(tmp_path, monkeypatch, state=None):
    from openjarvis.server import connectome_routes

    body = mb.MushroomBody(tmp_path / "m.json")
    monkeypatch.setattr(connectome_routes, "get_memory", lambda: body)
    app = FastAPI()
    app.include_router(connectome_routes.router)
    for k, v in (state or {}).items():
        setattr(app.state, k, v)
    return TestClient(app)


def test_routes_learn_and_map(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    learn = {"query": "tensión", "action": "salud:explorar"}
    assert client.post("/v1/connectome/learn", json=learn).json() == {"ok": True}
    learned = client.get("/v1/connectome/learned", params={"q": "tension"}).json()[
        "learned"
    ]
    assert learned[0]["action"] == "salud:explorar"
    m = client.get("/v1/connectome/map").json()
    assert (
        m["memory"]["synapses"] > 0 and len(m["regions"]) == 7 and m["facts"]["sources"]
    )
    assert (
        client.post(
            "/v1/connectome/learn", json={"query": "x", "action": "no válida!"}
        ).status_code
        == 400
    )
    assert client.delete("/v1/connectome/memory").json() == {"ok": True}


def test_escape_cancels_only_what_is_running(tmp_path, monkeypatch):
    cancelled = []
    working = SimpleNamespace(id="rihno", status="working")
    idle = SimpleNamespace(id="hous", status="idle")
    worker = SimpleNamespace(
        store=SimpleNamespace(all=lambda: [working, idle]),
        cancel=lambda nid: cancelled.append(("node", nid)) or True,
    )

    class Engine:
        def __init__(self, name, runs):
            self.name, self.runs = name, runs

        def list(self):
            return [SimpleNamespace(id=r) for r in self.runs]

        def cancel(self, rid):
            cancelled.append((self.name, rid))
            return rid.startswith("vivo")

    client = _client(
        tmp_path,
        monkeypatch,
        {"node_worker": worker, "swarm_engine": Engine("swarm", ["vivo-1", "hecho-2"])},
    )
    out = client.post("/v1/connectome/escape").json()
    assert out["stopped"] == {"nodes": 1, "swarm": 1, "cowork": 0}
    assert ("node", "hous") not in cancelled
