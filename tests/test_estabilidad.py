"""Stability: checks in plain words, repairs that never touch a running
video, and a watchdog that restarts a stuck server."""

from __future__ import annotations

import json
import os
import time

from openjarvis import estabilidad as E


def test_checks_name_every_area_in_plain_words(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    items = E.checks(tmp_path)
    names = {c["nombre"] for c in items}
    assert {"Disco", "ffmpeg (video)", "Carpeta de Sergio", "Modelos de IA"} <= names
    ai = next(c for c in items if c["nombre"] == "Modelos de IA")
    assert ai["estado"] == "aviso" and "otra" in ai["arreglo"]
    assert E.summary(items)


def test_repair_frees_finished_jobs_only(tmp_path):
    jobs = tmp_path / "video_jobs"
    done, running = jobs / "a", jobs / "b"
    for folder, status in ((done, "listo"), (running, "en curso")):
        folder.mkdir(parents=True)
        (folder / "state.json").write_text(json.dumps({"status": status}))
        (folder / "voz.wav").write_bytes(b"0" * 10)
        old = time.time() - 9 * 86400
        os.utime(folder / "voz.wav", (old, old))
    out = E.repair(tmp_path)
    assert not (done / "voz.wav").exists()
    assert (running / "voz.wav").exists()
    assert out["quitado"]


def test_a_huge_log_is_trimmed_not_deleted(tmp_path):
    log = tmp_path / "servidor.log"
    log.write_bytes(b"x" * (51 * 2**20))
    E.repair(tmp_path)
    assert 0 < log.stat().st_size <= 5 * 2**20


def test_the_watchdog_exits_after_three_failures_in_a_row(monkeypatch):
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    answers = iter([True, False, True, False, False, False])
    exits = []
    t = E.start_watchdog(
        "http://x/health", every=0.01, get=lambda u: next(answers), exit=exits.append
    )
    t.join(2)
    assert exits == [1]
