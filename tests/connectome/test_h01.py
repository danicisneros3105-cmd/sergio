"""Google's human cortex connectome (H01) wired into the brain (connectome/h01.py)."""

from __future__ import annotations

import gzip
import shutil

import pytest

from openjarvis.connectome import cortex, h01
from openjarvis.connectome.memory import kenyon_code


@pytest.fixture(scope="module")
def col():
    c = h01.column()
    assert c is not None, "the H01 files are missing or do not match their SHA-256"
    return c


def test_the_shipped_wiring_is_real_and_verified(col):
    info = col.describe()
    assert info["verificado"] and info["licencia"] == "CC BY 4.0"
    assert info["neuronas"] > 1000 and info["conexiones"] > 1000
    assert {"Layer 2", "Layer 4", "Layer 5"} <= set(info["capas"])
    assert info["tipos"]["PYRAMIDAL"] > info["tipos"]["INTERNEURON"] > 0


def test_a_request_enters_through_layer_4_and_spreads(col):
    run = col.run(kenyon_code("explícame cómo funciona la inflación"))
    first = run["pasos"][0]
    assert len(first) and (col.layer[first] == 3).mean() > 0.5  # thalamus → layer 4
    assert len(run["pasos"]) >= 2 and len(run["activas"]) >= len(first)
    assert (
        col.run(kenyon_code("explícame cómo funciona la inflación"))["activas"].tolist()
        == run["activas"].tolist()
    )


def test_interneurons_inhibit_and_pyramids_excite(col):
    kinds = [col.kind[i] for i in col.pre]
    for kind, w in zip(kinds, col.weight):
        if kind in h01.INHIBITORY:
            assert w < 0
        elif kind in h01.EXCITATORY:
            assert w > 0


def test_like_lights_up_like(col):
    p = cortex.column_proof()
    assert p["parecidos"] > p["distintos"] + 0.2


def test_the_basal_ganglia_read_the_column(monkeypatch, tmp_path):
    b = cortex.HumanBrain(tmp_path, terry=False)
    t = b.think("explícame cómo funciona la inflación", "chat")
    assert t.percept.cortex and t.percept.column.get("Layer 4")
    assert any(cortex.KENYON_CELLS <= i < cortex.DENSE_AT for i in t.x_idx)
    monkeypatch.setenv("SERGIO_H01", "0")
    off = cortex.HumanBrain(tmp_path / "off", terry=False).think(
        "explícame algo", "chat"
    )
    assert off.percept.cortex == []


def test_altered_files_are_refused(tmp_path):
    for f in h01.DATA.iterdir():
        if f.is_file():
            shutil.copy(f, tmp_path / f.name)
    with gzip.open(tmp_path / "h01_sinapsis.csv.gz", "at") as f:
        f.write("1,2,99,0,0\n")
    assert not h01.Column(tmp_path).verified
