"""A path of tools that keeps working grows a neuron of its own."""

from __future__ import annotations

from openjarvis.connectome import neurons
from openjarvis.connectome.brain import Brain

PATH = [("inspiracion_video", True), ("planear_video", True), ("video_essay", True)]


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def test_chain_key_keeps_the_order_and_leaves_out_core_and_failures():
    tools = [("web_search", True), ("inspiracion_video", True), ("planear_video", False),
             ("planear_video", True), ("inspiracion_video", True)]  # fmt: skip
    assert neurons.chain_key(tools) == "cadena:inspiracion_video>planear_video"
    assert neurons.chain_key([("video_essay", True)]) == ""
    key = neurons.chain_key(PATH)
    assert neurons.tools_of(key) == (
        "inspiracion_video",
        "planear_video",
        "video_essay",
    )
    assert neurons.label(key).startswith("Camino: inspiracion_video →")


def test_a_born_chain_neuron_brings_its_tools_and_its_order():
    key = neurons.chain_key(PATH)
    sel = neurons.select("algo sin palabras conocidas", {key: 0.9})
    assert (
        sel is not None
        and {"inspiracion_video", "planear_video", "video_essay"} <= sel.tools
    )
    text = neurons.superskill_for(sel)
    assert (
        "CAMINO APRENDIDO" in text and "`inspiracion_video` → `planear_video`" in text
    )


def test_the_brain_grows_the_neuron_after_the_path_works_again(tmp_path):
    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    for _ in range(neurons.CHAIN_BIRTH):
        clock.t += 60
        brain.context("haz un short viral de recetas")
        for name, ok in PATH:
            brain.note_tool(name, ok)
        brain.observe(
            "haz un short viral de recetas", "Listo, tres opciones y el plan."
        )
    key = neurons.chain_key(PATH)
    assert brain.stats_["cadenas"][key] == neurons.CHAIN_BIRTH
    assert f"neurona:{key}" in brain.fly().codes  # born in the mushroom body
