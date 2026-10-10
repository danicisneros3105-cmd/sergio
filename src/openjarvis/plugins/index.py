"""Where plugins are found: indexes of ``{name, version, url|path, sha256}``.

Sources, in order: the catalog that ships with Sergio (example plugins),
``~/.openjarvis/plugins/index.json`` (your own list), and any URLs or files
in ``SERGIO_PLUGIN_INDEX`` (comma-separated). Remote entries must pin a
SHA-256, and only ``https`` downloads are accepted.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.plugins.manifest import NAME_RE, version_key
from openjarvis.plugins.package import pack
from openjarvis.plugins.store import PluginError, plugins_root

CATALOG = Path(__file__).parent / "catalog"
MAX_DOWNLOAD = 50 * 1024 * 1024


@dataclass
class IndexEntry:
    name: str
    version: str
    description: str = ""
    author: str = ""
    permissions: List[str] = field(default_factory=list)
    url: str = ""
    path: str = ""  # a local folder or .zip (the bundled catalog)
    sha256: str = ""
    source: str = ""
    premium: bool = False  # part of the Pro plan's premium skills

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def _entries(data: Any, origin: str, base: Optional[Path]) -> List[IndexEntry]:
    items = data.get("plugins") if isinstance(data, dict) else data
    out: List[IndexEntry] = []
    for raw in items or []:
        if not isinstance(raw, dict) or not NAME_RE.match(str(raw.get("name") or "")):
            continue
        path = str(raw.get("path") or "")
        if path and base is not None and not Path(path).is_absolute():
            path = str((base / path).resolve())
        out.append(
            IndexEntry(
                name=str(raw["name"]),
                version=str(raw.get("version") or "0.0.0"),
                description=str(raw.get("description") or "")[:300],
                author=str(raw.get("author") or "")[:120],
                permissions=[str(p) for p in raw.get("permissions") or []],
                url=str(raw.get("url") or ""),
                path=path,
                sha256=str(raw.get("sha256") or ""),
                source=origin,
                premium=bool(raw.get("premium", False)),
            )
        )
    return out


def _load_source(spec: str) -> List[IndexEntry]:
    spec = spec.strip()
    if not spec:
        return []
    if spec.startswith("https://"):
        import httpx

        resp = httpx.get(spec, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return [e for e in _entries(resp.json(), spec, None) if e.url and e.sha256]
    path = Path(spec).expanduser()
    if not path.is_file():
        return []
    return _entries(json.loads(path.read_text("utf-8")), str(path), path.parent)


def all_entries() -> List[IndexEntry]:
    sources = [str(CATALOG / "index.json"), str(plugins_root() / "index.json")]
    sources += [s for s in os.environ.get("SERGIO_PLUGIN_INDEX", "").split(",") if s]
    found: Dict[str, IndexEntry] = {}
    for spec in sources:
        try:
            entries = _load_source(spec)
        except Exception:  # noqa: BLE001 - one bad index never hides the others
            continue
        for entry in entries:
            best = found.get(entry.name)
            if best is None or version_key(entry.version) > version_key(best.version):
                found[entry.name] = entry
    return sorted(found.values(), key=lambda e: e.name)


def search(query: str = "") -> List[IndexEntry]:
    words = [w for w in query.lower().split() if w]
    scored = []
    for entry in all_entries():
        hay = f"{entry.name} {entry.description} {entry.author}".lower()
        score = sum(hay.count(w) + (3 if w in entry.name else 0) for w in words)
        if not words or score:
            scored.append((score, entry))
    return [e for _, e in sorted(scored, key=lambda x: (-x[0], x[1].name))]


def find(name: str) -> Optional[IndexEntry]:
    return next((e for e in all_entries() if e.name == name), None)


def fetch(entry: IndexEntry) -> bytes:
    """The plugin archive for an index entry (packed on the fly for folders)."""
    if entry.path:
        path = Path(entry.path)
        if path.is_dir():
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                archive, _, _ = pack(path, Path(tmp))
                return archive.read_bytes()
        if path.is_file():
            return path.read_bytes()
        raise PluginError(f"no encuentro {path}")
    if not entry.url.startswith("https://"):
        raise PluginError("solo se descargan plugins por https")
    if not entry.sha256:
        raise PluginError("el índice no fija la huella sha256 de este plugin")
    return download(entry.url)


def download(url: str) -> bytes:
    import httpx

    if not url.startswith("https://"):
        raise PluginError("solo se descargan plugins por https")
    chunks = []
    size = 0
    with httpx.stream("GET", url, timeout=60, follow_redirects=True) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_bytes():
            size += len(chunk)
            if size > MAX_DOWNLOAD:
                raise PluginError("el plugin pasa de 50 MB")
            chunks.append(chunk)
    return b"".join(chunks)


__all__ = [
    "CATALOG",
    "IndexEntry",
    "all_entries",
    "download",
    "fetch",
    "find",
    "search",
]
