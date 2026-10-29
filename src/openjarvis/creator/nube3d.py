"""A description or a photo turned into a detailed 3D model by a cloud service.

The owner (29 Oct 2026): «agrégale un modelo de la nube para convertir cosas
como descripciones o imágenes a modelos 3D, para que sea profesional; usa
herramientas populares de la web y con demasiado detalle».

The services the professionals use, best first, each with the owner's own
key in ``~/.openjarvis/sergio.env`` (no key, that service is skipped):

* **Meshy** (``MESHY_API_KEY``) — text to 3D in two passes (the shape, then
  the refine with PBR textures) and image to 3D, remeshed for clean topology;
* **Tripo** (``TRIPO_API_KEY``, ``tools/tripo.py``) — text or image to a
  PBR model;
* **fal.ai** (``FAL_KEY``) — Hunyuan3D and TRELLIS from a photo; a
  description first becomes a picture with Sergio's image model.

The model comes back as GLB and lands where the chat's 3D viewer opens it
piece by piece (``creator/despiece.register_file``). Nothing is invented: if
no service has a key, it says which one to add.
"""

from __future__ import annotations

import base64
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

MESHY = "https://api.meshy.ai/openapi"
FAL_QUEUE = "https://queue.fal.run"
FAL_MODELS = ("fal-ai/hunyuan3d/v2", "fal-ai/trellis")
POLL = 5.0
TIMEOUT = 900.0

Http = Any


class Nube3DError(RuntimeError):
    """Plain words for the owner when no 3D service could do it."""


def _key(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def services() -> List[str]:
    """The services with a key on this computer, in the order they are tried."""
    from openjarvis.tools import tripo

    out = []
    if _key("MESHY_API_KEY"):
        out.append("meshy")
    if tripo.configured():
        out.append("tripo")
    if _key("FAL_KEY"):
        out.append("fal")
    return out


def _http() -> Http:
    import httpx

    return httpx.Client(timeout=60, follow_redirects=True)


def _wait(
    http: Http,
    url: str,
    headers: Dict[str, str],
    done: Callable[[Dict[str, Any]], bool],
    failed: Callable[[Dict[str, Any]], str],
    sleep: Callable[[float], None],
    timeout: float = TIMEOUT,
) -> Dict[str, Any]:
    start = time.monotonic()
    while True:
        r = http.get(url, headers=headers)
        r.raise_for_status()
        data = r.json() or {}
        why = failed(data)
        if why:
            raise Nube3DError(why)
        if done(data):
            return data
        if time.monotonic() - start > timeout:
            raise Nube3DError("El servicio 3D tardó demasiado; lo dejé de esperar.")
        sleep(POLL)


def _data_uri(image: bytes) -> str:
    kind = "png" if image[:4] == b"\x89PNG" else "jpeg"
    return f"data:image/{kind};base64," + base64.b64encode(image).decode()


# -- Meshy ---------------------------------------------------------------------------


def meshy(
    prompt: str = "",
    image: bytes = b"",
    *,
    http: Optional[Http] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """GLB bytes from Meshy: preview + refine (text) or image to 3D."""
    http = http or _http()
    headers = {"Authorization": f"Bearer {_key('MESHY_API_KEY')}"}

    def ok(d: Dict[str, Any]) -> bool:
        return d.get("status") == "SUCCEEDED"

    def bad(d: Dict[str, Any]) -> str:
        if d.get("status") in ("FAILED", "CANCELED", "EXPIRED"):
            err = (d.get("task_error") or {}).get("message") or d.get("status")
            return f"Meshy no pudo: {err}"
        return ""

    if image:
        r = http.post(f"{MESHY}/v1/image-to-3d", headers=headers, json={
            "image_url": _data_uri(image), "enable_pbr": True, "should_remesh": True,
            "should_texture": True, "topology": "quad", "target_polycount": 100000,
        })  # fmt: skip
        r.raise_for_status()
        task = r.json()["result"]
        data = _wait(http, f"{MESHY}/v1/image-to-3d/{task}", headers, ok, bad, sleep)
    else:
        r = http.post(f"{MESHY}/v2/text-to-3d", headers=headers, json={
            "mode": "preview", "prompt": prompt[:600], "art_style": "realistic",
            "should_remesh": True, "topology": "quad", "target_polycount": 100000,
        })  # fmt: skip
        r.raise_for_status()
        preview = r.json()["result"]
        _wait(http, f"{MESHY}/v2/text-to-3d/{preview}", headers, ok, bad, sleep)
        r = http.post(f"{MESHY}/v2/text-to-3d", headers=headers, json={
            "mode": "refine", "preview_task_id": preview, "enable_pbr": True,
            "texture_prompt": prompt[:600],
        })  # fmt: skip
        r.raise_for_status()
        refine = r.json()["result"]
        data = _wait(http, f"{MESHY}/v2/text-to-3d/{refine}", headers, ok, bad, sleep)
    url = (data.get("model_urls") or {}).get("glb")
    if not url:
        raise Nube3DError("Meshy terminó sin devolver el archivo GLB.")
    got = http.get(url)
    got.raise_for_status()
    return got.content


# -- fal.ai (Hunyuan3D, TRELLIS) ----------------------------------------------------------


def fal(
    image: bytes,
    *,
    http: Optional[Http] = None,
    sleep: Callable[[float], None] = time.sleep,
    models: tuple = FAL_MODELS,
) -> bytes:
    """GLB bytes from a photo, by the first fal.ai 3D model that answers."""
    http = http or _http()
    headers = {"Authorization": f"Key {_key('FAL_KEY')}"}
    last = ""
    for model in models:
        try:
            r = http.post(f"{FAL_QUEUE}/{model}", headers=headers, json={
                "input_image_url": _data_uri(image), "image_url": _data_uri(image),
                "textured_mesh": True,
            })  # fmt: skip
            r.raise_for_status()
            job = r.json()
            status_url = (
                job.get("status_url")
                or f"{FAL_QUEUE}/{model}/requests/{job['request_id']}/status"
            )
            result_url = (
                job.get("response_url")
                or f"{FAL_QUEUE}/{model}/requests/{job['request_id']}"
            )
            _wait(
                http, status_url, headers,
                lambda d: d.get("status") == "COMPLETED",
                lambda d: f"fal.ai: {d.get('error')}" if d.get("status") == "FAILED" else "",
                sleep,
            )  # fmt: skip
            out = http.get(result_url, headers=headers)
            out.raise_for_status()
            data = out.json() or {}
            mesh = (
                data.get("model_mesh") or data.get("model_glb") or data.get("glb") or {}
            )
            url = mesh.get("url") if isinstance(mesh, dict) else str(mesh or "")
            if not url:
                raise Nube3DError("fal.ai terminó sin devolver el modelo.")
            got = http.get(url)
            got.raise_for_status()
            return got.content
        except Exception as exc:  # noqa: BLE001 — the next model
            last = str(exc)[:160]
    raise Nube3DError(f"fal.ai no pudo hacer el modelo ({last}).")


# -- the whole thing ------------------------------------------------------------------


DETAIL = (
    "Highly detailed, production-quality 3D asset, accurate real-world proportions, "
    "clean quad topology, PBR materials (albedo, roughness, metallic, normal), "
    "every visible part modelled separately, no text, centred, neutral pose."
)


def generate(
    request: str = "",
    image: bytes = b"",
    *,
    order: Optional[List[str]] = None,
    make_image: Optional[Callable[[str], bytes]] = None,
    runners: Optional[Dict[str, Callable[..., bytes]]] = None,
    home: Optional[Path] = None,
) -> Dict[str, Any]:
    """The model for *request* (a description) or *image* (a photo), ready in
    the chat's 3D viewer: ``{"name", "titulo", "fuente", ...}``."""
    if not request.strip() and not image:
        raise Nube3DError("Dígame qué modelar o mándeme una foto.")
    order = order if order is not None else services()
    if not order:
        raise Nube3DError(
            "Para modelos 3D profesionales en la nube falta una clave en sergio.env: "
            "MESHY_API_KEY (meshy.ai), TRIPO_API_KEY (tripo3d.ai) o FAL_KEY (fal.ai). "
            "Mientras tanto puedo dibujarlo yo por piezas."
        )
    prompt = f"{request.strip()}. {DETAIL}" if request.strip() else ""
    from openjarvis.tools import tripo

    table: Dict[str, Callable[..., bytes]] = {
        "meshy": lambda: meshy(prompt, image),
        "tripo": lambda: tripo.generate(prompt, image, quality="detailed")["glb"],
        "fal": lambda: fal(image or _picture(prompt, make_image)),
    }
    table.update(runners or {})
    problems = []
    for name in order:
        try:
            glb = table[name]()
        except Exception as exc:  # noqa: BLE001 — the next service
            problems.append(f"{name}: {str(exc)[:120]}")
            continue
        if not glb or glb[:4] != b"glTF":
            problems.append(f"{name}: no devolvió un GLB")
            continue
        from openjarvis.creator import despiece

        with tempfile.TemporaryDirectory() as tmp:
            title = (request.strip() or "modelo de la foto")[:60]
            path = Path(tmp) / "modelo.glb"
            path.write_bytes(glb)
            meta = despiece.register_file(str(path), title=title, home=home)
        meta["fuente"] = {"meshy": "Meshy", "tripo": "Tripo", "fal": "fal.ai"}.get(
            name, name
        )
        meta["licencia"] = "suya (generado con su cuenta)"
        return meta
    raise Nube3DError("Ningún servicio 3D pudo hacerlo: " + "; ".join(problems))


def _picture(prompt: str, make_image: Optional[Callable[[str], bytes]]) -> bytes:
    """A description becomes a clean product shot first (for photo-to-3D)."""
    if make_image is None:
        from openjarvis.creator.studio import generate_image as make_image
    shot = make_image(
        f"{prompt} Single object, three-quarter view, plain white background, "
        "soft studio light, the whole object in frame."
    )
    if not shot:
        raise Nube3DError("No pude hacer la imagen previa para el modelo 3D.")
    return shot


__all__ = ["DETAIL", "Nube3DError", "fal", "generate", "meshy", "services"]
