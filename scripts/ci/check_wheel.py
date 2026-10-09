"""Build the wheel and fail if any tracked package file is missing from it.

v1.0.1 shipped without ``openjarvis/traces/`` because an unanchored
``.gitignore`` pattern made hatchling drop the package (#372). This builds
the wheel the same way a release does and compares its contents with every
file Git tracks under ``src/openjarvis``. Then it installs the wheel into a
fresh virtual environment and imports the package and its CLI.

Usage: python scripts/ci/check_wheel.py [--no-install]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Deliberately left out of the wheel (see [tool.hatch.build.targets.wheel]).
EXCLUDED_PREFIXES = ("openjarvis/agents/claude_code_runner/",)
# Byte-compiled caches and editor leftovers are never expected in a wheel.
IGNORED_SUFFIXES = (".pyc", ".pyo")


def tracked_package_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files", "src/openjarvis"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\n")
    files = set()
    for line in out:
        if not line or line.endswith(IGNORED_SUFFIXES):
            continue
        rel = line.removeprefix("src/")
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        files.add(rel)
    return files


def build_wheel(out_dir: Path) -> Path:
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=ROOT,
        check=True,
    )
    wheels = sorted(out_dir.glob("*.whl"))
    if not wheels:
        raise SystemExit("uv build produced no wheel")
    return wheels[-1]


def missing_from(wheel: Path, expected: set[str]) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        present = set(zf.namelist())
    return sorted(expected - present)


def smoke_install(wheel: Path, work: Path) -> None:
    venv = work / "venv"
    subprocess.run(["uv", "venv", "--quiet", str(venv)], check=True)
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        # The server extra too, so the API modules import like in a real install.
        [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--python",
            str(python),
            f"{wheel}[server]",
        ],
        check=True,
    )
    check = (
        "import importlib, openjarvis\n"
        "for name in ('openjarvis.traces', 'openjarvis.cli', 'openjarvis.server.app',"
        " 'openjarvis.i18n', 'openjarvis.evals.datasets.doc_qa'):\n"
        "    importlib.import_module(name)\n"
        "from openjarvis.i18n import catalog\n"
        "assert catalog('en').translate('Salida JSON.') == 'JSON output.'\n"
        "print('wheel imports ok')\n"
    )
    subprocess.run([str(python), "-c", check], check=True, cwd=work)
    cli = venv / ("Scripts/jarvis.exe" if sys.platform == "win32" else "bin/jarvis")
    subprocess.run([str(cli), "--help"], check=True, cwd=work, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-install", action="store_true", help="only check contents")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        wheel = build_wheel(work / "dist")
        expected = tracked_package_files()
        missing = missing_from(wheel, expected)
        if missing:
            print(f"{len(missing)} tracked files are missing from {wheel.name}:")
            for name in missing[:50]:
                print(f"  {name}")
            return 1
        print(f"{wheel.name}: all {len(expected)} tracked package files present")
        if not args.no_install:
            smoke_install(wheel, work)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
