"""Installed plugins: ``~/.openjarvis/plugins/<name>/`` plus ``installed.json``.

Installing verifies the archive (and its SHA-256 when an index pins one),
unpacks it into a temporary folder and only then swaps it in, so a failed
install never leaves half a plugin behind. Plugins can be switched off
without uninstalling them.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.plugins.manifest import PluginManifest, parse_manifest
from openjarvis.plugins.package import PackageError, read_manifest, sha256_bytes, unpack


class PluginError(RuntimeError):
    """Installing, removing or toggling a plugin failed."""


def plugins_root() -> Path:
    home = Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")
    return home / "plugins"


class PluginStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or plugins_root()
        self._lock = threading.Lock()

    # -- state ----------------------------------------------------------------
    @property
    def _state_path(self) -> Path:
        return self.root / "installed.json"

    def _read(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = json.loads(self._state_path.read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self._state_path)

    # -- queries ----------------------------------------------------------------
    def installed(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return self._read()

    def manifest(self, name: str) -> PluginManifest:
        path = self.root / name / "plugin.toml"
        if not path.is_file():
            raise PluginError(f"«{name}» no está instalado")
        return parse_manifest(path.read_text("utf-8"))

    def enabled(self) -> List[str]:
        return sorted(n for n, e in self.installed().items() if e.get("enabled", True))

    # -- changes ----------------------------------------------------------------
    def install(
        self,
        data: bytes,
        *,
        source: str = "",
        expected_sha256: str = "",
        force: bool = False,
    ) -> PluginManifest:
        digest = sha256_bytes(data)
        if expected_sha256 and digest.lower() != expected_sha256.lower():
            raise PluginError(
                "el archivo descargado no coincide con su huella (sha256): no lo instalo"
            )
        try:
            manifest = read_manifest(data)
        except (PackageError, ValueError) as exc:
            raise PluginError(str(exc)) from exc
        with self._lock:
            state = self._read()
            current = state.get(manifest.name)
            if current and current.get("version") == manifest.version and not force:
                raise PluginError(
                    f"«{manifest.name}» {manifest.version} ya está instalado (use --forzar)"
                )
            self.root.mkdir(parents=True, exist_ok=True)
            staging = self.root / f".tmp-{uuid.uuid4().hex[:8]}"
            try:
                unpack(data, staging)
            except (PackageError, ValueError) as exc:
                shutil.rmtree(staging, ignore_errors=True)
                raise PluginError(str(exc)) from exc
            final = self.root / manifest.name
            old = self.root / f".old-{uuid.uuid4().hex[:8]}"
            if final.exists():
                final.rename(old)
            staging.rename(final)
            shutil.rmtree(old, ignore_errors=True)
            state[manifest.name] = {
                "version": manifest.version,
                "enabled": True,
                "sha256": digest,
                "permissions": manifest.permissions,
                "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": source[:500],
            }
            self._write(state)
        return manifest

    def uninstall(self, name: str) -> None:
        with self._lock:
            state = self._read()
            if name not in state and not (self.root / name).exists():
                raise PluginError(f"«{name}» no está instalado")
            state.pop(name, None)
            shutil.rmtree(self.root / name, ignore_errors=True)
            self._write(state)

    def set_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            state = self._read()
            if name not in state:
                raise PluginError(f"«{name}» no está instalado")
            state[name]["enabled"] = bool(enabled)
            self._write(state)


__all__ = ["PluginError", "PluginStore", "plugins_root"]
