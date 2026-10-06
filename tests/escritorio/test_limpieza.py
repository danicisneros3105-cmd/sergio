"""Keep only the latest: cache, superseded Pythons, Blender leftovers."""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

from sergio_escritorio import limpieza

UV_DIR = "/home/u/.local/share/uv/python"


def item(key, version, path):
    return {"key": key, "version": version, "path": path, "implementation": "cpython"}


def test_only_superseded_uv_pythons_go():
    installed = [
        item("cpython-3.12.3-linux", "3.12.3", f"{UV_DIR}/cpython-3.12.3-linux/bin/python3"),
        item("cpython-3.12.9-linux", "3.12.9", f"{UV_DIR}/cpython-3.12.9-linux/bin/python3"),
        item("cpython-3.12.1-linux", "3.12.1", f"{UV_DIR}/cpython-3.12.1-linux/bin/python3"),
        item("cpython-3.11.2-linux", "3.11.2", f"{UV_DIR}/cpython-3.11.2-linux/bin/python3"),
        item("cpython-3.10.1-linux", "3.10.1", "/usr/bin/python3.10"),  # the system's
    ]
    in_use = [f"{UV_DIR}/cpython-3.12.1-linux/bin/python3"]  # Sergio still runs on this one
    assert limpieza.stale_pythons(installed, UV_DIR, in_use) == ["cpython-3.12.3-linux"]


def test_clean_python_prunes_and_uninstalls():
    calls = []

    def run(cmd, **_k):
        calls.append(cmd[1:])
        if cmd[1:3] == ["python", "list"]:
            out = (
                '[{"key": "cpython-3.12.3-x", "version": "3.12.3", "path": "%s/a/bin/py", "implementation": "cpython"},'
                ' {"key": "cpython-3.12.9-x", "version": "3.12.9", "path": "%s/b/bin/py", "implementation": "cpython"}]'
            ) % (UV_DIR, UV_DIR)
            return SimpleNamespace(stdout=out, returncode=0)
        if cmd[1:3] == ["python", "dir"]:
            return SimpleNamespace(stdout=UV_DIR + "\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    assert limpieza.clean_python("uv", [f"{UV_DIR}/b/bin/py"], run) == ["cpython-3.12.3-x"]
    assert ["cache", "prune"] in calls and ["python", "uninstall", "cpython-3.12.3-x"] in calls


def test_blender_leftovers_go_and_the_latest_stays(tmp_path):
    docs, scripts = tmp_path / "Blender", tmp_path / "scripts"
    docs.mkdir(), scripts.mkdir()
    keep = ["pro-1.blend", "pro-1-vista.png", "pro-1-planos.png"]
    junk = ["pro-1.blend1", "pro-1.blend2", "pro-2-vista.png", "pro-1-vista-front.png"]
    for name in keep + junk:
        (docs / name).write_bytes(b"x")
    for i in range(8):
        f = scripts / f"pro-{i}.py"
        f.write_text("x")
        os.utime(f, (time.time() - 100 + i, time.time() - 100 + i))
    assert limpieza.clean_blender(docs, scripts, keep_scripts=5) == len(junk) + 3
    assert sorted(p.name for p in docs.iterdir()) == sorted(keep)
    assert sorted(p.name for p in scripts.iterdir()) == [f"pro-{i}.py" for i in range(3, 8)]


def test_a_failed_attempt_leaves_nothing(tmp_path):
    blend = tmp_path / "pro-9.blend"
    for name in ("pro-9.blend", "pro-9.blend1", "pro-9-vista.png", "pro-9-planos.png"):
        (tmp_path / name).write_bytes(b"x")
    limpieza.forget_attempt(str(blend))
    assert not list(tmp_path.iterdir())


def test_blender_pro_keeps_the_best_build():
    from sergio_escritorio.media import blender_score, worse_build

    good = "SERGIO_SAVED x 6\nSERGIO_PARTS 6 meshes: a, b, c, d, e, f"
    broken = "SERGIO_STEP_ERROR in mats(): AttributeError\nSERGIO_SAVED x 1\nSERGIO_PARTS 1 meshes: a"
    assert worse_build(blender_score(broken), blender_score(good))  # 1 part + an error: discarded
    better = "SERGIO_SAVED x 9\nSERGIO_PARTS 9 meshes: a"
    assert not worse_build(blender_score(better), blender_score(good))
    assert worse_build(blender_score("Traceback… no save"), blender_score(good))
