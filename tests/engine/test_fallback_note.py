"""The "default engine not running; using X" note: once, and silent when the
command only reads."""

from __future__ import annotations

import logging

import pytest

from openjarvis.cli import quiet_fallback_for
from openjarvis.engine import _discovery


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    monkeypatch.setattr(_discovery, "QUIET_FALLBACK", False)
    monkeypatch.setattr(_discovery, "_NOTED", set())


def _levels(caplog):
    return [r.levelno for r in caplog.records if "not running" in r.getMessage()]


def test_warns_once_then_debug(caplog):
    caplog.set_level(logging.DEBUG, logger=_discovery.logger.name)
    for _ in range(3):
        _discovery.note_engine_fallback(
            "Default engine %r is not running; using %r", "ollama", "nim"
        )
    assert _levels(caplog) == [logging.WARNING, logging.DEBUG, logging.DEBUG]


def test_read_only_commands_stay_quiet(caplog):
    caplog.set_level(logging.DEBUG, logger=_discovery.logger.name)
    _discovery.QUIET_FALLBACK = True
    _discovery.note_engine_fallback(
        "Default engine %r is not running; using %r", "ollama", "nim"
    )
    assert _levels(caplog) == [logging.DEBUG]


@pytest.mark.parametrize(
    "argv,quiet",
    [
        (["status"], True),
        (["doctor"], True),
        (["model", "list"], True),
        (["memory", "stats"], True),
        (["config", "show"], True),
        (["chat", "--help"], True),
        (["ask", "list", "my", "files"], False),
        (["chat"], False),
        (["serve"], False),
        ([], False),
    ],
)
def test_which_commands_are_read_only(argv, quiet):
    assert quiet_fallback_for(argv) is quiet
