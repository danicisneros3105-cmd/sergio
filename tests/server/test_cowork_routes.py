"""/v1/cowork over HTTP, with a fake planner and runner behind the engine."""

from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.cowork.scrutiny import TrustStore
from openjarvis.cowork.session import CoworkEngine
from openjarvis.server.cowork_routes import router

GOAL = "Comparar los 3 mejores portátiles para Blender"


def _planner(goal):
    return {
        "titulo": "Portátiles",
        "pasos": [
            {
                "paso": "Buscar los mejores portátiles para Blender",
                "herramientas": ["web_search"],
                "comprobar": "3",
            },
            {
                "paso": "Compra el portátil más barato",
                "herramientas": ["web_search"],
                "comprobar": "x",
            },
        ],
    }


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    app.state.cowork_engine = CoworkEngine(
        planner=_planner,
        runner=lambda prompt, tools, budget: ("TERMINADO: listo", 1),
        root=tmp_path / "cowork",
        trust=TrustStore(tmp_path / "trust.json"),
    )
    return TestClient(app)


def _wait(client, run_id, status, tries=1000):
    for _ in range(tries):
        run = client.get(f"/v1/cowork/{run_id}").json()
        if run["status"] in status:
            return run
        time.sleep(0.01)
    raise AssertionError(run)


def test_full_flow(client):
    started = client.post("/v1/cowork", json={"goal": GOAL, "max_actions": 10}).json()
    assert started["max_actions"] == 10 and started["autonomy"] == "normal"
    run = _wait(client, started["id"], ("waiting_approval",))
    assert run["waiting"] == [1] and run["steps"][1]["verdict"]["decision"] == "ask"
    assert (
        client.post(
            f"/v1/cowork/{run['id']}/decision", json={"step": 1, "approve": True}
        ).status_code
        == 409
    )
    assert client.post(
        f"/v1/cowork/{run['id']}/decision", json={"step": 2, "approve": False}
    ).json() == {"ok": True}
    run = _wait(client, run["id"], ("partial",))
    assert [s["status"] for s in run["steps"]] == ["done", "skipped"]
    listed = client.get("/v1/cowork").json()["runs"]
    assert listed[0]["id"] == run["id"]
    audit = client.get(f"/v1/cowork/{run['id']}/audit").json()
    assert audit["intact"] and audit["entries"][0]["event"] == "started"
    events = [e["event"] for e in audit["entries"]]
    assert "owner_decision" in events and events[-1] == "finished"


def test_events_stream_ends_with_the_run(client):
    started = client.post("/v1/cowork", json={"goal": GOAL}).json()
    run = _wait(client, started["id"], ("waiting_approval",))
    client.post(f"/v1/cowork/{run['id']}/cancel")
    _wait(client, run["id"], ("cancelled",))
    with client.stream("GET", f"/v1/cowork/{run['id']}/events") as resp:
        lines = [line for line in resp.iter_lines() if line.startswith("data:")]
    payloads = [json.loads(line[5:]) for line in lines]
    assert (
        payloads[0]["type"] == "snapshot"
        and payloads[-1]["run"]["status"] == "cancelled"
    )


def test_steer_while_waiting_and_follow_up(client):
    started = client.post("/v1/cowork", json={"goal": GOAL}).json()
    run = _wait(client, started["id"], ("waiting_approval",))
    ok = client.post(
        f"/v1/cowork/{run['id']}/note", json={"text": "Mejor de 14 pulgadas"}
    )
    assert ok.json() == {"ok": True}
    assert client.get(f"/v1/cowork/{run['id']}").json()["notes"][0]["text"] == (
        "Mejor de 14 pulgadas"
    )
    client.post(f"/v1/cowork/{run['id']}/decision", json={"step": 2, "approve": False})
    run = _wait(client, run["id"], ("partial",))
    late = client.post(f"/v1/cowork/{run['id']}/note", json={"text": "otra cosa"})
    assert late.status_code == 409
    nxt = client.post(
        "/v1/cowork", json={"goal": "Y ahora una tabla", "follows": run["id"]}
    )
    assert nxt.json()["follows"] == run["id"] and "Portátiles" in nxt.json()["context"]


def test_scrutinize_and_axes(client):
    verdict = client.post(
        "/v1/cowork/scrutinize",
        json={"text": "Envía la tabla por WhatsApp a Juan", "tools": ["whatsapp_send"]},
    ).json()
    assert verdict["decision"] == "block" and len(verdict["scores"]) == 10
    axes = client.get("/v1/cowork/axes").json()["axes"]
    assert len(axes) == 10 and axes[0]["label"]


def test_errors(client):
    assert client.post("/v1/cowork", json={"goal": "   "}).status_code == 400
    assert client.get("/v1/cowork/nope").status_code == 404
    assert client.post("/v1/cowork/nope/cancel").status_code == 404


def test_owner_notices_only_to_the_owner():
    from types import SimpleNamespace as NS

    from openjarvis.cowork.notify import owner_sender

    sent = []

    class Adapter:
        def send(self, to, text, **kw):
            sent.append((to, text))
            return True

    bridge = NS(_channels={"whatsapp": Adapter(), "telegram": Adapter()})
    cfg = lambda ch, to: NS(  # noqa: E731
        cowork=NS(notify_channel=ch, notify_to=to),
        phone=NS(owner_numbers=["+593 99 111 2222"]),
    )
    assert owner_sender(cfg("whatsapp", "+593991112222"), bridge)("hola")
    assert (
        owner_sender(cfg("whatsapp", "+15550000000"), bridge) is None
    )  # not the owner
    assert owner_sender(cfg("telegram", "12345"), bridge)("ok")
    assert owner_sender(cfg("", ""), bridge) is None
    assert owner_sender(cfg("discord", "x"), bridge) is None  # not connected
    assert sent == [("+593991112222", "hola"), ("12345", "ok")]


def test_plan_mode_waits_for_the_plan(client):
    started = client.post("/v1/cowork", json={"goal": GOAL, "plan_first": True}).json()
    run = _wait(client, started["id"], ("waiting_plan",))
    assert [s["status"] for s in run["steps"]] == ["pending", "pending"]
    ok = client.post(
        f"/v1/cowork/{run['id']}/decision", json={"step": 0, "approve": True}
    )
    assert ok.json() == {"ok": True}
    run = _wait(client, run["id"], ("waiting_approval",))
    assert run["steps"][0]["status"] == "done"
    client.post(f"/v1/cowork/{run['id']}/cancel")


def test_plan_mode_refused_does_nothing(client):
    started = client.post("/v1/cowork", json={"goal": GOAL, "plan_first": True}).json()
    run = _wait(client, started["id"], ("waiting_plan",))
    client.post(f"/v1/cowork/{run['id']}/decision", json={"step": 0, "approve": False})
    run = _wait(client, run["id"], ("cancelled",))
    assert all(s["status"] == "pending" for s in run["steps"])
    assert "plan" in run["summary"]


def test_interrupted_run_events_close_without_waiting(client, monkeypatch):
    from openjarvis.cowork.session import CoworkRun

    engine = client.app.state.cowork_engine
    run = CoworkRun(
        id="interrupted-qa", goal="Verificar una tarea", status="interrupted"
    )
    engine.runs[run.id] = run
    box = engine.listen(run.id)

    def unexpected_wait(*_args, **_kwargs):
        pytest.fail("An interrupted run must not wait for another event")

    monkeypatch.setattr(box, "get", unexpected_wait)
    monkeypatch.setattr(engine, "listen", lambda _run_id: box)
    response = client.get(f"/v1/cowork/{run.id}/events")
    assert response.status_code == 200
    snapshots = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert snapshots and snapshots[-1]["run"]["status"] == "interrupted"
