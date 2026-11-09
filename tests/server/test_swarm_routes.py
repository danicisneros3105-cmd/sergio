"""Hosted Swarm isolation, quotas and identity propagation."""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.accounts.provision import CUSTOMER, CUSTOMER_KEY, CUSTOMER_PLAN
from openjarvis.server.swarm_routes import router


def _app(plan: str = "work"):
    app = FastAPI()

    @app.middleware("http")
    async def customer(request, call_next):
        uid = request.headers.get("X-Test-Customer", "")
        marks = (
            (CUSTOMER, CUSTOMER.set(uid)),
            (CUSTOMER_PLAN, CUSTOMER_PLAN.set(plan)),
            (CUSTOMER_KEY, CUSTOMER_KEY.set(f"key-for-{uid}")),
        )
        try:
            return await call_next(request)
        finally:
            for variable, mark in reversed(marks):
                variable.reset(mark)

    app.include_router(router)
    return app


def _wait(client: TestClient, run_id: str, headers: dict[str, str]):
    for _ in range(500):
        run = client.get(f"/v1/swarm/{run_id}", headers=headers).json()
        if run.get("status") in {"done", "failed", "cancelled"}:
            return run
        time.sleep(0.01)
    raise AssertionError(run)


def test_customer_swarms_are_isolated_and_workers_keep_their_account(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    memories = []
    monkeypatch.setattr(
        "openjarvis.connectome.brain.remember_exchange",
        lambda *args, **kwargs: memories.append((args, kwargs)),
    )
    app = _app()
    client = TestClient(app)
    seen = []
    for uid in ("a" * 16, "b" * 16):
        headers = {"X-Test-Customer": uid}
        assert client.get("/v1/swarm", headers=headers).json() == {"runs": []}
        engine = app.state.swarm_customer_engines[uid]

        def ask(prompt, **_kwargs):
            if "Divide la tarea" in prompt:
                return {
                    "titulo": "Investigación",
                    "roles": [{"nombre": "Investigador", "especialidad": "Web"}],
                    "subtareas": [
                        {
                            "titulo": "Fuente",
                            "rol": "Investigador",
                            "instruccion": "Buscar una fuente",
                            "herramientas": ["web_search", "file_read"],
                        }
                    ],
                    "sintesis": "Una el resultado",
                }
            return {"informe": "Resultado respaldado por el trabajador."}

        def run(prompt, tools, budget, on_tool=None):
            seen.append((CUSTOMER.get(), CUSTOMER_KEY.get(), list(tools)))
            return "Resultado verificado", 1

        engine.ask = ask
        engine.runner = run
        engine._live = True
        started = client.post(
            "/v1/swarm",
            data={"task": "Buscar una fuente", "parallel": "2", "scout": "false"},
            headers=headers,
        ).json()
        run = _wait(client, started["id"], headers)
        assert run["status"] == "done"
        assert client.get("/v1/swarm", headers=headers).json()["runs"][0]["id"] == started["id"]
        workspace = client.post(f"/v1/swarm/{started['id']}/workspace", headers=headers)
        assert workspace.status_code == 403

    engines = app.state.swarm_customer_engines
    assert engines["a" * 16].home != engines["b" * 16].home
    assert [(uid, key) for uid, key, _ in seen] == [
        ("a" * 16, "key-for-" + "a" * 16),
        ("b" * 16, "key-for-" + "b" * 16),
    ]
    assert all("file_read" not in tools for _, _, tools in seen)
    assert memories == []


def test_free_customer_cannot_start_a_swarm():
    client = TestClient(_app(plan="free"))
    response = client.post(
        "/v1/swarm",
        data={"task": "Investigar"},
        headers={"X-Test-Customer": "c" * 16},
    )
    assert response.status_code == 402
    assert "Work" in response.json()["detail"]
