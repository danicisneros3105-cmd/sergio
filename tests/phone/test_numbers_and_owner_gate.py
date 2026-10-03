"""Owner-only phone channels and number normalization."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from openjarvis.phone.numbers import is_owner, to_e164
from openjarvis.server.channel_bridge import ChannelBridge
from openjarvis.server.session_store import SessionStore


def test_to_e164_normalizes_and_refuses_guessing():
    assert to_e164("+593 99-123 4567") == "+593991234567"
    assert to_e164("00593991234567") == "+593991234567"
    for bad in ("0991234567", "+1234", "abc", ""):
        with pytest.raises(ValueError):
            to_e164(bad)


def test_is_owner_ignores_formatting():
    assert is_owner("593991234567", ["+593 99 123 4567"])
    assert not is_owner("593991234568", ["+593991234567"])
    assert not is_owner("", ["+593991234567"])


def _bridge(owners):
    system = MagicMock()
    system.ask.return_value = {"content": "hola"}
    return ChannelBridge(
        channels={},
        session_store=SessionStore(db_path=":memory:"),
        bus=MagicMock(),
        system=system,
        owner_numbers=owners,
    ), system


def test_strangers_are_ignored_on_phone_channels():
    bridge, system = _bridge(["+593991234567"])
    assert bridge.handle_incoming("+15550000000", "lee mis archivos", "whatsapp") == ""
    assert bridge.handle_incoming("15550000000", "hola", "twilio") == ""
    system.ask.assert_not_called()


def test_no_owner_configured_fails_closed():
    bridge, system = _bridge([])
    assert bridge.handle_incoming("+593991234567", "hola", "whatsapp") == ""
    system.ask.assert_not_called()


def test_owner_and_non_phone_channels_are_served():
    bridge, system = _bridge(["+593991234567"])
    assert bridge._sender_allowed("593991234567", "whatsapp")
    assert bridge._sender_allowed("anyone", "telegram")
