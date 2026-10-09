"""The audit trail of a Cowork run: every decision and action, in order.

One JSON line per event in ``~/.openjarvis/cowork/<run>/audit.jsonl``. Each
line carries the SHA-256 of the previous one, so editing or deleting a line
afterwards breaks the chain and :meth:`AuditTrail.verify` says where. Secrets
that slip into step results (API keys, tokens) are masked before writing.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

GENESIS = "0" * 64
MAX_TEXT = 2000
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|AQ\.[0-9A-Za-z_-]{30,}|"
    r"ghp_[A-Za-z0-9]{30,}|xox[abpr]-[A-Za-z0-9-]{10,}|sm_[A-Za-z0-9_-]{30,}|"
    r"(?i:bearer)\s+[A-Za-z0-9._-]{20,})"
)


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        text = _SECRET.sub("[oculto]", value)
        return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"
    if isinstance(value, dict):
        return {str(k): _mask(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask(v) for v in value]
    return value


def _digest(prev: str, body: Dict[str, Any]) -> str:
    payload = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()


class AuditTrail:
    """Append-only, hash-chained log of one run."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._seq, self._last = self._tail()

    def _tail(self) -> Tuple[int, str]:
        last_seq, last_hash = 0, GENESIS
        for entry in self.entries():
            last_seq, last_hash = int(entry.get("seq", 0)), str(entry.get("hash", ""))
        return last_seq, last_hash

    def record(self, event: str, **data: Any) -> Dict[str, Any]:
        with self._lock:
            body = {
                "seq": self._seq + 1,
                "ts": round(time.time(), 3),
                "event": event,
                "data": _mask(data),
                "prev": self._last,
            }
            entry = {**body, "hash": _digest(self._last, body)}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._seq, self._last = entry["seq"], entry["hash"]
            return entry

    def entries(self) -> Iterator[Dict[str, Any]]:
        try:
            lines = self.path.read_text("utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    yield {"event": "corrupt", "raw": line[:200]}

    def verify(self) -> Tuple[bool, Optional[int]]:
        """(intact, first bad sequence number or None)."""
        prev = GENESIS
        for expected, entry in enumerate(self.entries(), start=1):
            body = {k: entry.get(k) for k in ("seq", "ts", "event", "data", "prev")}
            if entry.get("seq") != expected or entry.get("prev") != prev:
                return False, expected
            if _digest(prev, body) != entry.get("hash"):
                return False, expected
            prev = str(entry["hash"])
        return True, None

    def to_list(self) -> List[Dict[str, Any]]:
        return list(self.entries())


__all__ = ["AuditTrail", "GENESIS"]
