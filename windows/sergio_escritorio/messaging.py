"""Messages, emails and calls to other people, done the human way.

Each platform has a shortcut that opens the right conversation directly
(a link), so Sergio does not have to hunt through menus; from there the
operator (``operador.py``) writes the text key by key and, once you said
"sí, envíalo", presses send — and looks to check it was sent.

* WhatsApp: ``whatsapp://send?phone=…&text=…`` (desktop app) or WhatsApp Web.
* Instagram: ``https://ig.me/m/<usuario>`` (the DM thread in the browser).
* Messenger: ``https://m.me/<usuario>``. Telegram: ``tg://resolve?domain=…``.
* Gmail: the compose window already filled (to, subject, body).
  Outlook: the same with outlook.live.com. Any other: ``mailto:``.
* Calls: ``tel:`` (Phone Link rings from your phone), WhatsApp calls in its app.
* Anything else (X, TikTok, LinkedIn, Discord, Teams...): the operator does
  it like a person, from the platform's page.

``Contacts`` remembers how to reach people ("el Instagram de Ana es ana.mz").
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

PLATFORMS = {
    "whatsapp": ("whatsapp", "wsp", "wasap", "whats"),
    "instagram": ("instagram", "insta", "ig"),
    "messenger": ("messenger", "facebook", "fb"),
    "telegram": ("telegram",),
    "gmail": ("gmail", "correo", "email", "mail", "e mail"),
    "outlook": ("outlook", "hotmail"),
    "sms": ("sms", "mensaje de texto", "texto"),
    "x": ("x", "twitter"),
    "tiktok": ("tiktok",),
    "linkedin": ("linkedin",),
    "discord": ("discord",),
    "teams": ("teams",),
}
FIELDS = (
    "telefono",
    "whatsapp",
    "instagram",
    "messenger",
    "telegram",
    "correo",
    "x",
    "tiktok",
)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9@._+ -]", " ", text).split())


def platform_of(name: str) -> str:
    plain = _plain(name)
    for key, words in PLATFORMS.items():
        if plain == key or plain in words:
            return key
    return plain or "whatsapp"


def phone_digits(value: str, country: str = "593") -> str:
    """'099 123 4567' (Ecuador) -> '593991234567' for wa.me / tel:."""
    digits = re.sub(r"\D", "", value or "")
    if value.strip().startswith("+") or digits.startswith(country):
        return digits
    if digits.startswith("0"):
        return country + digits[1:]
    return digits


class Contacts:
    """How to reach people (JSON beside Sergio's settings)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.people: dict[str, dict[str, str]] = {}
        if path is not None:
            try:
                self.people = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.people = {}

    def save(self) -> None:
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.people, ensure_ascii=False, indent=1), encoding="utf-8"
            )

    def find(self, name: str) -> tuple[str, dict[str, str]] | None:
        wanted = _plain(name)
        if not wanted:
            return None
        for person, info in self.people.items():
            if _plain(person) == wanted:
                return person, info
        hits = [
            (p, i)
            for p, i in self.people.items()
            if wanted in _plain(p).split() or _plain(p).startswith(wanted)
        ]
        return hits[0] if len(hits) == 1 else None

    def remember(self, name: str, field: str, value: str) -> str:
        field = {
            "whatsapp": "telefono",
            "celular": "telefono",
            "email": "correo",
            "mail": "correo",
        }.get(_plain(field), _plain(field))
        if field not in FIELDS:
            raise ValueError(f"No sé guardar «{field}»; uso: {', '.join(FIELDS)}.")
        found = self.find(name)
        person = found[0] if found else name.strip().title()
        self.people.setdefault(person, {})[field] = value.strip().lstrip("@")
        self.save()
        return f"Guardado: {field} de {person}."

    def address(self, name: str, platform: str) -> str:
        """The handle / number / email for *name* on *platform*, or ''."""
        if "@" in name or re.fullmatch(r"\+?[\d\s()-]{7,}", name.strip()):
            return name.strip()  # already an address
        found = self.find(name)
        if not found:
            return ""
        info = found[1]
        key = {
            "whatsapp": "telefono",
            "sms": "telefono",
            "gmail": "correo",
            "outlook": "correo",
        }.get(platform, platform)
        return info.get(key) or (info.get("whatsapp", "") if key == "telefono" else "")


@dataclass
class Plan:
    open: str  # link or app to open first ("" = let the operator start)
    goal: str  # what the operator must finish on screen


def message_plan(
    platform: str, to: str, text: str, subject: str = "", country: str = "593"
) -> Plan:
    """Shortest human route to a message on *platform* for *to*."""
    platform = platform_of(platform)
    who = to.strip()
    text = text.strip()
    if platform == "whatsapp" and re.sub(r"\D", "", who):
        number = phone_digits(who, country)
        return Plan(
            f"whatsapp://send?phone={number}&text={quote(text)}",
            f"WhatsApp is opening the chat with +{number} with the message already written. "
            f"Check the message box contains exactly «{text}» (write it if empty) and send it "
            "with Enter, then verify it appears as sent.",
        )
    if platform == "whatsapp":
        return Plan(
            "whatsapp",
            f"In WhatsApp, search the chat named «{who}» (Ctrl+F or the search box), open it, "
            f"write exactly «{text}» in the message box and send it with Enter; verify it was sent.",
        )
    if platform == "instagram":
        handle = who.lstrip("@")
        if re.fullmatch(r"[a-z0-9._]{1,30}", handle.lower()):
            return Plan(
                f"https://ig.me/m/{handle}",
                f"The Instagram direct message chat with @{handle} is opening in the browser. "
                f"Click the message box («Mensaje…»), write exactly «{text}» and send it with "
                "Enter; verify it appears in the chat.",
            )
        return Plan(
            "https://www.instagram.com/direct/inbox/",
            f"In Instagram direct messages, start a new message to «{who}» (search the name, "
            f"pick the right person, open the chat), write exactly «{text}» and send it with Enter.",
        )
    if platform == "messenger":
        return Plan(
            f"https://m.me/{who.lstrip('@')}",
            f"In the Messenger chat with {who}, write exactly «{text}» and send it with Enter.",
        )
    if platform == "telegram":
        handle = who.lstrip("@")
        return Plan(
            f"tg://resolve?domain={quote(handle)}",
            f"In Telegram's chat with @{handle}, write exactly «{text}» and send it with Enter.",
        )
    if platform in ("gmail", "outlook"):
        if platform == "gmail":
            link = (
                "https://mail.google.com/mail/?view=cm&fs=1"
                f"&to={quote(who)}&su={quote(subject)}&body={quote(text)}"
            )
        else:
            link = (
                "https://outlook.live.com/mail/0/deeplink/compose"
                f"?to={quote(who)}&subject={quote(subject)}&body={quote(text)}"
            )
        return Plan(
            link,
            f"An email to {who} is open with subject «{subject}» and the body already written. "
            "Check recipient, subject and body are right, then send it (Ctrl+Enter or the "
            "Send/Enviar button) and verify it was sent.",
        )
    if platform == "sms":
        number = phone_digits(who, country)
        return Plan(
            f"sms:+{number}?body={quote(text)}",
            f"Phone Link (Enlace Móvil) opens a text message to +{number}. Make sure it says "
            f"exactly «{text}» and send it.",
        )
    sites = {
        "x": "https://x.com/messages",
        "tiktok": "https://www.tiktok.com/messages",
        "linkedin": "https://www.linkedin.com/messaging/",
        "discord": "discord",
        "teams": "teams",
    }
    return Plan(
        sites.get(platform, ""),
        f"Send a direct message on {platform} to «{who}» saying exactly «{text}»: find the "
        "person, open the conversation, write it and send it.",
    )


def call_plan(to: str, how: str = "telefono", country: str = "593") -> Plan:
    how = (
        platform_of(how) if how not in ("telefono", "phone", "celular") else "telefono"
    )
    if how == "whatsapp":
        number = phone_digits(to, country)
        target = f"whatsapp://send?phone={number}" if number else "whatsapp"
        return Plan(
            target,
            f"In WhatsApp open the chat with {to} and start a VOICE call (the phone icon at "
            "the top right of the chat). Verify it is calling.",
        )
    number = phone_digits(to, country)
    return Plan(
        f"tel:+{number}",
        f"Phone Link (Enlace Móvil) shows a call to +{number}: press Call / Llamar and "
        "verify it is calling through the user's phone.",
    )


__all__ = [
    "Contacts",
    "PLATFORMS",
    "Plan",
    "call_plan",
    "message_plan",
    "phone_digits",
    "platform_of",
]
