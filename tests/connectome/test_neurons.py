"""The brain is the core: neurons with one job each decide the tools, and
what works grows new connections, shortcuts and even new neurons."""

from __future__ import annotations

import time

from openjarvis.connectome import brain as brain_mod
from openjarvis.connectome import neurons
from openjarvis.connectome.brain import Brain


class Clock:
    def __init__(self) -> None:
        self.t = time.time()

    def __call__(self) -> float:
        return self.t


def test_each_neuron_has_one_job_and_its_tools():
    sel = neurons.select("hazme una imagen de un gato astronauta", {})
    assert sel is not None and sel.neurons[0] == "imagen"
    assert "image_generate" in sel.tools and "desktop_action" not in sel.tools
    assert set(neurons.CORE) <= sel.tools
    pc = neurons.select("mi PC está muy lenta", {})
    assert pc is not None and "pc_checkup" in pc.tools


def test_nothing_clear_means_every_tool_as_before():
    assert neurons.select("hola, ¿cómo estás?", {}) is None


def test_a_request_without_the_innate_words_is_learned(tmp_path):
    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    ask = "prepara el cartel del concierto del sábado"
    assert brain.select_tools(ask) is None  # never seen: no neuron fires
    for _ in range(3):
        clock.t += 60
        brain.context(ask)
        brain.note_tool("image_generate", True)
        brain.observe(ask, "Listo, el cartel.")
    sel = brain.select_tools("prepara el cartel del concierto")
    assert sel is not None and "imagen" in sel.neurons
    assert "image_generate" in sel.tools


def test_repetition_becomes_a_shortcut(tmp_path):
    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    ask = "deja bonito el informe trimestral"
    for _ in range(6):
        clock.t += 60
        brain.context(ask)
        brain.note_tool("file_write", True)
        brain.observe(ask, "Hecho.")
    sel = brain.select_tools(ask)
    assert sel is not None and sel.shortcut
    stats = brain.stats()
    assert stats["shortcuts"] >= 1
    row = next(r for r in stats["neurons"] if r["key"] == "archivos")
    assert row["connections"] > 0 and row["shortcut"]


def test_a_new_tool_grows_a_new_neuron(tmp_path):
    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    ask = "pasa las tareas al tablero del equipo"
    for _ in range(3):
        clock.t += 60
        brain.context(ask)
        brain.note_tool("mcp_tablero_crear_tarjeta", True)
        brain.observe(ask, "Tarjetas creadas.")
    sel = brain.select_tools(ask)
    assert sel is not None and "mcp_tablero_crear_tarjeta" in sel.tools
    stats = brain.stats()
    assert stats["learned_neurons"] == 1
    assert any(r["learned"] and "mcp_tablero" in r["label"] for r in stats["neurons"])


def test_the_agent_only_sees_the_tools_of_the_neurons_that_fired(tmp_path, monkeypatch):
    from openjarvis.tools._stubs import ToolExecutor
    from openjarvis.tools.calculator import CalculatorTool
    from openjarvis.tools.desktop_tools import DesktopActionTool
    from openjarvis.tools.image_tool import ImageGenerateTool

    brain = Brain(tmp_path, clock=Clock())
    monkeypatch.setattr(brain_mod, "get_brain", lambda home=None: brain)
    executor = ToolExecutor(
        [CalculatorTool(), ImageGenerateTool(), DesktopActionTool()]
    )
    brain_mod.mind_context("dibuja un faro en la noche")
    names = {f["function"]["name"] for f in executor.get_openai_tools()}
    assert names == {"calculator", "image_generate"}
    brain_mod.mind_context("hola")  # nothing fired: all tools again
    names = {f["function"]["name"] for f in executor.get_openai_tools()}
    assert names == {"calculator", "image_generate", "desktop_action"}
