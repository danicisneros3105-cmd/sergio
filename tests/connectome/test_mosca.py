"""The fly's real brain — FlyWire, mapped by Google and Princeton — in the core."""

import shutil

import numpy as np

from openjarvis.connectome import decision, mosca
from openjarvis.connectome.memory import kenyon_code


def test_the_real_wiring_is_there_and_verified():
    f = mosca.fly()
    assert f is not None, "the FlyWire files are missing or do not match their SHA-256"
    d = f.describe()
    # the WHOLE brain by default (owner, 2 Nov 2026: «neuronas reales completas»)
    assert d["verificado"] and d["neuronas"] == 139255
    assert d["conexiones"] > 1_000_000 and d["sinapsis"] > 20_000_000
    assert d["neuronas_cerebro_completo"] == 139255
    central = mosca.Fly(prefix="mosca").describe()
    assert (
        central["verificado"]
        and central["neuronas"] == 49434
        and central["conexiones"] > 500_000
    )
    assert d["zonas"]["células de Kenyon"] > 5000
    assert "FlyWire" in d["fuente"] and "Google" in d["fuente"]


def test_signs_follow_the_transmitter():
    f = mosca.fly()
    w = f.weight
    assert (w > 0).any() and (w < 0).any()  # acetylcholine excites, GABA inhibits


def test_activity_goes_from_the_senses_inward():
    f = mosca.fly()
    path = f.path(kenyon_code("pon música para dormir"))
    first = path[0]["zonas"]
    assert set(first) <= {"olfato", "tacto", "gusto", "temperatura", "humedad"}
    later = {z for p in path[1:] for z in p["zonas"]}
    assert "células de Kenyon" in later


def test_like_with_like():
    p = decision.column_proof()
    assert p["parecidos"] > p["distintos"] + 0.15


def test_the_decision_reads_the_fly(tmp_path, monkeypatch):
    b = decision.FlyBrain(tmp_path, terry=False)
    t = b.think("explícame cómo funciona la inflación", "chat")
    assert any(decision.KENYON_CELLS <= i < decision.DENSE_AT for i in t.x_idx)
    monkeypatch.setenv("SERGIO_MOSCA", "0")
    off = decision.FlyBrain(tmp_path / "off", terry=False).think(
        "explícame cómo funciona la inflación", "chat"
    )
    assert not any(decision.KENYON_CELLS <= i < decision.DENSE_AT for i in off.x_idx)


def test_regions_are_the_flys():
    names = [r["region"] for r in decision.REGIONS]
    assert "Cuerpo fungiforme" in names and "Complejo central" in names
    assert not {"Amígdala", "Hipocampo", "Neocorteza", "Tálamo"} & set(names)


def test_altered_files_are_refused(tmp_path):
    for f in mosca.DATA.iterdir():
        if f.name.startswith("mosca"):
            shutil.copy(f, tmp_path / f.name)
    for name in ("mosca_sinapsis.npz", "mosca_completa_sinapsis.npz"):
        data = dict(np.load(tmp_path / name))
        data["syn"] = data["syn"] + 1
        np.savez_compressed(tmp_path / name, **data)
    assert not mosca.Fly(tmp_path).verified
    assert not mosca.Fly(tmp_path, prefix="mosca").verified


def test_the_old_folder_moves_over(tmp_path):
    old = decision.FlyBrain(tmp_path / "connectome" / "humano", terry=False)
    old.mbon.go[:, 0] = 1.0
    old.mbon.go[:, decision.KENYON_CELLS] = 1.0
    old.save(force=True)
    decision._BRAINS.clear()
    new = decision.get_brain(tmp_path)
    assert new.mbon.go[0, 0] == 1.0  # his taste in words stays
    assert new.mbon.go[0, decision.KENYON_CELLS] == 0.0  # the old wiring's part goes
