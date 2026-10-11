"""Regression tests for the session-wide test-home lifecycle."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["collect-only", "collection-error"])
def test_non_running_sessions_restore_environment_and_remove_test_home(
    mode: str,
) -> None:
    """Cleanup must run when fixtures never start or collection aborts."""
    repo_root = Path(__file__).resolve().parents[1]
    script = r"""
import os
import pathlib
import sys
import tempfile

import pytest

created = []
real_mkdtemp = tempfile.mkdtemp

def recording_mkdtemp(*args, **kwargs):
    path = real_mkdtemp(*args, **kwargs)
    if kwargs.get("prefix") == "openjarvis-test-home-":
        created.append(path)
    return path

tempfile.mkdtemp = recording_mkdtemp
os.environ["OPENJARVIS_HOME"] = "/tmp/openjarvis-original-home-sentinel"
os.environ["OPENJARVIS_CONFIG"] = "/tmp/openjarvis-original-config-sentinel"

# Never create an intentionally invalid module inside the real checkout:
# interruption can otherwise poison the next suite's collection.
with tempfile.TemporaryDirectory(prefix="openjarvis-lifecycle-") as temporary:
    root = pathlib.Path(temporary)
    (root / "conftest.py").write_bytes(pathlib.Path(sys.argv[2]).read_bytes())
    bad_test = root / "test_case.py"
    code = "def test_collected():\n    pass\n" if sys.argv[1] == "collect-only" else "def broken(:\n"
    bad_test.write_text(code, encoding="utf-8")
    os.chdir(root)
    result = pytest.main(["--collect-only", "-q", str(bad_test)])
    if sys.argv[1] == "collect-only":
        assert result == pytest.ExitCode.OK, result
    else:
        assert result != pytest.ExitCode.OK, result

assert os.environ["OPENJARVIS_HOME"] == "/tmp/openjarvis-original-home-sentinel"
assert os.environ["OPENJARVIS_CONFIG"] == "/tmp/openjarvis-original-config-sentinel"
assert len(created) == 1, created
assert not pathlib.Path(created[0]).exists(), created[0]
"""
    result = subprocess.run(
        [sys.executable, "-c", script, mode, str(repo_root / "tests" / "conftest.py")],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
