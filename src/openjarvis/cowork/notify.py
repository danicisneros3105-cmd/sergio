"""Cowork progress to the owner's own chat — never to anyone else.

``[cowork] notify_channel`` names a channel type ("telegram", "whatsapp" …)
and ``notify_to`` the owner's id on it. Phone channels (WhatsApp, SMS,
SendBlue) only accept a number listed in ``[phone] owner_numbers``; anything
else is refused, so a misconfiguration can never message a third party.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

PHONE_CHANNELS = frozenset({"whatsapp", "twilio", "sendblue", "sms"})


def owner_sender(config: Any, channels: Any) -> Optional[Callable[[str], bool]]:
    """A ``send(text) -> bool`` to the owner, or None when not configured/allowed.

    *channels* is the server's channel bridge (``app.state.channel_bridge``)
    or any object with a ``_channels`` mapping of type -> adapter.
    """
    cowork = getattr(config, "cowork", None)
    kind = str(getattr(cowork, "notify_channel", "") or "").strip().lower()
    target = str(getattr(cowork, "notify_to", "") or "").strip()
    if not kind or not target or channels is None:
        return None
    if kind in PHONE_CHANNELS:
        from openjarvis.phone.numbers import is_owner, owner_numbers

        if not is_owner(target, owner_numbers(config)):
            logger.warning(
                "Cowork notices not sent: %s is not one of [phone] owner_numbers",
                target,
            )
            return None
    adapters = getattr(channels, "_channels", None) or {}
    adapter = adapters.get(kind)
    if adapter is None:
        logger.info("Cowork notices: channel %r is not connected", kind)
        return None

    def send(text: str) -> bool:
        return bool(adapter.send(target, text))

    return send


__all__ = ["PHONE_CHANNELS", "owner_sender"]
