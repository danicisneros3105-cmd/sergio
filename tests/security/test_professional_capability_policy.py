"""Declared permissions prevent external app calls before dispatch."""

from unittest.mock import Mock

import pytest

from openjarvis.core.types import ToolCall
from openjarvis.security.capabilities import CapabilityPolicy
from openjarvis.tools._stubs import ToolExecutor
from openjarvis.tools.professional import (
    KronosTool,
    OpenDesignTool,
    ProfessionalAppsTool,
)


@pytest.mark.parametrize(
    "tool_type,permission",
    [
        (KronosTool, "code:execute"),
        (OpenDesignTool, "network:fetch"),
        (ProfessionalAppsTool, "system:admin"),
    ],
)
def test_restricted_agent_cannot_start_professional_work(
    monkeypatch, tool_type, permission
):
    execute = Mock(side_effect=AssertionError("dispatched despite denial"))
    monkeypatch.setattr(tool_type, "execute", execute)
    tool = tool_type()
    result = ToolExecutor(
        [tool],
        capability_policy=CapabilityPolicy(default_deny=True),
        agent_id="restricted",
    ).execute(ToolCall(id="denied", name=tool.tool_id, arguments="{}"))
    assert not result.success and permission in result.content
    execute.assert_not_called()
