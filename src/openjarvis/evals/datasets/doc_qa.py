"""doc_qa dataset — 30 document-grounded QA tasks.

Each task provides 3-6 real-world documentation excerpts and a question.
The agent must answer using only the provided documents and cite sources.

Difficulty tiers:
- easy (10): answer in a single document, straightforward extraction
- medium (10): answer requires synthesizing 2-3 documents
- hard (10): answer requires reasoning across documents with distractors
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from openjarvis.evals.core.dataset import DatasetProvider
from openjarvis.evals.core.types import EvalRecord

_PROMPT_TEMPLATE = """Answer the following question using ONLY the provided documents. Cite which document(s) support each claim (e.g., [Doc 1], [Doc 3]).

## Question
{question}

## Documents

{documents}

Provide a clear, well-structured answer with citations."""


# The 30 tasks live in data/doc_qa_tasks.json, grouped by difficulty tier.
_TASKS_FILE = Path(__file__).parent / "data" / "doc_qa_tasks.json"
_TIERS: Dict[str, List[Dict[str, Any]]] = json.loads(_TASKS_FILE.read_text("utf-8"))
_EASY_TASKS: List[Dict[str, Any]] = _TIERS["easy"]
_MEDIUM_TASKS: List[Dict[str, Any]] = _TIERS["medium"]
_HARD_TASKS: List[Dict[str, Any]] = _TIERS["hard"]


class DocQADataset(DatasetProvider):
    """30 document-grounded QA tasks."""

    def load(
        self,
        *,
        max_samples: Optional[int] = None,
        split: str = "test",
        seed: Optional[int] = None,
    ) -> None:
        all_tasks = _EASY_TASKS + _MEDIUM_TASKS + _HARD_TASKS
        difficulties = (
            ["easy"] * len(_EASY_TASKS)
            + ["medium"] * len(_MEDIUM_TASKS)
            + ["hard"] * len(_HARD_TASKS)
        )

        paired = list(zip(all_tasks, difficulties))
        if seed is not None:
            rng = random.Random(seed)
            rng.shuffle(paired)

        if max_samples is not None:
            paired = paired[:max_samples]

        self._records: List[EvalRecord] = []
        for idx, (task, diff) in enumerate(paired):
            doc_listing = "\n\n".join(
                f"### Document {i + 1}: {doc['title']}\n{doc['content']}"
                for i, doc in enumerate(task["documents"])
            )

            prompt = _PROMPT_TEMPLATE.format(
                question=task["question"],
                documents=doc_listing,
            )

            # Build reference from required facts
            ref_parts = [f["fact"] for f in task["required_facts"]]

            self._records.append(
                EvalRecord(
                    record_id=f"doc-qa-{idx:03d}",
                    problem=prompt,
                    reference="; ".join(ref_parts),
                    category="agentic",
                    subject=diff,
                    metadata={
                        "question": task["question"],
                        "documents": task["documents"],
                        "required_facts": task["required_facts"],
                    },
                )
            )

    def iter_records(self) -> Iterable[EvalRecord]:
        return iter(self._records)

    def size(self) -> int:
        return len(self._records)


__all__ = ["DocQADataset"]
