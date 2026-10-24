"""How the one-time codes reach the person signing up.

* **Email** — SMTP with TLS when ``SERGIO_SMTP_HOST`` (and ``_PORT``,
  ``_USER``, ``_PASSWORD``, ``_FROM``) are in ``~/.openjarvis/sergio.env``.
* **SMS** — Twilio Verify when ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN`` and
  ``TWILIO_VERIFY_SID`` are there; Twilio makes and checks the code.

Without them the option says so; a code is never written to a log.
These are security codes the person asks for themselves, not messages sent
on the owner's behalf.
"""

from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage

_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")


def phone(raw: str) -> str:
    """E.164 (+593…) or '' when it is not a phone number."""
    p = re.sub(r"[\s\-().]", "", raw or "")
    return p if _PHONE.match(p) else ""


def smtp_ready() -> bool:
    return bool(
        os.environ.get("SERGIO_SMTP_HOST") and os.environ.get("SERGIO_SMTP_FROM")
    )


def sms_ready() -> bool:
    return all(
        os.environ.get(k)
        for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SID")
    )


def send_email_code(to: str, code: str) -> None:
    if not smtp_ready():
        raise RuntimeError("No hay servidor de correo configurado.")
    msg = EmailMessage()
    msg["From"] = os.environ["SERGIO_SMTP_FROM"]
    msg["To"] = to
    msg["Subject"] = f"Su código de Sergio: {code}"
    msg.set_content(
        f"Su código es {code}. Vale 10 minutos.\n\n"
        "Si no lo pidió usted, ignore este correo: nadie entra sin el código."
    )
    port = int(os.environ.get("SERGIO_SMTP_PORT") or 587)
    host = os.environ["SERGIO_SMTP_HOST"]
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, context=context, timeout=20)
    else:
        server = smtplib.SMTP(host, port, timeout=20)
        server.starttls(context=context)
    with server:
        if os.environ.get("SERGIO_SMTP_USER"):
            server.login(
                os.environ["SERGIO_SMTP_USER"],
                os.environ.get("SERGIO_SMTP_PASSWORD", ""),
            )
        server.send_message(msg)


def _twilio(path: str, data: dict) -> dict:
    import httpx

    sid = os.environ["TWILIO_VERIFY_SID"]
    url = f"https://verify.twilio.com/v2/Services/{sid}/{path}"
    with httpx.Client(timeout=20) as c:
        r = c.post(
            url,
            data=data,
            auth=(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]),
        )
        r.raise_for_status()
        return r.json()


def send_sms_code(to: str) -> None:
    if not sms_ready():
        raise RuntimeError("Los SMS no están configurados.")
    _twilio("Verifications", {"To": to, "Channel": "sms", "Locale": "es"})


def check_sms_code(to: str, code: str) -> bool:
    if not sms_ready():
        return False
    try:
        return (
            _twilio("VerificationCheck", {"To": to, "Code": code.strip()}).get("status")
            == "approved"
        )
    except Exception:  # noqa: BLE001 — a wrong or expired code
        return False


__all__ = [
    "check_sms_code",
    "phone",
    "send_email_code",
    "send_sms_code",
    "sms_ready",
    "smtp_ready",
]
