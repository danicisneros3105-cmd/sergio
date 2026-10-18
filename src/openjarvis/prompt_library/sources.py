"""Where the prompt library comes from.

The owner asked for "Awesome-System-Prompts" and "LLM-Persona-Prompts" in full.
No repository carries that second name, so the closest public collections are
used: two system-prompt collections, the largest role-prompt collection and a
persona collection. ``extra_sources.json`` in the library folder adds more:
``[{"key": "...", "repo": "https://github.com/owner/name", "paths": ["dir"],
"kind": "sistema"}]``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

KINDS = ("sistema", "rol", "personaje")


@dataclass(frozen=True)
class Source:
    key: str
    repo: str
    kind: str
    license: str
    # Sparse checkout: only these paths are downloaded (empty = whole repo).
    paths: Tuple[str, ...] = field(default_factory=tuple)
    about: str = ""


SOURCES: Tuple[Source, ...] = (
    Source(
        key="sistema-a",
        repo="https://github.com/EliFuzz/awesome-system-prompts",
        kind="sistema",
        license="GPL-3.0",
        paths=("leaks",),
        about="Prompts de sistema publicados de más de 80 asistentes y agentes.",
    ),
    Source(
        key="sistema-b",
        repo="https://github.com/langgptai/awesome-system-prompts",
        kind="sistema",
        license="Apache-2.0",
        paths=("Agents", "LLMs"),
        about="Prompts de sistema de agentes de código y modelos de chat.",
    ),
    Source(
        key="roles",
        repo="https://github.com/f/awesome-chatgpt-prompts",
        kind="rol",
        license="CC0-1.0",
        paths=("prompts.csv",),
        about="Más de 2 500 prompts de rol («actúa como…»).",
    ),
    Source(
        key="personajes",
        repo="https://github.com/UtopianFuturist/Personality-Prompts-For-LLMs",
        kind="personaje",
        license="sin licencia declarada (solo uso local)",
        about="Prompts de personalidad y ética para asistentes.",
    ),
)

_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
_REPO = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def extra_sources(folder: Path) -> List[Source]:
    """Owner-added sources; anything malformed is skipped, never fatal."""
    path = folder / "extra_sources.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found: List[Source] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key, repo = str(row.get("key", "")), str(row.get("repo", "")).rstrip("/")
        kind = str(row.get("kind", "sistema"))
        paths = tuple(
            str(p).strip("/") for p in row.get("paths") or [] if str(p).strip("/")
        )
        if not _KEY.match(key) or not _REPO.match(repo) or kind not in KINDS:
            continue
        if any(".." in p.split("/") for p in paths):
            continue
        found.append(
            Source(
                key=key,
                repo=repo,
                kind=kind,
                license=str(row.get("license", "")),
                paths=paths,
            )
        )
    return found


def all_sources(folder: Path) -> List[Source]:
    known = {s.key for s in SOURCES}
    return list(SOURCES) + [s for s in extra_sources(folder) if s.key not in known]


__all__ = ["KINDS", "SOURCES", "Source", "all_sources", "extra_sources"]
