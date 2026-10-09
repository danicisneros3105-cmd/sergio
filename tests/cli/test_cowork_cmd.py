"""``sergio cowork``: local runs, following a server run, and the subcommands."""

from __future__ import annotations

from click.testing import CliRunner

from openjarvis.cli import cowork_cmd
from openjarvis.cowork import session as session_mod

PLAN = {
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
RUN = {
    "id": "r1",
    "goal": "portátiles",
    "title": "Portátiles",
    "status": "done",
    "autonomy": "normal",
    "max_actions": 50,
    "actions_used": 3,
    "summary": "Tabla lista",
    "steps": [{"index": 0, "text": "Buscar", "status": "done", "result": "3 modelos"}],
}


def test_goal_without_subcommand_starts_a_local_run(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    monkeypatch.setattr(cowork_cmd, "_base", lambda: None)
    monkeypatch.setattr(session_mod.CoworkEngine, "_plan", lambda self, goal: PLAN)
    monkeypatch.setattr(
        session_mod,
        "_default_runner",
        lambda: lambda prompt, tools, budget: ("TERMINADO: ok", 1),
    )
    result = CliRunner().invoke(
        cowork_cmd.cowork, ["compara", "portátiles", "para", "Blender"], input="n\n"
    )
    assert result.exit_code == 0, result.output
    assert "trabajo aquí mismo" in result.output
    # Not a terminal: the step that needs approval is shown and refused.
    assert "Plan: 2 pasos" in result.output and "¿Hago esto?" in result.output
    assert "hecho en parte" in result.output  # the purchase was refused


def test_follow_a_server_run(monkeypatch):
    calls = []
    monkeypatch.setattr(cowork_cmd, "_base", lambda: "http://x")
    monkeypatch.setattr(
        cowork_cmd,
        "_http",
        lambda method, path, **kw: (
            calls.append((method, path, kw))
            or ({**RUN, "status": "running"} if method == "POST" else RUN)
        ),
    )
    monkeypatch.setattr(
        cowork_cmd,
        "_events",
        lambda base, run_id: iter(
            [
                {"type": "snapshot", "run": RUN},
                {"type": "step", "text": "Paso 1: Buscar"},
                {"type": "finished", "text": "Tabla lista"},
            ]
        ),
    )
    result = CliRunner().invoke(
        cowork_cmd.cowork, ["iniciar", "portátiles", "--max-acciones", "20"]
    )
    assert result.exit_code == 0, result.output
    assert calls[0][0] == "POST" and calls[0][2]["json"]["max_actions"] == 20
    assert "Paso 1: Buscar" in result.output and "terminado" in result.output


def test_subcommands(monkeypatch):
    calls = []

    def fake(method, path, **kw):
        calls.append((method, path, kw.get("json")))
        if path == "/v1/cowork":
            return {"runs": [RUN]}
        if path.endswith("/audit"):
            return {
                "entries": [{"seq": 1, "event": "started", "data": {"text": "x"}}],
                "intact": True,
                "broken_at": None,
            }
        return RUN if method == "GET" else {"ok": True}

    monkeypatch.setattr(cowork_cmd, "_http", fake)
    runner = CliRunner()
    assert "Portátiles" in runner.invoke(cowork_cmd.cowork, ["lista"]).output
    assert "3 modelos" in runner.invoke(cowork_cmd.cowork, ["estado"]).output
    assert runner.invoke(cowork_cmd.cowork, ["aprobar", "r1", "2"]).exit_code == 0
    assert ("POST", "/v1/cowork/r1/decision", {"step": 2, "approve": True}) in calls
    assert runner.invoke(cowork_cmd.cowork, ["rechazar", "r1", "2"]).exit_code == 0
    assert "íntegro" in runner.invoke(cowork_cmd.cowork, ["auditoria", "r1"]).output
    assert "Cancelada" in runner.invoke(cowork_cmd.cowork, ["cancelar", "r1"]).output


def test_server_off_for_subcommands(monkeypatch):
    monkeypatch.setattr(cowork_cmd, "_base", lambda: None)
    result = CliRunner().invoke(cowork_cmd.cowork, ["lista"])
    assert result.exit_code != 0 and "servicio encender" in result.output
