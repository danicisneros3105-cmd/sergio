"""Agents primitive — multi-turn reasoning and tool use."""

from __future__ import annotations

import logging
import logging as _logging

from openjarvis.agents._stubs import (
    AgentContext,
    AgentResult,
    BaseAgent,
    ToolUsingAgent,
)

logger = logging.getLogger(__name__)

# Import agent modules to trigger @AgentRegistry.register() decorators
try:
    import openjarvis.agents.simple  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.simple): %s", _exc
    )

try:
    import openjarvis.agents.orchestrator  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.orchestrator): %s", _exc
    )

try:
    import openjarvis.agents.native_react  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.native_react): %s", _exc
    )

try:
    import openjarvis.agents.native_openhands  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.native_openhands): %s", _exc
    )

try:
    import openjarvis.agents.react  # noqa: F401 -- backward-compat shim
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.react): %s", _exc
    )

try:
    import openjarvis.agents.openhands  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.openhands): %s", _exc
    )

try:
    import openjarvis.agents.rlm  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.rlm): %s", _exc
    )

try:
    import openjarvis.agents.claude_code  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.claude_code): %s", _exc
    )

try:
    import openjarvis.agents.opencode  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.opencode): %s", _exc
    )

try:
    import openjarvis.agents.operative  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.operative): %s", _exc
    )

try:
    import openjarvis.agents.monitor  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.monitor): %s", _exc
    )

try:
    import openjarvis.agents.monitor_operative  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.monitor_operative): %s", _exc
    )

try:
    import openjarvis.agents.deep_research  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.deep_research): %s", _exc
    )

try:
    import openjarvis.agents.morning_digest  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.morning_digest): %s", _exc
    )

# Hybrid local+cloud paradigm agents (Minions, Conductor, Archon, Advisors,
# SkillOrchestra, ToolOrchestra). Each module registers under its own name
# via @AgentRegistry.register(). Optional deps may make some unavailable.
try:
    import openjarvis.agents.hybrid  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.agents.hybrid): %s", _exc
    )

# Registry alias: "react" -> NativeReActAgent (for backward compat)
try:
    from openjarvis.core.registry import AgentRegistry

    if AgentRegistry.contains("native_react") and not AgentRegistry.contains("react"):
        AgentRegistry.register_value("react", AgentRegistry.get("native_react"))
except Exception as exc:
    logger.debug("Registry alias 'react' creation skipped: %s", exc)

__all__ = ["AgentContext", "AgentResult", "BaseAgent", "ToolUsingAgent"]
