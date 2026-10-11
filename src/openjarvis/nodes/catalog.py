"""Optional adapters; inspect installed executables without launching them."""

from __future__ import annotations

import shutil
from copy import deepcopy

__all__ = ["presets", "preset_spec"]

_PRESETS = {
    "browser-use": {
        "id": "browser-use",
        "name": "Browser-use · navegador dedicado",
        "kind": "mcp",
        "command": ["browser-use", "--mcp"],
        "session_mode": "persistent",
        "repository": "https://github.com/browser-use/browser-use",
        "license": "MIT",
        "note": "Mantiene la sesión entre acciones revisadas; se cierra tras dos minutos sin uso. "
        "No es una VM ni garantiza aislamiento de archivos.",
    },
    "openclaw": {
        "id": "openclaw",
        "name": "OpenClaw · CLI local",
        "kind": "cli",
        "command": ["openclaw"],
        "session_mode": "ephemeral",
        "repository": "https://github.com/openclaw/openclaw",
        "license": "MIT",
        "note": 'Usa argumentos como ["--version"]. Autorizar un agente delega sus acciones internas: '
        "configura también los permisos de OpenClaw. Límite de 30 segundos; un Gateway externo "
        "puede continuar una tarea tras perder la conexión.",
    },
}


def presets() -> list[dict]:
    return [
        {**deepcopy(value), "available": shutil.which(value["command"][0]) is not None}
        for value in _PRESETS.values()
    ]


def preset_spec(preset_id: str) -> dict:
    if preset_id not in _PRESETS:
        raise ValueError("Integración desconocida")
    preset = _PRESETS[preset_id]
    executable = shutil.which(preset["command"][0])
    if not executable:
        raise FileNotFoundError("Instala primero la integración en Ubuntu/WSL")
    return {
        "name": preset["name"],
        "kind": preset["kind"],
        "command": [executable, *preset["command"][1:]],
        "policy": "confirm",
        "session_mode": preset["session_mode"],
    }
