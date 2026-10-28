"""Automation for the owner: channels, opportunities and trading (/v1/automatiza).

Only the owner reaches these (the customer gate denies by default and they are
not in its list): connect YouTube and Instagram, schedule channels that post
on their own, read and approve comment replies, the client/job tracker, and
trading settings, backtests and its journal. The Instagram file link
(``/archivo/{token}``) is the one open path: a one-time random token.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

router = APIRouter(prefix="/v1/automatiza", tags=["automatiza"])


def _owner(request: Request) -> None:
    from openjarvis.server.accounts_routes import _owner as owner

    owner(request)


def _base(request: Request) -> str:
    return os.environ.get("SERGIO_PUBLIC_URL", "").rstrip("/") or str(
        request.base_url
    ).rstrip("/")


@router.get("")
def estado(request: Request) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import canales, oportunidades, trading
    from openjarvis.video_essay import schedule, skillbook

    return {
        "canales": canales.estado(),
        "programados": schedule.load(),
        "oportunidades": {
            "perfil": oportunidades.profile(),
            "total": len(oportunidades.items()),
        },
        "trading": trading.estado(),
        "skills": skillbook.counts(),
    }


# -- channels -------------------------------------------------------------------------------


@router.get("/youtube/conectar")
def youtube_conectar(request: Request) -> Dict[str, str]:
    _owner(request)
    from openjarvis.automatiza import canales

    try:
        return canales.youtube_connect_url(
            f"{_base(request)}/v1/automatiza/youtube/vuelta"
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/youtube/vuelta", response_class=HTMLResponse)
def youtube_vuelta(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> HTMLResponse:
    from openjarvis.automatiza import canales

    if error or not code:
        return HTMLResponse(
            "<p>No se conectó YouTube. Puede cerrar esta ventana.</p>", status_code=400
        )
    try:
        got = canales.youtube_finish(
            code, state, f"{_base(request)}/v1/automatiza/youtube/vuelta"
        )
    except RuntimeError as exc:
        return HTMLResponse(f"<p>{str(exc)[:200]}</p>", status_code=400)
    name = (got.get("canal") or {}).get("nombre") or "su canal"
    return HTMLResponse(
        f"<p>YouTube conectado: {name}. Ya puede cerrar esta ventana.</p>"
    )


class Instagram(BaseModel):
    user_id: str
    token: str


@router.post("/instagram")
def instagram(request: Request, body: Instagram) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import canales

    try:
        return canales.instagram_connect(body.user_id.strip(), body.token.strip())
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/canal/{name}")
def desconectar(request: Request, name: str) -> Dict[str, bool]:
    _owner(request)
    from openjarvis.automatiza import canales

    if name not in ("youtube", "instagram"):
        raise HTTPException(404, "canal desconocido")
    return {"ok": canales.forget(name)}


@router.get("/archivo/{token}")
def archivo(token: str) -> FileResponse:
    from openjarvis.automatiza import canales

    path = canales.take_shared(token)
    if path is None or not path.exists():
        raise HTTPException(404, "enlace usado o vencido")
    return FileResponse(path, media_type="video/mp4")


class Canal(BaseModel):
    idea: str
    por_dia: int = 3
    formato: str = "9:16"
    segundos: int = 45
    modo: str = "basic"
    publicar_en: List[str] = ["youtube"]
    auto: bool = True


@router.post("/canal")
def canal(request: Request, body: Canal) -> Dict[str, Any]:
    """A channel that makes N videos a day and posts them (shorts by default)."""
    _owner(request)
    from openjarvis.video_essay import schedule

    per_day = max(1, min(6, body.por_dia))
    every = min(schedule.EVERY_HOURS, key=lambda h: abs(h - 24 / per_day))
    try:
        return schedule.add(
            body.idea, every_hours=every, mode=body.modo, aspect=body.formato, seconds=body.segundos,
            publish_to=body.publicar_en, auto=body.auto,
        )  # fmt: skip
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/respuestas")
def respuestas(request: Request) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import canales

    return {"pendientes": canales.pending_replies()}


@router.post("/respuestas/redactar")
def redactar(request: Request) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import canales

    try:
        return {"nuevas": canales.draft_replies(canales.youtube_comments())}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)[:200]) from exc


class Ids(BaseModel):
    ids: List[str]


@router.post("/respuestas/enviar")
def enviar(request: Request, body: Ids) -> Dict[str, int]:
    """Send the replies the owner approved (his tap is the approval)."""
    _owner(request)
    from openjarvis.automatiza import canales

    return {"enviadas": canales.send_replies(body.ids)}


# -- opportunities --------------------------------------------------------------------------


class Perfil(BaseModel):
    busco: str = "ambos"
    habilidades: List[str] = []
    servicio: str = ""
    idiomas: List[str] = ["español"]
    lugar: str = ""
    remoto: bool = True
    tarifa: str = ""
    sobre_mi: str = ""


@router.put("/oportunidades/perfil")
def perfil(request: Request, body: Perfil) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import oportunidades

    return oportunidades.save_profile(body.model_dump())


@router.get("/oportunidades")
def oportunidades_lista(request: Request) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import oportunidades

    return {"perfil": oportunidades.profile(), "lista": oportunidades.items()[:200]}


@router.post("/oportunidades/buscar")
def buscar(request: Request) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import oportunidades

    try:
        return oportunidades.hunt()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class Estado(BaseModel):
    estado: str


@router.put("/oportunidades/{item_id}")
def marcar(request: Request, item_id: str, body: Estado) -> Dict[str, bool]:
    _owner(request)
    from openjarvis.automatiza import oportunidades

    try:
        return {"ok": oportunidades.set_state(item_id, body.estado)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# -- trading --------------------------------------------------------------------------------


class Ajustes(BaseModel):
    activo: Optional[bool] = None
    real: Optional[bool] = None
    estrategia: Optional[str] = None
    simbolos: Optional[List[str]] = None
    limites: Optional[Dict[str, float]] = None


@router.put("/trading")
def trading_ajustes(request: Request, body: Ajustes) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import trading

    trading.save_settings({k: v for k, v in body.model_dump().items() if v is not None})
    return trading.estado()


class Prueba(BaseModel):
    simbolo: str = "SPY"
    estrategia: str = "cruce_medias"
    dias: int = 1500


@router.post("/trading/prueba")
def trading_prueba(request: Request, body: Prueba) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import trading

    try:
        broker = trading.Broker(real=False)
        closes = broker.closes(
            body.simbolo.upper()[:10], days=max(300, min(5000, body.dias))
        )
        return trading.backtest(closes, body.estrategia)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/trading/detener")
def trading_detener(request: Request) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import trading

    trading.stop(True)
    return trading.estado()


@router.post("/trading/reanudar")
def trading_reanudar(request: Request) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import trading

    trading.stop(False)
    return trading.estado()


# -- the conversation and the trends ----------------------------------------------------------


class Charla(BaseModel):
    texto: str
    pais: str = "EC"


@router.post("/charla")
def charla(request: Request, body: Charla) -> Dict[str, Any]:
    """What the owner asked, understood: a reply and cards with a button for
    anything that changes something (nothing runs without that tap)."""
    _owner(request)
    from openjarvis import estabilidad
    from openjarvis.automatiza import canales, oportunidades, trading
    from openjarvis.automatiza import charla as talk

    def ask(prompt: str, **_: Any) -> str:
        from openjarvis.creator import llm

        return llm.ask(prompt)

    return talk.answer(
        body.texto,
        ask=ask,
        pais=body.pais,
        readers={
            "estado": lambda: estado(request),
            "tope": canales.per_day,
            "oportunidades": oportunidades.items,
            "respuestas": lambda: len(canales.pending_replies()),
            "trading": trading.estado,
            "estabilidad": estabilidad.checks,
        },
    )


@router.get("/tendencias")
def tendencias_leer(
    request: Request, pais: str = "EC", nicho: str = ""
) -> Dict[str, Any]:
    _owner(request)
    from openjarvis.automatiza import tendencias

    return tendencias.read(pais, nicho)


class Idea(BaseModel):
    titulo: str
    gancho: str = ""
    genero: str = ""
    formato: str = "short"
    por_que: str = ""
    senal: Dict[str, Any] = {}


@router.post("/tendencias/video")
def tendencias_video(request: Request, body: Idea) -> Dict[str, Any]:
    """«Hacer este video»: the idea goes to the video studio, with the same
    limits as any other video (one at a time, the daily cap)."""
    _owner(request)
    from openjarvis.automatiza import charla as talk
    from openjarvis.video_essay import job as jobs

    order = talk.order(body.model_dump())
    busy, why = jobs.guard(order)
    if busy is not None:
        raise HTTPException(409, {"en curso": "Ya hay un video en camino; este espera su turno.",
                                  "tope diario": "Hoy ya se hizo el máximo de videos.",
                                  "repetido": "Ese video ya está hecho."}.get(why, why))  # fmt: skip
    made = jobs.start(order)
    return {"ok": True, "trabajo": made.id, "titulo": body.titulo}


# -- stability ----------------------------------------------------------------------------------


@router.get("/estabilidad")
def estabilidad_estado(request: Request) -> Dict[str, Any]:
    _owner(request)
    from openjarvis import estabilidad

    items = estabilidad.checks()
    return {"resumen": estabilidad.summary(items), "chequeos": items}


@router.post("/estabilidad/reparar")
def estabilidad_reparar(request: Request) -> Dict[str, Any]:
    _owner(request)
    from openjarvis import estabilidad

    return estabilidad.repair()


# -- the background loop ----------------------------------------------------------------------

_started = False


def start_loop(interval: float = 300.0) -> None:
    """Every 5 minutes: trading once an hour while the market is open, the
    opportunities once a day (09:00 local), each in its own try."""
    global _started
    if _started:
        return
    _started = True

    def run() -> None:
        import logging

        log = logging.getLogger(__name__)
        last_trade, last_hunt, last_repair = 0.0, "", 0.0
        while True:
            time.sleep(interval)
            try:
                from openjarvis.automatiza import trading

                if trading.settings().activo and time.time() - last_trade > 3600:
                    trading.run_once()
                    last_trade = time.time()
            except Exception:  # noqa: BLE001 — the loop never dies
                log.exception("trading")
            try:  # once a day: free disk, tighten permissions
                from openjarvis import estabilidad

                if (
                    time.localtime().tm_hour == 4
                    and time.time() - last_repair > 20 * 3600
                ):
                    estabilidad.repair()
                    last_repair = time.time()
            except Exception:  # noqa: BLE001
                log.exception("estabilidad")
            try:
                from openjarvis.automatiza import oportunidades

                today = time.strftime("%Y-%m-%d")
                if (
                    oportunidades.profile()
                    and last_hunt != today
                    and time.localtime().tm_hour >= 9
                ):
                    oportunidades.hunt()
                    last_hunt = today
            except Exception:  # noqa: BLE001
                log.exception("oportunidades")

    threading.Thread(target=run, name="automatiza", daemon=True).start()


__all__ = ["router", "start_loop"]
