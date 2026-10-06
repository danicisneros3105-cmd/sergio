"""Blender Pro: blueprint sheet, photo modelling, four-view reviews."""

from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path

import pytest

from openjarvis.tools import blender_model as bm
from openjarvis.tools import blender_pro as bp

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
SCRIPT = (
    "import bpy\n"
    "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
    "def body():\n"
    "    bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=0.07, location=(0, 0, 0.035))\n"
    "    bpy.context.object.name = 'Cuerpo'\n"
    "def tip():\n"
    "    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.008, location=(0, 0, 0.075))\n"
    "    bpy.context.object.name = 'Punta'\n"
    "def broken():\n"
    "    bpy.ops.mesh.primitive_cube_add(sizee=1)\n"
    "body(); tip(); broken()\n"
)
ANSWER = json.dumps(
    {"name": "labial", "description": "Un labial rojo.", "dimensions_cm": [2, 2, 8], "parts": 2, "script": SCRIPT}
)


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[list, str]] = []

    def __call__(self, images, prompt):
        self.calls.append((images, prompt))
        return ANSWER


def test_text_jobs_model_from_a_blueprint_sheet():
    ask = Recorder()
    drawn: list[str] = []
    model = bp.from_text(
        "un labial rojo", "C:/x/l.blend", "C:/x/l.png", ask=ask,
        draw=lambda prompt, photo: drawn.append(prompt) or PNG,
    )
    images, prompt = ask.calls[0]
    assert drawn and "FRONT" in drawn[0] and "un labial rojo" in drawn[0]
    assert images == [(PNG, "image/png")] and "blueprint reference sheet" in prompt
    assert "ONE FUNCTION PER" in prompt and "lathe" in prompt  # pro technique rules
    assert base64.b64decode(model["reference_b64"]) == PNG
    assert model["raw_script"] == SCRIPT and "SERGIO_SAVED" in model["script"]


def test_without_an_image_model_it_still_models():
    def no_draw(prompt, photo):
        raise RuntimeError("quota")

    ask = Recorder()
    model = bp.from_text("una taza", "C:/x/t.blend", ask=ask, draw=no_draw)
    assert ask.calls[0][0] == [] and "blueprint" not in ask.calls[0][1]
    assert "reference_b64" not in model


def test_photo_jobs_send_the_photo_and_a_sheet_of_the_same_object():
    ask = Recorder()
    seen: list[bytes] = []
    photo = b"\xff\xd8jpeg"
    bp.from_photo(photo, "C:/x/o.blend", "", ask=ask, draw=lambda p, ph: seen.append(ph) or PNG)
    images, prompt = ask.calls[0]
    assert seen == [photo]  # the sheet is drawn from the photo itself
    assert images == [(photo, "image/jpeg"), (PNG, "image/png")]
    assert "PHOTO of the real object" in prompt and "hand is ~18 cm" in prompt


def test_reviews_see_four_views_the_references_and_the_target_size():
    ask = Recorder()
    log = "SERGIO_SAVED x 2\nSERGIO_DIMS width 2.0 x depth 2.0 x height 15.0 cm\nSERGIO_STEP_ERROR in broken()"
    bp.refine(
        "un labial", SCRIPT, log, PNG, "C:/x/l.blend", ask=ask,
        reference=b"\xff\xd8photo", target_cm=[2, 2, 8], sheet=PNG,
    )
    images, prompt = ask.calls[0]
    assert [m for _, m in images] == ["image/jpeg", "image/png", "image/png"]
    assert "Target real size: 2 x 2 x 8 cm" in prompt and "SERGIO_DIMS" in prompt
    assert "top right FRONT" in prompt and "blueprint reference sheet" in prompt


BPY = os.environ.get("SERGIO_BPY_PYTHON", "")


@pytest.mark.skipif(not (BPY and Path(BPY).exists()), reason="Blender (bpy) not available")
def test_blender_saves_measures_and_renders_the_four_view_sheet(tmp_path):
    target, preview = tmp_path / "labial.blend", tmp_path / "vista.png"
    script = tmp_path / "labial.py"
    script.write_text(bm.finish_script(SCRIPT, str(target), "labial", str(preview)))
    done = subprocess.run(
        [BPY, "-c", f"import runpy; runpy.run_path({str(script)!r})"],
        capture_output=True, text=True, timeout=600, cwd=tmp_path,
    )
    out = done.stdout
    assert "SERGIO_SAVED" in out and "SERGIO_STEP_ERROR in broken()" in out, done.stderr[-2000:]
    assert "SERGIO_DIMS width 2.0 x depth 2.0 x height 8.3 cm" in out
    assert "SERGIO_PARTS 2 meshes: Cuerpo, Punta" in out
    assert "SERGIO_PREVIEW" in out, out[-2000:]
    from PIL import Image

    assert Image.open(preview).size == (1024, 1024)
    assert not list(tmp_path.glob("vista-*.png"))  # the single views were cleaned up
