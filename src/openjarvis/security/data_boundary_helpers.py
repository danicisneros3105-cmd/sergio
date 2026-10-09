"""Small pure helpers of the data-boundary audit: config lookups, cloud vs
local classification, path labels and text formatting. Split out of
``data_boundary_audit.py``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from openjarvis.security.data_boundary_surfaces import (
    CLOUD_PROVIDER_KEYS,
    LOCAL_ENGINE_KEYS,
)


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _get(obj: Any, dotted_path: str, default: Any = None) -> Any:
    current = obj
    for part in dotted_path.split("."):
        if current is None:
            return default
        current = getattr(current, part, default)
    return current


def _is_cloud_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    if not text or text in LOCAL_ENGINE_KEYS:
        return False
    return any(key in text for key in CLOUD_PROVIDER_KEYS)


def _is_local_engine_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower().replace("-", "_")
    return text in LOCAL_ENGINE_KEYS


def _target_is_cloud(engine: Any, model: Any) -> bool:
    """Classify a model target without treating local vendor model IDs as cloud."""
    if _is_cloud_value(engine):
        return True
    if _is_local_engine_value(engine):
        return False
    return _looks_like_cloud_model(model)


def _primary_cloud_signals(config: Any) -> list[str]:
    """Return explicit cloud signals for the primary inference target."""
    provider = _get(config, "intelligence.provider", "")
    preferred_engine = _get(config, "intelligence.preferred_engine", "")
    default_engine = _get(config, "engine.default", "")
    default_model = _get(config, "intelligence.default_model", "")
    signals = [
        str(value)
        for value in (provider, preferred_engine, default_engine)
        if _is_cloud_value(value)
    ]
    effective_engine = _first_nonempty(preferred_engine, default_engine, provider)
    if not signals and _target_is_cloud(effective_engine, default_model):
        signals.append(str(default_model))
    return signals


def _looks_like_cloud_model(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    if not text:
        return False
    return any(key in text for key in CLOUD_PROVIDER_KEYS) or text.startswith("gpt-")


def _is_loopback_host(host: str) -> bool:
    if host in {"", "localhost"}:
        return True
    try:
        import ipaddress

        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _iter_digest_sources(config: Any) -> Iterable[str]:
    digest = _get(config, "digest", None)
    if digest is None:
        return []
    sections = _get(digest, "sections", []) or []
    optional_sections = _get(digest, "optional_sections", []) or []
    names = list(sections) + list(optional_sections)
    sources: list[str] = []
    for name in names:
        section = getattr(digest, str(name), None)
        if section is None:
            continue
        section_sources = getattr(section, "sources", []) or []
        sources.extend(str(source) for source in section_sources)
    return sources


def _non_empty_paths(
    config: Any,
    fields: tuple[tuple[str, str, str], ...],
) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for dotted_path, label, service in fields:
        value = _get(config, dotted_path, "")
        if str(value or "").strip():
            results.append((dotted_path, label, service))
    return results


def _location_label(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return "<redacted>"


def _permission_note(path: Path) -> str:
    try:
        if path.is_symlink():
            return "path is a symlink"
        if os.name == "nt":
            return ""
        mode = path.stat().st_mode & 0o777
    except OSError:
        return "could not read filesystem metadata"
    if mode & 0o077:
        return f"permissions are {mode:03o}; group/other access is present"
    return ""


def _format_tools(tools: Iterable[str]) -> str:
    return ", ".join(sorted(tools))


def _quote(value: Any) -> str:
    return repr(str(value))


def _redact_root(root: str) -> str:
    if root.startswith("<"):
        return root
    path = Path(root)
    if path.name == ".openjarvis":
        return "~/.openjarvis"
    if path.name == "openjarvis":
        return "<xdg-data-home>/openjarvis"
    return "<openjarvis-home>"
