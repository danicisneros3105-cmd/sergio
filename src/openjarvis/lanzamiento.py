"""Is Sergio ready to open to the public? What the code can check, checked; what
only a person can do, said as such (owner, 2 Nov 2026: «déjalo listo para
publicar»).

Two kinds of step, never mixed:

* ``codigo`` — settings of this computer or server that can be read (public
  edition, open sign-up with e-mail codes, https address, payments, the AI
  provider key, the master key, sealing on). Each is ``ok`` only if it was
  really read.
* ``dueño`` — things no program can do or see (the company, the bank, the
  legal texts reviewed by a lawyer, the code-signing certificate, a private
  repository, the outside security audit, the disk's own encryption). They are
  listed as pending and are never marked done by Sergio: ``docs/LANZAMIENTO.md``
  says how to do each one.

Nothing here changes anything.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List


def _step(who: str, name: str, ok: bool, detail: str) -> Dict[str, Any]:
    return {"quien": who, "paso": name, "ok": bool(ok), "detalle": detail}


def _key_step() -> Dict[str, Any]:
    """The master key is safe off the disk: in the environment (a secret
    manager) or in a keyring encrypted with a passphrase (``sergio boveda proteger``)."""
    if os.environ.get("SERGIO_CLAVE_MAESTRA", "").strip():
        return _step(
            "codigo",
            "Clave maestra fuera del disco",
            True,
            "En una variable de entorno (gestor de secretos).",
        )
    try:
        from openjarvis.pagos import cifrado

        wrapped = bool(cifrado.status().get("protegida_con_frase"))
    except Exception:  # noqa: BLE001 — a locked or missing keyring is «not yet»
        wrapped = False
    return _step(
        "codigo",
        "Clave maestra fuera del disco",
        wrapped,
        "El llavero está cifrado con frase (sergio boveda proteger)."
        if wrapped
        else (
            "Está en ~/.openjarvis/clave_maestra, junto a los datos: protéjala con "
            "`sergio boveda proteger` o póngala en un gestor de secretos."
        ),
    )


def revisar(base: str = "") -> Dict[str, Any]:
    """The list, and whether the code-checkable part is ready."""
    from openjarvis import edicion
    from openjarvis.accounts import provision, registro, senders
    from openjarvis.security import boveda

    base = base or os.environ.get("SERGIO_PUBLIC_URL", "").strip()
    steps: List[Dict[str, Any]] = [
        _step(
            "codigo",
            "Edición pública",
            edicion.publica(),
            "Los clips ajenos, las canciones con derechos, los prompts GPL y lo no comercial están apagados."
            if edicion.publica()
            else "Falta SERGIO_EDICION=publica en el servidor que atiende a clientes.",
        ),
        _step(
            "codigo",
            "Registro abierto con verificación",
            registro.abierto() and senders.smtp_ready(),
            "Cualquiera crea su cuenta con términos, edad y código por correo."
            if registro.abierto() and senders.smtp_ready()
            else "Falta SERGIO_REGISTRO=abierto y el correo que envía los códigos (SMTP).",
        ),
        _step(
            "codigo",
            "Dirección pública con https",
            base.startswith("https://"),
            base
            if base.startswith("https://")
            else "Falta SERGIO_PUBLIC_URL con https://.",
        ),
        _step(
            "codigo",
            "Claves de IA por cliente (OpenRouter)",
            provision.enabled(),
            "Lista."
            if provision.enabled()
            else "Falta la clave de gestión: Sergio no puede crear la de cada cliente.",
        ),
        _step(
            "codigo",
            "Cifrado de datos sensibles",
            boveda.enabled(),
            "Salud, recordatorios, memoria y Nodes se guardan cifrados."
            if boveda.enabled()
            else "SERGIO_CIFRAR=0: está apagado.",
        ),
        _key_step(),
    ]
    try:
        from openjarvis.pagos import service

        pay = service.readiness(base)
        ok = any(s["ok"] for s in pay["pasos"] if "claves puestas" in s["paso"])
        steps.append(
            _step(
                "codigo",
                "Cobros con procesador con licencia",
                ok,
                "Hay un procesador con sus claves."
                if ok
                else "Falta Stripe o PayPal con sus claves (sergio.env).",
            )
        )
    except Exception as exc:  # noqa: BLE001 — a failed check is a missing step, not a crash
        steps.append(
            _step(
                "codigo",
                "Cobros con procesador con licencia",
                False,
                f"No pude revisarlo: {exc}"[:160],
            )
        )

    pending = [
        (
            "Empresa internacional constituida y cuenta bancaria",
            "Sin ella no se puede abrir Stripe/PayPal ni firmar contratos.",
        ),
        (
            "Términos de uso y privacidad redactados y revisados por un abogado",
            "Hay borradores de criterio en docs/; no son texto legal.",
        ),
        (
            "Nombre y marca comprobados (Sergio, Visage)",
            "Búsqueda de disponibilidad y registro.",
        ),
        (
            "Certificado de firma de código para el instalador de Windows",
            "Sin él, Windows avisa «aplicación no reconocida».",
        ),
        ("Repositorio privado", "Hoy es público: cualquiera puede copiar el código."),
        (
            "Cifrado del disco del servidor (y copias de seguridad cifradas)",
            "Cierra lo que el cifrado por campo no cubre.",
        ),
        (
            "Auditoría de seguridad hecha por alguien de fuera",
            "Sin ella no se puede decir «nivel bancario».",
        ),
        (
            "Beta cerrada con personas reales y facturas reales",
            "Para confirmar costos y uso típico (docs/ECONOMIA.md).",
        ),
        (
            "Términos de OpenRouter y de cada proveedor de IA leídos por escrito",
            "Para confirmar que se puede revender el acceso.",
        ),
    ]
    steps += [_step("dueño", p, False, d) for p, d in pending]
    code = [s for s in steps if s["quien"] == "codigo"]
    return {
        "listo_codigo": all(s["ok"] for s in code),
        "codigo_ok": sum(1 for s in code if s["ok"]),
        "codigo_total": len(code),
        "pendientes_del_dueno": len(pending),
        "pasos": steps,
    }


__all__ = ["revisar"]
