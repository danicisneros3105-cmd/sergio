"""Blender Pro's worked examples (in-context training) and spatial check."""

from __future__ import annotations

from openjarvis.tools import blender_examples as ex
from openjarvis.tools import blender_model as bm
from openjarvis.tools import blender_pro

GOOD_LOG = """SERGIO_TOPOLOGY normals fixed 0, non-manifold edges 0, open border edges 0, loose vertices 0, curved parts smoothed 0
SERGIO_SPATIAL planned 5, found 5, in place 5; floating 0; below ground 0
SERGIO_SAVED C:/x.blend 9
SERGIO_PARTS 9 meshes: a, b"""


def test_the_seeds_are_safe_complete_and_plan_their_space():
    seeds = [e for e in ex.all_examples() if e.get("seed")]
    assert len(seeds) >= 2
    for seed in seeds:
        bm.check_script(seed["script"])  # passes Sergio's safety check
        assert "SERGIO_LAYOUT = [" in seed["script"] and "def " in seed["script"]
        if "import bmesh" in seed["script"]:  # bmesh only exists once bpy is loaded
            assert seed["script"].index("import bpy") < seed["script"].index(
                "import bmesh"
            )


def test_the_closest_example_comes_first_within_budget(tmp_path):
    assert ex.similar("una taza de café con plato", k=1, folder=tmp_path)[0][
        "request"
    ].startswith("una taza")
    assert ex.similar("una mesa de comedor", k=1, folder=tmp_path)[0][
        "request"
    ].startswith("una mesa")
    picked = ex.similar("una lámpara", k=2, max_chars=10**6, folder=tmp_path)
    assert len(picked) == 2
    assert (
        sum(
            len(e["script"])
            for e in ex.similar("algo", max_chars=4000, folder=tmp_path)
        )
        <= 4000
    )


def test_only_clean_builds_become_examples(tmp_path):
    assert ex.remember("una silla", "print(1)", GOOD_LOG, folder=tmp_path)["saved"]
    floating = GOOD_LOG.replace("floating 0", "floating 1")
    assert ex.remember("otra", "x", floating, folder=tmp_path)["why"].startswith(
        "piezas fuera"
    )
    broken = GOOD_LOG.replace("non-manifold edges 0", "non-manifold edges 4")
    assert (
        ex.remember("otra", "x", broken, folder=tmp_path)["why"] == "malla con errores"
    )
    no_plan = GOOD_LOG.replace(
        "planned 5, found 5, in place 5", "planned 0, found 0, in place 0"
    )
    assert not ex.remember("otra", "x", no_plan, folder=tmp_path)["saved"]
    assert (
        ex.similar("una silla de madera", k=1, folder=tmp_path)[0]["request"]
        == "una silla"
    )


def test_the_prompt_teaches_with_examples_and_asks_for_a_spatial_plan():
    seen = []

    def ask(images, prompt):
        seen.append(prompt)
        return '{"name": "taza", "script": "import bpy\\nSERGIO_LAYOUT = []\\n"}'

    blender_pro.from_text("una taza grande", "C:/x.blend", ask=ask, sheet=b"")
    assert "Worked examples" in seen[0] and "Example for «una taza" in seen[0]
    assert (
        "SPATIAL PLAN FIRST" in seen[0] and "transform_apply(location=False" in seen[0]
    )


def test_the_finished_script_measures_plan_against_build():
    full = bm.finish_script("import bpy\n", "/tmp/x.blend", "x", "")
    for line in (
        "SERGIO_LAYOUT_OFF",
        "SERGIO_FLOATING",
        "SERGIO_BELOW_GROUND",
        "SERGIO_SPATIAL planned",
        "view_layer.update()",
    ):
        assert line in full
    assert full.index("SERGIO_SPATIAL planned") < full.index("save_as_mainfile")
    compile(full, "finish", "exec")


def test_old_socket_names_are_renamed_and_a_floating_model_is_grounded():
    script, fixed = bm.fix_api(
        'b.inputs["Clearcoat Weight"].default_value = 1\nb.inputs["Transmission"].x = 1\n'
        'b.inputs["Transmission Weight"].x = 1'
    )
    assert (
        'inputs["Coat Weight"]' in script and 'inputs["Transmission Weight"]' in script
    )
    assert '"Clearcoat Weight"' not in script and len(fixed) == 2
    full = bm.finish_script('b.inputs["Emission"].x = 1\n', "/tmp/x.blend", "x", "")
    assert "SERGIO_API_FIXED" in full and 'inputs[\\"Emission Color\\"]' in full
    assert "SERGIO_GROUNDED" in full and full.index("SERGIO_GROUNDED") < full.index(
        "save_as_mainfile"
    )
    compile(full, "finish", "exec")
