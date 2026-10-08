"""Long-Context Mastery: answer questions about texts far bigger than the model's window.

1. Split at natural boundaries (headings, blank lines, code blocks) into
   chunks of a token budget, with a little overlap, keeping line numbers.
2. Rank chunks for the question with BM25 (local, free) and read only the
   relevant ones; with ``exhaustive=True`` read them all.
3. Map: from each read chunk the model extracts only facts relevant to the
   question, quoting and citing ``[c3 L120-L180]``.
4. Reduce: notes are merged hierarchically until they fit one prompt, then
   the final answer is written from the notes with citations kept.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm

CHARS_PER_TOKEN = 4

MAP_PROMPT = """QUESTION: {question}

From this excerpt ({cite}), copy or summarise ONLY what helps answer the
question, citing {cite}. If nothing helps, reply exactly: NOTHING.

EXCERPT:
{text}"""

REDUCE_PROMPT = """QUESTION: {question}

Merge these notes into fewer, non-repeating notes. Keep every citation in
square brackets and every number exactly.

NOTES:
{notes}"""

ANSWER_PROMPT = """QUESTION: {question}

Answer using only these notes taken from a long document. Cite the
[c.. L..] references you rely on. If the notes do not contain the answer,
say so plainly.

NOTES:
{notes}"""

_TOKEN = re.compile(r"[a-záéíóúñü0-9_]+", re.I)


def tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class Chunk:
    index: int
    text: str
    start_line: int
    end_line: int

    @property
    def cite(self) -> str:
        return f"[c{self.index} L{self.start_line}-L{self.end_line}]"


def chunk_text(text: str, max_tokens: int = 1500, overlap_lines: int = 2) -> list[Chunk]:
    """Chunks at blank lines / headings / fences, each under *max_tokens*."""
    lines = text.splitlines()
    budget = max_tokens * CHARS_PER_TOKEN
    chunks: list[Chunk] = []
    start = 0
    size = 0
    last_break = None
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            in_fence = not in_fence
        size += len(line) + 1
        if not in_fence and (not line.strip() or re.match(r"#{1,6} |def |class |function ", line)):
            last_break = i
        if size >= budget and i > start:
            cut = last_break if last_break is not None and last_break > start else i
            chunks.append(Chunk(len(chunks), "\n".join(lines[start:cut + 1]), start + 1, cut + 1))
            start = max(cut + 1 - overlap_lines, start + 1)
            size = sum(len(x) + 1 for x in lines[start:i + 1])
            last_break = None
        i += 1
    if start < len(lines):
        chunks.append(Chunk(len(chunks), "\n".join(lines[start:]), start + 1, len(lines)))
    return [c for c in chunks if c.text.strip()]


def bm25_rank(question: str, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75) -> list[tuple[float, Chunk]]:
    """Chunks by BM25 relevance to *question*, best first."""
    docs = [Counter(t.lower() for t in _TOKEN.findall(c.text)) for c in chunks]
    if not docs:
        return []
    avg = sum(sum(d.values()) for d in docs) / len(docs) or 1
    query = [t.lower() for t in _TOKEN.findall(question) if len(t) > 2]
    n = len(docs)
    scored = []
    for chunk, doc in zip(chunks, docs):
        length = sum(doc.values())
        score = 0.0
        for term in query:
            df = sum(1 for d in docs if term in d)
            if not df or term not in doc:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            tf = doc[term]
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / avg))
        scored.append((round(score, 4), chunk))
    return sorted(scored, key=lambda sc: (-sc[0], sc[1].index))


@dataclass
class LongAnswer:
    answer: str
    read: list[int]
    notes: list[str] = field(default_factory=list)
    chunks: int = 0
    calls: int = 0


def answer_long(
    question: str,
    text: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    chunk_tokens: int = 1500,
    window_tokens: int = 6000,
    max_chunks: int = 12,
    exhaustive: bool = False,
) -> LongAnswer:
    """Answer *question* about *text* of any length."""
    model = as_llm(llm)
    calls0 = model.calls
    chunks = chunk_text(text, chunk_tokens)
    if tokens(text) <= window_tokens:  # fits: no need to map/reduce
        answer = model(ANSWER_PROMPT.format(question=question, notes=f"[c0 L1-L{len(text.splitlines())}]\n{text}"))
        return LongAnswer(answer.strip(), [0], [], len(chunks), model.calls - calls0)
    if exhaustive:
        chosen = chunks
    else:
        ranked = bm25_rank(question, chunks)
        chosen = [c for s, c in ranked if s > 0][:max_chunks] or [c for _, c in ranked[:max_chunks]]
        chosen.sort(key=lambda c: c.index)
    notes: list[str] = []
    for chunk in chosen:
        note = model(MAP_PROMPT.format(question=question, cite=chunk.cite, text=chunk.text), temperature=0.1).strip()
        if note and note.upper() != "NOTHING" and not note.upper().startswith("NOTHING"):
            notes.append(note if "[c" in note else f"{chunk.cite} {note}")
    while notes and tokens("\n\n".join(notes)) > window_tokens and len(notes) > 1:
        merged: list[str] = []
        group: list[str] = []
        for note in notes:
            if group and tokens("\n\n".join(group + [note])) > window_tokens // 2:
                merged.append(model(REDUCE_PROMPT.format(question=question, notes="\n\n".join(group)),
                                    temperature=0.1).strip())
                group = []
            group.append(note)
        if group:
            merged.append(group[0] if len(group) == 1 else
                          model(REDUCE_PROMPT.format(question=question, notes="\n\n".join(group)),
                                temperature=0.1).strip())
        if len(merged) >= len(notes):
            break  # cannot shrink further
        notes = merged
    answer = model(ANSWER_PROMPT.format(question=question, notes="\n\n".join(notes) or "(no relevant notes)"),
                   temperature=0.2).strip()
    return LongAnswer(answer, [c.index for c in chosen], notes, len(chunks), model.calls - calls0)


def answer_file(question: str, path: str, llm: Optional[LLM] = None, **kw) -> LongAnswer:
    from pathlib import Path

    return answer_long(question, Path(path).read_text("utf-8", errors="replace"), llm, **kw)


__all__ = ["Chunk", "LongAnswer", "answer_file", "answer_long", "bm25_rank", "chunk_text", "tokens"]
