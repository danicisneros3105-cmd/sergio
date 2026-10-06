import json

import pytest

from openjarvis.tools.holo_model import design, parse_recipe, recipe_brief


def test_recipe_is_checked():
    text = json.dumps({"name": "silla", "parts": [
        {"name": "asiento", "shape": "rounded_box", "size": [0.45, 0.05, 0.45], "pos": [0, 0.45, 0],
         "rot": [0, 0, 370], "color": [2, -1, 0.5]},
        {"name": "rara", "shape": "nube", "size": "x"},
        "basura",
    ]})  # fmt: skip
    r = parse_recipe("```json\n" + text + "\n```")
    assert [p["shape"] for p in r["parts"]] == ["rounded_box", "box"]
    assert r["parts"][0]["color"] == [1.0, 0.0, 0.5] and r["parts"][0]["rot"][2] == 10
    assert "asiento: rounded_box 45.0 x 5.0 x 45.0 cm" in recipe_brief(r)
    with pytest.raises(RuntimeError):
        parse_recipe('{"parts": []}')


def test_design_asks_for_real_parts():
    seen = {}

    def ask(prompt):
        seen["p"] = prompt
        return json.dumps({"name": "dron", "parts": [{"shape": "box", "size": [0.3, 0.05, 0.3]}]})

    assert design("un dron", ask=ask)["name"] == "dron"
    assert "METRES" in seen["p"] and "un dron" in seen["p"]
