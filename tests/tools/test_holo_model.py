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
        return json.dumps(
            {"name": "dron", "parts": [{"shape": "box", "size": [0.3, 0.05, 0.3]}]}
        )

    assert design("un dron", ask=ask)["name"] == "dron"
    assert "METRES" in seen["p"] and "un dron" in seen["p"]


def test_curved_parts_keep_their_points_and_bad_ones_become_boxes():
    import json as _json

    from openjarvis.tools.holo_model import parse_recipe, recipe_brief

    r = parse_recipe(
        _json.dumps(
            {
                "name": "taza",
                "parts": [
                    {
                        "name": "cuerpo",
                        "shape": "lathe",
                        "profile": [[0, 0], [-0.04, 0], [0.045, 0.1], [0, 0.1]],
                    },
                    {
                        "name": "asa",
                        "shape": "tube",
                        "path": [[0.04, 0.07, 0], [0.07, 0.05, 0]],
                        "radius": "0.006",
                    },
                    {
                        "name": "logo",
                        "shape": "extrude",
                        "outline": [[0, 0], [1, 0]],
                    },  # too few points
                ],
            }
        )
    )
    body, handle, logo = r["parts"]
    assert (
        body["profile"][1] == [0.04, 0.0]
        and handle["radius"] == 0.006
        and logo["shape"] == "box"
    )
    brief = recipe_brief(r)
    assert (
        "lathe profile (radius, height) cm (0.0, 0.0), (4.0, 0.0)" in brief
        and "tube path" in brief
    )


def test_short_quota_pauses_are_waited_out_once():
    from openjarvis.engine.google_client import short_wait

    assert (
        short_wait(
            [
                "a: 429 RESOURCE_EXHAUSTED (vuelve en ~1 min)",
                "b: 503 UNAVAILABLE high demand",
            ]
        )
        == 65.0
    )
    assert (
        short_wait(["a: 429 RESOURCE_EXHAUSTED (vuelve en ~177 min)"]) == 0.0
    )  # a long pause: tell the user
    assert short_wait(["a: 404 not found"]) == 0.0 and short_wait([]) == 0.0
