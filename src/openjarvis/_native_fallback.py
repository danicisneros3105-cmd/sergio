"""Pure-Python twins of the ``openjarvis_rust`` classes Sergio needs to run.

The native extension is the fast path, but it has to be compiled (or
downloaded as a prebuilt wheel) and that sometimes fails on a user's PC.
Without it the capability policy, the secret/PII scanners, the rate limiter
and the SQLite/BM25 memories used to raise ``ImportError`` and take whole
features down with them. These classes expose the same constructor
signatures, methods and JSON return formats as the PyO3 bindings in
``rust/crates/openjarvis-python/src`` and follow the Rust logic line by line,
so callers do not need to know which one they got.

Differences that cannot matter to callers: ``start``/``end`` in scan
findings are character offsets (Rust reports byte offsets; they agree on
ASCII), and ``BM25Memory`` also offers ``delete``/``clear``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Capability policy (rust/crates/openjarvis-security/src/capabilities.rs)
# ---------------------------------------------------------------------------


def glob_match(pattern: str, text: str) -> bool:
    """The Rust policy's wildcard match: only ``*``, case-sensitive."""
    if pattern == "*" or pattern == text:
        return True
    parts = pattern.split("*")
    if len(parts) == 1:
        return pattern == text
    pos = 0
    for i, part in enumerate(parts):
        if not part:
            continue
        found = text.find(part, pos)
        if found < 0 or (i == 0 and found != 0):
            return False
        pos = found + len(part)
    last = parts[-1]
    return not (last and not text.endswith(last))


class CapabilityPolicy:
    def __init__(self, default_deny: bool = True) -> None:
        self._default_deny = default_deny
        self._policies: Dict[str, Dict[str, list]] = {}
        self._lock = threading.Lock()

    def _policy(self, agent_id: str) -> Dict[str, list]:
        return self._policies.setdefault(agent_id, {"grants": [], "deny": []})

    def grant(self, agent_id: str, capability: str, pattern: str) -> None:
        with self._lock:
            self._policy(agent_id)["grants"].append((capability, pattern))

    def deny(self, agent_id: str, capability: str) -> None:
        with self._lock:
            self._policy(agent_id)["deny"].append(capability)

    def check(self, agent_id: str, capability: str, resource: str) -> bool:
        policy = self._policies.get(agent_id)
        if policy is None:
            return not self._default_deny
        if any(glob_match(denied, capability) for denied in policy["deny"]):
            return False
        for cap, pattern in policy["grants"]:
            if glob_match(cap, capability):
                if resource and pattern != "*":
                    if glob_match(pattern, resource):
                        return True
                else:
                    return True
        return not self._default_deny

    def list_agents(self) -> List[str]:
        return list(self._policies)


# ---------------------------------------------------------------------------
# Secret and PII scanners (rust/crates/openjarvis-security/src/scanner.rs)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: Sequence[Tuple[str, str, str, str]] = (
    ("openai_key", r"sk-[A-Za-z0-9_-]{20,}", "critical", "OpenAI API key"),
    ("anthropic_key", r"sk-ant-[A-Za-z0-9_-]{20,}", "critical", "Anthropic API key"),
    ("aws_access_key", r"AKIA[0-9A-Z]{16}", "critical", "AWS access key"),
    (
        "github_token",
        r"(?:ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}",
        "critical",
        "GitHub token",
    ),
    (
        "password_assignment",
        r"""(?:password|passwd|pwd)\s*[=:]\s*['"]([^'"]{4,})['"]""",
        "high",
        "Password assignment",
    ),
    (
        "db_connection_string",
        r"(?:postgres|mysql|mongodb|redis)://[^\s]{10,}",
        "high",
        "Database connection string",
    ),
    ("private_key", r"-----BEGIN (?:RSA )?PRIVATE KEY-----", "critical", "Private key"),
    ("slack_token", r"xox[bpors]-[A-Za-z0-9\-]{10,}", "high", "Slack token"),
    (
        "stripe_key",
        r"(?:sk|pk)_(?:test|live)_[A-Za-z0-9]{20,}",
        "critical",
        "Stripe key",
    ),
    (
        "generic_api_key",
        r"""(?:api_key|secret_key|auth_token)\s*[=:]\s*['"]([^'"]{8,})['"]""",
        "high",
        "Generic API key/secret",
    ),
)

_PII_PATTERNS: Sequence[Tuple[str, str, str, str]] = (
    (
        "email",
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "medium",
        "Email address",
    ),
    ("us_ssn", r"\b\d{3}-\d{2}-\d{4}\b", "critical", "US Social Security Number"),
    (
        "credit_card_visa",
        r"\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        "critical",
        "Visa credit card",
    ),
    (
        "credit_card_mastercard",
        r"\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        "critical",
        "Mastercard credit card",
    ),
    (
        "credit_card_amex",
        r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b",
        "critical",
        "Amex credit card",
    ),
    (
        "us_phone",
        r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "medium",
        "US phone number",
    ),
    ("ipv4_address", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "low", "IPv4 address"),
)


class _PatternScanner:
    _PATTERNS: Sequence[Tuple[str, str, str, str]] = ()

    def __init__(self) -> None:
        self._compiled = [
            (name, re.compile(rx), level, desc)
            for name, rx, level, desc in self._PATTERNS
        ]

    def scan(self, text: str) -> str:
        findings = [
            {
                "pattern_name": name,
                "matched_text": m.group(0),
                "threat_level": level,
                "start": m.start(),
                "end": m.end(),
                "description": desc,
            }
            for name, rx, level, desc in self._compiled
            for m in rx.finditer(text)
        ]
        return json.dumps({"findings": findings})

    def redact(self, text: str) -> str:
        for name, rx, _level, _desc in self._compiled:
            text = rx.sub(lambda _m, n=name: f"[REDACTED:{n}]", text)
        return text


class SecretScanner(_PatternScanner):
    _PATTERNS = _SECRET_PATTERNS


class PIIScanner(_PatternScanner):
    _PATTERNS = _PII_PATTERNS


# ---------------------------------------------------------------------------
# Rate limiter (rust/crates/openjarvis-security/src/rate_limiter.rs)
# ---------------------------------------------------------------------------


class RateLimiter:
    def __init__(self, requests_per_minute: int = 60, burst_size: int = 10) -> None:
        self._rate = requests_per_minute / 60.0
        self._capacity = float(burst_size)
        self._buckets: Dict[str, List[float]] = {}  # key -> [tokens, last_refill]
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, float]:
        with self._lock:
            now = time.monotonic()
            bucket = self._buckets.setdefault(key, [self._capacity, now])
            bucket[0] = min(bucket[0] + (now - bucket[1]) * self._rate, self._capacity)
            bucket[1] = now
            if bucket[0] >= 1.0:
                bucket[0] -= 1.0
                return True, 0.0
            wait = (1.0 - bucket[0]) / self._rate if self._rate > 0 else math.inf
            return False, wait

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is not None:
                self._buckets.pop(key, None)
            else:
                self._buckets.clear()


# ---------------------------------------------------------------------------
# Loop guard (rust/crates/openjarvis-agents/src/loop_guard.rs)
# ---------------------------------------------------------------------------


class LoopGuard:
    def __init__(
        self, max_identical: int = 50, max_ping_pong: int = 4, poll_budget: int = 100
    ) -> None:
        self._max_identical = (
            max_identical  # kept for parity; Rust blocks the first repeat
        )
        self._max_ping_pong = max_ping_pong
        self._poll_budget = poll_budget
        self.reset()

    def check(self, tool_name: str, arguments: str) -> Optional[str]:
        digest = hashlib.sha256(f"{tool_name}|{arguments}".encode()).hexdigest()
        if digest in self._seen:
            return f"Loop detected: identical call to '{tool_name}' with same arguments"
        self._seen.add(digest)
        self._recent.append(tool_name)
        if len(self._recent) > self._max_ping_pong * 2:
            self._recent.pop(0)
        calls = self._recent
        if (
            len(calls) >= 4
            and calls[-1] == calls[-3]
            and calls[-2] == calls[-4]
            and calls[-1] != calls[-2]
        ):
            return f"Ping-pong loop detected between '{calls[-1]}' and '{calls[-2]}'"
        self._poll_count += 1
        if self._poll_count > self._poll_budget:
            return f"Poll budget exceeded: {self._poll_count} calls made (budget: {self._poll_budget})"
        return None

    def reset(self) -> None:
        self._seen: set = set()
        self._recent: List[str] = []
        self._poll_count = 0


# ---------------------------------------------------------------------------
# Memories (rust/crates/openjarvis-tools/src/storage/{sqlite,bm25}.rs)
# ---------------------------------------------------------------------------


def _meta_json(metadata: Optional[str]) -> str:
    if metadata is None:
        return "{}"
    return json.dumps(json.loads(metadata))  # validates like serde_json::from_str


class SQLiteMemory:
    """SQLite + FTS5 store with the same schema as the Rust backend.

    A database written by one implementation is readable by the other.
    """

    def __init__(self, path: str = ":memory:") -> None:
        if path.startswith("~"):
            path = str(Path(path).expanduser())
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            try:
                self._conn.execute("PRAGMA journal_mode=WAL").fetchone()
            except sqlite3.Error:
                pass  # some filesystems cannot do WAL; the default mode still works
        self._conn.executescript(
            """CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                created_at REAL DEFAULT (julianday('now'))
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                content, source, tokenize='porter unicode61'
            );"""
        )
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents_fts'"
        ).fetchone()
        if row and "unicode61" not in (row[0] or ""):
            self._conn.executescript(
                """DROP TABLE IF EXISTS documents_fts;
                CREATE VIRTUAL TABLE documents_fts USING fts5(
                    id, content, source, tokenize='unicode61'
                );
                INSERT INTO documents_fts (id, content, source)
                    SELECT id, content, source FROM documents;"""
            )
        self._conn.commit()

    def backend_id(self) -> str:
        return "sqlite"

    def _insert(self, cur: sqlite3.Cursor, content: str, source: str, meta: str) -> str:
        doc_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO documents (id, content, source, metadata) VALUES (?, ?, ?, ?)",
            (doc_id, content, source, meta),
        )
        cur.execute(
            "INSERT INTO documents_fts (rowid, content, source) VALUES (?, ?, ?)",
            (cur.lastrowid, content, source),
        )
        return doc_id

    def store(self, content: str, source: str, metadata: Optional[str] = None) -> str:
        meta = _meta_json(metadata)
        with self._lock, self._conn:
            return self._insert(self._conn.cursor(), content, source, meta)

    def replace_source(
        self, source: str, documents: Sequence[Tuple[str, Optional[str]]]
    ) -> List[str]:
        parsed = [(content, _meta_json(meta)) for content, meta in documents]
        with self._lock, self._conn:
            cur = self._conn.cursor()
            cur.execute(
                "DELETE FROM documents_fts WHERE rowid IN (SELECT rowid FROM documents WHERE source = ?)",
                (source,),
            )
            cur.execute("DELETE FROM documents WHERE source = ?", (source,))
            return [
                self._insert(cur, content, source, meta) for content, meta in parsed
            ]

    def retrieve(self, query: str, top_k: int = 5) -> str:
        # Alphanumeric words only, each quoted, so FTS5 never sees an
        # apostrophe or an operator word such as OR/NOT as syntax.
        words = [w for w in re.split(r"[^\w]|_", query) if w]
        if not words:
            return "[]"
        with self._lock:
            rows = self._conn.execute(
                """SELECT d.content, d.source, d.metadata,
                          bm25(documents_fts, 1.0, 0.5) * -1 AS score
                   FROM documents_fts f
                   JOIN documents d ON d.rowid = f.rowid
                   WHERE documents_fts MATCH ?
                   ORDER BY bm25(documents_fts, 1.0, 0.5)
                   LIMIT ?""",
                (" OR ".join(f'"{w}"' for w in words), top_k),
            ).fetchall()
        results = []
        for content, source, metadata, score in rows:
            try:
                meta = json.loads(metadata) if metadata else {}
            except ValueError:
                meta = {}
            results.append(
                {
                    "content": content,
                    "score": float(score or 0.0),
                    "source": source or "",
                    "metadata": meta if isinstance(meta, dict) else {},
                }
            )
        return json.dumps(results)

    def count(self) -> int:
        with self._lock:
            return int(
                self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            )

    def delete(self, doc_id: str) -> bool:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM documents_fts WHERE rowid = (SELECT rowid FROM documents WHERE id = ?)",
                (doc_id,),
            )
            return (
                self._conn.execute(
                    "DELETE FROM documents WHERE id = ?", (doc_id,)
                ).rowcount
                > 0
            )

    def clear(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                "DELETE FROM documents_fts; DELETE FROM documents;"
            )


def _bm25_terms(text: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for word in text.split():
        token = word.lower()
        start, end = 0, len(token)
        while start < end and not token[start].isalnum():
            start += 1
        while end > start and not token[end - 1].isalnum():
            end -= 1
        token = token[start:end]
        if token:
            counts[token] = counts.get(token, 0) + 1
    return counts


class BM25Memory:
    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        self._k1, self._b = k1, b
        self._docs: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def backend_id(self) -> str:
        return "bm25"

    def store(self, content: str, source: str, metadata: Optional[str] = None) -> str:
        meta = json.loads(metadata) if metadata is not None else {}
        terms = _bm25_terms(content)
        doc = {
            "id": str(uuid.uuid4()),
            "content": content,
            "source": source,
            "metadata": meta if isinstance(meta, dict) else {},
            "terms": terms,
            "term_count": sum(terms.values()),
        }
        with self._lock:
            self._docs.append(doc)
        return doc["id"]

    def retrieve(self, query: str, top_k: int = 5) -> str:
        with self._lock:
            docs = list(self._docs)
        if not docs:
            return "[]"
        query_terms = _bm25_terms(query)
        n = float(len(docs))
        avg_dl = sum(d["term_count"] for d in docs) / n
        df: Dict[str, int] = {}
        for d in docs:
            for term in d["terms"]:
                df[term] = df.get(term, 0) + 1
        scored = []
        for d in docs:
            score = 0.0
            dl = float(d["term_count"])
            for term in query_terms:
                tf = float(d["terms"].get(term, 0))
                freq = float(df.get(term, 0))
                if freq == 0 or tf == 0:
                    continue
                idf = math.log((n - freq + 0.5) / (freq + 0.5) + 1.0)
                norm = avg_dl if avg_dl else 1.0
                score += (
                    idf
                    * (tf * (self._k1 + 1.0))
                    / (tf + self._k1 * (1.0 - self._b + self._b * dl / norm))
                )
            if score > 0:
                scored.append((d, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return json.dumps(
            [
                {
                    "content": d["content"],
                    "score": s,
                    "source": d["source"],
                    "metadata": d["metadata"],
                }
                for d, s in scored[:top_k]
            ]
        )

    def count(self) -> int:
        return len(self._docs)

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            before = len(self._docs)
            self._docs = [d for d in self._docs if d["id"] != doc_id]
            return len(self._docs) < before

    def clear(self) -> None:
        with self._lock:
            self._docs.clear()


__all__ = [
    "BM25Memory",
    "CapabilityPolicy",
    "LoopGuard",
    "PIIScanner",
    "RateLimiter",
    "SQLiteMemory",
    "SecretScanner",
    "glob_match",
]
