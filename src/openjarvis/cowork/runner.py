"""The default way a Cowork step runs on this computer: an agent with tools.

The step goes to the ``native_react`` agent with only the tools the plan
named for it (those that exist here and that Cowork allows). Its turn limit
is the run's remaining action budget, and every tool call it makes is
counted from the event bus, so the run's hard cap holds.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from typing import List, Tuple

from openjarvis.cowork.scrutiny import EXTERNAL_TOOLS

logger = logging.getLogger(__name__)

# Never handed to a Cowork step, whatever the plan says: these reach other
# people, run arbitrary shells or spawn more agents.
FORBIDDEN_TOOLS = frozenset(EXTERNAL_TOOLS) | {
    "shell_exec",
    "docker_shell_exec",
    "agent_spawn",
    "agent_kill",
    "git_commit",
    "execute_pending_actions",
}
# A step that names no tool still gets these read-only helpers.
BASE_TOOLS = ("think", "calculator")


def personal_browser_enabled() -> bool:
    """A persisted browser profile is only for a dedicated installation."""
    return os.environ.get("SERGIO_COWORK_PERSONAL_BROWSER") == "1"


def usable_tools(names: List[str]) -> List[str]:
    """The plan's tools that exist in this install and are allowed."""
    import openjarvis.tools  # noqa: F401 - registers the built-in tools
    from openjarvis.core.registry import ToolRegistry

    wanted = [n for n in dict.fromkeys(list(names) + list(BASE_TOOLS)) if n]
    return [
        n
        for n in wanted
        if n not in FORBIDDEN_TOOLS
        and (n != "en_segundo_plano" or personal_browser_enabled())
        and ToolRegistry.contains(n)
    ]


def _read_evidence(results: list, check: str) -> dict | None:
    """Accept only the tool receipt for this URL and expected literal."""
    from openjarvis.asistente.navegador import verify_read

    url, sep, expected = check.partition(" | ")
    if not sep or not url.startswith(("https://", "http://")) or not expected.strip():
        return None
    for item in results:
        if (
            item.get("tool_name") != "en_segundo_plano"
            or item.get("success") is not True
        ):
            continue
        try:
            data = json.loads(item["content"])
            if data["url"] == url and data["evidencia"]["verificado"] is True:
                evidence = verify_read(data, expected)
                if evidence["verificado"]:
                    return evidence
        except (KeyError, TypeError, AttributeError, ValueError):
            continue
    return None


def verified_read(results: list, check: str) -> bool:
    """Only a tool reading the exact URL and literal in the plan counts."""
    return _read_evidence(results, check) is not None


def _written_file_evidence(results: list, check: str) -> str | None:
    """Require a write and a successful reread of the requested text file."""
    kind, sep, rule = check.partition(" | ")
    if kind != "ARCHIVO" or not sep:
        return None
    path, sep, expected = rule.partition(" | ")
    if (
        not sep
        or not expected.strip()
        or len(path) > 280
        or not os.path.isabs(path)
        or any(ord(char) < 32 for char in path)
    ):
        return None
    key = os.path.normcase(os.path.normpath(path))
    wrote = confirmed = False
    for item in results:
        actual = item.get("file_path")
        if (
            not isinstance(actual, str)
            or os.path.normcase(os.path.normpath(actual)) != key
        ):
            continue
        if item.get("tool_name") == "file_write":
            wrote = item.get("success") is True
            confirmed = False
        elif item.get("tool_name") == "file_read" and wrote:
            content = item.get("content")
            confirmed = (
                item.get("success") is True
                and isinstance(content, str)
                and expected in content
            )
    return path if confirmed else None


def sdk_step_runner(
    prompt: str, tools: List[str], budget: int, *, expected_check: str = ""
) -> Tuple[str, int]:
    """Run one step; returns (answer, tool calls made)."""
    from openjarvis.core.config import load_config
    from openjarvis.core.events import EventType
    from openjarvis.sdk import Jarvis

    if budget <= 0:
        return "NO POSIBLE: no quedan acciones en el tope de esta tarea.", 0
    config = copy.deepcopy(load_config())
    config.agent.max_turns = max(1, min(int(config.agent.max_turns or 10), budget))
    jarvis = Jarvis(config=config)
    calls = {"n": 0}

    def count(_event: object) -> None:
        calls["n"] += 1

    jarvis._bus.subscribe(EventType.TOOL_CALL_START, count)
    try:
        result = jarvis.ask_full(
            prompt,
            agent="native_react",
            tools=usable_tools(tools),
            file_receipts=expected_check.startswith("ARCHIVO | "),
        )
    finally:
        try:
            jarvis.close()
        except Exception:  # noqa: BLE001
            logger.debug("Jarvis close failed", exc_info=True)
    used = max(calls["n"], len(result.get("tool_results") or []))
    answer = str(result.get("content") or "")
    # The SDK returns model text and a record of calls, not a verifier for
    # the user's requested outcome. Do not certify the model's own marker.
    from openjarvis.cowork.session import step_status

    status, detail = step_status(answer)
    if status == "done":
        receipts = result.get("tool_results") or []
        file_path = _written_file_evidence(receipts, expected_check)
        if file_path is not None:
            return (
                f"TERMINADO: Archivo guardado y contenido comprobado: {file_path}",
                used,
            )
        evidence = _read_evidence(receipts, expected_check)
        if evidence is not None:
            extract = " ".join(evidence["extracto"].split())
            return (
                f"TERMINADO: Texto verificado en {evidence['url']}: «{extract}».",
                used,
            )
        return (
            "NO POSIBLE: No pude verificar el resultado esperado. "
            f"Resultado informado: {detail or answer}"[:600],
            used,
        )
    return answer, used


__all__ = [
    "BASE_TOOLS",
    "FORBIDDEN_TOOLS",
    "personal_browser_enabled",
    "sdk_step_runner",
    "usable_tools",
    "verified_read",
]
