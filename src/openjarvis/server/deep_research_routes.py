"""``POST /v1/investigar`` — deep research on the web, live.

Streams Server-Sent Events while it works — ``plan``, ``ronda``, ``busqueda``,
``lectura``, ``afirmaciones``, ``contraste`` — and ends with ``informe`` (the
report in Markdown, its findings and sources) or ``error``.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1", tags=["investigar"])
_END = object()


class Pedido(BaseModel):
    pregunta: str = Field(..., min_length=3, max_length=2000)
    rondas: int = Field(2, ge=1, le=3)


def _sse(kind: str, data: Dict[str, Any]) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/investigar")
async def investigar(body: Pedido) -> StreamingResponse:
    from openjarvis.research.deep import research

    events: "queue.Queue[Any]" = queue.Queue()

    def work() -> None:
        try:
            report = research(
                body.pregunta,
                rounds=body.rondas,
                on_event=lambda kind, data: events.put((kind, data)),
            )
            events.put(
                (
                    "informe",
                    {
                        "markdown": report.markdown(),
                        "hallazgos": [
                            {
                                "texto": f.text,
                                "fuentes": f.sources,
                                "estado": f.status,
                                "contra": f.against,
                            }
                            for f in report.findings
                        ],
                        "fuentes": [
                            {
                                "id": s.id,
                                "titulo": s.title,
                                "url": s.url,
                                "sitio": s.site,
                                "leida": s.read,
                            }
                            for s in report.sources
                        ],
                        "stats": report.stats,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001 — said plainly in the stream
            events.put(("error", {"mensaje": f"No pude investigar: {exc}"}))
        finally:
            events.put(_END)

    threading.Thread(target=work, daemon=True, name="investigar").start()

    async def stream() -> AsyncIterator[str]:
        while True:
            item = await asyncio.to_thread(events.get)
            if item is _END:
                return
            kind, data = item
            yield _sse(kind, data)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/vista-previa")
def link_preview(url: str) -> Dict[str, Any]:
    """Title, description, picture and site of a public web page (research/preview.py)."""
    from fastapi import HTTPException

    from openjarvis.research import preview as P

    try:
        return P.preview(url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:  # noqa: BLE001 — the page did not answer: a plain link instead
        raise HTTPException(502, "La página no respondió.")



@router.get("/vista-previa/img/{name}")
def link_preview_image(name: str) -> Any:
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    from openjarvis.research import preview as P

    path = P.image_file(name)
    if path is None:
        raise HTTPException(404, "No hay imagen.")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


__all__ = ["router"]
