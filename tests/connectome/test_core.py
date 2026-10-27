"""The new core: the measured wiring, the mushroom body, receptors, the hive."""

from __future__ import annotations

import hashlib
import json
import time

import numpy as np
import pytest

from openjarvis.connectome import flywire
from openjarvis.connectome.colmena import Colmena, Organ, Supervisor
from openjarvis.connectome.core import Core
from openjarvis.connectome.mushroom import GROW_AFTER, MushroomBody
from openjarvis.connectome.receptors import Receptors


class Meaning:
    """A fake embedder: sentences about the same topic point the same way."""

    space = "prueba-8"
    TOPICS = ("video", "dinero", "salud", "viaje")

    def __call__(self, texts):
        out = []
        for t in texts:
            v = np.full(8, 0.1, dtype=np.float32)
            for i, topic in enumerate(self.TOPICS):
                if topic in t:
                    v[i] += 1.0
            v[4 + len(t) % 4] += 0.05
            out.append(v / np.linalg.norm(v))
        return np.stack(out)


def _tiny_graph():
    """2 PNs, 3 KCs, 1 MBON, 1 DAN as a destination-row CSR graph."""
    types = ["PN_a", "PN_b", "KCg-m", "KCab-c", "KCa'b'-ap1", "MBON01", "PAM01"]
    inputs = {  # destination: [(source, weight)]
        2: [(0, 5.0), (1, 2.0)],
        3: [(1, 4.0)],
        4: [(0, 1.0)],
        5: [(2, 3.0), (3, 6.0), (6, 9.0)],
    }
    offsets, source, weight = [0], [], []
    for dst in range(len(types)):
        for s, w in inputs.get(dst, []):
            source.append(s)
            weight.append(w)
        offsets.append(len(source))
    return (
        np.array(offsets, dtype=np.int32),
        np.array(source, dtype=np.uint16),
        np.array(weight, dtype=np.float32),
        types,
    )


def test_the_mushroom_body_is_extracted_from_a_measured_graph():
    w = flywire.extract(*_tiny_graph(), {"source": "prueba"})
    assert (w.n_pn, w.n_kc, w.n_mbon) == (2, 3, 1)
    assert list(w.claws[0][:2]) == [0, 1]  # strongest claw first
    assert w.mask0[0].tolist() == [True, True, False]  # only measured KC->MBON
    assert w.mbon_dan[0] == 0 and w.kc_class == ["gamma", "alpha-beta", "alpha'-beta'"]
    assert w.info["kc_mbon_synapses"] == 2


def test_download_verifies_every_file_and_refuses_a_wrong_one(tmp_path):
    offsets, source, weight, types = _tiny_graph()
    blobs = {
        "graph/edges_offsets.i32": offsets.tobytes(),
        "graph/edges_source.u16": source.tobytes(),
        "graph/edges_weight.f32": weight.tobytes(),
        "neurons/cell_type.json": json.dumps(types).encode(),
    }
    manifest = {
        "neurons": 7,
        "files": {
            k: {"sha256": hashlib.sha256(blobs[p]).hexdigest()}
            for k, p in flywire.FILES.items()
        },
    }
    blobs["manifest.json"] = json.dumps(manifest).encode()
    w = flywire.download(tmp_path, fetch=blobs.__getitem__)
    assert w.info["real"] and (tmp_path / "mb.npz").exists()
    again = flywire.load(tmp_path)
    assert again.n_kc == 3 and again.info["sha256"]

    blobs["graph/edges_source.u16"] = b"\x00\x00" * len(source)
    with pytest.raises(ValueError, match="huella"):
        flywire.download(tmp_path / "mal", fetch=blobs.__getitem__)


def test_without_the_download_the_stand_in_has_the_published_counts(tmp_path):
    w = flywire.load(tmp_path)
    assert not w.info.get("real")
    assert (w.n_pn, w.n_kc) == (150, 2000)
    claws = (w.claws >= 0).sum(1)
    assert 5 <= claws.mean() <= 9  # about 7 claws per Kenyon cell


def test_learning_changes_measured_synapses_and_grows_new_ones():
    mb = MushroomBody(flywire.synthetic())
    text = "edita mi video de viaje"
    before = mb.scores(text, ["a", "b"])
    out = {"grown": 0}
    for _ in range(GROW_AFTER):
        out = mb.learn(text, "a", 1.0)
    after = mb.scores(text, ["a", "b"])
    assert after["a"] > before["a"] and after["a"] > after["b"]
    assert out["changed"] > 0 and out["grown"] > 0  # structural plasticity
    stats = mb.stats()["synapses"]
    assert stats["cambiadas"] > 0 and stats["nuevas"] == stats["nuevas_total"] > 0


def test_punishment_lowers_and_sleep_consolidates_into_the_slow_memory():
    mb = MushroomBody(flywire.synthetic())
    mb.learn("borra mis archivos", "borrar", 1.0)
    high = mb.scores("borra mis archivos", ["borrar"])["borrar"]
    mb.learn("borra mis archivos", "borrar", -1.0)
    assert mb.scores("borra mis archivos", ["borrar"])["borrar"] < high

    mb2 = MushroomBody(flywire.synthetic())
    for t, a in [("haz un video", "video"), ("cuánto gané", "dinero")] * 3:
        mb2.learn(t, a, 1.0)
    slow0 = float(np.abs(mb2.slow).sum())
    report = mb2.consolidate(epochs=2)
    assert float(np.abs(mb2.slow).sum()) > slow0
    assert report["accuracy_after"] >= report["accuracy_before"]
    assert mb2.stats()["sleeps"] == 1


def test_forgetting_and_reset():
    mb = MushroomBody(flywire.synthetic())
    now = time.time()
    mb.learn("pon música", "musica", 1.0, now=now)
    mb.meta["decayed"] = now
    fast = float(np.abs(mb.fast).sum())
    mb.decay(now + 8 * 3600)
    assert float(np.abs(mb.fast).sum()) < fast * 0.5
    mb.reset()
    assert not mb.fast.any() and not mb.grown.any() and mb.replay == []


def test_a_brain_survives_a_restart_and_two_brains_diverge(tmp_path):
    w = flywire.synthetic()
    a = MushroomBody(w, tmp_path, "a")
    a.learn("haz un logo", "diseno", 1.0)
    a.save()
    again = MushroomBody(w, tmp_path, "a")
    assert np.allclose(again.fast, a.fast) and again.replay
    b = MushroomBody(w, None, "b")
    assert a.divergence(b) == 1.0
    b.learn("cuánto cuesta", "numeros", 1.0)
    assert 0 < a.divergence(b) <= 1.0
    assert a.divergence(again) == 0.0


def test_receptors_learn_the_background_and_share_meaning(tmp_path):
    r = Receptors(tmp_path, 150, embedder=Meaning())
    for t in ("un video corto", "video de viaje", "mi dinero", "salud diaria"):
        r.activity(t)
    a = r.activity("haz un video", adapt=False)
    b = r.activity("quiero un video bonito", adapt=False)
    c = r.activity("cuánto dinero tengo", adapt=False)
    assert a is not None and a.shape == (150,) and a.max() > 0

    def cos(x, y):
        return float(x @ y / (np.linalg.norm(x) * np.linalg.norm(y)))

    assert cos(a, b) > cos(a, c) + 0.2  # similar meaning, shared receptors
    r.save()
    assert json.loads((tmp_path / "receptores.json").read_text())["space"] == "prueba-8"


def test_receptors_rest_after_a_failed_call_and_warm_in_batches(tmp_path):
    calls = []

    class Flaky:
        space = "x"
        cache = tmp_path / "cache.db"

        def __call__(self, texts):
            calls.append(len(texts))
            raise RuntimeError("429")

    r = Receptors(tmp_path, 150, embedder=Flaky())
    assert r.activity("hola mundo") is None
    assert r.activity("otra cosa") is None and calls == [1]  # cooling down
    r._cool_until = 0
    assert r.warm([f"frase {i}" for i in range(200)]) == 200 and calls[-1] == 90


def test_core_brains_have_their_own_sparsity_and_are_born_once(tmp_path):
    core = Core(tmp_path)
    assert core.brain("sergio").k_active == 100
    assert core.brain("especialista:cine").k_active == 40
    born = []

    def train(mb):
        born.append(1)
        mb.learn("hola", "x", 1.0)
        return {"ok": True}

    core.born("node:prueba", "temperament", ["hola"], train)
    core.born("node:prueba", "temperament", ["hola"], train)
    assert born == [1]
    core.receptors._embedder = Meaning()  # the senses changed: born again
    mb = core.born("node:prueba", "temperament", ["hola"], train)
    assert born == [1, 1] and mb.meta["temperament"]["space"] == "prueba-8"


def test_the_core_sleeps_every_brain_and_remembers_the_night(tmp_path):
    core = Core(tmp_path)
    core.brain("sergio").learn("abre la calculadora", "tool:calc", 1.0)
    core.brain("node:hous").learn("haz un póster", "mov:boceto", 1.0)
    report = core.sleep()
    assert set(report) == {"sergio", "node:hous"}
    assert core.last_sleep() > 0
    again = Core(tmp_path)
    assert "node:hous" in again.info()["brains"]


def test_the_hive_runs_organs_in_parallel_without_an_orchestrator():
    hive = Colmena()
    started = []

    def slow(name, give):
        def fn(board):
            started.append((name, time.perf_counter()))
            time.sleep(0.2)
            return give

        return fn

    hive.add(
        Organ("ojos", "lóbulo óptico", "ver", ("pedido",), "visto", slow("ojos", 1))
    )
    hive.add(
        Organ(
            "memoria",
            "cuerpo fungiforme",
            "recordar",
            ("pedido",),
            "recuerdo",
            slow("memoria", 2),
        )
    )
    hive.add(Organ("boca", "SEZ", "responder", ("visto", "recuerdo"), "respuesta",
                   lambda b: b["visto"] + b["recuerdo"]))  # fmt: skip
    t = time.perf_counter()
    board = hive.run({"pedido": "hola"})
    assert board["respuesta"] == 3
    assert time.perf_counter() - t < 0.39  # the first two ran at the same time
    assert hive.status()["organos"][2]["veces"] == 1


def test_a_failing_organ_does_not_stop_the_others():
    hive = Colmena()

    def boom(board):
        raise RuntimeError("roto")

    hive.add(Organ("roto", "", "", ("pedido",), "x", boom))
    hive.add(Organ("bien", "", "", ("pedido",), "y", lambda b: "ok"))
    board = hive.run({"pedido": "hola"})
    assert board["y"] == "ok" and "x" not in board
    assert hive.organs["roto"].fails == 1


def test_the_supervisor_judges_answers_and_the_owners_next_words():
    sup = Supervisor()
    assert sup.judge("hola", "", [])["respuesta"] == -1.0
    assert sup.judge("abre", "Listo", [("open_app", False)])["herramientas"] < 0
    assert sup.judge("abre", "Listo, señor.", [("open_app", True)]) == {
        "respuesta": 0.4
    }
    assert sup.feedback("no, eso no es lo que pedí") == -1.0
    assert sup.feedback("perfecto, gracias") == 1.0
    assert sup.feedback("y mañana qué hago") == 0.0
    assert sup.flagged


def test_the_proof_route_measures_learning_and_sleep_works(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.connectome import core as core_mod
    from openjarvis.connectome import proof
    from openjarvis.server.connectome_routes import router

    core = Core(tmp_path)
    monkeypatch.setattr(core_mod, "get_core", lambda home=None: core)
    proof.clear_cache()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    p = client.get("/v1/connectome/proof").json()
    rounds = p["live"]["rondas"]
    assert rounds[0]["acierto"] == 0 and rounds[-1]["acierto"] > p["live"]["azar"]
    assert rounds[-1]["cambiadas"] > 0
    assert set(p["specialists"]) == {"cine", "creadores"}
    assert set(p["nodes"]["instintos"]) == {"rihno", "manchas", "hous", "tennessee"}
    assert not p["wiring"]["real"] and p["wiring"]["neuronas"]["kenyon"] == 2000
    human = p["mosca"]["rondas"]  # the fly brain at the base (decision.py)
    assert human[-1]["acierto"] > human[0]["acierto"]
    assert len(p["mosca_viva"]["regiones"]) == 10
    assert client.post("/v1/connectome/sleep").json()["ok"]
