"""The default way a Cowork step runs on this computer: an agent with tools.

The step goes to the ``native_react`` agent with only the tools the plan
named for it (those that exist here and that Cowork allows). Its turn limit
is the run's remaining action budget, and every tool call it makes is
counted from the event bus, so the run's hard cap holds.
"""

from __future__ import annotations

import copy
import logging
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


def usable_tools(names: List[str]) -> List[str]:
    """The plan's tools that exist in this install and are allowed."""
    import openjarvis.tools  # noqa: F401 - registers the built-in tools
    from openjarvis.core.registry import ToolRegistry

    wanted = [n for n in dict.fromkeys(list(names) + list(BASE_TOOLS)) if n]
    return [n for n in wanted if n not in FORBIDDEN_TOOLS and ToolRegistry.contains(n)]


def sdk_step_runner(prompt: str, tools: List[str], budget: int) -> Tuple[str, int]:
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
            prompt, agent="native_react", tools=usable_tools(tools)
        )
    finally:
        try:
            jarvis.close()
        except Exception:  # noqa: BLE001
            logger.debug("Jarvis close failed", exc_info=True)
    used = max(calls["n"], len(result.get("tool_results") or []))
    return str(result.get("content") or ""), used


__all__ = ["BASE_TOOLS", "FORBIDDEN_TOOLS", "sdk_step_runner", "usable_tools"]
