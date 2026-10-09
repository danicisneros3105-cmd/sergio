"""Tools primitive — tool system with ABC interface and built-in tools."""

from __future__ import annotations

import logging as _logging

from openjarvis.tools._stubs import BaseTool, ToolExecutor, ToolSpec

# Import built-in tools to trigger @ToolRegistry.register() decorators.
# Each is wrapped in try/except so the package loads even before the
# individual tool modules are created.
try:
    import openjarvis.tools.calculator  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.calculator): %s", _exc
    )

try:
    import openjarvis.tools.think  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.think): %s", _exc
    )

try:
    import openjarvis.tools.retrieval  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.retrieval): %s", _exc
    )

try:
    import openjarvis.tools.llm_tool  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.llm_tool): %s", _exc
    )

try:
    import openjarvis.tools.file_read  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.file_read): %s", _exc
    )

try:
    import openjarvis.tools.web_search  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.web_search): %s", _exc
    )

try:
    import openjarvis.tools.weather  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.weather): %s", _exc
    )

try:
    import openjarvis.tools.live_world  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.live_world): %s", _exc
    )

try:
    import openjarvis.tools.clacky_task  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.clacky_task): %s", _exc
    )

try:
    import openjarvis.tools.phone_tools  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.phone_tools): %s", _exc
    )

try:
    import openjarvis.tools.face_tools  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.face_tools): %s", _exc
    )

try:
    import openjarvis.tools.desktop_tools  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.desktop_tools): %s", _exc
    )

try:
    import openjarvis.tools.skill_guide_tool  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.skill_guide_tool): %s", _exc
    )

try:
    import openjarvis.tools.code_interpreter  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.code_interpreter): %s", _exc
    )

try:
    import openjarvis.tools.code_interpreter_docker  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.code_interpreter_docker): %s", _exc
    )

try:
    import openjarvis.tools.repl  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.repl): %s", _exc
    )

try:
    import openjarvis.tools.storage_tools  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.storage_tools): %s", _exc
    )

try:
    import openjarvis.tools.mcp_adapter  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.mcp_adapter): %s", _exc
    )

try:
    import openjarvis.tools.channel_tools  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.channel_tools): %s", _exc
    )

try:
    import openjarvis.tools.http_request  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.http_request): %s", _exc
    )

try:
    import openjarvis.tools.docker_shell_exec  # noqa: F401
    import openjarvis.tools.shell_exec  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.docker_shell_exec, openjarvis.tools.shell_exec): %s",
        _exc,
    )

try:
    import openjarvis.tools.memory_manage  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.memory_manage): %s", _exc
    )
try:
    import openjarvis.tools.user_profile_manage  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.user_profile_manage): %s", _exc
    )

try:
    import openjarvis.tools.skill_manage  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.skill_manage): %s", _exc
    )

try:
    import openjarvis.tools.file_write  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.file_write): %s", _exc
    )

try:
    import openjarvis.tools.apply_patch  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.apply_patch): %s", _exc
    )

try:
    import openjarvis.tools.git_tool  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.git_tool): %s", _exc
    )

try:
    import openjarvis.tools.db_query  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.db_query): %s", _exc
    )

try:
    import openjarvis.tools.pdf_tool  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.pdf_tool): %s", _exc
    )

try:
    import openjarvis.tools.image_tool  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.image_tool): %s", _exc
    )

try:
    import openjarvis.tools.audio_tool  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.audio_tool): %s", _exc
    )

try:
    import openjarvis.tools.knowledge_tools  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.knowledge_tools): %s", _exc
    )

try:
    import openjarvis.tools.text_to_speech  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.text_to_speech): %s", _exc
    )

try:
    import openjarvis.tools.digest_collect  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.digest_collect): %s", _exc
    )

try:
    import openjarvis.tools.scan_chunks  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.scan_chunks): %s", _exc
    )

try:
    import openjarvis.tools.knowledge_sql  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.knowledge_sql): %s", _exc
    )

try:
    import openjarvis.tools.apple_calendar  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.apple_calendar): %s", _exc
    )

try:
    import openjarvis.tools.deep_think_tool  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.deep_think_tool): %s", _exc
    )

try:
    import openjarvis.tools.coding_tools  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.tools.coding_tools): %s", _exc
    )

__all__ = ["BaseTool", "ToolExecutor", "ToolSpec"]
