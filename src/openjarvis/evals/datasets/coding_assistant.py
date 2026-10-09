"""coding_assistant dataset — 30 buggy code projects for agent-based debugging.

Each task presents a bug report, buggy source code, and a test suite.
The agent must identify and fix the bug(s) so that all tests pass.

Difficulty tiers:
- easy (10): single-line bugs — off-by-one, wrong operator, missing return
- medium (10): multi-line logic bugs — incorrect algorithm, bad state management
- hard (10): subtle bugs — race conditions, edge cases, incorrect rounding
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from openjarvis.evals.core.dataset import DatasetProvider
from openjarvis.evals.core.types import EvalRecord

_PROMPT_TEMPLATE = """You are a coding assistant. A user has reported a bug in their code.

## Bug Report
{bug_report}

## Source Code
```python
{buggy_code}
```

## Test Suite
```python
{test_code}
```

Fix the bug(s) in the source code so that ALL tests pass. Return the complete fixed source code inside a ```python code block."""  # noqa: E501

# The 30 tasks (bug report, buggy code, tests, expected fix) live in
# data/coding_assistant_tasks.json, grouped by difficulty tier.
_TASKS_FILE = Path(__file__).parent / "data" / "coding_assistant_tasks.json"
_TIERS: Dict[str, List[Dict[str, Any]]] = json.loads(_TASKS_FILE.read_text("utf-8"))
_EASY_TASKS: List[Dict[str, Any]] = _TIERS["easy"]
_MEDIUM_TASKS: List[Dict[str, Any]] = _TIERS["medium"]
_HARD_TASKS: List[Dict[str, Any]] = _TIERS["hard"]


def _build_all_tasks() -> List[Dict[str, Any]]:
    """Combine all difficulty tiers with assigned difficulty labels."""
    tasks = []
    for task in _EASY_TASKS:
        tasks.append({**task, "difficulty": "easy"})
    for task in _MEDIUM_TASKS:
        tasks.append({**task, "difficulty": "medium"})
    for task in _HARD_TASKS:
        tasks.append({**task, "difficulty": "hard"})
    return tasks


_ALL_TASKS = _build_all_tasks()


class CodingAssistantDataset(DatasetProvider):
    """30 buggy code projects for agent-based debugging evaluation."""

    dataset_id = "coding_assistant"
    dataset_name = "Coding Assistant"

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
            prompt = _PROMPT_TEMPLATE.format(
                bug_report=task["bug_report"],
                buggy_code=task["buggy_code"],
                test_code=task["test_code"],
            )
            self._records.append(
                EvalRecord(
                    record_id=f"coding-assistant-{i}",
                    problem=prompt,
                    reference=task.get("fixed_code", ""),
                    category="agentic",
                    subject=task["difficulty"],
                    metadata={
                        "bug_report": task["bug_report"],
                        "buggy_code": task["buggy_code"],
                        "test_code": task["test_code"],
                        "bugs": task["bugs"],
                        "originally_failing_tests": task["originally_failing_tests"],
                        "originally_passing_tests": task["originally_passing_tests"],
                    },
                )
            )

    def iter_records(self) -> Iterable[EvalRecord]:
        return iter(self._records)

    def size(self) -> int:
        return len(self._records)


__all__ = ["CodingAssistantDataset"]
