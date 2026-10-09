"""security_scanner dataset — 30 vulnerable code projects for security auditing.

Each task presents a small Python project with planted vulnerabilities.
The agent must identify vulnerabilities, classify severity, and recommend fixes.

Difficulty tiers:
- easy (10): single obvious vulnerability (hardcoded secret, SQL injection)
- medium (10): multiple vulnerabilities requiring deeper analysis
- hard (10): subtle vulnerabilities mixed with safe patterns (false positive traps)
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from openjarvis.evals.core.dataset import DatasetProvider
from openjarvis.evals.core.types import EvalRecord

_PROMPT_TEMPLATE = """You are a security auditor. Scan the following Python project for security vulnerabilities.

## Project Files

{file_listing}

Produce a structured security report with these sections:
- **Secrets Found**: any hardcoded credentials, API keys, or tokens.
- **Vulnerabilities**: code patterns that could be exploited (include file name and line).
- **Dependency Issues**: outdated or vulnerable packages.
- **Recommendations**: prioritized list of fixes.
- **Risk Level**: CRITICAL, HIGH, MEDIUM, or LOW overall assessment."""  # noqa: E501


# The 30 tasks live in data/security_scanner_tasks.json, grouped by difficulty tier.
_TASKS_FILE = Path(__file__).parent / "data" / "security_scanner_tasks.json"
_TIERS: Dict[str, List[Dict[str, Any]]] = json.loads(_TASKS_FILE.read_text("utf-8"))
_EASY_TASKS: List[Dict[str, Any]] = _TIERS["easy"]
_MEDIUM_TASKS: List[Dict[str, Any]] = _TIERS["medium"]
_HARD_TASKS: List[Dict[str, Any]] = _TIERS["hard"]


def _build_all_tasks() -> List[Dict[str, Any]]:
    tasks = []
    for task in _EASY_TASKS:
        tasks.append({**task, "difficulty": "easy"})
    for task in _MEDIUM_TASKS:
        tasks.append({**task, "difficulty": "medium"})
    for task in _HARD_TASKS:
        tasks.append({**task, "difficulty": "hard"})
    return tasks


_ALL_TASKS = _build_all_tasks()


class SecurityScannerDataset(DatasetProvider):
    """30 vulnerable code projects for security auditing evaluation."""

    dataset_id = "security_scanner"
    dataset_name = "Security Scanner"

    def __init__(self) -> None:
        self._records: List[EvalRecord] = []

    def load(
        self,
        *,
        max_samples: Optional[int] = None,
        split: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> None:
        tasks = list(_ALL_TASKS)
        if seed is not None:
            rng = random.Random(seed)
            rng.shuffle(tasks)
        if max_samples is not None:
            tasks = tasks[:max_samples]

        self._records = []
        for i, task in enumerate(tasks):
            file_listing = ""
            for fname, content in task["project_files"].items():
                file_listing += f"### {fname}\n```python\n{content}```\n\n"

            prompt = _PROMPT_TEMPLATE.format(file_listing=file_listing)

            self._records.append(
                EvalRecord(
                    record_id=f"security-scanner-{i}",
                    problem=prompt,
                    reference="",
                    category="agentic",
                    subject=task["difficulty"],
                    metadata={
                        "project_files": task["project_files"],
                        "vulnerabilities": task["vulnerabilities"],
                        "safe_patterns": task["safe_patterns"],
                    },
                )
            )

    def iter_records(self) -> Iterable[EvalRecord]:
        return iter(self._records)

    def size(self) -> int:
        return len(self._records)


__all__ = ["SecurityScannerDataset"]
