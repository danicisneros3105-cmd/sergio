"""Data-boundary checks on configuration: outbound settings, telemetry, the
memory service, deep research, knowledge and memory stores combined with
cloud engines, security settings, traces and learning.

Split out of ``data_boundary_audit.py``; its names are looked up on that
module at call time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import openjarvis.security.data_boundary_audit as _dba
from openjarvis.security.data_boundary_surfaces import Status


def _audit_outbound_settings(config: Any, builder: _dba._FindingBuilder) -> None:
    if bool(_dba._get(config, "analytics.enabled", False)):
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

    provider = _dba._get(config, "intelligence.provider", "")
    if _dba._is_cloud_value(provider):
        builder.add(
            finding_id="cloud-provider-configured",
            status="warn",
            title="Cloud model provider configured",
            potential_data_path=(
                "prompts, memory context, and tool outputs -> cloud provider"
            ),
            evidence=f"intelligence.provider = {_dba._quote(provider)}",
            recommendation=(
                "Review what context is sent before enabling cloud inference, "
                "or use a local provider for local-only operation."
            ),
        )

    default_model = _dba._get(config, "intelligence.default_model", "")
    effective_engine = _dba._first_nonempty(
        _dba._get(config, "intelligence.preferred_engine", ""),
        _dba._get(config, "engine.default", ""),
        provider,
    )
    if _dba._target_is_cloud(effective_engine, default_model):
        builder.add(
            finding_id="cloud-default-model-configured",
            status="warn",
            title="Cloud default model configured",
            potential_data_path="model requests -> default cloud model",
            evidence=f"intelligence.default_model = {_dba._quote(default_model)}",
            recommendation=("Use a local default model for local-only operation."),
        )

    preferred_engine = _dba._get(config, "intelligence.preferred_engine", "")
    if _dba._is_cloud_value(preferred_engine):
        builder.add(
            finding_id="cloud-preferred-engine-configured",
            status="warn",
            title="Cloud preferred engine configured",
            potential_data_path="model requests -> preferred cloud engine",
            evidence=f"intelligence.preferred_engine = {_dba._quote(preferred_engine)}",
            recommendation="Use a local preferred engine for local-only operation.",
        )

    default_engine = _dba._get(config, "engine.default", "")
    if _dba._is_cloud_value(default_engine):
        builder.add(
            finding_id="cloud-default-engine-configured",
            status="warn",
            title="Cloud default engine configured",
            potential_data_path="model requests -> default cloud engine",
            evidence=f"engine.default = {_dba._quote(default_engine)}",
            recommendation="Use a local default engine for local-only operation.",
        )

    optimize_provider = _dba._get(config, "optimize.optimizer_provider", "")
    if _dba._is_cloud_value(optimize_provider):
        builder.add(
            finding_id="cloud-optimizer-provider-configured",
            status="info",
            title="Cloud optimizer provider is configured",
            potential_data_path="optimization context -> optimizer provider",
            evidence=f"optimize.optimizer_provider = {_dba._quote(optimize_provider)}",
            recommendation=(
                "Before running optimization, review whether examples, traces, "
                "or prompts may be sent to this provider."
            ),
        )

    judge_model = _dba._get(config, "optimize.judge_model", "")
    if _dba._target_is_cloud(optimize_provider, judge_model):
        builder.add(
            finding_id="cloud-judge-model-configured",
            status="info",
            title="Cloud judge model appears configured",
            potential_data_path="optimization examples/results -> judge model",
            evidence=f"optimize.judge_model = {_dba._quote(judge_model)}",
            recommendation="Use a local judge model for local-only optimization.",
        )


def _audit_telemetry_settings(config: Any, builder: _dba._FindingBuilder) -> None:
    if bool(_dba._get(config, "telemetry.enabled", False)):
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


def _audit_memory_service(config: Any, builder: _dba._FindingBuilder) -> None:
    if not bool(_dba._get(config, "tools.storage.enabled", False)):
        return
    has_cloud = bool(_dba._primary_cloud_signals(config))
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


def _audit_deep_research_settings(config: Any, builder: _dba._FindingBuilder) -> None:
    engine = _dba._get(config, "deep_research.engine", "")
    model = _dba._get(config, "deep_research.model", "")
    cloud_engine = _dba._is_cloud_value(engine)
    effective_engine, effective_model = _dba._effective_deep_research_target(config)
    cloud_model = bool(model) and _dba._target_is_cloud(
        effective_engine, effective_model
    )
    if not cloud_engine and not cloud_model:
        return
    evidence_parts = []
    if cloud_engine:
        evidence_parts.append(f"deep_research.engine = {_dba._quote(engine)}")
    if cloud_model:
        evidence_parts.append(f"deep_research.model = {_dba._quote(model)}")
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
    engine = _dba._first_nonempty(
        _dba._get(config, "deep_research.engine", ""),
        _dba._get(config, "engine.default", ""),
    )
    model = _dba._first_nonempty(
        _dba._get(config, "deep_research.model", ""),
        _dba._get(config, "server.model", ""),
        _dba._get(config, "intelligence.default_model", ""),
    )
    return engine, model


def _scan_chunks_surface_active(config: Any, tools: set[str] | None = None) -> bool:
    """Whether scan_chunks is configured or auto-installed via Deep Research."""
    active = tools if tools is not None else _dba._configured_tools(config)
    if active & _dba.KNOWLEDGE_ENGINE_TOOLS:
        return True
    agent = str(_dba._get(config, "agent.default_agent", "") or "").strip().lower()
    return agent in {"deep_research", "research"}


def _knowledge_store_exists(root: Path) -> bool:
    """True when knowledge.db exists under the OpenJarvis home (metadata only)."""
    return (root / "knowledge.db").exists()


def _audit_knowledge_cloud_composition(
    config: Any,
    root: Path,
    builder: _dba._FindingBuilder,
) -> None:
    """Flag local knowledge chunks routed toward cloud Deep Research inference."""
    tools = _dba._configured_tools(config)
    scan_active = _dba._scan_chunks_surface_active(config, tools)
    knowledge_exists = _dba._knowledge_store_exists(root)
    engine, model = _dba._effective_deep_research_target(config)
    cloud_target = _dba._target_is_cloud(engine, model)

    if knowledge_exists and cloud_target:
        # Deep Research auto-installs ScanChunksTool when knowledge.db exists.
        evidence_parts = [
            "knowledge.db exists",
            (
                "effective deep_research engine = "
                f"{_dba._quote(engine) if engine else '<empty>'}"
            ),
            (
                "effective deep_research model = "
                f"{_dba._quote(model) if model else '<empty>'}"
            ),
        ]
        if tools & _dba.KNOWLEDGE_ENGINE_TOOLS:
            evidence_parts.append(
                f"configured tool(s) = {_dba._format_tools(tools & _dba.KNOWLEDGE_ENGINE_TOOLS)}"
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
        if tools & _dba.KNOWLEDGE_ENGINE_TOOLS:
            evidence = f"configured tool(s) = {_dba._format_tools(tools & _dba.KNOWLEDGE_ENGINE_TOOLS)}"
        else:
            agent_name = _dba._get(config, "agent.default_agent", "")
            evidence = f"agent.default_agent = {_dba._quote(agent_name)}"
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
    builder: _dba._FindingBuilder,
    *,
    has_external_surface: bool,
) -> None:
    profile = str(_dba._get(config, "security.profile", "") or "").strip()
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

    if bool(_dba._get(config, "security.local_engine_bypass", False)):
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

    if bool(_dba._get(config, "security.local_tool_bypass", False)):
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
    builder: _dba._FindingBuilder,
) -> None:
    context_from_memory = bool(_dba._get(config, "agent.context_from_memory", False))
    active_cloud = _dba._primary_cloud_signals(config)

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
    builder: _dba._FindingBuilder,
) -> None:
    if bool(_dba._get(config, "traces.enabled", False)):
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

    if bool(_dba._get(config, "learning.enabled", False)):
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

    if bool(_dba._get(config, "learning.training_enabled", False)):
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

    if bool(_dba._get(config, "learning.auto_update", False)):
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

    spec_search_enabled = bool(_dba._get(config, "learning.spec_search.enabled", False))
    teacher_engine = _dba._get(config, "learning.spec_search.teacher_engine", "")
    teacher_model = _dba._get(config, "learning.spec_search.teacher_model", "")
    if spec_search_enabled and _dba._is_cloud_value(teacher_engine):
        builder.add(
            finding_id="spec-search-cloud-teacher-enabled",
            status="fail",
            title="LLM-guided spec search uses a cloud teacher engine",
            potential_data_path=(
                "diagnostics/spec-search context -> cloud teacher model"
            ),
            evidence=(
                "learning.spec_search.enabled = true; "
                f"teacher_engine = {_dba._quote(teacher_engine)}; "
                f"teacher_model = {_dba._quote(teacher_model)}"
            ),
            recommendation=(
                "Use a local teacher engine/model or keep spec search disabled for "
                "local-only operation."
            ),
        )


__all__ = [
    "_audit_outbound_settings",
    "_audit_telemetry_settings",
    "_audit_memory_service",
    "_audit_deep_research_settings",
    "_effective_deep_research_target",
    "_scan_chunks_surface_active",
    "_knowledge_store_exists",
    "_audit_knowledge_cloud_composition",
    "_audit_security_settings",
    "_audit_memory_cloud_composition",
    "_audit_trace_and_learning_settings",
]
