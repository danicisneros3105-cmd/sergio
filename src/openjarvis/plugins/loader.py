"""Loading installed plugins into Sergio.

Each enabled plugin's entry module is imported from its own folder and its
``register(api)`` is called. ``api.tool(ToolClass)`` adds a tool to Sergio
under the plugin's name, refusing tools that would replace a built-in one or
that need a capability the plugin did not declare. A plugin that fails to
load is logged and skipped; it never stops Sergio from starting.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.plugins.manifest import PluginManifest
from openjarvis.plugins.store import PluginStore

logger = logging.getLogger(__name__)
_LOADED: Dict[str, List[str]] = {}  # plugin -> tool ids it registered
_FAILED: Dict[str, str] = {}
_LOADING = False
_CLASSES: Dict[str, Dict[str, Any]] = {}  # plugin -> {tool id: class}


class PluginAPI:
    """What a plugin's ``register(api)`` receives."""

    def __init__(self, manifest: PluginManifest, folder: Path) -> None:
        self.manifest = manifest
        self.folder = folder
        self.tools: List[str] = []

    def tool(self, cls: Any) -> Any:
        """Register a :class:`~openjarvis.tools._stubs.BaseTool` subclass."""
        from openjarvis.core.registry import ToolRegistry
        from openjarvis.tools._stubs import BaseTool

        if not (isinstance(cls, type) and issubclass(cls, BaseTool)):
            raise TypeError("api.tool() espera una clase BaseTool")
        tool_id = str(getattr(cls, "tool_id", "") or "")
        if not tool_id:
            raise ValueError("la herramienta necesita un tool_id")
        builtin = ToolRegistry._builtin()
        if tool_id in builtin:
            raise ValueError(f"«{tool_id}» ya es una herramienta de Sergio")
        needed = set(cls().spec.required_capabilities)
        extra = needed - set(self.manifest.permissions)
        if extra:
            raise PermissionError(
                f"«{tool_id}» necesita {', '.join(sorted(extra))}, que el plugin no declaró"
            )
        if ToolRegistry.contains(tool_id):
            owner = next((p for p, ids in _LOADED.items() if tool_id in ids), None)
            if owner != self.manifest.name:
                raise ValueError(f"otra extensión ya usa el nombre «{tool_id}»")
            return cls
        ToolRegistry.register_value(tool_id, cls)
        self.tools.append(tool_id)
        return cls

    def asset(self, relative: str) -> Path:
        """A file from the plugin's own folder (never outside it)."""
        path = (self.folder / relative).resolve()
        if self.folder.resolve() not in path.parents:
            raise ValueError("ruta fuera del plugin")
        return path


def _import_entry(manifest: PluginManifest, folder: Path) -> Any:
    module_name = "sergio_plugins." + manifest.name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, folder / manifest.entry)
    if spec is None or spec.loader is None:
        raise ImportError(f"no puedo cargar {manifest.entry}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_enabled(store: Optional[PluginStore] = None) -> Dict[str, List[str]]:
    """Load every enabled plugin; returns {plugin: [tool ids]}. Idempotent."""
    global _LOADING
    if os.environ.get("SERGIO_NO_PLUGINS") or _LOADING:
        # Re-entry: a plugin importing openjarvis.tools while it loads.
        return dict(_LOADED)
    store = store or PluginStore()
    from openjarvis.core.registry import ToolRegistry

    _LOADING = True
    try:
        _load_all(store, ToolRegistry)
    finally:
        _LOADING = False
    return dict(_LOADED)


def _load_all(store: PluginStore, ToolRegistry: Any) -> None:  # noqa: N803
    for name in store.enabled():
        classes = _CLASSES.get(name)
        if classes is not None:
            # Already imported in this process: only put back tools that a
            # registry reset (tests, reloads) removed. No second import.
            for tool_id, cls in classes.items():
                if not ToolRegistry.contains(tool_id):
                    ToolRegistry.register_value(tool_id, cls)
            continue
        api: Optional[PluginAPI] = None
        try:
            manifest = store.manifest(name)
            folder = store.root / name
            module = _import_entry(manifest, folder)
            register = getattr(module, "register", None)
            if not callable(register):
                raise AttributeError("el plugin no define register(api)")
            api = PluginAPI(manifest, folder)
            register(api)
            _CLASSES[name] = {t: ToolRegistry.get(t) for t in api.tools}
            _LOADED[name] = api.tools
            _FAILED.pop(name, None)
        except Exception as exc:  # noqa: BLE001 - a bad plugin never stops Sergio
            for tool_id in api.tools if api is not None else []:
                ToolRegistry._entries().pop(tool_id, None)  # no half-loaded plugin
            _FAILED[name] = f"{type(exc).__name__}: {exc}"
            logger.warning("Plugin %s not loaded: %s", name, exc)


def status() -> Dict[str, Any]:
    return {"loaded": dict(_LOADED), "failed": dict(_FAILED)}


def forget(name: str) -> None:
    """Drop a plugin's tools from this process (after uninstall/disable)."""
    from openjarvis.core.registry import ToolRegistry

    for tool_id in _LOADED.pop(name, []):
        ToolRegistry._entries().pop(tool_id, None)
    _CLASSES.pop(name, None)
    _FAILED.pop(name, None)
    sys.modules.pop("sergio_plugins." + name.replace("-", "_"), None)


__all__ = ["PluginAPI", "forget", "load_enabled", "status"]
