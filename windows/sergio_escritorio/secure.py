"""Private files (health, therapy notes) encrypted for your Windows user.

Windows DPAPI (``CryptProtectData``) ties the file to your Windows account:
another user, or the file copied to another PC, cannot read it. Elsewhere
(tests, Linux) the data is stored as is, marked so it is never mistaken.
"""

from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path
from typing import Any

MAGIC = b"SERGIO-DPAPI1\n"
PLAIN = b"SERGIO-PLAIN1\n"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out))  # UI_FORBIDDEN
    if not ok:
        raise OSError("DPAPI falló")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def available() -> bool:
    return sys.platform == "win32"


def seal(data: bytes) -> bytes:
    return MAGIC + _dpapi(data, True) if available() else PLAIN + data


def unseal(data: bytes) -> bytes:
    if data.startswith(MAGIC):
        return _dpapi(data[len(MAGIC) :], False)
    if data.startswith(PLAIN):
        return data[len(PLAIN) :]
    return data  # an old unencrypted file: read it (it is sealed on next save)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(seal(json.dumps(value, ensure_ascii=False).encode("utf-8")))
    tmp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(unseal(path.read_bytes()).decode("utf-8"))
    except (OSError, ValueError):
        return default


__all__ = ["available", "read_json", "seal", "unseal", "write_json"]
