"""ECC (Everything Claude Code, github.com/affaan-m/ECC) as an on-demand library.

ECC ships ~290 skills and ~60 agent guides. Turning each one into a tool, or
pasting them into every prompt, would bury a local model in tokens. Instead
only the ``skills/`` and ``agents/`` folders are downloaded (sparse, shallow
clone, a few MB) and Sergio looks guides up through a single tool when one is
relevant: search by keywords, then read the best match.

ECC is MIT-licensed and is downloaded at install time, not vendored here.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import yaml

ECC_REPO = "https://github.com/affaan-m/ECC.git"
SPARSE_DIRS = ("skills", "agents")
MAX_READ_CHARS = 8000

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=False)


def ecc_dir() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "ecc"


class ECCError(RuntimeError):
    pass


def sync(root: Path | None = None, runner: Runner = _run) -> str:
    """Download ECC (first time) or update it to the latest commit."""
    root = root or ecc_dir()
    if (root / ".git").is_dir():
        steps = [
            ["git", "-C", str(root), "fetch", "--depth", "1", "origin"],
            ["git", "-C", str(root), "reset", "--hard", "FETCH_HEAD"],
        ]
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        steps = [
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                ECC_REPO,
                str(root),
            ],
            ["git", "-C", str(root), "sparse-checkout", "set", *SPARSE_DIRS],
        ]
    for cmd in steps:
        done = runner(cmd)
        if done.returncode != 0:
            raise ECCError((done.stderr or done.stdout or "git failed").strip()[-800:])
    head = runner(["git", "-C", str(root), "rev-parse", "--short", "HEAD"])
    return head.stdout.strip()


@dataclass(frozen=True)
class Guide:
    name: str
    kind: str  # "skill" or "agent"
    description: str
    path: Path  # SKILL.md or agents/<name>.md


_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _split(text: str) -> tuple[dict, str]:
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), text[match.end() :]


def _read_meta(path: Path, default_name: str) -> tuple[str, str]:
    try:
        with path.open(encoding="utf-8") as fh:
            head = fh.read(4096)
    except OSError:
        return default_name, ""
    meta, _ = _split(head)
    name = str(meta.get("name") or default_name).strip()
    description = " ".join(str(meta.get("description") or "").split())
    return name, description


class Library:
    """Index of the downloaded ECC guides (rebuilt when the folder changes)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ecc_dir()
        self._guides: list[Guide] | None = None
        self._stamp = 0.0

    @property
    def installed(self) -> bool:
        return (self.root / "skills").is_dir()

    def guides(self) -> list[Guide]:
        if not self.installed:
            return []
        stamp = max(
            (self.root / d).stat().st_mtime
            for d in SPARSE_DIRS
            if (self.root / d).exists()
        )
        if self._guides is None or stamp != self._stamp:
            found: list[Guide] = []
            for skill_md in sorted((self.root / "skills").glob("*/SKILL.md")):
                name, desc = _read_meta(skill_md, skill_md.parent.name)
                found.append(Guide(name, "skill", desc, skill_md))
            for agent_md in sorted((self.root / "agents").glob("*.md")):
                name, desc = _read_meta(agent_md, agent_md.stem)
                found.append(Guide(name, "agent", desc, agent_md))
            self._guides, self._stamp = found, stamp
        return self._guides

    def search(self, query: str, limit: int = 6) -> list[Guide]:
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
        if not words:
            return []
        scored = []
        for guide in self.guides():
            name = guide.name.lower()
            text = guide.description.lower()
            score = sum(3 * (w in name) + (w in text) for w in words)
            if score:
                scored.append((score, guide.kind == "skill", guide.name, guide))
        scored.sort(key=lambda item: (-item[0], not item[1], item[2]))
        return [item[3] for item in scored[:limit]]

    def find(self, name: str) -> Guide | None:
        wanted = name.strip().lower()
        for guide in self.guides():
            if wanted in (
                guide.name.lower(),
                guide.path.parent.name.lower(),
                guide.path.stem.lower(),
            ):
                return guide
        return None

    def read(self, name: str, file: str = "") -> str:
        guide = self.find(name)
        if guide is None:
            raise ECCError(f"No ECC guide called {name!r}. Search first.")
        if file:
            if guide.kind != "skill":
                raise ECCError("Only skills have extra files.")
            base = guide.path.parent.resolve()
            target = (base / file).resolve()
            if base not in target.parents or not target.is_file():
                raise ECCError(f"{file!r} is not a file of the skill {guide.name}.")
            body = target.read_text(encoding="utf-8", errors="replace")
        else:
            _, body = _split(guide.path.read_text(encoding="utf-8", errors="replace"))
        body = body.strip()
        if len(body) > MAX_READ_CHARS:
            body = body[:MAX_READ_CHARS] + "\n\n[... cut: the guide is longer ...]"
        return body

    def extra_files(self, guide: Guide) -> list[str]:
        if guide.kind != "skill":
            return []
        base = guide.path.parent
        return sorted(
            str(p.relative_to(base))
            for p in base.rglob("*")
            if p.is_file() and p.name != "SKILL.md" and p.suffix in (".md", ".txt")
        )[:20]


__all__ = ["ECCError", "ECC_REPO", "Guide", "Library", "ecc_dir", "sync"]
