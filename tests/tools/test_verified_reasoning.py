"""Reasoning produces checked numbers, not claims of model-level parity."""

import json
import xml.etree.ElementTree as ET

import pytest

from openjarvis.tools.scene_reason import SceneReasonTool, scene
from openjarvis.tools.verified_math import VerifiedMathTool, verified


def test_decimal_money_and_linear_equations_are_exact():
    assert verified("0.1+0.2")["exact"] == "3/10"
    assert verified("0.10000000000000001")["exact"] == "10000000000000001/100000000000000000"
    assert verified("99.90*3*1.15")["exact"] == "68931/200"
    for expected in range(-12, 12):
        result = verified(f"7*x+3={7 * expected + 3}")
        assert result["solutions"] == [str(expected)]
        assert result["residuals"] == ["0"] and result["verified"]


def test_equation_edge_cases_are_not_invented():
    assert set(verified("x**2-5*x+6=0")["solutions"]) == {"2", "3"}
    assert verified("x*x+1=0")["kind"] == "no_real_roots"
    assert verified("x*x=2")["verified"] is False
    assert verified("x-x=0")["kind"] == "identity"
    assert verified("x-x=1")["kind"] == "inconsistent"


@pytest.mark.parametrize("text", ["__import__('os').system('id')", "x.__class__", "[1]*1000000",
                                   "2**1000000", "2**(2**8)", "1e-99999999", "1e99999999",
                                   "1/0", "x**3=1", "true+1"])
def test_expression_rejects_code_and_unbounded_work(text):
    assert not VerifiedMathTool().execute(expression=text).success


def test_layout_checks_distance_collision_and_escape():
    result = scene([
        {"name": "Desk <script>", "position": [0, 0, 0], "size": [2, 1, 2]},
        {"name": "Chair", "position": [1, 0, 0], "size": [1, 1, 1]},
        {"name": "Lamp", "position": [4, 0, 0], "size": [1, 1, 1]},
    ])
    assert result["overlaps"] == [["Desk <script>", "Chair"]]
    assert result["distances"][0]["center_distance"] == 1
    assert result["mode"] == "proposal" and "no observación" in result["note"]
    svg = ET.fromstring(result["top_view_svg"])
    assert not any(element.tag.endswith("script") for element in svg.iter())


@pytest.mark.parametrize("size", [[float("nan"), 1, 1], [0, 1, 1], [1e-300, 1, 1]])
def test_invalid_dimensions_are_not_presented_as_valid_geometry(size):
    result = SceneReasonTool().execute(objects=[{"name": "a", "position": [0, 0, 0], "size": size}])
    assert not result.success


def test_live_math_works_without_a_cloud_agent():
    from openjarvis.speech.gemini_live import make_executor

    run, tools = make_executor(None)
    assert {t["function"]["name"] for t in tools} == {"verified_math", "scene_reason"}
    assert json.loads(run("verified_math", {"expression": "2*x+3=11"}))["solutions"] == ["4"]
