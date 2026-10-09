"""Application data-boundary diagnostics for OpenJarvis.

The report builder intentionally limits itself to configuration values,
environment-key presence, and file existence. It never reads private user
content from connector credential files, memory files, trace databases, logs, or
other local runtime stores.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from openjarvis.security.data_boundary_credentials import (  # noqa: F401 — re-exported for existing imports
    _audit_channel_environment_credentials,
    _audit_channel_settings,
    _audit_connector_credentials,
    _audit_environment_credentials,
    _audit_generic_runtime_credentials,
    _audit_local_channel_credential_dirs,
)
from openjarvis.security.data_boundary_helpers import (  # noqa: F401 — re-exported for existing imports
    _first_nonempty,
    _format_tools,
    _get,
    _is_cloud_value,
    _is_local_engine_value,
    _is_loopback_host,
    _iter_digest_sources,
    _location_label,
    _looks_like_cloud_model,
    _non_empty_paths,
    _permission_note,
    _primary_cloud_signals,
    _quote,
    _redact_root,
    _target_is_cloud,
)
from openjarvis.security.data_boundary_surfaces import (  # noqa: F401 — re-exported for existing imports
    _CONFIG_STORE_PATHS,
    _SPECIALIZED_CREDENTIAL_ENV_VARS,
    API_KEY_ENV_VARS,
    BROWSER_TOOLS,
    CHANNEL_OUTBOUND_TOOLS,
    CHANNEL_REFERENCE_ENV_VARS,
    CHANNEL_REFERENCE_FIELDS,
    CHANNEL_SECRET_ENV_VARS,
    CHANNEL_SECRET_FIELDS,
    CLOUD_API_SURFACES,
    CLOUD_MEDIA_TOOLS,
    CLOUD_PROVIDER_KEYS,
    CLOUD_TTS_BACKENDS,
    EXTERNAL_TOOL_SURFACES,
    GENERIC_CREDENTIAL_ENV_VARS,
    GENERIC_NETWORK_TOOLS,
    KNOWLEDGE_ENGINE_TOOLS,
    LOCAL_ACCESS_TOOLS,
    LOCAL_ENGINE_KEYS,
    LOCAL_STORE_CANDIDATES,
    OUTBOUND_TOOL_SURFACES,
    PERSONAL_DIGEST_SOURCES,
    RUNTIME_CREDENTIAL_ENV_KEYS,
    WEATHER_TOOLS,
    WEB_SEARCH_TOOLS,
    Status,
)


@dataclass(frozen=True, slots=True)
class DataBoundaryFinding:
    """One application data-boundary finding."""

    id: str
    status: Status
    title: str
    potential_data_path: str
    evidence: str
    recommendation: str
    location: str = ""
    absolute_location: str = ""

    def to_dict(self, *, show_paths: bool = False) -> dict[str, str]:
        """Return a stable JSON-serializable representation.

        Absolute paths and connector basenames are redacted by default. When
        ``show_paths`` is true, the location field exposes the absolute path for
        local debugging.
        """
        payload = {
            "id": self.id,
            "status": self.status,
            "title": self.title,
            "potential_data_path": self.potential_data_path,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }
        if self.absolute_location:
            payload["location"] = (
                self.absolute_location if show_paths else self.location
            )
        elif self.location:
            payload["location"] = self.location
        return payload


@dataclass(frozen=True, slots=True)
class DataBoundaryReport:
    """Structured result returned by the data-boundary audit."""

    verdict: str
    root: str
    config_loaded: bool
    findings: tuple[DataBoundaryFinding, ...]

    def summary(self) -> dict[str, int]:
        """Count findings by status."""
        counts = {"fail": 0, "warn": 0, "info": 0}
        for finding in self.findings:
            counts[finding.status] += 1
        return counts

    def to_dict(self, *, show_paths: bool = False) -> dict[str, Any]:
        """Return a stable JSON-serializable representation."""
        return {
            "schema_version": 1,
            "verdict": self.verdict,
            "root": self.root if show_paths else _redact_root(self.root),
            "config_loaded": self.config_loaded,
            "summary": self.summary(),
            "findings": [
                finding.to_dict(show_paths=show_paths) for finding in self.findings
            ],
        }


class _FindingBuilder:
    """Small helper that preserves insertion order and deduplicates by id."""

    def __init__(self) -> None:
        self._findings: list[DataBoundaryFinding] = []
        self._seen: set[str] = set()

    def add(
        self,
        *,
        finding_id: str,
        status: Status,
        title: str,
        potential_data_path: str,
        evidence: str,
        recommendation: str,
        location: str = "",
        absolute_location: str = "",
    ) -> None:
        if finding_id in self._seen:
            return
        self._seen.add(finding_id)
        self._findings.append(
            DataBoundaryFinding(
                id=finding_id,
                status=status,
                title=title,
                potential_data_path=potential_data_path,
                evidence=evidence,
                recommendation=recommendation,
                location=location,
                absolute_location=absolute_location,
            )
        )

    def build(self) -> tuple[DataBoundaryFinding, ...]:
        return tuple(self._findings)


def build_data_boundary_report(
    config: Any,
    root: Path | None,
    *,
    config_loaded: bool = True,
    config_error: str = "",
    root_error: str = "",
) -> DataBoundaryReport:
    """Build a data-boundary report from config and runtime paths.

    The function is side-effect-free. It uses defensive ``getattr`` access so
    the command remains robust across configuration additions.
    """

    builder = _FindingBuilder()
    root_path: Path | None = None
    root_label = "<unresolved-openjarvis-home>"
    if root is not None:
        try:
            root_path = root.expanduser().resolve()
            root_label = str(root_path)
        except Exception as exc:  # pragma: no cover - defensive path handling
            root_error = f"{type(exc).__name__}: {exc}"

    if root_error:
        error_type = str(root_error).partition(":")[0].strip() or "Error"
        if not error_type.replace("_", "").isalnum():
            error_type = "Error"
        builder.add(
            finding_id="config-root-error",
            status="fail",
            title="OpenJarvis home directory could not be resolved",
            potential_data_path="runtime state root -> local store checks",
            evidence=(
                f"{error_type} while resolving OpenJarvis home; "
                "path details were redacted"
            ),
            recommendation=(
                "Fix OPENJARVIS_HOME or XDG_DATA_HOME before relying on "
                "local-store data-boundary checks."
            ),
        )

    if config_error:
        builder.add(
            finding_id="config-load-error",
            status="fail",
            title="OpenJarvis config could not be loaded",
            potential_data_path="config.toml -> data-boundary report",
            evidence=_truncate(config_error),
            recommendation=(
                "Fix the configuration file before relying on config-derived "
                "data-boundary checks. Local store and environment checks still run."
            ),
        )
    elif config_loaded:
        _audit_outbound_settings(config, builder)
        _audit_telemetry_settings(config, builder)
        _audit_memory_cloud_composition(config, builder)
        _audit_memory_service(config, builder)
        _audit_deep_research_settings(config, builder)
        _audit_trace_and_learning_settings(config, builder)
        _audit_tool_surfaces(config, builder)
        _audit_server_exposure(config, builder)
        _audit_channel_settings(config, builder)
        _audit_skills_and_digest(config, builder)
        _audit_speech_settings(config, builder)
    elif not root_error:
        builder.add(
            finding_id="config-file-missing",
            status="info",
            title="OpenJarvis config file was not found",
            potential_data_path="configuration defaults -> data-boundary report",
            evidence="config_loaded = false",
            recommendation=(
                "Run `jarvis init` before relying on config-derived checks. "
                "Local store and environment checks still run."
            ),
        )

    active_tools = (
        _configured_tools(config) if config_loaded and not config_error else set()
    )
    active_config = config if config_loaded and not config_error else None
    if active_config is not None:
        _audit_security_settings(
            active_config,
            builder,
            has_external_surface=_has_external_surface(active_config, active_tools),
        )

    if root_path is not None:
        _audit_local_stores(root_path, builder, config=active_config)
        _audit_connector_credentials(root_path, builder)
        if active_config is not None:
            _audit_local_channel_credential_dirs(active_config, root_path, builder)
            _audit_knowledge_cloud_composition(active_config, root_path, builder)
    _audit_environment_credentials(
        active_config,
        builder,
        active_tools=active_tools,
    )
    _audit_channel_environment_credentials(active_config, builder)
    _audit_generic_runtime_credentials(builder)
    if _has_cloud_api_surface(active_config, active_tools):
        _audit_frontend_storage_scope(builder)

    findings = builder.build()
    return DataBoundaryReport(
        verdict=_derive_verdict(findings),
        root=root_label,
        config_loaded=config_loaded and not bool(config_error),
        findings=findings,
    )


def _audit_outbound_settings(config: Any, builder: _FindingBuilder) -> None:
    if bool(_get(config, "analytics.enabled", False)):
        builder.add(
            finding_id="analytics-enabled",
            status="info",
            title="Outbound usage analytics are enabled",
            potential_data_path="runtime usage events -> analytics endpoint",
            evidence="analytics.enabled = true",
            recommendation=(
                "Set analytics.enabled = false for no outbound usage analytics. "
                "This finding does not assert that prompt content is sent."
            ),
        )

    provider = _get(config, "intelligence.provider", "")
    if _is_cloud_value(provider):
        builder.add(
            finding_id="cloud-provider-configured",
            status="warn",
            title="Cloud model provider configured",
            potential_data_path=(
                "prompts, memory context, and tool outputs -> cloud provider"
            ),
            evidence=f"intelligence.provider = {_quote(provider)}",
            recommendation=(
                "Review what context is sent before enabling cloud inference, "
                "or use a local provider for local-only operation."
            ),
        )

    default_model = _get(config, "intelligence.default_model", "")
    effective_engine = _first_nonempty(
        _get(config, "intelligence.preferred_engine", ""),
        _get(config, "engine.default", ""),
        provider,
    )
    if _target_is_cloud(effective_engine, default_model):
        builder.add(
            finding_id="cloud-default-model-configured",
            status="warn",
            title="Cloud default model configured",
            potential_data_path="model requests -> default cloud model",
            evidence=f"intelligence.default_model = {_quote(default_model)}",
            recommendation=("Use a local default model for local-only operation."),
        )

    preferred_engine = _get(config, "intelligence.preferred_engine", "")
    if _is_cloud_value(preferred_engine):
        builder.add(
            finding_id="cloud-preferred-engine-configured",
            status="warn",
            title="Cloud preferred engine configured",
            potential_data_path="model requests -> preferred cloud engine",
            evidence=f"intelligence.preferred_engine = {_quote(preferred_engine)}",
            recommendation="Use a local preferred engine for local-only operation.",
        )

    default_engine = _get(config, "engine.default", "")
    if _is_cloud_value(default_engine):
        builder.add(
            finding_id="cloud-default-engine-configured",
            status="warn",
            title="Cloud default engine configured",
            potential_data_path="model requests -> default cloud engine",
            evidence=f"engine.default = {_quote(default_engine)}",
            recommendation="Use a local default engine for local-only operation.",
        )

    optimize_provider = _get(config, "optimize.optimizer_provider", "")
    if _is_cloud_value(optimize_provider):
        builder.add(
            finding_id="cloud-optimizer-provider-configured",
            status="info",
            title="Cloud optimizer provider is configured",
            potential_data_path="optimization context -> optimizer provider",
            evidence=f"optimize.optimizer_provider = {_quote(optimize_provider)}",
            recommendation=(
                "Before running optimization, review whether examples, traces, "
                "or prompts may be sent to this provider."
            ),
        )

    judge_model = _get(config, "optimize.judge_model", "")
    if _target_is_cloud(optimize_provider, judge_model):
        builder.add(
            finding_id="cloud-judge-model-configured",
            status="info",
            title="Cloud judge model appears configured",
            potential_data_path="optimization examples/results -> judge model",
            evidence=f"optimize.judge_model = {_quote(judge_model)}",
            recommendation="Use a local judge model for local-only optimization.",
        )


def _audit_telemetry_settings(config: Any, builder: _FindingBuilder) -> None:
    if bool(_get(config, "telemetry.enabled", False)):
        builder.add(
            finding_id="telemetry-enabled",
            status="warn",
            title="Telemetry capture is enabled",
            potential_data_path=(
                "runtime metrics and inference events -> telemetry database"
            ),
            evidence="telemetry.enabled = true",
            recommendation=(
                "Disable telemetry when local-only metrics collection is not "
                "needed. Treat telemetry.db as sensitive when enabled."
            ),
        )


def _audit_memory_service(config: Any, builder: _FindingBuilder) -> None:
    if not bool(_get(config, "tools.storage.enabled", False)):
        return
    has_cloud = bool(_primary_cloud_signals(config))
    evidence = "tools.storage.enabled = true"
    if has_cloud:
        evidence += "; cloud inference surface detected"
    builder.add(
        finding_id="memory-service-enabled",
        status="warn",
        title="Automatic memory service is enabled",
        potential_data_path=(
            "conversation content -> extracted facts -> local memory store"
        ),
        evidence=evidence,
        recommendation=(
            "Review what conversations are persisted before enabling the "
            "background memory service on sensitive workloads."
        ),
    )


def _audit_deep_research_settings(config: Any, builder: _FindingBuilder) -> None:
    engine = _get(config, "deep_research.engine", "")
    model = _get(config, "deep_research.model", "")
    cloud_engine = _is_cloud_value(engine)
    effective_engine, effective_model = _effective_deep_research_target(config)
    cloud_model = bool(model) and _target_is_cloud(effective_engine, effective_model)
    if not cloud_engine and not cloud_model:
        return
    evidence_parts = []
    if cloud_engine:
        evidence_parts.append(f"deep_research.engine = {_quote(engine)}")
    if cloud_model:
        evidence_parts.append(f"deep_research.model = {_quote(model)}")
    builder.add(
        finding_id="deep-research-cloud-configured",
        status="warn",
        title="Cloud deep-research engine or model configured",
        potential_data_path="research planner context -> cloud engine/model",
        evidence="; ".join(evidence_parts),
        recommendation=(
            "Use local deep-research engine and model settings for local-only "
            "operation."
        ),
    )


def _effective_deep_research_target(config: Any) -> tuple[str, str]:
    """Return static-config effective Deep Research engine and model.

    Resolution uses configuration only (no request overrides or live chat
    session engines):

    * engine: first nonempty of ``deep_research.engine``, ``engine.default``
    * model: first nonempty of ``deep_research.model``, ``server.model``,
      ``intelligence.default_model``
    """
    engine = _first_nonempty(
        _get(config, "deep_research.engine", ""),
        _get(config, "engine.default", ""),
    )
    model = _first_nonempty(
        _get(config, "deep_research.model", ""),
        _get(config, "server.model", ""),
        _get(config, "intelligence.default_model", ""),
    )
    return engine, model


def _scan_chunks_surface_active(config: Any, tools: set[str] | None = None) -> bool:
    """Whether scan_chunks is configured or auto-installed via Deep Research."""
    active = tools if tools is not None else _configured_tools(config)
    if active & KNOWLEDGE_ENGINE_TOOLS:
        return True
    agent = str(_get(config, "agent.default_agent", "") or "").strip().lower()
    return agent in {"deep_research", "research"}


def _knowledge_store_exists(root: Path) -> bool:
    """True when knowledge.db exists under the OpenJarvis home (metadata only)."""
    return (root / "knowledge.db").exists()


def _audit_knowledge_cloud_composition(
    config: Any,
    root: Path,
    builder: _FindingBuilder,
) -> None:
    """Flag local knowledge chunks routed toward cloud Deep Research inference."""
    tools = _configured_tools(config)
    scan_active = _scan_chunks_surface_active(config, tools)
    knowledge_exists = _knowledge_store_exists(root)
    engine, model = _effective_deep_research_target(config)
    cloud_target = _target_is_cloud(engine, model)

    if knowledge_exists and cloud_target:
        # Deep Research auto-installs ScanChunksTool when knowledge.db exists.
        evidence_parts = [
            "knowledge.db exists",
            (
                "effective deep_research engine = "
                f"{_quote(engine) if engine else '<empty>'}"
            ),
            (
                "effective deep_research model = "
                f"{_quote(model) if model else '<empty>'}"
            ),
        ]
        if tools & KNOWLEDGE_ENGINE_TOOLS:
            evidence_parts.append(
                f"configured tool(s) = {_format_tools(tools & KNOWLEDGE_ENGINE_TOOLS)}"
            )
        else:
            evidence_parts.append(
                "deep research auto-installs scan_chunks when knowledge.db exists"
            )
        builder.add(
            finding_id="knowledge-chunks-to-cloud-risk",
            status="fail",
            title="Local knowledge chunks may be sent to cloud inference",
            potential_data_path=(
                "local knowledge.db chunks -> scan_chunks / Deep Research -> "
                "cloud inference"
            ),
            evidence="; ".join(evidence_parts),
            recommendation=(
                "Use a local Deep Research engine/model when knowledge.db contains "
                "sensitive documents, or remove cloud defaults before scanning chunks."
            ),
        )
    elif scan_active:
        if tools & KNOWLEDGE_ENGINE_TOOLS:
            evidence = (
                f"configured tool(s) = {_format_tools(tools & KNOWLEDGE_ENGINE_TOOLS)}"
            )
        else:
            agent_name = _get(config, "agent.default_agent", "")
            evidence = f"agent.default_agent = {_quote(agent_name)}"
        # Local effective target is informational; unset/unknown stays warn.
        status: Status = "info" if engine and not cloud_target else "warn"
        builder.add(
            finding_id="knowledge-engine-tool-configured",
            status=status,
            title="Knowledge chunk scanning routes local chunks to an inference engine",
            potential_data_path=(
                "local knowledge-store chunks -> configured inference engine"
            ),
            evidence=evidence,
            recommendation=(
                "Review knowledge.db contents and the effective Deep Research "
                "engine/model before scanning sensitive documents."
            ),
        )


def _audit_security_settings(
    config: Any,
    builder: _FindingBuilder,
    *,
    has_external_surface: bool,
) -> None:
    profile = str(_get(config, "security.profile", "") or "").strip()
    if not profile:
        builder.add(
            finding_id="security-profile-unset",
            status="info",
            title="Security profile is not set",
            potential_data_path="security defaults -> guardrails and server posture",
            evidence="security.profile is empty",
            recommendation=(
                "Set security.profile to personal, shared, or server to apply "
                "a documented guardrails preset."
            ),
        )

    if not has_external_surface:
        return

    if bool(_get(config, "security.local_engine_bypass", False)):
        builder.add(
            finding_id="security-local-engine-bypass-enabled",
            status="warn",
            title="Local engine guardrail bypass is enabled with external surfaces",
            potential_data_path=(
                "external or cloud-bound prompts/outputs -> guardrails bypass "
                "for local engines"
            ),
            evidence=(
                "security.local_engine_bypass = true with external or "
                "cloud-capable settings"
            ),
            recommendation=(
                "Disable local_engine_bypass unless the external surface is "
                "intentional and reviewed."
            ),
        )

    if bool(_get(config, "security.local_tool_bypass", False)):
        builder.add(
            finding_id="security-local-tool-bypass-enabled",
            status="warn",
            title="Local tool guardrail bypass is enabled with external surfaces",
            potential_data_path=(
                "external or cloud-bound tool arguments/results -> guardrails bypass"
            ),
            evidence=(
                "security.local_tool_bypass = true with external or "
                "cloud-capable settings"
            ),
            recommendation=(
                "Disable local_tool_bypass unless the external surface is "
                "intentional and reviewed."
            ),
        )


def _audit_memory_cloud_composition(
    config: Any,
    builder: _FindingBuilder,
) -> None:
    context_from_memory = bool(_get(config, "agent.context_from_memory", False))
    active_cloud = _primary_cloud_signals(config)

    if context_from_memory and active_cloud:
        builder.add(
            finding_id="memory-context-to-cloud-risk",
            status="fail",
            title="Local memory may be injected into cloud-bound prompts",
            potential_data_path=(
                "indexed local memory -> prompt context -> cloud inference provider"
            ),
            evidence=(
                "agent.context_from_memory = true; cloud setting(s) = "
                + ", ".join(active_cloud)
            ),
            recommendation=(
                "Disable agent.context_from_memory before using cloud inference, "
                "or use local engines when indexed memory contains sensitive data."
            ),
        )
    elif context_from_memory:
        builder.add(
            finding_id="memory-context-injection-enabled",
            status="info",
            title="Memory context injection is enabled",
            potential_data_path="indexed local memory -> future prompt context",
            evidence="agent.context_from_memory = true",
            recommendation=(
                "Keep indexed memory scoped to data that may safely appear in future "
                "prompts, especially if cloud engines are enabled later."
            ),
        )


def _audit_trace_and_learning_settings(
    config: Any,
    builder: _FindingBuilder,
) -> None:
    if bool(_get(config, "traces.enabled", False)):
        builder.add(
            finding_id="traces-enabled",
            status="warn",
            title="Trace capture is enabled",
            potential_data_path=(
                "prompts, outputs, tool calls, and tool results -> traces database"
            ),
            evidence="traces.enabled = true",
            recommendation=(
                "Disable traces when debugging or trace-driven learning is not "
                "needed. Treat traces.db as sensitive when enabled."
            ),
        )

    if bool(_get(config, "learning.enabled", False)):
        builder.add(
            finding_id="learning-enabled",
            status="warn",
            title="Learning from local runtime data is enabled",
            potential_data_path=(
                "local traces/telemetry/feedback -> routing, agent, skill, or "
                "model updates"
            ),
            evidence="learning.enabled = true",
            recommendation=(
                "Review active learning sub-policies before using sensitive traces."
            ),
        )

    if bool(_get(config, "learning.training_enabled", False)):
        builder.add(
            finding_id="training-enabled",
            status="warn",
            title="Training pipeline is enabled",
            potential_data_path="trace-derived examples -> model adapters",
            evidence="learning.training_enabled = true",
            recommendation=(
                "Disable training unless trace reuse for model updates is intentional."
            ),
        )

    if bool(_get(config, "learning.auto_update", False)):
        builder.add(
            finding_id="learning-auto-update-enabled",
            status="warn",
            title="Automatic learning updates are enabled",
            potential_data_path="runtime feedback/traces -> automatic updates",
            evidence="learning.auto_update = true",
            recommendation=(
                "Use manual updates when explicit review is needed before "
                "trace-derived changes."
            ),
        )

    spec_search_enabled = bool(_get(config, "learning.spec_search.enabled", False))
    teacher_engine = _get(config, "learning.spec_search.teacher_engine", "")
    teacher_model = _get(config, "learning.spec_search.teacher_model", "")
    if spec_search_enabled and _is_cloud_value(teacher_engine):
        builder.add(
            finding_id="spec-search-cloud-teacher-enabled",
            status="fail",
            title="LLM-guided spec search uses a cloud teacher engine",
            potential_data_path=(
                "diagnostics/spec-search context -> cloud teacher model"
            ),
            evidence=(
                "learning.spec_search.enabled = true; "
                f"teacher_engine = {_quote(teacher_engine)}; "
                f"teacher_model = {_quote(teacher_model)}"
            ),
            recommendation=(
                "Use a local teacher engine/model or keep spec search disabled for "
                "local-only operation."
            ),
        )


def _audit_tool_surfaces(config: Any, builder: _FindingBuilder) -> None:
    tools = _configured_tools(config)

    if tools & WEB_SEARCH_TOOLS:
        destination = _web_search_destination()
        builder.add(
            finding_id="web-search-tool-configured",
            status="warn",
            title="Web search tool is configured",
            potential_data_path=(f"user or agent search query -> {destination}"),
            evidence=(
                f"configured tool(s) = {_format_tools(tools & WEB_SEARCH_TOOLS)}"
            ),
            recommendation=(
                "Review search queries before using web search with sensitive prompts."
            ),
        )

    if tools & BROWSER_TOOLS:
        builder.add(
            finding_id="browser-tool-configured",
            status="warn",
            title="Browser automation tool is configured",
            potential_data_path="agent browser actions -> external web pages",
            evidence=f"configured tool(s) = {_format_tools(tools & BROWSER_TOOLS)}",
            recommendation=(
                "Use browser automation only when web interactions are intentional."
            ),
        )

    if tools & GENERIC_NETWORK_TOOLS:
        builder.add(
            finding_id="generic-network-tool-configured",
            status="warn",
            title="Generic HTTP/network tool is configured",
            potential_data_path=("HTTP arguments, headers, and body -> external URL"),
            evidence=(
                f"configured tool(s) = {_format_tools(tools & GENERIC_NETWORK_TOOLS)}"
            ),
            recommendation=(
                "Review request destinations and payloads before using HTTP tools with "
                "sensitive data."
            ),
        )

    if tools & WEATHER_TOOLS:
        builder.add(
            finding_id="weather-tool-configured",
            status="warn",
            title="External weather lookup tool is configured",
            potential_data_path=(
                "user or agent location query -> OpenWeatherMap weather service"
            ),
            evidence=f"configured tool(s) = {_format_tools(tools & WEATHER_TOOLS)}",
            recommendation=(
                "Avoid sending sensitive or precise locations unless the external "
                "weather lookup is intentional."
            ),
        )

    if tools & CHANNEL_OUTBOUND_TOOLS:
        builder.add(
            finding_id="channel-outbound-tool-configured",
            status="warn",
            title="Channel outbound messaging tool is configured",
            potential_data_path="message content -> external messaging channel",
            evidence=(
                f"configured tool(s) = {_format_tools(tools & CHANNEL_OUTBOUND_TOOLS)}"
            ),
            recommendation=(
                "Review channel targets and message content before enabling outbound "
                "messaging tools."
            ),
        )

    cloud_media = tools & CLOUD_MEDIA_TOOLS
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
            evidence=f"configured tool(s) = {_format_tools(cloud_media)}",
            recommendation=(
                "Review prompts and local media files before sending them to external "
                "media providers."
            ),
        )

    # scan_chunks / Deep Research knowledge routing is handled in
    # _audit_knowledge_cloud_composition (needs knowledge.db existence).

    local_access = tools & LOCAL_ACCESS_TOOLS
    if local_access:
        builder.add(
            finding_id="local-access-tools-configured",
            status="info",
            title="Local file, shell, or code tools are configured",
            potential_data_path="local files/process output -> agent context",
            evidence=f"configured tool(s) = {_format_tools(local_access)}",
            recommendation=(
                "Review tool permissions and prompts before giving the agent access "
                "to sensitive local files or command output."
            ),
        )

    mcp_enabled = bool(_get(config, "tools.mcp.enabled", False))
    mcp_servers = str(_get(config, "tools.mcp.servers", "") or "").strip()
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
    engine = (os.environ.get("OPENJARVIS_WEB_SEARCH_ENGINE") or "auto").strip().lower()
    if engine not in {"auto", "youcom", "tavily", "duckduckgo", "serply"}:
        engine = "auto"
    if engine == "auto":
        if os.environ.get("TAVILY_API_KEY"):
            engine = "tavily"
        elif os.environ.get("YOUDOTCOM_API_KEY"):
            engine = "youcom"
        elif os.environ.get("SERPLY_API_KEY"):
            engine = "serply"
        else:
            engine = "youcom"

    if engine == "tavily":
        return "Tavily web search API"
    if engine == "duckduckgo":
        return "DuckDuckGo (HTML scrape)"
    if engine == "serply":
        location = os.environ.get("SERPLY_PROXY_LOCATION")
        if location:
            return f"Serply web search API (Google SERP, region {location})"
        return "Serply web search API (Google SERP)"
    tier = "keyed" if os.environ.get("YOUDOTCOM_API_KEY") else "keyless free tier"
    return f"You.com web search API ({tier})"


def _iter_local_store_targets(
    root: Path,
    config: Any | None,
) -> Iterable[tuple[str, str, Path, str, Status]]:
    """Yield store targets as (finding_id, title, path, location_label, status)."""
    targets: dict[str, tuple[str, Path, str, Status]] = {}

    for finding_id, title, relative_path, status in LOCAL_STORE_CANDIDATES:
        targets[finding_id] = (title, root / relative_path, relative_path, status)

    if config is not None:
        for finding_id, title, dotted_path, status in _CONFIG_STORE_PATHS:
            raw = str(_get(config, dotted_path, "") or "").strip()
            if not raw:
                if finding_id == "scheduler-db":
                    path = root / "scheduler.db"
                    location = "scheduler.db"
                else:
                    continue
            else:
                path = Path(raw).expanduser()
                if not path.is_absolute():
                    path = root / path
                try:
                    resolved_path = path.resolve()
                except OSError:
                    resolved_path = path
                location = _location_label(resolved_path, root)

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
    builder: _FindingBuilder,
    *,
    config: Any | None = None,
) -> None:
    if not root.exists():
        return
    for finding_id, title, path, location, status in _iter_local_store_targets(
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
        permission_note = _permission_note(path)
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


def _audit_server_exposure(config: Any, builder: _FindingBuilder) -> None:
    host = str(_get(config, "server.host", "") or "").strip()
    if not _is_loopback_host(host):
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
            evidence=f"server.host = {_quote(host)}",
            recommendation=(
                "Use server.host = '127.0.0.1' unless LAN exposure is intentional."
            ),
        )

    a2a_enabled = bool(_get(config, "a2a.enabled", False))
    a2a_token = str(_get(config, "a2a.auth_token", "") or "")
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


def _audit_frontend_storage_scope(builder: _FindingBuilder) -> None:
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


def _audit_skills_and_digest(config: Any, builder: _FindingBuilder) -> None:
    if bool(_get(config, "skills.enabled", False)):
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

    if bool(_get(config, "skills.auto_sync", False)):
        builder.add(
            finding_id="skills-auto-sync-enabled",
            status="warn",
            title="Skill auto-sync is enabled",
            potential_data_path="configured skill source -> local skill directory",
            evidence="skills.auto_sync = true",
            recommendation="Review external skill sources before enabling auto-sync.",
        )

    if bool(_get(config, "digest.enabled", False)):
        sources = sorted(set(_iter_digest_sources(config)) & PERSONAL_DIGEST_SOURCES)
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


def _audit_speech_settings(config: Any, builder: _FindingBuilder) -> None:
    speech_backend = str(_get(config, "speech.backend", "") or "").lower()
    if speech_backend in {"openai", "deepgram"}:
        builder.add(
            finding_id="cloud-speech-backend-configured",
            status="warn",
            title="Cloud speech backend configured",
            potential_data_path="speech audio or transcripts -> cloud speech provider",
            evidence=f"speech.backend = {_quote(speech_backend)}",
            recommendation=(
                "Use a local speech backend for local-only audio processing."
            ),
        )

    digest_enabled = bool(_get(config, "digest.enabled", False))
    tts_backend = str(_get(config, "digest.tts_backend", "") or "").lower()
    if digest_enabled and tts_backend in CLOUD_TTS_BACKENDS:
        builder.add(
            finding_id="cloud-tts-backend-configured",
            status="warn",
            title="Cloud text-to-speech backend configured for digests",
            potential_data_path=(
                "personal digest narrative -> cloud text-to-speech provider"
            ),
            evidence=f"digest.tts_backend = {_quote(tts_backend)}",
            recommendation=(
                "Use a local text-to-speech backend or disable digest audio when "
                "the generated narrative contains sensitive personal data."
            ),
        )


def _has_cloud_api_surface(config: Any | None, active_tools: set[str]) -> bool:
    """True when cloud inference/API-key surfaces are configured (not browser-only)."""
    if any(os.environ.get(name) for name in API_KEY_ENV_VARS):
        return True
    if active_tools & CLOUD_API_SURFACES:
        return True
    if config is None:
        return False
    if _primary_cloud_signals(config):
        return True
    deep_engine, deep_model = _effective_deep_research_target(config)
    if _target_is_cloud(deep_engine, deep_model):
        return True
    optimizer_provider = _get(config, "optimize.optimizer_provider", "")
    if _target_is_cloud(optimizer_provider, _get(config, "optimize.judge_model", "")):
        return True
    if str(_get(config, "speech.backend", "") or "").lower() in {
        "openai",
        "deepgram",
    }:
        return True
    if (
        bool(_get(config, "digest.enabled", False))
        and str(_get(config, "digest.tts_backend", "") or "").lower()
        in CLOUD_TTS_BACKENDS
    ):
        return True
    if bool(_get(config, "learning.spec_search.enabled", False)):
        return _target_is_cloud(
            _get(config, "learning.spec_search.teacher_engine", ""),
            _get(config, "learning.spec_search.teacher_model", ""),
        )
    return False


def _has_external_surface(config: Any | None, active_tools: set[str]) -> bool:
    """True when external egress or cloud/API surfaces are present."""
    if active_tools & EXTERNAL_TOOL_SURFACES:
        return True
    if (
        _scan_chunks_surface_active(config, active_tools)
        if config is not None
        else False
    ):
        return True
    return _has_cloud_api_surface(config, active_tools)


def _has_cloud_or_api_surface(config: Any | None, active_tools: set[str]) -> bool:
    """Backward-compatible alias for external-or-cloud surface detection."""
    return _has_external_surface(config, active_tools)


def _derive_verdict(findings: Iterable[DataBoundaryFinding]) -> str:
    finding_ids = {finding.id for finding in findings}
    statuses = {finding.status for finding in findings}

    if "memory-context-to-cloud-risk" in finding_ids:
        return "local memory may be sent to cloud inference"
    if "knowledge-chunks-to-cloud-risk" in finding_ids:
        return "local knowledge may be sent to cloud inference"
    if "config-root-error" in finding_ids:
        return "OpenJarvis home must be fixed before full data-boundary review"
    if "config-load-error" in finding_ids:
        return "configuration must be fixed before full data-boundary review"
    if "fail" in statuses:
        return "attention required for application data boundaries"
    if any(
        fid in finding_ids
        for fid in {
            "cloud-provider-configured",
            "cloud-preferred-engine-configured",
            "cloud-default-engine-configured",
            "cloud-default-model-configured",
            "cloud-speech-backend-configured",
            "cloud-tts-backend-configured",
            "deep-research-cloud-configured",
        }
    ):
        return "cloud-capable data boundaries configured"
    if "warn" in statuses:
        return "local sensitive stores or optional data flows detected"
    return "no fail or warn findings detected"


def _configured_tools(config: Any) -> set[str]:
    values: list[Any] = [
        _get(config, "tools.enabled", ""),
        _get(config, "agent.tools", ""),
    ]
    tools: set[str] = set()
    for value in values:
        if isinstance(value, str):
            raw_items = value.split(",")
        elif isinstance(value, Iterable):
            raw_items = list(value)
        else:
            raw_items = []
        for item in raw_items:
            normalized = str(item).strip().lower().replace("-", "_")
            if normalized:
                tools.add(normalized)
    return tools


def _truncate(text: str, limit: int = 240) -> str:
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"
