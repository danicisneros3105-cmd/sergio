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


def _points(faces: str) -> list[dict] | None:
    """The companion's face-mesh points (JSON), when it measured them."""
    import json

    try:
        data = json.loads(faces) if faces else None
    except ValueError:
        return None
    return data if isinstance(data, list) else None


@router.post("/enroll")
async def enroll(
    name: str = Form(...),
    consent: bool = Form(False),
    faces: str = Form(""),
    image: UploadFile = File(...),
) -> dict[str, Any]:
    data = await _read(image)
    try:
        samples = await asyncio.to_thread(
            _get_book().enroll, name, data, consent=consent, faces=_points(faces)
        )
    except FaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise _missing_opencv() from exc
    from openjarvis.faces.book import clean_name

    return {"name": clean_name(name), "samples": samples}


def describe_photo(matches: list[Any]) -> str:
    """Spanish summary of who is in a photo (for Sergio to say)."""
    if not matches:
        return "No encuentro caras en la foto."
    parts = []
    for i, m in enumerate(matches, 1):
        who = f"Cara {i}" if len(matches) > 1 else "La cara"
        geo = f"; sus 175 medidas faciales coinciden un {m.geometry * 100:.0f}%" if m.geometry is not None else ""
        if m.name:
            parts.append(f"{who}: {m.name} (similitud {m.score * 100:.0f}%{geo}).")
        elif m.quality != "ok":
            parts.append(f"{who}: demasiado {m.quality} para reconocerla.")
        elif m.candidates and m.candidates[0][1] >= 0.30:
            name, score = m.candidates[0]
            parts.append(
                f"{who}: no estoy seguro; se parece a {name} ({score * 100:.0f}%{geo}), "
                "pero no lo bastante para afirmarlo."
            )
        else:
            parts.append(f"{who}: no la conozco.")
    return " ".join(parts)


@router.post("/photo")
async def photo(image: UploadFile = File(...), faces: str = Form("")) -> dict[str, Any]:
    """Who is in a photo — also old, faded or scanned ones."""
    data = await _read(image)
    try:
        matches = await asyncio.to_thread(_get_book().identify_photo, data, _points(faces))
    except FaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise _missing_opencv() from exc
    return {"faces": [m.to_dict() for m in matches], "text": describe_photo(matches)}


def describe_kinship(faces: list[dict[str, Any]]) -> str:
    if not faces:
        return "No encuentro caras en la foto."
    parts = []
    for i, face in enumerate(faces, 1):
        people = face["people"]
        who = f"Cara {i}" if len(faces) > 1 else "Esa cara"
        if not people:
            parts.append(f"{who}: no tengo a nadie registrado para comparar.")
            continue
        top = people[0]
        if top["same_person"]:
            parts.append(f"{who} es {top['name']} (no un pariente).")
            continue
        listed = ", ".join(f"{p['name']} {p['kin'] * 100:.0f}% ({p['words']})" for p in people[:3])
        parts.append(f"{who}, parecido familiar con: {listed}.")
    parts.append(
        "Es un indicio por rasgos y proporciones de la cara, no una prueba: "
        "solo el ADN confirma un parentesco."
    )
    return " ".join(parts)


@router.post("/kinship")
async def kinship(image: UploadFile = File(...), faces: str = Form("")) -> dict[str, Any]:
    """Family resemblance of the faces in a photo with the enrolled people."""
    data = await _read(image)
    try:
        found = await asyncio.to_thread(_get_book().kinship, data, _points(faces))
    except FaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise _missing_opencv() from exc
    return {"faces": found, "text": describe_kinship(found)}


def _look(data: bytes, question: str) -> dict[str, Any]:
    from openjarvis.tools.vision_look import ask_vision

    people: list[str] = []
    strangers = 0
    try:
        found = _get_book().identify(data)
        people = sorted({m.name for m in found if m.name})
        strangers = sum(1 for m in found if not m.name)
    except Exception:  # noqa: BLE001 — recognition is a bonus here
        pass
    hint = ""
    if people or strangers:
        known = ", ".join(people)
        unknown = (
            "una persona que no conozco"
            if strangers == 1
            else f"{strangers} personas que no conozco"
        )
        who = " y ".join(p for p in (known, unknown if strangers else "") if p)
        hint = (
            f"(Reconocimiento facial: {who}. Usa estos nombres solo para esas "
            "caras y no inventes nombres para las demás.)\n"
        )
    answer = ask_vision(data, hint + question)
    return {"answer": answer, "people": people, "strangers": strangers}


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
