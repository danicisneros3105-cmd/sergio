"""HTTP API for the Faces page (camera in the browser → local recognition)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from openjarvis.faces.book import MAX_IMAGE_BYTES, FaceBook, FaceError

router = APIRouter(prefix="/v1/faces", tags=["faces"])

_book: FaceBook | None = None


def _get_book() -> FaceBook:
    global _book
    if _book is None:
        _book = FaceBook()
    return _book


async def _read(image: UploadFile) -> bytes:
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image larger than 10 MB")
    return data


def _missing_opencv() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Face recognition is not installed (uv sync --extra faces).",
    )


@router.get("")
async def list_people() -> dict[str, Any]:
    return {"people": _get_book().people()}


@router.post("/identify")
async def identify(image: UploadFile = File(...)) -> dict[str, Any]:
    data = await _read(image)
    try:
        matches = await asyncio.to_thread(_get_book().identify, data)
    except FaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise _missing_opencv() from exc
    return {"faces": [m.to_dict() for m in matches]}


@router.post("/enroll")
async def enroll(
    name: str = Form(...),
    consent: bool = Form(False),
    image: UploadFile = File(...),
) -> dict[str, Any]:
    data = await _read(image)
    try:
        samples = await asyncio.to_thread(
            _get_book().enroll, name, data, consent=consent
        )
    except FaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise _missing_opencv() from exc
    return {"name": name.strip(), "samples": samples}


def _look(data: bytes, question: str) -> dict[str, Any]:
    from openjarvis.tools.vision_look import ask_vision

    people: list[str] = []
    try:
        people = sorted({m.name for m in _get_book().identify(data) if m.name})
    except Exception:  # noqa: BLE001 — recognition is a bonus here
        pass
    answer = ask_vision(data, question)
    if people:
        answer = f"Veo a {', '.join(people)}. {answer}"
    return {"answer": answer, "people": people}


@router.post("/look")
async def look(
    question: str = Form("¿Qué ves?"),
    image: UploadFile = File(...),
) -> dict[str, Any]:
    """The companion's eyes: answer a question about a webcam photo."""
    data = await _read(image)
    try:
        return await asyncio.to_thread(_look, data, question)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/{name}")
async def forget(name: str) -> dict[str, Any]:
    if not _get_book().forget(name):
        raise HTTPException(status_code=404, detail=f"No enrolled person named {name}")
    return {"forgotten": name}
