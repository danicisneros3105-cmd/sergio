"""Brand colours for the services in the terminal (``sergio mcp list``).

The same Simple Icons data (CC0-1.0) the web uses in ``frontend/src/lib/
brands.ts``, colours only: the terminal draws a bar of the service's colour
before its name. The logos are their owners' trademarks and only name the
service the owner connects.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

ALIASES = {
    "google-calendar": "googlecalendar", "google-drive": "googledrive", "bigquery": "googlebigquery",
    "tiktok-ads": "tiktok", "hugging-face": "huggingface", "gcalendar": "googlecalendar",
    "gdrive": "googledrive", "gmail_imap": "gmail", "google_tasks": "googletasks",
    "github_notifications": "github", "garmin_connect": "garmin", "news_rss": "rss",
    "apple_music": "applemusic", "gemini": "googlegemini",
}  # fmt: skip


@lru_cache(maxsize=1)
def _brands() -> Dict[str, Dict[str, str]]:
    return json.loads((Path(__file__).with_name("brands.json")).read_text("utf-8"))


def brand(*names: Optional[str]) -> Optional[Dict[str, str]]:
    """{"title", "hex"} for a server id or name, or None."""
    data = _brands()
    for raw in names:
        if not raw:
            continue
        key = raw.lower().strip()
        for k in (key, ALIASES.get(key, ""), re.sub(r"[^a-z0-9]", "", key)):
            if k and k in data:
                return data[k]
    return None


def bar(*names: Optional[str]) -> str:
    """A rich-markup bar in the brand's colour (grey when unknown)."""
    b = brand(*names)
    return f"[on #{b['hex']}]  [/]" if b else "[on grey35]  [/]"


__all__ = ["bar", "brand"]
