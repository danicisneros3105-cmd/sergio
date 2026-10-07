"""The object in your hands -> a checked Blender script that saves a .blend."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from openjarvis.tools import blender_model as bm

GOOD = """import bpy, bmesh, math
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
root = bpy.data.objects.new("Taza", None)
bpy.context.scene.collection.objects.link(root)
bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.09, location=(0, 0, 0.045))
body = bpy.context.active_object
body.parent = root
mat = bpy.data.materials.new("Cerámica")
mat.use_nodes = True
body.data.materials.append(mat)
"""


@pytest.mark.parametrize(
    "bad, why",
    [
        ("import os\nos.remove('x')", "importa os"),
        ("import subprocess", "importa subprocess"),
        ("from urllib import request", "importa urllib"),
        ("open('x', 'w').write('y')", "usa open()"),
        ("exec('1')", "usa exec()"),
        ("x = ().__class__", "usa __class__"),
        (
            "import bpy\nbpy.ops.wm.save_as_mainfile(filepath='C:/x.blend')",
            "usa bpy.ops.wm.save",
        ),
        (
            "import bpy\nbpy.app.handlers.load_post.append(print)",
            "usa bpy.app.handlers",
        ),
        ("import bpy\nbpy.ops.script.reload()", "usa bpy.ops.script."),
        ("def broken(:\n  pass", "no compila"),
    ],
)
def test_anything_but_modelling_is_refused(bad, why):
    with pytest.raises(
        bm.UnsafeScript, match=why.replace("(", r"\(").replace(")", r"\)")
    ):
        bm.check_script(bad)


def test_plain_modelling_passes_and_sergio_adds_the_ending():
    bm.check_script(GOOD)
    full = bm.finish_script(
        GOOD, r"C:\Users\dani\Documents\Sergio\Blender\taza.blend", "taza"
    )
    assert json.dumps(GOOD.rstrip()) in full and "SERGIO_STEP_ERROR" in full  # run step by step
    assert "save_as_mainfile" in full and "SERGIO_SAVED" in full
    assert json.dumps(r"C:\Users\dani\Documents\Sergio\Blender\taza.blend") in full


def test_model_object_asks_again_when_the_script_is_unsafe():
    answers = [
        json.dumps({"name": "taza", "script": "import os\nos.system('x')"}),
        json.dumps(
            {
                "name": "taza",
                "description": "Una taza",
                "dimensions_cm": [8, 8, 9.5],
                "parts": 3,
                "script": GOOD,
            }
        ),
    ]
    prompts = []

    def ask(_image, prompt, _mime):
        prompts.append(prompt)
        return answers.pop(0)

    model = bm.model_object(b"jpg", "/tmp/x.blend", "es mi taza", ask=ask)
    assert (
        model["name"] == "taza"
        and model["dimensions_cm"] == [8.0, 8.0, 9.5]
        and model["parts"] == 3
    )
    assert "refused: importa os" in prompts[1] and "es mi taza" in prompts[0]
    with pytest.raises(RuntimeError, match="no lo ejecuto"):
        bm.model_object(
            b"jpg",
            "/tmp/x.blend",
            ask=lambda *_a: json.dumps({"script": "import socket"}),
        )


BPY = os.environ.get("SERGIO_BPY_PYTHON", "")


@pytest.mark.skipif(
    not (BPY and Path(BPY).exists()), reason="Blender (bpy) not available"
)
def test_the_finished_script_really_builds_and_saves_in_blender(tmp_path):
    target = tmp_path / "taza.blend"
    script = tmp_path / "taza.py"
    script.write_text(bm.finish_script(GOOD, str(target), "taza"))
    done = subprocess.run(
        [BPY, "-c", f"import runpy; runpy.run_path({str(script)!r})"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert "SERGIO_SAVED" in done.stdout, done.stderr[-2000:]
    assert target.exists() and target.stat().st_size > 10_000


def test_the_saved_project_is_checked_and_ready_for_a_final_render():
    full = bm.finish_script("import bpy\n", "/tmp/x.blend", "x", "/tmp/x.png")
    assert full.index("SERGIO_TOPOLOGY") < full.index("save_as_mainfile")  # fixed before saving
    for setting in ('"cycles.adaptive_threshold", 0.01', '"cycles.transparent_max_bounces", 32',
                    '"RGB_ALBEDO_NORMAL"', '"MULTI_LAYER_IMAGE"', "use_pass_cryptomatte_object"):
        assert setting in full
    assert 'file_format = "PNG"' in full  # the review previews stay PNG
    compile(full, "finish", "exec")
