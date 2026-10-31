"""Projects over HTTP: ``/v1/proyectos`` (pages/ProjectsPage.tsx).

* ``GET  /v1/proyectos``                         — every project
* ``POST /v1/proyectos``                         — a new one (nombre, instrucciones)
* ``GET|PATCH|DELETE /v1/proyectos/{id}``        — one project
* ``POST /v1/proyectos/{id}/archivos``           — add a file (multipart)
* ``DELETE /v1/proyectos/{id}/archivos/{name}``  — take one out
* ``GET  /v1/proyectos/{id}/contexto``           — what each of its chats starts with
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from openjarvis import proyectos as P

router = APIRouter(prefix="/v1/proyectos", tags=["proyectos"])


class NewProject(BaseModel):
    nombre: str
    instrucciones: str = ""


class ProjectChange(BaseModel):
    nombre: Optional[str] = None
    instrucciones: Optional[str] = None


def _fail(exc: P.ProjectError) -> HTTPException:
    code = 404 if "no existe" in str(exc) else 400
    return HTTPException(code, str(exc))


@router.get("")
def lista() -> Dict[str, Any]:
    return {"proyectos": P.all_projects()}


@router.post("")
def crear(body: NewProject) -> Dict[str, Any]:
    try:
        return P.create(body.nombre, body.instrucciones)
    except P.ProjectError as exc:
        raise _fail(exc) from exc


@router.get("/{pid}")
def uno(pid: str) -> Dict[str, Any]:
    try:
        return P.get(pid)
    except P.ProjectError as exc:
        raise _fail(exc) from exc


@router.patch("/{pid}")
def cambiar(pid: str, body: ProjectChange) -> Dict[str, Any]:
    try:
        return P.update(pid, **body.model_dump())
    except P.ProjectError as exc:
        raise _fail(exc) from exc


@router.delete("/{pid}")
def borrar(pid: str) -> Dict[str, Any]:
    try:
        P.delete(pid)
    except P.ProjectError as exc:
        raise _fail(exc) from exc
    return {"ok": True}


@router.post("/{pid}/archivos")
async def subir(pid: str, archivo: UploadFile = File(...)) -> Dict[str, Any]:
    data = await archivo.read(P.MAX_FILE + 1)
    try:
        return await asyncio.to_thread(P.add_file, pid, archivo.filename or "", data)
    except P.ProjectError as exc:
        raise _fail(exc) from exc


@router.delete("/{pid}/archivos/{name}")
def quitar(pid: str, name: str) -> Dict[str, Any]:
    try:
        return P.remove_file(pid, name)
    except P.ProjectError as exc:
        raise _fail(exc) from exc


@router.get("/{pid}/contexto")
async def contexto(pid: str) -> Dict[str, Any]:
    try:
        return {"contexto": await asyncio.to_thread(P.context, pid)}
    except P.ProjectError as exc:
        raise _fail(exc) from exc


__all__ = ["router"]
