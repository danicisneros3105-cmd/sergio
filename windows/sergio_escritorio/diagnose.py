"""What went wrong lately, read from the companion's own log.

``sergio probar`` shows these lines, so a failure on the laptop ("sale error
cuando le hablo") comes with its real cause instead of a guess.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_START = re.compile(
    r"^\d{4}-\d\d-\d\d (?P<time>\d\d:\d\d:\d\d),\d+ (?P<level>[A-Z]+) (?P<msg>.*)$"
)
_PROBLEMS = ("WARNING", "ERROR", "CRITICAL")
TAIL_BYTES = 600_000


def setup_log(path: Path) -> None:
    """Log to *path*, kept small (it used to grow forever)."""
    handler = RotatingFileHandler(
        path, maxBytes=2_000_000, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def recent_errors(path: Path, limit: int = 12) -> list[str]:
    """The last warnings/errors, one line each, with the exception's reason."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    found: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        m = _START.match(line)
        if m:
            current = None
            if m.group("level") in _PROBLEMS:
                current = [f"{m.group('time')} {m.group('msg').strip()}", ""]
                found.append(current)
            continue
        if current is not None and line.strip() and not line.startswith(" "):
            if not line.startswith("Traceback"):
                current[1] = line.strip()  # the exception's last line wins
    out = []
    for head, reason in found[-limit:]:
        out.append(f"{head} — {reason}"[:300] if reason and reason not in head else head[:300])
    return out


__all__ = ["recent_errors", "setup_log"]
