"""HTTP API for the Faces page (camera in the browser → local recognition)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

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


def owner_name() -> str:
    """Whose assistant this is (Sergio calls them «señor»): SERGIO_OWNER_NAME,
    else phone.owner_name, else the person enrolled first."""
    import os

    name = os.environ.get("SERGIO_OWNER_NAME", "").strip()
    if not name:
        try:
            from openjarvis.tools.desktop_tools import _config_owner

            name = _config_owner()
        except Exception:  # noqa: BLE001
            name = ""
    if name:
        from openjarvis.faces.book import clean_name

        return clean_name(name)
    try:
        people = _get_book().people()
    except Exception:  # noqa: BLE001
        return ""
    first = min(people, key=lambda p: p.get("enrolled_at") or 0, default=None)
    return str(first["name"]) if first else ""


@router.get("/owner")
async def owner() -> dict[str, Any]:
    return {"owner": owner_name()}


@router.post("/identify")
async def identify(
    image: UploadFile = File(...), learn: bool = Form(False)
) -> dict[str, Any]:
    """Who is in a camera frame. *learn*: keep learning faces it is very sure
    of from the angles it lacks (the companion asks for it while it watches)."""
    data = await _read(image)
    try:
        matches = await asyncio.to_thread(_get_book().identify, data, learn=learn)
    except FaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise _missing_opencv() from exc
    boss = owner_name().lower()
    faces = []
    for m in matches:
        face = m.to_dict()
        face["owner"] = bool(m.name) and m.name.lower() == boss
        faces.append(face)
    return {"faces": faces, "owner": owner_name()}


@router.post("/scan")
async def scan(
    name: str = Form(...),
    consent: bool = Form(False),
    mesh: str = Form(""),
    images: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Face ID-style enrolment: frames of one person turning their head."""
    import json

    frames = [await _read(image) for image in images[:80]]
    try:
        mesh_data = json.loads(mesh) if mesh else None
    except ValueError:
        mesh_data = None
    try:
        out = await asyncio.to_thread(
            _get_book().scan, name, frames, consent=consent, mesh=mesh_data
        )
    except FaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise _missing_opencv() from exc
    return out


@router.get("/mesh/{name}")
async def mesh(name: str) -> dict[str, Any]:
    found = _get_book().mesh(name)
    if not found:
        raise HTTPException(status_code=404, detail=f"No 3D map for {name}")
    return found


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
        geo = (
            f"; sus 175 medidas faciales coinciden un {m.geometry * 100:.0f}%"
            if m.geometry is not None
            else ""
        )
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
        matches = await asyncio.to_thread(
            _get_book().identify_photo, data, _points(faces)
        )
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
        listed = ", ".join(
            f"{p['name']} {p['kin'] * 100:.0f}% ({p['words']})" for p in people[:3]
        )
        parts.append(f"{who}, parecido familiar con: {listed}.")
    parts.append(
        "Es un indicio por rasgos y proporciones de la cara, no una prueba: "
        "solo el ADN confirma un parentesco."
    )
    return " ".join(parts)


@router.post("/kinship")
async def kinship(
    image: UploadFile = File(...), faces: str = Form("")
) -> dict[str, Any]:
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


# -- Face ID (faceid.py): Apple's rules on a webcam ---------------------------

_gate: Any = None


def _get_gate() -> Any:
    global _gate
    if _gate is None:
        from openjarvis.faces.faceid import Gate

        _gate = Gate(_get_book()._root)
    return _gate


def _local_only(request: Request) -> None:
    """The passcode and unlock never travel beyond this computer: a request
    relayed by a tunnel (``sergio movil``) or proxy is refused, even though it
    reaches the server from 127.0.0.1."""
    from openjarvis.server.vision_routes import from_this_computer

    host = request.client.host if request.client else ""
    if host != "testclient" and not from_this_computer(request):
        raise HTTPException(status_code=403, detail="Face ID solo desde este equipo.")


def _owner_key() -> str:
    """The enrolled name of the owner (case-insensitive), or the only person."""
    people = [p["name"] for p in _get_book().people()]
    boss = owner_name().lower()
    found = next((n for n in people if n.lower() == boss), "")
    return found or (people[0] if len(people) == 1 else "")


@router.get("/faceid")
async def faceid_status(request: Request) -> dict[str, Any]:
    _local_only(request)
    return {**_get_gate().status(), "owner": _owner_key()}


@router.post("/faceid/passcode")
async def faceid_set_passcode(
    request: Request, code: str = Form(...), current: str = Form("")
) -> dict[str, Any]:
    _local_only(request)
    try:
        await asyncio.to_thread(_get_gate().set_passcode, code, current)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _get_gate().status()


@router.post("/faceid/passcode/check")
async def faceid_check_passcode(
    request: Request, code: str = Form(...)
) -> dict[str, Any]:
    _local_only(request)
    return await asyncio.to_thread(_get_gate().check_passcode, code)


@router.post("/faceid/lock")
async def faceid_lock(request: Request) -> dict[str, Any]:
    _local_only(request)
    _get_gate().lock_now()
    return _get_gate().status()


@router.post("/faceid/challenge")
async def faceid_challenge(request: Request) -> dict[str, Any]:
    _local_only(request)
    reason = _get_gate().passcode_reason()
    if reason:
        return {"passcode_required": True, "reason": reason}
    return _get_gate().challenge().to_dict()


@router.post("/faceid/unlock")
async def faceid_unlock(
    request: Request,
    nonce: str = Form(...),
    images: list[UploadFile] = File(...),
) -> dict[str, Any]:
    _local_only(request)
    from openjarvis.faces.faceid import unlock

    owner = _owner_key()
    if not owner:
        raise HTTPException(status_code=409, detail="Primero configure Face ID.")
    frames = [await _read(image) for image in images[:16]]
    try:
        return await asyncio.to_thread(
            unlock, _get_book(), _get_gate(), nonce, frames, owner
        )
    except ImportError as exc:
        raise _missing_opencv() from exc


@router.post("/pose")
async def pose(image: UploadFile = File(...)) -> dict[str, Any]:
    """Where the face points (for the Face ID ring while setting it up)."""
    from openjarvis.faces.faceid import read_frames

    data = await _read(image)
    try:
        frames = await asyncio.to_thread(read_frames, _get_book(), [data])
    except ImportError as exc:
        raise _missing_opencv() from exc
    if not frames:
        return {"face": False}
    f = frames[0]
    return {
        "face": True,
        "yaw": f.yaw,
        "pitch": f.pitch,
        "eyes_open": f.eyes_open,
        "faces": f.faces,
    }


@router.delete("/{name}")
async def forget(name: str) -> dict[str, Any]:
    if not _get_book().forget(name):
        raise HTTPException(status_code=404, detail=f"No enrolled person named {name}")
    return {"forgotten": name}


__all__ = [
    "describe_kinship",
    "describe_photo",
    "enroll",
    "faceid_challenge",
    "faceid_check_passcode",
    "faceid_lock",
    "faceid_set_passcode",
    "faceid_status",
    "faceid_unlock",
    "forget",
    "identify",
    "kinship",
    "list_people",
    "look",
    "mesh",
    "owner",
    "owner_name",
    "photo",
    "pose",
    "scan",
]
