"""Plugins: tools other people write for Sergio, installed from a ZIP.

See :mod:`openjarvis.plugins.manifest` for the ``plugin.toml`` format,
:mod:`openjarvis.plugins.store` for installing and
:mod:`openjarvis.plugins.loader` for how they reach Sergio.
"""

from __future__ import annotations

from openjarvis.plugins.manifest import ManifestError, PluginManifest, parse_manifest
from openjarvis.plugins.package import PackageError, pack, unpack
from openjarvis.plugins.store import PluginError, PluginStore

__all__ = [
    "ManifestError",
    "PackageError",
    "PluginError",
    "PluginManifest",
    "PluginStore",
    "pack",
    "parse_manifest",
    "unpack",
]
