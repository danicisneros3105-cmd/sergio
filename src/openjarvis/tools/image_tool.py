"""Image generation: «haz una imagen de…» from the chat, the voice or a Node.

Sergio's own image path (``creator/studio.generate_image``): Gemini's image
models with the owner's key, then OpenAI, Hugging Face and a keyless service
when that key has no image quota. The picture is saved and shown in the chat.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("image_generate")
class ImageGenerateTool(BaseTool):
    """Make a picture from a description and show it in the chat."""

    tool_id = "image_generate"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="image_generate",
            description=(
                "Make a picture from a description (a photo, drawing, poster, "
                "logo idea...). Write the description in detail, in any language. "
                "The image is saved and shown in the chat."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "What the picture shows, in detail.",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Optional: also save it to this file.",
                    },
                },
                "required": ["prompt"],
            },
            category="media",
            required_capabilities=["network:fetch"],
        )

    def execute(self, **params: Any) -> ToolResult:
        prompt = str(params.get("prompt") or "").strip()
        if not prompt:
            return ToolResult(
                tool_name="image_generate",
                content="Dígame qué imagen quiere.",
                success=False,
            )
        from openjarvis.creator import studio
        from openjarvis.creator.llm import CreatorError

        asked = prompt
        try:  # art direction from the superskills that fit (never on a brief without design intent)
            if os.environ.get("SERGIO_ESTETICA", "1").strip() not in ("0", "no", "off"):
                from openjarvis.estetica.superskills import brief_for_images

                note = brief_for_images(prompt)
                if note:
                    prompt = f"{prompt}\n\nArt direction: {note}."
        except Exception:  # noqa: BLE001 — the picture never waits on this
            pass
        try:
            data = studio.generate_image(prompt)
        except CreatorError as exc:
            return ToolResult(
                tool_name="image_generate", content=str(exc), success=False
            )
        ext = ".jpg" if data[:3] == b"\xff\xd8\xff" else ".png"
        name = studio.media_name("imagen", ext)
        folder = studio.projects_root() / "imagenes"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
        saved = folder / name
        target = str(params.get("output_path") or "").strip()
        if target:
            out = Path(target).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            saved = out
        url = f"/v1/creator/media/{name}"
        return ToolResult(
            tool_name="image_generate",
            content=f"Imagen lista ({saved}).\n\n![{asked[:60]}]({url})",
            success=True,
            metadata={"url": url, "path": str(saved)},
        )


__all__ = ["ImageGenerateTool"]
