"""Sergio Pagos: ``/v1/pagos``.

* ``GET  /v1/pagos/metodos``            — the ways to pay that are switched on
* ``GET  /v1/pagos/precio``             — what a plan costs (for the checkout page)
* ``POST /v1/pagos/checkout``           — open an order and the processor's page
* ``GET  /v1/pagos/vuelta/{metodo}``    — the customer comes back (open: the
  order id and the processor's own id must match)
* ``POST /v1/pagos/aviso/{metodo}``     — the processor's notice (open: each
  notice's signature is checked before anything happens)
* ``GET  /v1/pagos/pedido/{id}``        — how an order is doing
* ``GET  /v1/pagos/resumen``            — the owner's ledger
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from openjarvis.pagos import service
from openjarvis.pagos.gateways import GatewayError

router = APIRouter(prefix="/v1/pagos", tags=["pagos"])


def _base(request: Request) -> str:
    return os.environ.get("SERGIO_PUBLIC_URL", "").rstrip("/") or str(
        request.base_url
    ).rstrip("/")


def _customer(request: Request) -> Dict[str, Any]:
    from openjarvis.server.accounts_routes import _me

    me = _me(request)
    if not me:
        raise HTTPException(401, "Entre con su cuenta para pagar.")
    if me.get("role") == "dueño":
        raise HTTPException(400, "La cuenta del dueño no paga planes.")
    if me.get("role") != "aprobado":
        raise HTTPException(403, "Su cuenta todavía no está aprobada.")
    return me


@router.get("/metodos")
def metodos() -> Dict[str, Any]:
    return {"metodos": service.methods()}


@router.get("/precio")
def precio(plan: str, mult: int = 0) -> Dict[str, Any]:
    try:
        return service.price(plan, mult)
    except service.PaymentError as exc:
        raise HTTPException(400, str(exc)) from exc


class CheckoutBody(BaseModel):
    plan: str
    mult: int = 0
    metodo: str


@router.post("/checkout")
def checkout(body: CheckoutBody, request: Request) -> Dict[str, Any]:
    me = _customer(request)
    try:
        return service.checkout(
            me["id"], body.plan, body.mult, body.metodo, _base(request)
        )
    except service.PaymentError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/vuelta/{metodo}")
def vuelta(metodo: str, pedido: str, request: Request) -> RedirectResponse:
    out = service.come_back(metodo, pedido, dict(request.query_params))
    state = "listo" if out.get("ok") else "problema"
    return RedirectResponse(f"/pagar/{state}?pedido={pedido}", status_code=303)


@router.post("/aviso/{metodo}")
async def aviso(metodo: str, request: Request) -> Dict[str, Any]:
    body = await request.body()
    try:
        done = service.notice(metodo, dict(request.headers), body)
    except service.PaymentError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (GatewayError, ValueError) as exc:
        raise HTTPException(400, "Aviso rechazado.") from exc
    return {"ok": True, "aplicados": len(done)}


@router.get("/pedido/{pedido}")
def pedido(pedido: str, request: Request) -> Dict[str, Any]:
    from openjarvis.server.accounts_routes import _me, is_local

    me = _me(request)
    owner = is_local(request) or (me and me.get("role") == "dueño")
    out = service.order(pedido, "" if owner else (me or {}).get("id", "-"))
    if out is None:
        raise HTTPException(404, "No encuentro ese pedido.")
    return out


@router.get("/resumen")
def resumen(request: Request) -> Dict[str, Any]:
    from openjarvis.server.accounts_routes import _owner

    _owner(request)
    return service.summary()


__all__ = ["router"]
