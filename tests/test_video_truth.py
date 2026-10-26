"""The real state of the videos, told to the chat and the Nodes (no invented progress)."""

import json
import time

from openjarvis.nodes import worker
from openjarvis.video_essay import job as jobs


def _job(root, job_id, **state):
    folder = root / job_id
    folder.mkdir(parents=True)
    (folder / "state.json").write_text(json.dumps(state), "utf-8")


def test_no_jobs_says_nothing_is_running(tmp_path):
    text = jobs.truth(root=tmp_path)
    assert "<videos_reales>" in text
    assert "no hay nada en marcha" in text


def test_stalled_job_is_called_stopped(tmp_path):
    now = time.time()
    _job(
        tmp_path,
        "abc123",
        status="en curso",
        stage="script",
        created=now - 24 * 3600,
        updated=now - 20 * 3600,
        params={"prompt": "La caída de abril"},
    )
    text = jobs.truth(now=now, root=tmp_path)
    assert "[abc123]" in text
    assert "DETENIDO" in text
    assert "pedido hace 24 h" in text


def test_old_jobs_are_left_out(tmp_path):
    now = time.time()
    _job(tmp_path, "old", status="listo", created=now - 10 * 86400, updated=now)
    assert "no hay nada en marcha" in jobs.truth(now=now, root=tmp_path)


def test_truth_only_for_video_turns(monkeypatch):
    monkeypatch.setattr(jobs, "truth", lambda: "<videos_reales>X</videos_reales>")
    assert worker._with_truth("¿Y dónde está el video?", "P").endswith(
        "<videos_reales>X</videos_reales>"
    )
    assert worker._with_truth("Resume mi correo", "P") == "P"


def test_turn_prompt_forbids_invented_progress():
    assert "videos_reales" in worker.TURN_PROMPT
