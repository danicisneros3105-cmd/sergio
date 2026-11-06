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
* ``GET  /v1/pagos/estado``             — the owner's setup checklist
* ``POST /v1/pagos/pedido/{id}/devolver`` — the owner records a refund
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from openjarvis.pagos import referidos, service
from openjarvis.pagos.gateways import GatewayError

router = APIRouter(prefix="/v1/pagos", tags=["pagos"])
MAX_NOTICE = 256 * 1024  # a processor's notice is a few KB


def _base(request: Request) -> str:
    return os.environ.get("SERGIO_PUBLIC_URL", "").rstrip("/") or str(
        request.base_url
    ).rstrip("/")


def _payer(request: Request) -> Dict[str, Any]:
    """Who pays: an approved customer, or the owner (only the test charge)."""
    from openjarvis.server.accounts_routes import _me, is_local

    me = _me(request)
    if me and me.get("role") == "dueño":
        return {"id": me["id"], "owner": True}
    if not me and is_local(request):
        return {"id": "dueño", "owner": True}
    if not me:
        raise HTTPException(401, "Entre con su cuenta para pagar.")
    if me.get("role") != "aprobado":
        raise HTTPException(403, "Su cuenta todavía no está aprobada.")
    return {"id": me["id"], "owner": False}


@router.get("/metodos")
def metodos() -> Dict[str, Any]:
    return {"metodos": service.methods()}


@router.get("/precio")
def precio(plan: str, mult: int = 0) -> Dict[str, Any]:
    try:
        return service.price(plan, mult)
    except service.PaymentError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/referidos")
def referral_status(request: Request) -> Dict[str, Any]:
    if not referidos.enabled():
        return {"activo": False}
    me = _payer(request)
    return (
        {"activo": False}
        if me["owner"]
        else {"activo": True, **referidos.status(me["id"])}
    )


class ReferralBody(BaseModel):
    codigo: str


@router.post("/referidos")
def referral_link(body: ReferralBody, request: Request) -> Dict[str, Any]:
    me = _payer(request)
    if me["owner"] or not referidos.enabled():
        raise HTTPException(404, "Referidos no está activado.")
    if len(body.codigo) != 16 or not referidos.link(me["id"], body.codigo):
        raise HTTPException(400, "Código no válido o cuenta no elegible.")
    return {"activo": True, **referidos.status(me["id"])}


@router.post("/portal")
def portal(request: Request) -> Dict[str, str]:
    me = _payer(request)
    if me["owner"]:
        raise HTTPException(403, "La cuenta del dueño no tiene suscripción.")
    try:
        return {"url": service.billing_portal(me["id"], _base(request))}
    except service.PaymentError as exc:
        raise HTTPException(400, str(exc)) from exc


class CheckoutBody(BaseModel):
    plan: str
    mult: int = 0
    metodo: str


@router.post("/checkout")
def checkout(body: CheckoutBody, request: Request) -> Dict[str, Any]:
    me = _payer(request)
    try:
        return service.checkout(
            me["id"],
            body.plan,
            body.mult,
            body.metodo,
            _base(request),
            owner=me["owner"],
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
    if int(request.headers.get("content-length") or 0) > MAX_NOTICE:
        raise HTTPException(413, "Aviso demasiado grande.")
    body = await request.body()
    if len(body) > MAX_NOTICE:
        raise HTTPException(413, "Aviso demasiado grande.")
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


@router.get("/lanzamiento")
def lanzamiento(request: Request) -> Dict[str, Any]:
    """Ready to open to the public? What was checked and what only the owner can do."""
    from openjarvis.lanzamiento import revisar
    from openjarvis.server.accounts_routes import _owner

    _owner(request)
    return revisar()


@router.get("/economia")
def economia(request: Request) -> Dict[str, Any]:
    """What each plan leaves after fees and AI, worst and typical case. Owner only."""
    from openjarvis.pagos import economia as E
    from openjarvis.server.accounts_routes import _owner

    _owner(request)
    return E.report()


@router.get("/clientes")
def clientes(request: Request) -> Dict[str, Any]:
    """Each paying customer: price, real AI cost this month, margin; and the
    models each plan includes. Only the owner."""
    from openjarvis.pagos import clientes as C
    from openjarvis.server.accounts_routes import _owner

    _owner(request)
    return C.report()


@router.get("/estado")
def estado(request: Request, revisar: bool = False) -> Dict[str, Any]:
    """What is ready to charge and what is missing (``revisar`` asks each
    processor whether its keys work)."""
    from openjarvis.server.accounts_routes import _owner

    _owner(request)
    return service.readiness(_base(request), online=revisar)


@router.post("/pedido/{pedido}/devolver")
def devolver(pedido: str, request: Request) -> Dict[str, Any]:
    """After refunding in the processor's dashboard, the owner records it."""
    from openjarvis.server.accounts_routes import _owner

    _owner(request)
    try:
        return service.revoke(pedido)
    except service.PaymentError as exc:
        raise HTTPException(400, str(exc)) from exc


__all__ = ["router"]
