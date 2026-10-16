"""Adapter for OpenDesign's actual REST contract, pinned a0ea785 (MIT).

The separate full editor remains responsible for canvas, fonts and export.
Only a loopback service configured by the owner can receive design data.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlsplit

import httpx


def endpoint() -> str:
    raw = os.environ.get("SERGIO_OPENDESIGN_URL", "http://127.0.0.1:8787")
    url = urlsplit(raw)
    if (
        url.scheme != "http"
        or url.hostname not in ("127.0.0.1", "localhost", "::1")
        or url.username
        or url.password
        or url.path not in ("", "/")
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "OpenDesign debe ser un servicio HTTP local, sin credenciales en la URL."
        )
    port = url.port or 80
    host = "[::1]" if url.hostname == "::1" else "127.0.0.1"
    return f"http://{host}:{port}"


def request(operation: str, payload: dict | None = None, *, client=None):
    payload = dict(payload or {})
    ident = str(payload.pop("id", ""))
    if operation in ("get", "fields", "fill", "update") and not re.fullmatch(
        r"[A-Za-z0-9_-]{1,64}", ident
    ):
        raise ValueError("Identificador de diseño inválido.")
    routes = {
        "list": ("GET", "/api/designs"),
        "templates": ("GET", "/api/templates"),
        "create": ("POST", "/api/designs"),
        "get": ("GET", f"/api/designs/{ident}"),
        "fields": ("GET", f"/api/designs/{ident}/fields"),
        "fill": ("POST", f"/api/designs/{ident}/fill"),
        "update": ("PUT", f"/api/designs/{ident}"),
        "brands": ("GET", "/api/brand-kits"),
    }
    if operation not in routes:
        raise ValueError("Operación de OpenDesign no permitida.")
    if len(json.dumps(payload, allow_nan=False).encode()) > 512_000:
        raise ValueError("Diseño demasiado grande para esta operación.")
    if operation == "create":
        if set(payload) - {"name", "width", "height", "canvas_json"}:
            raise ValueError("Campos de diseño no válidos.")
        for key in ("width", "height"):
            value = payload.get(key, 1080)
            if type(value) is not int or not 64 <= value <= 8192:
                raise ValueError("Dimensiones de lienzo entre 64 y 8192 píxeles.")
    method, path = routes[operation]
    owns_client = client is None
    client = client or httpx.Client(timeout=15, trust_env=False, follow_redirects=False)
    try:
        token = os.environ.get("SERGIO_OPENDESIGN_TOKEN", "")
        with client.stream(
            method,
            endpoint() + path,
            json=payload if method != "GET" else None,
            headers={"Authorization": "Bearer " + token} if token else {},
        ) as res:
            res.raise_for_status()
            buf = bytearray()
            for block in res.iter_bytes():
                buf.extend(block)
                if len(buf) > 2_000_000:
                    raise ValueError("Respuesta de OpenDesign demasiado grande.")
            return json.loads(buf)
    finally:
        if owns_client:
            client.close()


__all__ = ["endpoint", "request"]
