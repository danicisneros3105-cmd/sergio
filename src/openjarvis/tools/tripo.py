"""Tripo 3D (VAST-AI-Research): text or image -> a textured, PBR 3D model.

Uses the official SDK (``tripo3d``) with the user's key (``TRIPO_API_KEY``,
starts with ``tsk_``, from platform.tripo3d.ai; ``sergio nube configurar
--tripo``). The model comes back as GLB; Sergio imports it into Blender,
adds light and camera, renders the four views and has the vision model
check it like any other build.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any


def configured() -> bool:
    return str(os.environ.get("TRIPO_API_KEY", "")).startswith("tsk_")


async def _generate(
    prompt: str, image: bytes, out_dir: Path, quality: str
) -> dict[str, Any]:
    from tripo3d import TripoClient
    from tripo3d.models import TaskStatus

    async with TripoClient(api_key=os.environ.get("TRIPO_API_KEY")) as client:
        common = {
            "texture": True,
            "pbr": True,
            "texture_quality": quality,
            "geometry_quality": quality,
        }
        if image:
            path = out_dir / "referencia.png"
            path.write_bytes(image)
            task_id = await client.image_to_model(image=str(path), **common)
        else:
            task_id = await client.text_to_model(prompt=prompt, **common)
        task = await client.wait_for_task(task_id, polling_interval=3.0, timeout=900)
        if task.status != TaskStatus.SUCCESS:
            raise RuntimeError(f"Tripo terminó con estado {task.status}")
        files = await client.download_task_models(task, str(out_dir))
    best = files.get("pbr_model") or files.get("model") or files.get("base_model")
    if not best:
        raise RuntimeError("Tripo no devolvió un modelo.")
    return {"task_id": task_id, "glb": Path(best).read_bytes()}


def generate(
    prompt: str = "", image: bytes = b"", quality: str = "standard"
) -> dict[str, Any]:
    """{"task_id", "glb"} for *prompt* (text to 3D) or *image* (image to 3D)."""
    if not configured():
        raise RuntimeError(
            "Falta la clave de Tripo: sergio nube configurar --tripo tsk_… (platform.tripo3d.ai)"
        )
    if not prompt.strip() and not image:
        raise ValueError("Dígame qué modelar o pásele una imagen.")
    with tempfile.TemporaryDirectory(prefix="sergio-tripo-") as tmp:
        return asyncio.run(
            _generate(
                prompt,
                image,
                Path(tmp),
                "detailed" if quality == "detailed" else "standard",
            )
        )


__all__ = ["configured", "generate"]
