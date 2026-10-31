"""Projects: chats that share instructions and files (owner, 29 Oct 2026:
«no veo dónde creas proyectos»).

Like the projects of the big chat apps: a project has a name, standing
instructions («responde como abogado laboral», «el cliente es X») and files
(documents, notes, data). Every chat of the project starts with them, so
Sergio does not need to be told again. Kept on this computer only:
``~/.openjarvis/proyectos/<id>/`` (``proyecto.json`` and ``archivos/``).
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_FILE = 25 * 1024 * 1024  # one file
MAX_CONTEXT = 40_000  # characters of the files that go into each chat
TEXT = (".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".html", ".xml", ".py", ".js",
        ".ts", ".tsx", ".sql", ".log", ".ini", ".toml", ".rtf", ".tex")  # fmt: skip


class ProjectError(ValueError):
    """Something wrong in what was asked, in plain words."""


def root(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = Path(get_config_dir())
    return Path(home) / "proyectos"


def _dir(pid: str, home: Optional[Path]) -> Path:
    if not re.fullmatch(r"p_[a-z0-9]{10}", pid or ""):
        raise ProjectError("Ese proyecto no existe.")
    folder = root(home) / pid
    if not (folder / "proyecto.json").is_file():
        raise ProjectError("Ese proyecto no existe.")
    return folder


def _save(folder: Path, data: Dict[str, Any]) -> None:
    tmp = folder / "proyecto.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(folder / "proyecto.json")


def _files(folder: Path) -> List[Dict[str, Any]]:
    files = folder / "archivos"
    if not files.is_dir():
        return []
    return [
        {"nombre": f.name, "bytes": f.stat().st_size}
        for f in sorted(files.iterdir())
        if f.is_file()
    ]


def _public(folder: Path) -> Dict[str, Any]:
    data = json.loads((folder / "proyecto.json").read_text(encoding="utf-8"))
    return {**data, "archivos": _files(folder)}


def create(
    name: str, instructions: str = "", home: Optional[Path] = None
) -> Dict[str, Any]:
    name = " ".join(str(name or "").split())[:80]
    if not name:
        raise ProjectError("Ponga un nombre al proyecto.")
    pid = "p_" + secrets.token_hex(5)
    folder = root(home) / pid
    (folder / "archivos").mkdir(parents=True, exist_ok=True)
    now = time.time()
    data = {"id": pid, "nombre": name, "instrucciones": str(instructions or "")[:8000],
            "creado": now, "actualizado": now}  # fmt: skip
    _save(folder, data)
    return _public(folder)


def all_projects(home: Optional[Path] = None) -> List[Dict[str, Any]]:
    base = root(home)
    if not base.is_dir():
        return []
    out = []
    for folder in base.iterdir():
        if (folder / "proyecto.json").is_file():
            try:
                out.append(_public(folder))
            except (OSError, ValueError):
                continue
    return sorted(out, key=lambda p: -float(p.get("actualizado") or 0))


def get(pid: str, home: Optional[Path] = None) -> Dict[str, Any]:
    return _public(_dir(pid, home))


def update(pid: str, home: Optional[Path] = None, **fields: Any) -> Dict[str, Any]:
    folder = _dir(pid, home)
    data = json.loads((folder / "proyecto.json").read_text(encoding="utf-8"))
    if fields.get("nombre") is not None:
        name = " ".join(str(fields["nombre"]).split())[:80]
        if not name:
            raise ProjectError("Ponga un nombre al proyecto.")
        data["nombre"] = name
    if fields.get("instrucciones") is not None:
        data["instrucciones"] = str(fields["instrucciones"])[:8000]
    data["actualizado"] = time.time()
    _save(folder, data)
    return _public(folder)


def delete(pid: str, home: Optional[Path] = None) -> None:
    """Moves the project to the trash folder (it can be brought back)."""
    folder = _dir(pid, home)
    trash = root(home) / ".papelera"
    trash.mkdir(parents=True, exist_ok=True)
    shutil.move(str(folder), str(trash / f"{pid}-{int(time.time())}"))


def _safe_name(name: str) -> str:
    name = Path(str(name or "")).name.strip()
    name = re.sub(r"[^\w.\- ()áéíóúñÁÉÍÓÚÑ]", "_", name)[:120]
    if not name or name.startswith("."):
        raise ProjectError("Ese archivo no tiene un nombre válido.")
    return name


def add_file(
    pid: str, name: str, data: bytes, home: Optional[Path] = None
) -> Dict[str, Any]:
    folder = _dir(pid, home)
    if len(data) > MAX_FILE:
        raise ProjectError("El archivo pasa de 25 MB.")
    target = folder / "archivos" / _safe_name(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return update(pid, home)


def remove_file(pid: str, name: str, home: Optional[Path] = None) -> Dict[str, Any]:
    folder = _dir(pid, home)
    target = folder / "archivos" / _safe_name(name)
    if target.is_file():
        target.unlink()
    return update(pid, home)


def _text_of(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            return "\n".join(
                (p.extract_text() or "") for p in PdfReader(str(path)).pages[:60]
            )
        except Exception:  # noqa: BLE001 — not readable here: only its name goes
            return ""
    if suffix == ".docx":
        try:
            import docx  # python-docx

            return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
        except Exception:  # noqa: BLE001
            return ""
    return ""


def context(pid: str, home: Optional[Path] = None) -> str:
    """What every chat of the project starts with (instructions and files)."""
    folder = _dir(pid, home)
    data = _public(folder)
    parts = [f"[Proyecto «{data['nombre']}»]"]
    if data.get("instrucciones"):
        parts.append("Instrucciones del proyecto (siempre):\n" + data["instrucciones"])
    room = MAX_CONTEXT
    names = []
    for f in data["archivos"]:
        names.append(f["nombre"])
        if room <= 0:
            continue
        text = _text_of(folder / "archivos" / f["nombre"]).strip()
        if text:
            piece = text[:room]
            room -= len(piece)
            parts.append(f"--- Archivo del proyecto: {f['nombre']} ---\n{piece}")
    if names:
        parts.append("Archivos del proyecto: " + ", ".join(names))
    return "\n\n".join(parts)


__all__ = [
    "ProjectError",
    "add_file",
    "all_projects",
    "context",
    "create",
    "delete",
    "get",
    "remove_file",
    "update",
]
