"""Sign in and sign up (see :mod:`openjarvis.accounts`).

* ``GET  /v1/cuentas/estado``                 — what is available, and who is signed in
* ``POST /v1/cuentas/registro``               — email + password (a code confirms the email)
* ``POST /v1/cuentas/verificar``              — the emailed code
* ``POST /v1/cuentas/entrar``                 — email + password
* ``POST /v1/cuentas/telefono/codigo``        — send an SMS code
* ``POST /v1/cuentas/telefono/entrar``        — sign in (or up) with the SMS code
* ``GET  /v1/cuentas/oauth/{p}/inicio``       — Google / Microsoft / Apple
* ``GET|POST /v1/cuentas/oauth/{p}/vuelta``   — the provider sends the person back
* ``POST /v1/cuentas/llave/opciones-registro``, ``/llave/registrar`` — add this
  device's face, finger or PIN (a passkey) to the signed-in account
* ``POST /v1/cuentas/llave/opciones``, ``/llave/entrar`` — sign in with it
* ``GET /v1/cuentas/llave/lista``, ``DELETE /v1/cuentas/llave/{id}`` — the account's passkeys
* ``POST /v1/cuentas/salir``                  — close this session
* ``GET  /v1/cuentas/lista``, ``POST /v1/cuentas/{id}/rol``, ``DELETE /v1/cuentas/{id}``
  — the owner's view: approve, block or remove accounts

These routes are reachable without the API key (that is how one signs in);
each one checks what it needs. The first account made on the computer itself
is the owner's; every other one waits for the owner's approval.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/cuentas", tags=["cuentas"])

ROLES_IN = ("dueño", "aprobado")  # roles whose sessions open Sergio
RATE = 10  # attempts per minute and address
_hits: Dict[str, Deque[float]] = defaultdict(deque)
_FORWARDED = (
    "x-forwarded-for",
    "forwarded",
    "x-real-ip",
    "cf-connecting-ip",
    "ngrok-trace-id",
)


def _store():
    from openjarvis.accounts import get_store

    return get_store()


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def is_local(request: Request) -> bool:
    """The computer itself (a tunnel's forwarded request is not)."""
    if any(h in request.headers for h in _FORWARDED):
        return False
    return _ip(request) in ("127.0.0.1", "::1", "localhost", "testclient")


def _limit(request: Request) -> None:
    q = _hits[_ip(request)]
    now = time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE:
        raise HTTPException(429, "Demasiados intentos. Espere un minuto.")
    q.append(now)


def _bearer(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token if scheme.lower() == "bearer" else ""


def _me(request: Request) -> Optional[Dict[str, Any]]:
    return _store().session_user(_bearer(request))


def _owner(request: Request) -> None:
    me = _me(request)
    if not (is_local(request) or (me and me["role"] == "dueño")):
        raise HTTPException(403, "Solo el dueño puede hacer esto.")


def _first_local(request: Request) -> bool:
    return _store().count() == 0 and is_local(request)


def _signed_in(user: Dict[str, Any], device: str) -> Dict[str, Any]:
    from openjarvis.accounts.store import public

    if user["role"] not in ROLES_IN:
        return {
            "status": "pendiente" if user["role"] == "pendiente" else "bloqueada",
            "message": "Su cuenta espera la aprobación del dueño de este Sergio."
            if user["role"] == "pendiente"
            else "Esta cuenta está bloqueada.",
        }
    # Every AI configured by itself (accounts/autoconfig.py): the owner's own
    # OpenRouter key from the management key, a customer's sub-key, and the
    # list of models; all in the background, never blocking the sign-in.
    from openjarvis.accounts import autoconfig

    autoconfig.in_background(user)
    return {
        "status": "dentro",
        "token": _store().open_session(user["id"], device),
        "user": public(user),
    }


def _guard(
    email: str = "",
    phone: str = "",
    device: str = "",
    request: Optional[Request] = None,
) -> Dict[str, Any]:
    from openjarvis.accounts import fraud

    verdict = fraud.check(
        _store(),
        email=email,
        phone=phone,
        device=device,
        ip=_ip(request) if request else "",
    )
    if verdict["action"] == "block":
        raise HTTPException(
            403, "No se puede crear la cuenta: " + ", ".join(verdict["reasons"]) + "."
        )
    return verdict


class Register(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)
    name: str = Field("", max_length=80)
    device: str = Field("", max_length=64)


class Verify(BaseModel):
    email: str = Field(..., max_length=254)
    code: str = Field(..., max_length=12)
    device: str = Field("", max_length=64)


class Login(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)
    device: str = Field("", max_length=64)


class PhoneStart(BaseModel):
    phone: str = Field(..., max_length=24)
    device: str = Field("", max_length=64)


class PhoneLogin(PhoneStart):
    code: str = Field(..., max_length=12)


class Role(BaseModel):
    role: str = Field(..., pattern="^(aprobado|pendiente|bloqueado)$")


@router.get("/estado")
def estado(request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import autoconfig, oauth, senders
    from openjarvis.accounts import email as mail
    from openjarvis.accounts.store import public

    me = _me(request)
    return {
        "accounts": _store().count(),
        "providers": oauth.available(),
        "sms": senders.sms_ready(),
        "email_codes": senders.smtp_ready(),
        "secure_only": mail.secure_only(),
        "local": is_local(request),
        "me": public(me) if me else None,
        "ia": autoconfig.ready(),
    }


@router.post("/registro")
def registro(body: Register, request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import email as mail
    from openjarvis.accounts import security, senders

    _limit(request)
    email = body.email.strip()
    if not mail.valid(email):
        raise HTTPException(400, "Ese correo no parece válido.")
    problem = security.password_problem(body.password, email)
    if problem:
        raise HTTPException(400, problem)
    verdict = _guard(email=email, device=body.device, request=request)
    first = _first_local(request)
    user = _store().create(
        email=email, canonical=mail.canonical(email), name=body.name.strip(), password=body.password,
        role="dueño" if first else "pendiente",
        email_ok=first,
    )  # fmt: skip
    _store().note_signup(user["id"], body.device, verdict["network"])
    if first:
        return _signed_in(user, body.device)
    if senders.smtp_ready():
        try:
            senders.send_email_code(
                email, _store().put_code(mail.canonical(email), "correo")
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                503, "No pude enviar el código. Inténtelo en un momento."
            ) from exc
        return {"status": "codigo", "message": "Le enviamos un código a su correo."}
    return {
        "status": "pendiente",
        "message": "Cuenta creada: espera la aprobación del dueño.",
    }


@router.post("/verificar")
def verificar(body: Verify, request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import email as mail

    _limit(request)
    canon = mail.canonical(body.email)
    user = _store().find(canonical=canon)
    if not user or not _store().check_code(canon, body.code, "correo"):
        raise HTTPException(400, "El código no es correcto o caducó.")
    _store().set(user["id"], email_ok=1)
    return _signed_in(_store().get(user["id"]) or user, body.device)


@router.post("/entrar")
def entrar(body: Login, request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import email as mail
    from openjarvis.accounts import security

    _limit(request)
    user = _store().find(canonical=mail.canonical(body.email))
    wrong = HTTPException(401, "Correo o contraseña incorrectos.")
    if not user or not user["password"]:
        security.hash_password(body.password)  # same time either way
        raise wrong
    wait = _store().locked(user)
    if wait:
        raise HTTPException(
            429, f"Demasiados intentos. Espere {int(wait // 60) + 1} minutos."
        )
    if not security.check_password(body.password, user["password"]):
        _store().failed(user)
        raise wrong
    if not user["email_ok"]:
        return {
            "status": "codigo",
            "message": "Confirme su correo con el código que le enviamos.",
        }
    return _signed_in(user, body.device)


@router.post("/telefono/codigo")
def telefono_codigo(body: PhoneStart, request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import senders

    _limit(request)
    number = senders.phone(body.phone)
    if not number:
        raise HTTPException(
            400, "Escriba el número con el código del país, p. ej. +593 99 123 4567."
        )
    if not senders.sms_ready():
        raise HTTPException(503, "Los SMS no están configurados en este Sergio.")
    if not _store().find(phone=number):
        _guard(phone=number, device=body.device, request=request)
    try:
        senders.send_sms_code(number)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            503, "No pude enviar el SMS. Inténtelo en un momento."
        ) from exc
    return {"status": "codigo", "message": "Le enviamos un código por SMS."}


@router.post("/telefono/entrar")
def telefono_entrar(body: PhoneLogin, request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import fraud, senders

    _limit(request)
    number = senders.phone(body.phone)
    if not number or not senders.check_sms_code(number, body.code):
        raise HTTPException(400, "El código no es correcto o caducó.")
    user = _store().find(phone=number)
    if user is None:
        verdict = fraud.check(
            _store(), phone=number, device=body.device, ip=_ip(request)
        )
        if verdict["action"] == "block":
            raise HTTPException(
                403,
                "No se puede crear la cuenta: " + ", ".join(verdict["reasons"]) + ".",
            )
        first = _first_local(request)
        user = _store().create(phone=number, role="dueño" if first else "pendiente")
        _store().set(user["id"], phone_ok=1)
        _store().note_signup(user["id"], body.device, verdict["network"])
    return _signed_in(_store().get(user["id"]) or user, body.device)


def _redirect_uri(request: Request, key: str) -> str:
    import os

    base = os.environ.get("SERGIO_PUBLIC_URL", "").rstrip("/") or str(
        request.base_url
    ).rstrip("/")
    return f"{base}/v1/cuentas/oauth/{key}/vuelta"


@router.get("/oauth/{key}/inicio")
def oauth_inicio(key: str, request: Request, device: str = "") -> Dict[str, Any]:
    from openjarvis.accounts import oauth

    if key not in oauth.PROVIDERS:
        raise HTTPException(404, "Proveedor desconocido.")
    try:
        return {"url": oauth.start(key, _redirect_uri(request, key), device)}
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


async def _oauth_back(key: str, request: Request) -> RedirectResponse:
    from openjarvis.accounts import email as mail
    from openjarvis.accounts import fraud, oauth

    params = dict(request.query_params)
    if request.method == "POST":
        params.update({k: str(v) for k, v in (await request.form()).items()})
    try:
        claims = oauth.finish(key, params.get("code", ""), params.get("state", ""))
        store = _store()
        user = store.find(provider=key, subject=claims["subject"])
        if user is None and claims["email_ok"]:
            user = store.find(canonical=mail.canonical(claims["email"]))
        if user is None:
            verdict = fraud.check(
                store, email=claims["email"], device=claims["device"], ip=_ip(request)
            )
            if verdict["action"] == "block":
                raise ValueError(
                    "No se puede crear la cuenta: "
                    + ", ".join(verdict["reasons"])
                    + "."
                )
            first = _first_local(request)
            user = store.create(
                email=claims["email"], canonical=mail.canonical(claims["email"]) if claims["email"] else "",
                name=claims["name"], provider=key, subject=claims["subject"],
                role="dueño" if first else "pendiente", email_ok=claims["email_ok"],
            )  # fmt: skip
            store.note_signup(user["id"], claims["device"], verdict["network"])
        out = _signed_in(user, claims["device"])
    except Exception as exc:  # noqa: BLE001 — the page shows why
        return RedirectResponse(
            f"/entrar#error={quote(str(exc)[:200])}", status_code=303
        )
    if out.get("token"):
        return RedirectResponse(f"/entrar#token={out['token']}", status_code=303)
    return RedirectResponse(f"/entrar#estado={quote(out['status'])}", status_code=303)


@router.get("/oauth/{key}/vuelta")
async def oauth_vuelta_get(key: str, request: Request) -> RedirectResponse:
    return await _oauth_back(key, request)


@router.post("/oauth/{key}/vuelta")
async def oauth_vuelta_post(key: str, request: Request) -> RedirectResponse:
    return await _oauth_back(key, request)


# -- passkeys: the device's own Face ID, Touch ID or Windows Hello ------------------
class KeyRegister(BaseModel):
    clientDataJSON: str = Field(..., max_length=4096)
    attestationObject: str = Field(..., max_length=16384)
    name: str = Field("", max_length=60)


class KeyLogin(BaseModel):
    id: str = Field(..., max_length=1024)
    clientDataJSON: str = Field(..., max_length=4096)
    authenticatorData: str = Field(..., max_length=4096)
    signature: str = Field(..., max_length=2048)
    device: str = Field("", max_length=64)


def _site(request: Request) -> tuple[str, str]:
    """(origin, rp id) of this request, only for this server's own address."""
    from openjarvis.accounts.passkeys import rp_from_origin

    origin = request.headers.get("origin", "")
    rp = rp_from_origin(origin, request.headers.get("host", ""))
    if not rp:
        raise HTTPException(
            400,
            "La cara del dispositivo funciona en https o en este equipo (localhost).",
        )
    return origin, rp


def _account_for_keys(request: Request) -> Dict[str, Any]:
    me = _me(request)
    if me and me["role"] in ROLES_IN:
        return me
    if is_local(request):  # the owner on the computer itself, with the API key
        owner = next((u for u in _store().users() if u["role"] == "dueño"), None)
        if owner:
            return owner
    raise HTTPException(401, "Entre primero en su cuenta.")


@router.post("/llave/opciones-registro")
def llave_opciones_registro(request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import passkeys

    _limit(request)
    _, rp = _site(request)
    user = _account_for_keys(request)
    return {
        "challenge": passkeys.new_challenge("registro", user["id"]),
        "rp": {"id": rp, "name": "Sergio"},
        "user": {
            "id": passkeys.b64u(user["id"].encode()),
            "name": user.get("email") or user.get("phone") or user["id"],
            "displayName": user.get("name") or user.get("email") or "Sergio",
        },
        "pubKeyCredParams": [{"type": "public-key", "alg": a} for a in passkeys.ALGS],
        "authenticatorSelection": {
            "authenticatorAttachment": "platform",
            "residentKey": "required",
            "userVerification": "required",
        },
        "excludeCredentials": [
            {"type": "public-key", "id": k["id"]}
            for k in _store().passkeys_of(user["id"])
        ],
        "attestation": "none",
        "timeout": 60000,
    }


@router.post("/llave/registrar")
def llave_registrar(body: KeyRegister, request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import passkeys

    _limit(request)
    origin, rp = _site(request)
    user = _account_for_keys(request)
    try:
        key = passkeys.verify_registration(
            client_data=body.clientDataJSON,
            attestation=body.attestationObject,
            origin=origin,
            rp_id=rp,
        )
    except passkeys.PasskeyError as exc:
        raise HTTPException(400, str(exc)) from exc
    if key["user"] != user["id"]:
        raise HTTPException(400, "La solicitud era para otra cuenta.")
    if _store().passkey(key["id"]):
        raise HTTPException(409, "Este dispositivo ya está guardado.")
    _store().add_passkey(user["id"], key, body.name or "Este dispositivo")
    return {"status": "guardada", "llaves": _store().passkeys_of(user["id"])}


@router.post("/llave/opciones")
def llave_opciones(request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import passkeys

    _limit(request)
    _, rp = _site(request)
    return {
        "challenge": passkeys.new_challenge("entrar"),
        "rpId": rp,
        "userVerification": "required",
        "allowCredentials": [],  # the device offers the passkeys it has for this site
        "timeout": 60000,
    }


@router.post("/llave/entrar")
def llave_entrar(body: KeyLogin, request: Request) -> Dict[str, Any]:
    from openjarvis.accounts import passkeys

    _limit(request)
    origin, rp = _site(request)
    stored = _store().passkey(body.id)
    if not stored:
        raise HTTPException(401, "Este dispositivo no está guardado en ninguna cuenta.")
    try:
        count = passkeys.verify_assertion(
            stored=stored,
            client_data=body.clientDataJSON,
            authenticator_data=body.authenticatorData,
            signature=body.signature,
            origin=origin,
            rp_id=rp,
        )
    except passkeys.PasskeyError as exc:
        raise HTTPException(401, str(exc)) from exc
    _store().used_passkey(stored["id"], count)
    user = _store().get(stored["user"])
    if not user:
        raise HTTPException(401, "La cuenta ya no existe.")
    return _signed_in(user, body.device)


@router.get("/llave/lista")
def llave_lista(request: Request) -> Dict[str, Any]:
    user = _account_for_keys(request)
    return {"llaves": _store().passkeys_of(user["id"])}


@router.delete("/llave/{key_id}")
def llave_borrar(key_id: str, request: Request) -> Dict[str, Any]:
    user = _account_for_keys(request)
    if not _store().delete_passkey(user["id"], key_id):
        raise HTTPException(404, "No encontré esa llave.")
    return {"llaves": _store().passkeys_of(user["id"])}


@router.post("/salir")
def salir(request: Request) -> Dict[str, Any]:
    token = _bearer(request)
    if token.startswith("sg_"):
        _store().close_session(token)
    return {"ok": True}


@router.get("/lista")
def lista(request: Request) -> Dict[str, Any]:
    from openjarvis.accounts.store import public

    _owner(request)
    return {"accounts": [public(u) for u in _store().users()]}


@router.post("/{uid}/rol")
def rol(uid: str, body: Role, request: Request) -> Dict[str, Any]:
    _owner(request)
    user = _store().get(uid)
    if not user:
        raise HTTPException(404, "No encuentro esa cuenta.")
    if user["role"] == "dueño":
        raise HTTPException(400, "La cuenta del dueño no cambia.")
    _store().set(uid, role=body.role)
    from openjarvis.accounts import provision

    if body.role == "bloqueado":
        provision.in_background(provision.disable, uid)
    elif provision.enabled():
        provision.in_background(provision.ensure, uid)
    return {"ok": True}


class PlanBody(BaseModel):
    plan: str


@router.post("/{uid}/plan")
def plan(uid: str, body: PlanBody, request: Request) -> Dict[str, Any]:
    """The owner sets a customer's plan: their monthly AI budget follows."""
    from openjarvis import tiers
    from openjarvis.accounts import provision

    _owner(request)
    if body.plan not in tiers.PLANS:
        raise HTTPException(400, "Ese plan no existe.")
    if not _store().get(uid):
        raise HTTPException(404, "No encuentro esa cuenta.")
    if not provision.key_for(uid):
        provision.ensure(uid, body.plan)
    else:
        provision.set_plan(uid, body.plan)
    return {
        "ok": True,
        **provision.status(uid),
        "presupuesto_usd": provision.budget(body.plan),
    }


@router.get("/{uid}/clave-ia")
def clave_ia(uid: str, request: Request) -> Dict[str, Any]:
    """Whether the customer's AI key exists (never the key itself)."""
    from openjarvis.accounts import provision

    _owner(request)
    return {"configurado": provision.enabled(), **provision.status(uid)}


@router.delete("/{uid}")
def borrar(uid: str, request: Request) -> Dict[str, Any]:
    _owner(request)
    user = _store().get(uid)
    if not user or user["role"] == "dueño":
        raise HTTPException(400, "No se puede borrar esa cuenta.")
    _store().delete(uid)
    from openjarvis.accounts import provision

    provision.in_background(provision.disable, uid)
    return {"ok": True}


def session_allowed(token: str) -> bool:
    """For the API guard: a signed-in, approved account opens Sergio."""
    if not token.startswith("sg_"):
        return False
    try:
        user = _store().session_user(token)
    except Exception:  # noqa: BLE001 — never widen access on errors
        return False
    return bool(user and user["role"] in ROLES_IN)


__all__ = ["is_local", "router", "session_allowed"]
