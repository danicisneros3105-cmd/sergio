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


# Moved to their own module (it looks its helpers up here).
from openjarvis.security import data_boundary_settings as _data_boundary_settings  # noqa: E402,I001

_audit_outbound_settings = _data_boundary_settings._audit_outbound_settings
_audit_telemetry_settings = _data_boundary_settings._audit_telemetry_settings
_audit_memory_service = _data_boundary_settings._audit_memory_service
_audit_deep_research_settings = _data_boundary_settings._audit_deep_research_settings
_effective_deep_research_target = (
    _data_boundary_settings._effective_deep_research_target
)
_scan_chunks_surface_active = _data_boundary_settings._scan_chunks_surface_active
_knowledge_store_exists = _data_boundary_settings._knowledge_store_exists
_audit_knowledge_cloud_composition = (
    _data_boundary_settings._audit_knowledge_cloud_composition
)
_audit_security_settings = _data_boundary_settings._audit_security_settings
_audit_memory_cloud_composition = (
    _data_boundary_settings._audit_memory_cloud_composition
)
_audit_trace_and_learning_settings = (
    _data_boundary_settings._audit_trace_and_learning_settings
)

# Moved to their own module (it looks its helpers up here).
from openjarvis.security import data_boundary_exposure as _data_boundary_exposure  # noqa: E402,I001

_audit_tool_surfaces = _data_boundary_exposure._audit_tool_surfaces
_web_search_destination = _data_boundary_exposure._web_search_destination
_iter_local_store_targets = _data_boundary_exposure._iter_local_store_targets
_audit_local_stores = _data_boundary_exposure._audit_local_stores
_audit_server_exposure = _data_boundary_exposure._audit_server_exposure
_audit_frontend_storage_scope = _data_boundary_exposure._audit_frontend_storage_scope
_audit_skills_and_digest = _data_boundary_exposure._audit_skills_and_digest
_audit_speech_settings = _data_boundary_exposure._audit_speech_settings
