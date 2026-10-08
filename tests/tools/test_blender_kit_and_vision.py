"""Blender Pro: the modelling kit, the vision check, self-correction,
surgical edits and generated-model import."""

from __future__ import annotations

import ast
import json

import pytest

from openjarvis.tools import blender_examples as ex
from openjarvis.tools import blender_model as bm
from openjarvis.tools import blender_pro as bp
from openjarvis.tools.blender_kit import KIT, KIT_DOC


def test_the_kit_compiles_and_every_documented_function_exists():
    tree = ast.parse(KIT)
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in ("kit_lathe", "kit_extrude", "kit_tube", "kit_box", "kit_cylinder", "kit_sphere", "kit_material",
                 "kit_text", "kit_parent", "kit_copy", "kit_mirror_x", "kit_array_circle", "kit_cut",
                 "kit_rounded_rect", "kit_circle_points", "kit_bevel", "kit_subsurf", "kit_smooth"):
        assert name in defined and name in KIT_DOC or name in ("kit_rounded_rect",)
    assert "bpy.ops" not in KIT  # data API only: works headless in any Blender


def test_every_build_gets_the_kit_and_skips_boolean_cutters():
    script = bm.finish_script("import bpy\nSERGIO_LAYOUT = []\nkit_box('A', (1, 1, 1))\n", "C:/x.blend", "x")
    assert '"<kit>"' in script and json.dumps(KIT)[:40] in script
    assert 'not o.get("sergio_cutter")' in script and "SERGIO_BBOX" in script and "SERGIO_BLENDER" in script


def test_the_rules_teach_the_kit_and_the_seeds_use_it():
    assert "kit_lathe" in bp.RULES and "pile of plain cubes" in bp.RULES
    seeds = {e["request"]: e["script"] for e in ex.all_examples() if e.get("seed")}
    kit_seeds = [s for s in seeds.values() if "kit_" in s]
    assert len(kit_seeds) >= 2  # the cup and the phone
    for script in kit_seeds:
        bm.check_script(script)
        assert bp.static_report(script) == ""


def test_static_report_catches_a_pile_of_cubes():
    cubes = "import bpy\nSERGIO_LAYOUT = []\n" + "bpy.ops.mesh.primitive_cube_add()\n" * 4
    assert "plain cubes" in bp.static_report(cubes)
    assert "no SERGIO_LAYOUT" in bp.static_report("import bpy\nkit_lathe('a', [(0,0),(1,1)])\n")
    assert "safety" in bp.static_report("import os\n")


def test_self_correction_sends_a_cube_pile_back_once_and_keeps_the_fix(monkeypatch):
    lessons = []
    monkeypatch.setattr("openjarvis.evolution.memory.shared",
                        lambda: type("M", (), {"remember": lambda self, k, t: lessons.append((k, t))})())
    cubes = json.dumps({"name": "silla", "script": "import bpy\nSERGIO_LAYOUT = []\n" + "bpy.ops.mesh.primitive_cube_add()\n" * 5})
    good = json.dumps({"name": "silla", "script": "import bpy\nSERGIO_LAYOUT = []\nkit_box('Asiento', (0.4, 0.4, 0.05), bevel=0.01)\n"})
    asked = []

    def ask(images, prompt):
        asked.append(prompt)
        return good

    model = bp._checked(cubes, ask, [], "PROMPT", "una silla")
    assert "kit_box" in model["script"] and len(asked) == 1
    assert "plain cubes" in asked[0]  # the reason travels with the retry
    assert lessons and lessons[0][0] == "lesson"


def test_unsafe_scripts_are_never_returned():
    bad = json.dumps({"name": "x", "script": "import os\nos.remove('a')\n"})
    with pytest.raises(bm.UnsafeScript):
        bp._checked(bad, lambda images, prompt: bad, [], "P", "x")


def test_the_vision_verdict_is_checked_and_turned_into_review_notes():
    v = bp.parse_verdict('{"looks_like": "una caja", "is_it": true, "score": 14, "problems": ["asa: falta"]}')
    assert v["score"] == 10.0 and v["is_it"]
    low = bp.parse_verdict('{"looks_like": "una caja", "is_it": true, "score": 3, "problems": ["asa: falta"]}')
    assert not low["is_it"]  # 3/10 is never "it"
    note = bp.vision_note(low)
    assert "SERGIO_VISION score 3.0/10" in note and "NOT recognisable" in note and "SERGIO_VISION_FIX asa: falta" in note
    with pytest.raises(RuntimeError):
        bp.parse_verdict("no json")


def test_verify_sends_references_and_asks_blind_first():
    seen = {}

    def ask(images, prompt):
        seen["n"], seen["prompt"] = len(images), prompt
        return '{"looks_like": "una tetera", "is_it": true, "score": 8, "problems": [], "good": ["forma"]}'

    v = bp.verify("una tetera", b"\x89PNG..", reference=b"\xff\xd8ref", ask=ask)
    assert v["score"] == 8 and seen["n"] == 2 and "blind" in seen["prompt"] and "«una tetera»" in seen["prompt"]


LOG_A = "SERGIO_BBOX Asa | 5.0 0.0 6.0 | 1.0 3.0 6.0\nSERGIO_BBOX Cuerpo | 0.0 0.0 5.0 | 9.0 9.0 10.0\nSERGIO_BBOX Plato | 0.0 0.0 0.5 | 15.0 15.0 1.0\n"
LOG_B = "SERGIO_BBOX Asa | 6.0 0.0 6.0 | 2.0 3.0 8.0\nSERGIO_BBOX Cuerpo | 0.0 0.0 5.0 | 9.0 9.0 10.0\nSERGIO_BBOX Plato | 0.0 0.0 0.9 | 15.0 15.0 1.0\nSERGIO_BBOX Logo | 0 -4 6 | 3 0.1 1\n"


def test_surgical_report_tells_edited_from_collateral():
    rep = bp.surgical_report(LOG_A, LOG_B, ["Asa", "Logo"])
    assert rep["kept"] == 1 and "Asa" in rep["edited"] and "Logo" in rep["added"]
    assert rep["collateral"] == ["Plato"]  # it moved but was not asked for
    assert bp.bboxes(LOG_A)["Cuerpo"] == (0.0, 0.0, 5.0, 9.0, 9.0, 10.0)


def test_a_surgical_edit_keeps_the_script_and_lists_what_changed():
    seen = {}

    def ask(images, prompt):
        seen["prompt"] = prompt
        return json.dumps({"name": "taza", "changed": ["Asa"], "script": "import bpy\nSERGIO_LAYOUT = []\nkit_box('Asa', (1, 1, 1))\n"})

    m = bp.edit("una taza", "import bpy\nkit_box('Asa', (1,1,1))\n", "haz el asa más grande", b"png", "C:/t.blend",
                ask=ask, collateral=["Plato"])
    assert m["changed"] == ["Asa"] and m["instruction"] == "haz el asa más grande"
    assert "Change ONLY what the edit asks" in seen["prompt"] and "Plato" in seen["prompt"]
    assert "SERGIO_SAVED" in m["script"]


def test_generated_models_are_imported_to_real_size_on_the_floor():
    m = bp.import_model("C:/t/modelo.glb", "C:/t/m.blend", "C:/t/v.png", "Dragón", size_cm=40)
    assert "import_scene.gltf" in m["raw_script"] and '"C:/t/modelo.glb"' in m["raw_script"]
    assert "0.4000" in m["raw_script"] and "normalise()" in m["raw_script"] and "SERGIO_SAVED" in m["script"]


def test_prompts_carry_the_blender_version_and_memory_lessons(monkeypatch):
    monkeypatch.setattr(bp, "_lessons", lambda request: "LESSONS FROM YOUR LONG-TERM MEMORY: asa fina\n")
    seen = {}

    def ask(images, prompt):
        seen["prompt"] = prompt
        return json.dumps({"name": "taza", "script": "import bpy\nSERGIO_LAYOUT = []\nkit_lathe('T', [(0,0),(1,1)])\n"})

    bp.from_text("una taza", "C:/x.blend", ask=ask, sheet=b"", version="4.2.1")
    assert "Blender is 4.2.1" in seen["prompt"] and "asa fina" in seen["prompt"]
