"""Update refusal and rollback references, using local Git and fake installers."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "scripts").mkdir()
    source = Path(__file__).resolve().parents[2] / "scripts/actualizar-sergio.sh"
    shutil.copyfile(source, root / "scripts/actualizar-sergio.sh")
    (root / "frontend").mkdir()
    (root / "frontend/package.json").write_text("{}")
    git = shutil.which("git")

    def run(*args):
        return subprocess.run(
            [git, *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    run("init", "-b", "main")
    run("config", "user.name", "Update test")
    run("config", "user.email", "test@example.invalid")
    run("add", ".")
    run("commit", "-m", "initial")
    base = run("rev-parse", "HEAD")
    run("remote", "add", "origin", "https://github.com/danicisneros3105-cmd/sergio.git")
    remote = tmp_path / "remote.git"
    subprocess.run(
        [git, "clone", "--bare", str(root), str(remote)],
        check=True,
        capture_output=True,
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    scripts = {
        "git": (
            "#!/usr/bin/env bash\n"
            'if [[ "$1" == "fetch" ]]; then\n'
            '  exec "$REAL_GIT" fetch --no-tags "$TEST_REMOTE" main\n'
            'fi\nexec "$REAL_GIT" "$@"\n'
        ),
        "uv": '#!/usr/bin/env bash\nprintf "uv %s\\n" "$*" >> "$TEST_EVENTS"\nexit 0\n',
        "npm": (
            "#!/usr/bin/env bash\n"
            'if [[ "$1" == "--version" ]]; then echo 11.19.0; exit; fi\n'
            'printf "npm %s\\n" "$*" >> "$TEST_EVENTS"\n'
            'if [[ "${TEST_FAIL_BUILD:-}" == 1 ]]; then exit 9; fi\n'
        ),
    }
    for name, content in scripts.items():
        path = bin_dir / name
        path.write_text(content)
        path.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        "REAL_GIT": git,
        "TEST_REMOTE": str(remote),
        "TEST_EVENTS": str(tmp_path / "events"),
    }
    return root, env, run, base


@pytest.mark.parametrize("change", ["tracked", "untracked"])
def test_update_preserves_local_changes_and_never_installs(checkout, change):
    root, env, run, base = checkout
    path = root / (
        "frontend/package.json" if change == "tracked" else "personal-notes.txt"
    )
    path.write_text("my work")
    result = subprocess.run(
        ["bash", "scripts/actualizar-sergio.sh"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "cambios locales" in result.stderr
    assert path.read_text() == "my work" and run("rev-parse", "HEAD") == base
    assert not Path(env["TEST_EVENTS"]).exists()


def test_update_build_failure_preserves_rollback_and_does_not_launch_desktop(checkout):
    root, env, run, base = checkout
    env["TEST_FAIL_BUILD"] = "1"
    result = subprocess.run(
        ["bash", "scripts/actualizar-sergio.sh"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    refs = run("for-each-ref", "--format=%(objectname)", "refs/sergio/updates/")
    assert base in refs
    events = Path(env["TEST_EVENTS"]).read_text()
    assert "--locked --inexact" in events
    assert "npm ci --no-audit" in events
    assert "escritorio instalar" not in events
