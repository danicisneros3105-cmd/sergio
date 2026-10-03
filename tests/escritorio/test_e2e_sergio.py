"""End to end: what you say -> Sergio's server agent -> tools -> your Windows.

A scripted model plays Gemini (it answers with the tool calls Gemini would
make); everything else is real: the FastAPI server, the orchestrator agent,
Sergio's desktop tools, and the Windows control server (with a fake desktop
that records what would happen on screen).
"""

import json

import pytest
from fastapi.testclient import TestClient

from openjarvis.core.events import EventBus


def _config():
    from openjarvis.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    return cfg


class ScriptedGemini:
    """Plays the model: returns the next scripted turn on each call."""

    engine_id = "scripted"

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen_tools = []

    def health(self):
        return True

    def list_models(self):
        return ["gemini-3.8-flash"]

    def generate(self, messages, *, model, **kwargs):
        self.seen_tools.append(
            [t["function"]["name"] for t in kwargs.get("tools") or []]
        )
        turn = self.turns.pop(0)
        if isinstance(turn, str):
            return {"content": turn, "finish_reason": "stop", "model": model}
        calls = [
            {"id": f"call-{i}", "name": name, "arguments": json.dumps(args)}
            for i, (name, args) in enumerate(turn)
        ]
        return {"content": "", "tool_calls": calls, "finish_reason": "tool_calls"}

    async def stream(self, *a, **k):  # pragma: no cover
        yield ""


def _ask(turns, text, tools):
    from openjarvis.agents.orchestrator import OrchestratorAgent
    from openjarvis.server.app import create_app

    engine = ScriptedGemini(turns)
    agent = OrchestratorAgent(
        engine, "gemini-3.8-flash", tools=tools, bus=EventBus(), parallel_tools=False
    )
    client = TestClient(
        create_app(engine, "gemini-3.8-flash", agent=agent, config=_config())
    )
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gemini-3.8-flash@low",
            "messages": [{"role": "user", "content": text}],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["choices"][0]["message"]["content"], engine


@pytest.fixture
def windows(control_server, monkeypatch):
    controller, url = control_server
    monkeypatch.setenv("SERGIO_DESKTOP_URL", url)
    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "secreto")
    return controller


def _desktop_tools():
    from openjarvis.tools.desktop_tools import (
        DesktopActionTool,
        FilesOrganizeTool,
        ScreenReadTool,
        TerminalRunTool,
    )

    return [
        ScreenReadTool(),
        DesktopActionTool(),
        TerminalRunTool(),
        FilesOrganizeTool(),
    ]


def test_google_search_then_first_link(windows, desktop):
    answer, engine = _ask(
        [
            [
                (
                    "desktop_action",
                    {
                        "action": "open",
                        "target": "https://www.google.com/search?q=nvidia",
                    },
                )
            ],
            [("screen_read", {})],
            [("desktop_action", {"action": "click", "element": 2})],
            "Listo, abrí el primer resultado de Nvidia.",
        ],
        "Sergio, abre Google, busca Nvidia y entra al primer link",
        _desktop_tools(),
    )
    assert answer == "Listo, abrí el primer resultado de Nvidia."
    assert ("open", "https://www.google.com/search?q=nvidia") in desktop.calls
    assert ("click", 930, 1020, "left", 1) in desktop.calls  # element 2 = Enviar
    assert "desktop_action" in engine.seen_tools[0]


def test_open_and_close_apps_and_terminal(windows, desktop):
    answer, _ = _ask(
        [
            [("desktop_action", {"action": "open_app", "target": "Spotify"})],
            [("desktop_action", {"action": "close_app", "target": "Spotify"})],
            [("terminal_run", {"command": "Get-Location"})],
            "Abrí y cerré Spotify, y estás en tu carpeta de usuario.",
        ],
        "abre Spotify, ciérralo y dime dónde estoy en la terminal",
        _desktop_tools(),
    )
    kinds = [c[0] for c in desktop.calls]
    assert kinds == ["open_app", "close_app", "shell"]
    assert "carpeta de usuario" in answer


def test_point_to_show_something(windows):
    shown = []
    windows.on_point = lambda x, y, label: shown.append((x, y, label))
    _ask(
        [
            [("screen_read", {})],
            [("desktop_action", {"action": "point", "element": 1, "text": "Buscar"})],
            "Ese es el buscador, arriba a la izquierda.",
        ],
        "¿dónde está el buscador?",
        _desktop_tools(),
    )
    assert shown == [(200, 120, "Buscar")]


def test_hands_mode_by_voice(windows):
    modes = []
    windows.on_hands = lambda mode: modes.append(mode) or f"hands mode: {mode}"
    _ask(
        [[("desktop_action", {"action": "hands", "target": "mouse"})], "Listo."],
        "quiero mover el mouse con la mano",
        _desktop_tools(),
    )
    assert modes == ["mouse"]


def test_paused_control_is_respected_end_to_end(windows, desktop):
    windows.enabled = False
    answer, _ = _ask(
        [
            [("desktop_action", {"action": "open_app", "target": "Spotify"})],
            "No puedo: pausaste el control.",
        ],
        "abre Spotify",
        _desktop_tools(),
    )
    assert desktop.calls == [] and "pausaste" in answer


def test_every_desktop_tool_schema_is_accepted_by_gemini():
    """The chat failed with 400 'additional_properties': never again."""
    import openjarvis.tools  # noqa: F401 — registers the tools
    from openjarvis.cli.escritorio_cmd import BASE_TOOLS, DESKTOP_TOOLS
    from openjarvis.core.registry import ToolRegistry
    from openjarvis.engine.cloud import _convert_tools_to_google

    forbidden = {"additionalProperties", "$schema", "oneOf", "const", "default"}

    def walk(node):
        if isinstance(node, dict):
            assert not forbidden & set(node), node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for name in (*BASE_TOOLS, *DESKTOP_TOOLS):
        if not ToolRegistry.contains(name):
            continue
        spec = ToolRegistry.get(name)().spec
        decl = _convert_tools_to_google(
            [
                {
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters,
                    }
                }
            ]
        )[0]
        walk(decl)
