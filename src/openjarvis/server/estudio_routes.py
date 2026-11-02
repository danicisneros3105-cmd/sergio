"""The four studio programs over HTTP (``/v1/estudio``): one route each."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/estudio", tags=["estudio"])


class Clips(BaseModel):
    tema: str
    cuantas: int = 5


class Thumbs(BaseModel):
    archivo: str
    texto: str = ""
    titulo: str = ""
    acento: str = ""


class Titles(BaseModel):
    tema: str
    plataforma: str = "youtube"
    tendencias: List[str] = []


class Radar(BaseModel):
    nicho: str = ""
    pais: str = "EC"
    plataforma: str = "youtube"
    profundo: bool = False


class School(BaseModel):
    categoria: str = ""


@router.get("/escuela")
def school_status() -> Dict[str, Any]:
    from openjarvis.video_essay import escuela

    return escuela.status()


@router.post("/escuela")
def school_start(body: School) -> Dict[str, Any]:
    from openjarvis.video_essay import escuela

    refs = escuela.references()
    started = escuela.start([body.categoria] if body.categoria in refs else None)
    return {"empezado": started, **escuela.status()}


@router.post("/clips")
def clips(body: Clips) -> Dict[str, Any]:
    from openjarvis.estudio import clips_cine

    return clips_cine.buscar(body.tema, max(1, min(body.cuantas, 10)))


@router.post("/miniaturas")
def thumbs(body: Thumbs) -> Dict[str, Any]:
    from openjarvis.estudio import miniaturas

    try:
        return miniaturas.crear(
            body.archivo, body.texto, body.titulo, acento=body.acento
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/titulos")
def titles(body: Titles) -> Dict[str, Any]:
    from openjarvis.estudio import titulos

    return titulos.generar(body.tema, body.plataforma, tendencias=body.tendencias)


@router.post("/radar")
def radar(body: Radar) -> Dict[str, Any]:
    from openjarvis.estudio import radar as r

    return r.analizar(body.nicho, body.pais, body.plataforma, profundo=body.profundo)


__all__ = ["router"]
