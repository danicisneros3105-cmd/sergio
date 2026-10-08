"""VFX effects: every script compiles, parameters are validated, and — when a
Blender is available (SERGIO_BPY_PYTHON or SERGIO_BLENDER) — runs for real."""

from __future__ import annotations

import os

import pytest

from openjarvis.vfx import EFFECTS, build_scene, catalog, effect, find_blender, run

CASES = [
    ("smoke_fire", {"resolution": 24}),
    ("fluid", {"resolution": 24, "scenario": "splash"}),
    ("destruction", {"pieces": 10, "frames": 25, "bake": True}),
    ("cloth", {"scenario": "drape", "subdivisions": 14, "frames": 25, "bake": True}),
    ("cloth", {"scenario": "garment", "subdivisions": 10, "frames": 20, "bake": True}),
    ("hair_fur", {"preset": "curly"}),
    ("volumetrics", {"layers": "sky,clouds,fog,god_rays"}),
    ("shaders", {"shader": "hologram"}),
    ("shaders", {"shader": "dissolve"}),
    ("shaders", {"shader": "gold"}),
    ("geo_nodes", {"kind": "city", "count": 36}),
    ("geo_nodes", {"kind": "scatter", "count": 120}),
]


@pytest.mark.parametrize(("name", "params"), CASES)
def test_every_script_is_valid_python(name, params):
    compile(build_scene([(name, params)], save="/tmp/x.blend"), f"<{name}>", "exec")


def test_catalog_and_parameter_checks():
    cat = catalog()
    assert set(cat) == set(EFFECTS) and all(c["description"] and c["params"] for c in cat.values())
    with pytest.raises(ValueError, match="unknown parameter"):
        effect("cloth").build(colour="red")
    with pytest.raises(ValueError, match="unknown effect"):
        effect("teleport")
    assert "fabric = 'denim'" not in effect("cloth").build(fabric="denim")  # values are code literals, not names
    assert '"denim"' in effect("cloth").build(fabric="denim")


def test_effects_combine_into_one_scene():
    script = build_scene([("volumetrics", {"layers": "sky"}), ("shaders", {"shader": "lava"}),
                          ("geo_nodes", {"kind": "scatter"})], preview="/tmp/p.png", frames=(1, 12))
    assert script.count("vfx_reset()") == 2  # the definition + one call
    assert "VFX_OK" in script and '"/tmp/p.png"' in script


@pytest.mark.skipif(find_blender() is None, reason="no Blender here (set SERGIO_BPY_PYTHON or SERGIO_BLENDER)")
@pytest.mark.parametrize(("name", "params"), CASES)
def test_effect_runs_in_real_blender(name, params):
    if name in ("smoke_fire", "fluid") and os.environ.get("SERGIO_BPY_PYTHON") and not os.environ.get("SERGIO_BLENDER"):
        params = {**params, "bake": False}  # the bpy pip module cannot run Mantaflow
    result = run(build_scene([(name, params)]), timeout=900)
    assert result.ok, result.log[-2000:]
    assert result.info["effect"] == name
    if name == "destruction":
        assert result.info["shards"] >= 6 and result.info["moved"] >= 1
    if name == "cloth":
        assert result.info["lowest_z"] > -0.05  # never falls through the floor
    if name == "geo_nodes":
        assert result.info["evaluated_vertices"] > 100
