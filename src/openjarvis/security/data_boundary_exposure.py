"""Data-boundary checks on what is exposed: tools that reach the network,
local stores on disk, the server's bind address, frontend storage, skills,
the digest and speech backends.

Split out of ``data_boundary_audit.py``; its names are looked up on that
module at call time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import openjarvis.security.data_boundary_audit as _dba
from openjarvis.security.data_boundary_surfaces import Status


def _audit_tool_surfaces(config: Any, builder: _dba._FindingBuilder) -> None:
    tools = _dba._configured_tools(config)

    if tools & _dba.WEB_SEARCH_TOOLS:
        destination = _dba._web_search_destination()
        builder.add(
            finding_id="web-search-tool-configured",
            status="warn",
            title="Web search tool is configured",
            potential_data_path=(f"user or agent search query -> {destination}"),
            evidence=(
                f"configured tool(s) = {_dba._format_tools(tools & _dba.WEB_SEARCH_TOOLS)}"
            ),
            recommendation=(
                "Review search queries before using web search with sensitive prompts."
            ),
        )

    if tools & _dba.BROWSER_TOOLS:
        builder.add(
            finding_id="browser-tool-configured",
            status="warn",
            title="Browser automation tool is configured",
            potential_data_path="agent browser actions -> external web pages",
            evidence=f"configured tool(s) = {_dba._format_tools(tools & _dba.BROWSER_TOOLS)}",
            recommendation=(
                "Use browser automation only when web interactions are intentional."
            ),
        )

    if tools & _dba.GENERIC_NETWORK_TOOLS:
        builder.add(
            finding_id="generic-network-tool-configured",
            status="warn",
            title="Generic HTTP/network tool is configured",
            potential_data_path=("HTTP arguments, headers, and body -> external URL"),
            evidence=(
                f"configured tool(s) = {_dba._format_tools(tools & _dba.GENERIC_NETWORK_TOOLS)}"
            ),
            recommendation=(
                "Review request destinations and payloads before using HTTP tools with "
                "sensitive data."
            ),
        )

    if tools & _dba.WEATHER_TOOLS:
        builder.add(
            finding_id="weather-tool-configured",
            status="warn",
            title="External weather lookup tool is configured",
            potential_data_path=(
                "user or agent location query -> OpenWeatherMap weather service"
            ),
            evidence=f"configured tool(s) = {_dba._format_tools(tools & _dba.WEATHER_TOOLS)}",
            recommendation=(
                "Avoid sending sensitive or precise locations unless the external "
                "weather lookup is intentional."
            ),
        )

    if tools & _dba.CHANNEL_OUTBOUND_TOOLS:
        builder.add(
            finding_id="channel-outbound-tool-configured",
            status="warn",
            title="Channel outbound messaging tool is configured",
            potential_data_path="message content -> external messaging channel",
            evidence=(
                f"configured tool(s) = {_dba._format_tools(tools & _dba.CHANNEL_OUTBOUND_TOOLS)}"
            ),
            recommendation=(
                "Review channel targets and message content before enabling outbound "
                "messaging tools."
            ),
        )

    cloud_media = tools & _dba.CLOUD_MEDIA_TOOLS
    if cloud_media:
        path_parts: list[str] = []
        if "image_generate" in cloud_media:
            path_parts.append("image prompt -> external media provider")
        if "audio_transcribe" in cloud_media:
            path_parts.append("local audio file -> external media provider")
        if "text_to_speech" in cloud_media:
            path_parts.append("text content -> external text-to-speech provider")
        builder.add(
            finding_id="cloud-media-tool-configured",
            status="warn",
            title="Cloud media generation or transcription tool is configured",
            potential_data_path="; ".join(path_parts),
            evidence=f"configured tool(s) = {_dba._format_tools(cloud_media)}",
            recommendation=(
                "Review prompts and local media files before sending them to external "
                "media providers."
            ),
        )

    # scan_chunks / Deep Research knowledge routing is handled in
    # _audit_knowledge_cloud_composition (needs knowledge.db existence).

    local_access = tools & _dba.LOCAL_ACCESS_TOOLS
    if local_access:
        builder.add(
            finding_id="local-access-tools-configured",
            status="info",
            title="Local file, shell, or code tools are configured",
            potential_data_path="local files/process output -> agent context",
            evidence=f"configured tool(s) = {_dba._format_tools(local_access)}",
            recommendation=(
                "Review tool permissions and prompts before giving the agent access "
                "to sensitive local files or command output."
            ),
        )

    mcp_enabled = bool(_dba._get(config, "tools.mcp.enabled", False))
    mcp_servers = str(_dba._get(config, "tools.mcp.servers", "") or "").strip()
    if mcp_enabled and mcp_servers:
        builder.add(
            finding_id="mcp-servers-configured",
            status="warn",
            title="External MCP servers are configured",
            potential_data_path="agent tool calls/context -> configured MCP servers",
            evidence="tools.mcp.enabled = true; tools.mcp.servers is non-empty",
            recommendation=(
                "Review MCP server trust, transport, and tool schemas before sending "
                "sensitive prompts or tool arguments."
            ),
        )


def _web_search_destination() -> str:
    """Name the service ``web_search`` sends queries to, from env keys alone.

    The default engine is keyless, so no credential is involved and the
    credential-driven findings above cannot see this egress — hence a separate
    resolution here. It mirrors ``WebSearchTool._resolve_engine``, which is the
    source of truth; ``test_data_boundary_audit`` asserts the two agree.
    """
    engine = (
        (_dba.os.environ.get("OPENJARVIS_WEB_SEARCH_ENGINE") or "auto").strip().lower()
    )
    if engine not in {"auto", "youcom", "tavily", "duckduckgo", "serply"}:
        engine = "auto"
    if engine == "auto":
        if _dba.os.environ.get("TAVILY_API_KEY"):
            engine = "tavily"
        elif _dba.os.environ.get("YOUDOTCOM_API_KEY"):
            engine = "youcom"
        elif _dba.os.environ.get("SERPLY_API_KEY"):
            engine = "serply"
        else:
            engine = "youcom"

    if engine == "tavily":
        return "Tavily web search API"
    if engine == "duckduckgo":
        return "DuckDuckGo (HTML scrape)"
    if engine == "serply":
        location = _dba.os.environ.get("SERPLY_PROXY_LOCATION")
        if location:
            return f"Serply web search API (Google SERP, region {location})"
        return "Serply web search API (Google SERP)"
    tier = "keyed" if _dba.os.environ.get("YOUDOTCOM_API_KEY") else "keyless free tier"
    return f"You.com web search API ({tier})"


def _iter_local_store_targets(
    root: Path,
    config: Any | None,
) -> Iterable[tuple[str, str, Path, str, Status]]:
    """Yield store targets as (finding_id, title, path, location_label, status)."""
    targets: dict[str, tuple[str, Path, str, Status]] = {}

    for finding_id, title, relative_path, status in _dba.LOCAL_STORE_CANDIDATES:
        targets[finding_id] = (title, root / relative_path, relative_path, status)

    if config is not None:
        for finding_id, title, dotted_path, status in _dba._CONFIG_STORE_PATHS:
            raw = str(_dba._get(config, dotted_path, "") or "").strip()
            if not raw:
                if finding_id == "scheduler-db":
                    path = root / "scheduler.db"
                    location = "scheduler.db"
                else:
                    continue
            else:
                path = _dba.Path(raw).expanduser()
                if not path.is_absolute():
                    path = root / path
                try:
                    resolved_path = path.resolve()
                except OSError:
                    resolved_path = path
                location = _dba._location_label(resolved_path, root)

            existing = targets.get(finding_id)
            if existing is not None and existing[1].exists() and not path.exists():
                continue
            targets[finding_id] = (title, path, location, status)

    seen_resolved: set[str] = set()
    for finding_id, (title, path, location, status) in targets.items():
        try:
            resolved_key = str(path.resolve())
        except OSError:
            resolved_key = str(path)
        if resolved_key in seen_resolved:
            continue
        seen_resolved.add(resolved_key)
        yield finding_id, title, path, location, status


def _audit_local_stores(
    root: Path,
    builder: _dba._FindingBuilder,
    *,
    config: Any | None = None,
) -> None:
    if not root.exists():
        return
    for finding_id, title, path, location, status in _dba._iter_local_store_targets(
        root,
        config,
    ):
        if not path.exists():
            continue
        builder.add(
            finding_id=f"local-store-{finding_id}",
            status=status,
            title=f"{title} exists locally",
            potential_data_path=f"local runtime state -> {location}",
            evidence=f"path exists: {location}",
            recommendation=(
                "Review retention, backups, and filesystem permissions for this "
                "local store."
            ),
            location=location,
            absolute_location=str(path),
        )
        permission_note = _dba._permission_note(path)
        if permission_note:
            builder.add(
                finding_id=f"local-store-permissions-{finding_id}",
                status="warn",
                title=f"{title} permissions need review",
                potential_data_path=f"local runtime state -> {location}",
                evidence=permission_note,
                recommendation=(
                    "Restrict this file or directory to the current user before "
                    "storing sensitive data."
                ),
                location=location,
                absolute_location=str(path),
            )


def _audit_server_exposure(config: Any, builder: _dba._FindingBuilder) -> None:
    host = str(_dba._get(config, "server.host", "") or "").strip()
    if not _dba._is_loopback_host(host):
        binds_all = host in {"0.0.0.0", "::"}
        builder.add(
            finding_id=(
                "server-binds-all-interfaces"
                if binds_all
                else "server-binds-non-loopback-interface"
            ),
            status="warn",
            title=(
                "Server is configured to bind all network interfaces"
                if binds_all
                else "Server is configured to bind a non-loopback interface"
            ),
            potential_data_path="OpenJarvis HTTP server -> local network interfaces",
            evidence=f"server.host = {_dba._quote(host)}",
            recommendation=(
                "Use server.host = '127.0.0.1' unless LAN exposure is intentional."
            ),
        )

    a2a_enabled = bool(_dba._get(config, "a2a.enabled", False))
    a2a_token = str(_dba._get(config, "a2a.auth_token", "") or "")
    if a2a_enabled and not a2a_token:
        builder.add(
            finding_id="a2a-enabled-without-auth-token",
            status="fail",
            title="A2A server is enabled without an auth token",
            potential_data_path="inbound A2A requests -> OpenJarvis agent runtime",
            evidence="a2a.enabled = true; a2a.auth_token is empty",
            recommendation=(
                "Set a2a.auth_token or disable A2A unless the network is trusted."
            ),
        )


def _audit_frontend_storage_scope(builder: _dba._FindingBuilder) -> None:
    builder.add(
        finding_id="frontend-credential-storage-not-inspected",
        status="info",
        title="Frontend credential storage is outside this CLI scan",
        potential_data_path="desktop/web frontend storage -> cloud API keys",
        evidence="CLI scan cannot inspect browser localStorage or Tauri storage",
        recommendation=(
            "Review frontend credential-storage work separately. This finding is "
            "a scope note for cloud/API-key deployments, not a detected leak."
        ),
    )


def _audit_skills_and_digest(config: Any, builder: _dba._FindingBuilder) -> None:
    if bool(_dba._get(config, "skills.enabled", False)):
        builder.add(
            finding_id="skills-enabled",
            status="info",
            title="Skills are enabled",
            potential_data_path="agent-selected skills -> local files and tools",
            evidence="skills.enabled = true",
            recommendation=(
                "Review installed skills, especially skills with file, shell, "
                "browser, or network access."
            ),
        )

    if bool(_dba._get(config, "skills.auto_sync", False)):
        builder.add(
            finding_id="skills-auto-sync-enabled",
            status="warn",
            title="Skill auto-sync is enabled",
            potential_data_path="configured skill source -> local skill directory",
            evidence="skills.auto_sync = true",
            recommendation="Review external skill sources before enabling auto-sync.",
        )

    if bool(_dba._get(config, "digest.enabled", False)):
        sources = sorted(
            set(_dba._iter_digest_sources(config)) & _dba.PERSONAL_DIGEST_SOURCES
        )
        builder.add(
            finding_id="digest-enabled",
            status="warn",
            title="Morning digest is enabled",
            potential_data_path="personal connectors -> digest generation context",
            evidence=(
                "digest.enabled = true; sources = "
                + (", ".join(sources) or "configured sections")
            ),
            recommendation=(
                "Review digest sources and connector scopes before enabling "
                "personal-data digests."
            ),
        )


def _audit_speech_settings(config: Any, builder: _dba._FindingBuilder) -> None:
    speech_backend = str(_dba._get(config, "speech.backend", "") or "").lower()
    if speech_backend in {"openai", "deepgram"}:
        builder.add(
            finding_id="cloud-speech-backend-configured",
            status="warn",
            title="Cloud speech backend configured",
            potential_data_path="speech audio or transcripts -> cloud speech provider",
            evidence=f"speech.backend = {_dba._quote(speech_backend)}",
            recommendation=(
                "Use a local speech backend for local-only audio processing."
            ),
        )

    digest_enabled = bool(_dba._get(config, "digest.enabled", False))
    tts_backend = str(_dba._get(config, "digest.tts_backend", "") or "").lower()
    if digest_enabled and tts_backend in _dba.CLOUD_TTS_BACKENDS:
        builder.add(
            finding_id="cloud-tts-backend-configured",
            status="warn",
            title="Cloud text-to-speech backend configured for digests",
            potential_data_path=(
                "personal digest narrative -> cloud text-to-speech provider"
            ),
            evidence=f"digest.tts_backend = {_dba._quote(tts_backend)}",
            recommendation=(
                "Use a local text-to-speech backend or disable digest audio when "
                "the generated narrative contains sensitive personal data."
            ),
        )


__all__ = [
    "_audit_tool_surfaces",
    "_web_search_destination",
    "_iter_local_store_targets",
    "_audit_local_stores",
    "_audit_server_exposure",
    "_audit_frontend_storage_scope",
    "_audit_skills_and_digest",
    "_audit_speech_settings",
]
