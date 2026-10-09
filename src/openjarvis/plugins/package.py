"""Packing a plugin folder into a ZIP, and unpacking one safely.

Unpacking refuses anything that could escape the plugin's folder (absolute
paths, ``..``, links), archives over 50 MB or 2,000 files, and compiled
binaries; the SHA-256 of the archive is what an index entry pins.
"""

from __future__ import annotations

import hashlib
import io
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Tuple

from openjarvis.plugins.manifest import PluginManifest, parse_manifest

MAX_BYTES = 50 * 1024 * 1024
MAX_FILES = 2000
BLOCKED_SUFFIXES = (
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pyd",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
)
SKIP_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}


class PackageError(ValueError):
    """The archive is not a valid, safe plugin."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pack(folder: Path, out_dir: Path | None = None) -> Tuple[Path, str, PluginManifest]:
    """Zip *folder* (which holds plugin.toml) → (zip path, sha256, manifest)."""
    folder = folder.resolve()
    manifest_path = folder / "plugin.toml"
    if not manifest_path.is_file():
        raise PackageError(f"falta plugin.toml en {folder}")
    manifest = parse_manifest(manifest_path.read_text("utf-8"))
    if not (folder / manifest.entry).is_file():
        raise PackageError(f"falta el archivo de entrada {manifest.entry}")
    buffer = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(folder)
            if any(part in SKIP_DIRS for part in rel.parts) or path.is_dir():
                continue
            if path.is_symlink():
                raise PackageError(f"no se admiten enlaces: {rel}")
            if path.suffix.lower() in BLOCKED_SUFFIXES or path.suffix == ".pyc":
                continue
            info = zipfile.ZipInfo(rel.as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes())
            count += 1
            if count > MAX_FILES:
                raise PackageError(f"demasiados archivos (máximo {MAX_FILES})")
    data = buffer.getvalue()
    if len(data) > MAX_BYTES:
        raise PackageError("el paquete pasa de 50 MB")
    out_dir = (out_dir or folder.parent).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{manifest.name}-{manifest.version}.zip"
    target.write_bytes(data)
    return target, sha256_bytes(data), manifest


def read_manifest(data: bytes) -> PluginManifest:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            try:
                text = zf.read("plugin.toml").decode("utf-8")
            except KeyError:
                raise PackageError("el ZIP no tiene plugin.toml en la raíz") from None
    except zipfile.BadZipFile as exc:
        raise PackageError("no es un ZIP válido") from exc
    return parse_manifest(text)


def unpack(data: bytes, dest: Path) -> PluginManifest:
    """Extract a plugin archive into *dest* (which must not exist yet)."""
    if len(data) > MAX_BYTES:
        raise PackageError("el paquete pasa de 50 MB")
    manifest = read_manifest(data)
    dest = dest.resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise PackageError(f"demasiados archivos (máximo {MAX_FILES})")
        total = sum(i.file_size for i in infos)
        if total > MAX_BYTES * 4:
            raise PackageError("el contenido descomprimido es demasiado grande")
        names = {i.filename for i in infos}
        if manifest.entry not in names:
            raise PackageError(f"falta el archivo de entrada {manifest.entry}")
        for info in infos:
            name = info.filename
            posix = PurePosixPath(name)
            if (
                name.startswith(("/", "\\"))
                or ".." in posix.parts
                or ":" in name
                or "\\" in name
            ):
                raise PackageError(f"ruta peligrosa en el ZIP: {name}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise PackageError(f"no se admiten enlaces: {name}")
            if posix.suffix.lower() in BLOCKED_SUFFIXES:
                raise PackageError(
                    f"no se admiten binarios ni scripts del sistema: {name}"
                )
        dest.mkdir(parents=True, exist_ok=False)
        for info in infos:
            if info.is_dir():
                continue
            target = (dest / info.filename).resolve()
            if dest not in target.parents:
                raise PackageError(f"ruta fuera del plugin: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
    return manifest


__all__ = [
    "BLOCKED_SUFFIXES",
    "MAX_BYTES",
    "MAX_FILES",
    "PackageError",
    "pack",
    "read_manifest",
    "sha256_bytes",
    "unpack",
]
