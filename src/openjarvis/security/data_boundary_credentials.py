"""Credential checks of the data-boundary audit: connector tokens, API keys
in the environment, messaging-channel secrets and their local folders.
Only presence is checked, never the secret itself. Split out of
``data_boundary_audit.py``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openjarvis.security.data_boundary_helpers import (
    _get,
    _non_empty_paths,
)
from openjarvis.security.data_boundary_surfaces import (
    API_KEY_ENV_VARS,
    CHANNEL_REFERENCE_ENV_VARS,
    CHANNEL_REFERENCE_FIELDS,
    CHANNEL_SECRET_ENV_VARS,
    CHANNEL_SECRET_FIELDS,
    GENERIC_CREDENTIAL_ENV_VARS,
    Status,
)


def _audit_connector_credentials(root: Path, builder: _FindingBuilder) -> None:
    connectors_dir = root / "connectors"
    if not connectors_dir.exists():
        return
    for path in sorted(connectors_dir.glob("*.json")):
        digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:8]
        builder.add(
            finding_id=f"connector-token-{digest}",
            status="info",
            title="Connector credential file is present",
            potential_data_path="connector OAuth/API credentials -> local file",
            evidence="credential file exists under connectors/*.json",
            recommendation=(
                "This audit did not read the file contents. Use --show-paths for "
                "local debugging, and review account scopes and token rotation."
            ),
            location="connectors/<redacted>.json",
            absolute_location=str(path),
        )


def _audit_environment_credentials(
    config: Any | None,
    builder: _FindingBuilder,
    *,
    active_tools: set[str],
) -> None:
    active_values: set[str] = set(active_tools)
    if config is not None:
        active_values.update(
            {
                str(_get(config, "intelligence.provider", "")).lower(),
                str(_get(config, "intelligence.preferred_engine", "")).lower(),
                str(_get(config, "engine.default", "")).lower(),
                str(_get(config, "intelligence.default_model", "")).lower(),
                str(_get(config, "speech.backend", "")).lower(),
            }
        )
        if bool(_get(config, "digest.enabled", False)):
            active_values.add(str(_get(config, "digest.tts_backend", "")).lower())

    for env_name, (purpose, aliases) in sorted(API_KEY_ENV_VARS.items()):
        if not os.environ.get(env_name):
            continue
        active = any(alias in value for alias in aliases for value in active_values)
        status: Status = "warn" if active else "info"
        builder.add(
            finding_id=f"env-credential-{env_name.lower()}",
            status=status,
            title=f"Cloud/API credential available in environment: {env_name}",
            potential_data_path=f"process environment -> {purpose}",
            evidence=f"{env_name} is set; value was not read or printed",
            recommendation=(
                "Unset this variable for local-only operation. The audit reports "
                "only presence and never prints credential values."
            ),
        )


def _audit_channel_settings(config: Any, builder: _FindingBuilder) -> None:
    channel_enabled = bool(_get(config, "channel.enabled", False))
    default_channel = str(_get(config, "channel.default_channel", "") or "")
    configured_secrets = _non_empty_paths(config, CHANNEL_SECRET_FIELDS)
    configured_refs = _non_empty_paths(config, CHANNEL_REFERENCE_FIELDS)

    if channel_enabled:
        evidence = "channel.enabled = true"
        if default_channel:
            evidence += "; channel.default_channel is set; value redacted"
        has_channel_surface = bool(
            default_channel or configured_secrets or configured_refs
        )
        status: Status = "warn" if has_channel_surface else "info"
        builder.add(
            finding_id="channels-enabled",
            status=status,
            title="Messaging channels are enabled",
            potential_data_path=(
                "user messages and assistant replies -> configured channel services"
            ),
            evidence=evidence,
            recommendation=(
                "Review active channel credentials and account scopes before "
                "routing sensitive conversations through external services."
            ),
        )

    for dotted_path, label, service in configured_secrets:
        status = "warn" if channel_enabled else "info"
        normalized = dotted_path.replace(".", "-").replace("_", "-")
        builder.add(
            finding_id=f"channel-secret-{normalized}",
            status=status,
            title=f"Channel secret configured: {label}",
            potential_data_path=f"OpenJarvis channel messages -> {service}",
            evidence=f"{dotted_path} is non-empty; value was not printed",
            recommendation=(
                "Use dedicated bot/service credentials and rotate them after tests. "
                "The audit reports only presence and never prints secret values."
            ),
        )

    for dotted_path, label, service in configured_refs:
        status = "warn" if channel_enabled else "info"
        normalized = dotted_path.replace(".", "-").replace("_", "-")
        builder.add(
            finding_id=f"channel-reference-{normalized}",
            status=status,
            title=f"Channel endpoint or identifier configured: {label}",
            potential_data_path=f"OpenJarvis channel messages -> {service}",
            evidence=f"{dotted_path} is non-empty; value was not printed",
            recommendation=(
                "Review configured channel endpoints and identifiers before "
                "routing sensitive conversations through external services."
            ),
        )


def _audit_channel_environment_credentials(
    config: Any | None,
    builder: _FindingBuilder,
) -> None:
    channel_enabled = bool(_get(config, "channel.enabled", False)) if config else False
    for env_name, purpose in sorted(CHANNEL_SECRET_ENV_VARS.items()):
        if not os.environ.get(env_name):
            continue
        status: Status = "warn" if channel_enabled else "info"
        builder.add(
            finding_id=f"channel-env-secret-{env_name.lower()}",
            status=status,
            title=f"Channel secret available in environment: {env_name}",
            potential_data_path=f"process environment -> {purpose}",
            evidence=f"{env_name} is set; value was not read or printed",
            recommendation=(
                "Unset channel secrets when external messaging is not in use. "
                "The audit reports only presence and never prints secret values."
            ),
        )

    for env_name, purpose in sorted(CHANNEL_REFERENCE_ENV_VARS.items()):
        if not os.environ.get(env_name):
            continue
        status = "warn" if channel_enabled else "info"
        builder.add(
            finding_id=f"channel-env-reference-{env_name.lower()}",
            status=status,
            title=f"Channel endpoint or identifier in environment: {env_name}",
            potential_data_path=f"process environment -> {purpose}",
            evidence=f"{env_name} is set; value was not read or printed",
            recommendation=(
                "Unset channel endpoint variables when external messaging is not "
                "in use. The audit reports only presence."
            ),
        )


def _audit_local_channel_credential_dirs(
    config: Any,
    root: Path,
    builder: _FindingBuilder,
) -> None:
    auth_dir_value = str(
        _get(config, "channel.whatsapp_baileys.auth_dir", "") or ""
    ).strip()
    candidates: list[tuple[Path, str]] = []
    if auth_dir_value:
        candidates.append((Path(auth_dir_value).expanduser(), "<redacted>"))
    candidates.append(
        (root / "whatsapp_baileys_bridge" / "auth", "whatsapp_baileys_bridge/auth")
    )

    seen_resolved: set[str] = set()
    for path, location in candidates:
        try:
            resolved = path.resolve()
            resolved_key = str(resolved)
        except OSError:
            resolved = path
            resolved_key = str(path)
        if resolved_key in seen_resolved or not path.exists():
            continue
        seen_resolved.add(resolved_key)
        path_digest = hashlib.sha256(resolved_key.encode("utf-8")).hexdigest()[:8]
        builder.add(
            finding_id=f"channel-local-credential-dir-whatsapp-baileys-{path_digest}",
            status="info",
            title="WhatsApp Baileys credential directory is present",
            potential_data_path="WhatsApp session credentials -> local directory",
            evidence="credential directory exists; contents were not inspected",
            recommendation=(
                "Review permissions and retention for local messaging session "
                "credentials."
            ),
            location=location,
            absolute_location=resolved_key,
        )


def _audit_generic_runtime_credentials(builder: _FindingBuilder) -> None:
    """Report presence-only findings for remaining TOOL_CREDENTIALS env keys."""
    for env_name in sorted(GENERIC_CREDENTIAL_ENV_VARS):
        if not os.environ.get(env_name):
            continue
        builder.add(
            finding_id=f"env-credential-generic-{env_name.lower()}",
            status="info",
            title=f"Runtime credential available in environment: {env_name}",
            potential_data_path=f"process environment -> {env_name}",
            evidence=f"{env_name} is set; value was not read or printed",
            recommendation=(
                "Unset unused runtime credentials. The audit reports only presence "
                "and never prints credential values."
            ),
        )


if TYPE_CHECKING:  # annotations only; the builder lives with the report
    from openjarvis.security.data_boundary_audit import _FindingBuilder
