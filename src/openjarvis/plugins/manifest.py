"""``plugin.toml``: what a Sergio plugin is and what it may do.

A plugin is a ZIP with a ``plugin.toml`` at its root, a Python entry module
and optional ``assets/``::

    [plugin]
    name = "clima-cuenca"            # lower-case letters, digits, dashes
    version = "1.0.0"                # semantic version
    description = "El clima de Cuenca en una frase"
    author = "Nombre del autor"
    license = "Apache-2.0"
    entry = "plugin.py"              # defines register(api)
    permissions = ["network:fetch"]  # capabilities its tools may use
    homepage = "https://…"           # optional

``permissions`` uses Sergio's capability names (``file:read``,
``network:fetch``, ``code:execute`` …). They are shown before installing,
and a tool whose spec asks for more than the plugin declared is refused.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from openjarvis.security.capabilities import Capability

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([.-][0-9A-Za-z.-]+)?$")
KNOWN_PERMISSIONS = frozenset(c.value for c in Capability)
# Never granted to a plugin: acting through other people or as the admin.
FORBIDDEN_PERMISSIONS = frozenset({"channel:send", "system:admin"})
PERMISSIONS_ES = {
    "file:read": "leer archivos",
    "file:write": "escribir archivos",
    "network:fetch": "conectarse a internet",
    "code:execute": "ejecutar código",
    "memory:read": "leer la memoria de Sergio",
    "memory:write": "escribir en la memoria de Sergio",
    "tool:invoke": "usar otras herramientas",
    "schedule:create": "programar tareas",
}


class ManifestError(ValueError):
    """The plugin.toml is missing, malformed or asks for too much."""


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = ""
    entry: str = "plugin.py"
    permissions: List[str] = field(default_factory=list)
    homepage: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def permissions_es(self) -> List[str]:
        return [PERMISSIONS_ES.get(p, p) for p in self.permissions]


def parse_manifest(text: str) -> PluginManifest:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"plugin.toml no es TOML válido: {exc}") from exc
    section = data.get("plugin")
    if not isinstance(section, dict):
        raise ManifestError("plugin.toml necesita una sección [plugin]")
    name = str(section.get("name") or "")
    if not NAME_RE.match(name):
        raise ManifestError(
            f"nombre inválido {name!r}: minúsculas, dígitos y guiones (2-41 caracteres)"
        )
    version = str(section.get("version") or "")
    if not VERSION_RE.match(version):
        raise ManifestError(f"versión inválida {version!r} (use 1.2.3)")
    entry = str(section.get("entry") or "plugin.py")
    if (
        not entry.endswith(".py")
        or "/" in entry
        or "\\" in entry
        or entry.startswith(".")
    ):
        raise ManifestError("entry debe ser un archivo .py en la raíz del plugin")
    raw_permissions = section.get("permissions") or []
    if not isinstance(raw_permissions, list):
        raise ManifestError("permissions debe ser una lista")
    permissions = [str(p) for p in raw_permissions]
    unknown = [p for p in permissions if p not in KNOWN_PERMISSIONS]
    if unknown:
        raise ManifestError(f"permisos desconocidos: {', '.join(unknown)}")
    forbidden = [p for p in permissions if p in FORBIDDEN_PERMISSIONS]
    if forbidden:
        raise ManifestError(
            "un plugin no puede pedir: " + ", ".join(forbidden) + " (enviar a otras "
            "personas o administrar el sistema)"
        )
    return PluginManifest(
        name=name,
        version=version,
        description=str(section.get("description") or "")[:300],
        author=str(section.get("author") or "")[:120],
        license=str(section.get("license") or "")[:60],
        entry=entry,
        permissions=sorted(set(permissions)),
        homepage=str(section.get("homepage") or "")[:300],
    )


def version_key(version: str) -> tuple:
    """Sort key for versions: 1.10.0 > 1.9.2; pre-releases sort before."""
    core, _, pre = version.partition("-")
    parts = []
    for piece in core.split("."):
        parts.append(int(piece) if piece.isdigit() else 0)
    return (*parts, 0 if pre else 1, pre)


__all__ = [
    "FORBIDDEN_PERMISSIONS",
    "KNOWN_PERMISSIONS",
    "ManifestError",
    "PERMISSIONS_ES",
    "PluginManifest",
    "parse_manifest",
    "version_key",
]
