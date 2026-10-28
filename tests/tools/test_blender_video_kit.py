"""The kit's video helpers: a soft studio, the slow push-in camera, the
cutaway and the x-ray shell, documented for the 3D shot prompt."""

from __future__ import annotations

import ast

from openjarvis.tools.blender_kit import KIT, KIT_DOC
from openjarvis.tools.blender_model import check_script
from openjarvis.video_essay import blender3d


def test_video_helpers_exist_are_documented_and_safe():
    defined = {n.name for n in ast.parse(KIT).body if isinstance(n, ast.FunctionDef)}
    for name in ("kit_studio", "kit_camera_push", "kit_cutaway", "kit_xray"):
        assert name in defined and name in KIT_DOC
    assert "bpy.ops" not in KIT  # data API only
    check_script(
        "kit_studio()\nb = kit_sphere('B', 0.5)\nkit_cutaway(b)\nkit_xray(b)\n"
        "kit_camera_push((0, 0, 0.5), frames=60, orbit=20)\n"
    )


def test_the_3d_shot_prompt_teaches_the_inside_views():
    for word in ("kit_studio", "kit_camera_push", "kit_cutaway", "kit_xray"):
        assert word in blender3d.SCENE_PROMPT
