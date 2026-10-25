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


__all__ = ["router"]
