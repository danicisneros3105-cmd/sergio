"""Local connector boundaries: argv is data, provider credentials are opt-in."""

from __future__ import annotations

import os
import re

_SAFE_ENV = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "TMP",
    "TEMP",
    "SystemRoot",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PROGRAMDATA",
    "HOMEDRIVE",
    "HOMEPATH",
}


def validate_command(command: list[str]) -> list[str]:
    if (
        not isinstance(command, list)
        or not command
        or len(command) > 256
        or not all(isinstance(p, str) and "\0" not in p for p in command)
        or not command[0].strip()
        or sum(map(len, command)) > 65536
    ):
        raise ValueError("Indique un ejecutable y argumentos válidos, sin shell.")
    return list(command)


def local_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    extra = {} if extra is None else extra
    if (
        not isinstance(extra, dict)
        or len(extra) > 100
        or any(
            not isinstance(k, str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k)
            or not isinstance(v, str)
            or "\0" in v
            or len(v) > 32768
            for k, v in extra.items()
        )
    ):
        raise ValueError("Las variables deben ser nombres y valores de texto válidos.")
    # Preserve Windows' case-insensitive environment names, without passing keys,
    # proxy credentials or provider settings to arbitrary local programs.
    safe = {key.upper() for key in _SAFE_ENV}
    return {
        **{k: v for k, v in os.environ.items() if k.upper() in safe},
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        **extra,
    }


__all__ = ["local_environment", "validate_command"]
