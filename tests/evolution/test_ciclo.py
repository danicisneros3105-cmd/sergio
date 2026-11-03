"""The nightly self-fix works only from real failures and through automejora."""

from __future__ import annotations

import json
import time

from openjarvis.evolution import automejora, ciclo


def _job(home, name, stage, error, status="error"):
    d = home / "video_jobs" / name
    d.mkdir(parents=True)
    (d / "state.json").write_text(
        json.dumps({"status": status, "stage": stage, "error": error})
    )


def test_evidence_counts_real_failures_of_the_week(tmp_path):
    _job(tmp_path, "a", "sonido", "ffmpeg: no audio stream")
    _job(tmp_path, "b", "sonido", "ffmpeg: no audio stream")
    _job(tmp_path, "c", "render", "libass missing")
    _job(tmp_path, "d", "render", "ok", status="listo")
    ev = ciclo.evidence(home=tmp_path)
    assert ev[0] == {"stage": "sonido", "error": "ffmpeg: no audio stream", "count": 2,
                     "path": ciclo.STAGE_FILES["sonido"]}  # fmt: skip
    assert len(ev) == 2
    assert ciclo.evidence(now=time.time() + 8 * 86400, home=tmp_path) == []


def test_a_night_proposes_one_change_and_only_automejora_applies_it(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("SERGIO_AUTOMEJORA_NOCHE", raising=False)
    monkeypatch.setattr(automejora, "home", lambda: tmp_path / "automejora")
    monkeypatch.setattr(automejora, "failed_before", lambda files: 0)
    _job(tmp_path, "a", "sonido", "division by zero")
    root = tmp_path / "repo"
    target = root / ciclo.STAGE_FILES["sonido"]
    target.parent.mkdir(parents=True)
    target.write_text("def level(x):\n    return 1 / x\n")
    asked, tried = [], []

    def ask(prompt, **kw):
        asked.append(prompt)
        return json.dumps(
            {
                "razon": "x puede ser 0",
                "cambios": [
                    {"old": "return 1 / x", "new": "return 1 / x if x else 0.0"}
                ],
            }
        )

    class M:
        state, id = "aplicada", "m1"

    def improve(reason, changes, root):
        tried.append((reason, changes))
        return M()

    out = ciclo.night(ask=ask, improve=improve, root=root, home=tmp_path)
    assert out["hecho"] and out["estado"] == "aplicada"
    assert "division by zero" in asked[0] and "return 1 / x" in asked[0]
    assert tried[0][1][0].path == ciclo.STAGE_FILES["sonido"] and tried[0][
        0
    ].startswith("noche: sonido")
    assert ciclo.nights()[-1]["mejora"] == "m1"


def test_nothing_is_touched_without_evidence_or_when_off(tmp_path, monkeypatch):
    monkeypatch.setattr(automejora, "home", lambda: tmp_path / "automejora")
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe llamarse"))  # noqa: E731
    assert ciclo.night(ask=boom, improve=boom, root=tmp_path, home=tmp_path)[
        "motivo"
    ].startswith("sin fallos")
    monkeypatch.setenv("SERGIO_AUTOMEJORA_NOCHE", "0")
    _job(tmp_path, "a", "sonido", "x")
    assert (
        ciclo.night(ask=boom, improve=boom, root=tmp_path, home=tmp_path)["hecho"]
        is False
    )
