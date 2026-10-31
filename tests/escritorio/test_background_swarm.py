"""Tests for Background Swarm (10 concurrent humans equivalent) and Ultra Deep Research."""

from __future__ import annotations

import time
from openjarvis.connectome import neurons
from openjarvis.core.types import ToolResult
from openjarvis.tools.app_control import SergioAppControlTool
from sergio_escritorio.voice import needs_agent


def test_voice_recognizes_ultra_deep_and_background_swarm():
    phrases = [
        "Sergio, haz un ultra deep research sobre los mejores fabricantes de empaque magnético",
        "lanza un enjambre en segundo plano con 10 humanos para buscar clientes",
        "investiga en segundo plano este mercado de autos clásicos",
    ]
    for p in phrases:
        assert needs_agent(p), f"needs_agent failed for: {p}"
        sel = neurons.select(neurons.normalise(p), {})
        assert sel is not None, f"neurons.select failed for: {p}"
        assert ("sergio_app" in sel.tools) or ("investigacion_profunda" in sel.tools), p


def test_background_swarm_launch_status_and_cancel(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("openjarvis.swarm.engine._home", lambda: tmp_path / ".openjarvis" / "swarm")

    tool = SergioAppControlTool()

    # 1. Launch a background swarm with 10 parallel specialists
    res = tool.execute(
        action="background_swarm",
        content="Auditar y comparar 20 proveedores de micro-rotores y logística asegurada",
        parallel=10,
    )
    assert res.success
    assert "Enjambre de 10 Especialistas en Segundo Plano Iniciado" in res.content
    assert "10 subagentes concurrentes" in res.content
    assert "Recordatorio proactivo agendado" in res.content

    # Extract ID
    import re
    m = re.search(r"`(sw_[a-f0-9]+)`", res.content)
    assert m is not None
    swarm_id = m.group(1)

    # 2. Check status of the background swarm
    st_res = tool.execute(action="background_status", id=swarm_id)
    assert st_res.success
    assert swarm_id in st_res.content
    assert "Estado de Misión en Segundo Plano" in st_res.content

    # 3. Cancel the background swarm
    cancel_res = tool.execute(action="background_cancel", id=swarm_id)
    assert cancel_res.success
    assert "cancelada y recursos liberados" in cancel_res.content


def test_ultra_deep_research_background_execution(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    tool = SergioAppControlTool()

    # Launch Ultra Deep Research in the background
    res = tool.execute(
        action="ultra_deep_research",
        content="Análisis forense de patentes de calibres de micro-rotor de platino",
        background=True,
        workers=10,
        rounds=3,
    )
    assert res.success
    assert "Ultra Deep Research Iniciado en Segundo Plano" in res.content
    assert "10 especialistas concurrentes en 10 dimensiones" in res.content
    assert "Recordatorio proactivo agendado" in res.content
    assert "investigaciones" in res.content
