"""Download the prompt library sources whole (shallow, sparse git clones)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from openjarvis.prompt_library.index import build, library_dir
from openjarvis.prompt_library.sources import Source, all_sources

Runner = Callable[..., subprocess.CompletedProcess]


def _git(
    run: Runner, args: List[str], cwd: Optional[Path] = None, timeout: int = 900
) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo")
    done = run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "advice.detachedHead=false",
            *args,
        ],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(
            (done.stderr or done.stdout or "git falló").strip().splitlines()[-1][:300]
        )
    return (done.stdout or "").strip()


def _fetch(source: Source, root: Path, run: Runner) -> str:
    """Clone (first time) or refresh to the newest commit; returns the commit."""
    if not (root / ".git").is_dir():
        if root.exists():
            shutil.rmtree(root)
        root.parent.mkdir(parents=True, exist_ok=True)
        args = ["clone", "--depth", "1", "--no-tags", "--filter=blob:none"]
        if source.paths:
            args.append("--sparse")
        _git(run, [*args, source.repo, str(root)])
        if source.paths:
            _git(
                run,
                [
                    "sparse-checkout",
                    "set",
                    "--no-cone",
                    *(f"/{p}" for p in source.paths),
                ],
                cwd=root,
            )
    else:
        _git(
            run,
            [
                "fetch",
                "--depth",
                "1",
                "--no-tags",
                "--filter=blob:none",
                "origin",
                "HEAD",
            ],
            cwd=root,
        )
        _git(run, ["reset", "--hard", "-q", "FETCH_HEAD"], cwd=root)
    return _git(run, ["rev-parse", "HEAD"], cwd=root)


def sync(
    folder: Optional[Path] = None,
    sources: Optional[Sequence[Source]] = None,
    *,
    run: Runner = subprocess.run,
    on_step: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Fetch every source, then rebuild the index from what is on disk.

    A source that fails keeps its previous copy; the others still update."""
    folder = folder or library_dir()
    folder.mkdir(parents=True, exist_ok=True)
    sources = list(sources) if sources is not None else all_sources(folder)
    state: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        if on_step:
            on_step(f"Descargando {source.key} ({source.repo})…")
        try:
            commit = _fetch(source, folder / "repos" / source.key, run)
            state[source.key] = {"commit": commit, "at": int(time.time())}
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            state[source.key] = {"error": str(exc)[:300], "at": int(time.time())}
    (folder / "sync.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    if on_step:
        on_step("Indexando…")
    counts = build(folder, sources)
    return {"sources": state, "counts": counts}


__all__ = ["sync"]
