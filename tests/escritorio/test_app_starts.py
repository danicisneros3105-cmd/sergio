"""The whole companion app starts (Windows-only pieces faked) and answers.

This catches a crash at start-up: every widget, tile, signal and the
control server come up, and /diag reports the new abilities.
"""

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("PIL")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_app_starts_and_reports(tmp_path):
    script = Path(__file__).with_name("start_app_fakes.py")
    done = subprocess.run(
        [sys.executable, str(script), str(tmp_path), str(_free_port())],
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = done.stdout
    assert "STARTED-AND-QUIT" in out, done.stderr[-3000:]
    line = next(l for l in out.splitlines() if l.startswith("DIAG"))
    assert line.startswith("DIAG "), line
    diag = json.loads(line[5:])
    assert diag["ok"] is True
    for key in ("vision", "holograms", "call", "gym", "hands", "reminders"):
        assert key in diag, key
    assert diag["gym"].startswith("cada 12 min")
    assert diag["wake"] in ("instantáneo (Vosk)", "Whisper por frase")
    assert isinstance(diag["voice_timeline"], list)
