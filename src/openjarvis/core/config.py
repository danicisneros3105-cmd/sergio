"""Configuration loading, hardware detection, and engine recommendation.

User configuration lives at ``~/.openjarvis/config.toml``.  ``load_config()``
detects hardware, fills sensible defaults, then overlays any user overrides
found in the TOML file.
"""

from __future__ import annotations

import functools
import os
import platform  # noqa: F401 - config_hardware looks it up here
import shutil  # noqa: F401 - config_hardware looks it up here
import subprocess  # noqa: F401 - config_hardware looks it up here
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Optional,
)

from openjarvis.core.config_channels import (  # noqa: F401 (re-exported)
    BlueBubblesChannelConfig,
    ChannelConfig,
    DiscordChannelConfig,
    EmailChannelConfig,
    FeishuChannelConfig,
    GoogleChatChannelConfig,
    IRCChannelConfig,
    MatrixChannelConfig,
    MattermostChannelConfig,
    SignalChannelConfig,
    SlackChannelConfig,
    TeamsChannelConfig,
    TelegramChannelConfig,
    WebChatChannelConfig,
    WebhookChannelConfig,
    WhatsAppBaileysChannelConfig,
    WhatsAppChannelConfig,
)
from openjarvis.core.config_engines import (  # noqa: F401 (re-exported)
    AfmEngineConfig,
    AppleFmEngineConfig,
    EngineConfig,
    ExoEngineConfig,
    GemmaCppEngineConfig,
    LemonadeEngineConfig,
    LlamaCppEngineConfig,
    LMStudioEngineConfig,
    MLXEngineConfig,
    NexaEngineConfig,
    OllamaEngineConfig,
    SGLangEngineConfig,
    UzuEngineConfig,
    VLLMEngineConfig,
)
from openjarvis.core.config_learning import (  # noqa: F401 (re-exported)
    ACEOptimizerConfig,
    AgentLearningConfig,
    DeepResearchConfig,
    DSPyOptimizerConfig,
    GEPAOptimizerConfig,
    GRPOConfig,
    IntelligenceConfig,
    IntelligenceLearningConfig,
    LearningConfig,
    MetricsConfig,
    RoutingLearningConfig,
    SFTConfig,
    SkillsLearningConfig,
    SpecSearchCompositeRewardConfig,
    SpecSearchLearningConfig,
)
from openjarvis.core.config_sections import (  # noqa: F401 (re-exported)
    A2AConfig,
    AgentConfig,
    AgentManagerConfig,
    AnalyticsConfig,
    BrowserConfig,
    ClackyExtensionConfig,
    CompressionConfig,
    CoworkConfig,
    DigestConfig,
    DigestSectionConfig,
    ExtensionsConfig,
    GlobeExtensionConfig,
    MCPConfig,
    MemoryFilesConfig,
    OperatorsConfig,
    OptimizeConfig,
    PhoneConfig,
    ProactiveConfig,
    SandboxConfig,
    SchedulerConfig,
    ServerConfig,
    SessionConfig,
    SkillsConfig,
    SkillSourceConfig,
    SpeechConfig,
    StorageConfig,
    SystemPromptConfig,
    TelemetryConfig,
    ToolsConfig,
    TracesConfig,
    TunnelConfig,
    WeatherToolConfig,
    WorkflowConfig,
)
from openjarvis.core.paths import (
    ConfigurationError,
    get_cache_dir,
    get_config_dir,
    get_config_path,
    get_data_dir,
)

if TYPE_CHECKING:
    # Only used by type-checkers (mypy/pyright) for the ``JarvisConfig.mining``
    # field annotation. The runtime import is deferred inside
    # ``_parse_mining_section()`` to break the import cycle:
    # ``mining/_stubs.py`` imports ``HardwareInfo`` from this module at its
    # top level.
    from openjarvis.mining._stubs import MiningConfig

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Hardware dataclasses
# ---------------------------------------------------------------------------

# Legacy names, kept for the ~45 modules that import them. They are resolved
# once at import via the env-aware resolver in ``openjarvis.core.paths`` (the
# install-script model: ``OPENJARVIS_HOME`` / ``XDG_DATA_HOME`` are set before
# the process starts). They are real module attributes — not computed lazily —
# so existing tests can ``monkeypatch.setattr`` them and so dataclass-instance
# defaults stay consistent. Code that must react to a mid-process env change
# (or wants the override regardless of import order) should call
# ``get_config_dir()`` / ``get_config_path()`` directly; the dataclass field
# defaults below already do this via ``default_factory``.
DEFAULT_CONFIG_DIR = get_config_dir()
DEFAULT_CONFIG_PATH = get_config_path()


def _ensure_config_dir() -> Path:
    """Ensure the config directory exists with restrictive permissions."""
    from openjarvis.security.file_utils import secure_mkdir

    return secure_mkdir(get_config_dir())


@dataclass(slots=True)
class GpuInfo:
    """Detected GPU metadata."""

    vendor: str = ""
    name: str = ""
    vram_gb: float = 0.0
    compute_capability: str = ""
    count: int = 0


@dataclass(slots=True)
class HardwareInfo:
    """Detected system hardware."""

    platform: str = ""
    cpu_brand: str = ""
    cpu_count: int = 0
    ram_gb: float = 0.0
    gpu: Optional[GpuInfo] = None


# ---------------------------------------------------------------------------
# Hardware detection helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Engine recommendation
# ---------------------------------------------------------------------------


# Explicit tier table: (max_ram_gb, model_id).
# Walked in order — first tier where available_gb <= max_ram is chosen.
# Uses dense Qwen3.5 models at increasing parameter sizes.
_MODEL_TIERS = [
    (8, "qwen3.5:2b"),
    (16, "qwen3.5:4b"),
    (32, "qwen3.5:9b"),
    (64, "qwen3.5:27b"),
]
_MODEL_TIER_FALLBACK = "qwen3.5:27b"
_LEMONADE_DEFAULT_MODEL = "Qwen3.6-35B-A3B-GGUF"


# ---------------------------------------------------------------------------
# Configuration hierarchy
# ---------------------------------------------------------------------------


# Backward-compatibility alias
MemoryConfig = StorageConfig


_MAX_EXTERNAL_JSON_BYTES = 4 * 1024 * 1024


def resolve_mcp_servers(raw: str, config_dir: Path) -> list[dict[str, Any]]:
    """Resolve MCP server configuration from inline JSON or an external file.

    Wraps :func:`resolve_json_or_file` with MCP-specific validation:
    a single server object ``{...}`` is automatically wrapped in a list,
    and the result must be a ``list``.
    """
    import json

    result = resolve_json_or_file(raw, config_dir)
    if result is None:
        return []
    if isinstance(result, dict):
        result = [result]
    if not isinstance(result, list):
        raise ValueError(
            "MCP servers config must be a JSON array or object, "
            f"got {type(result).__name__}"
        )

    servers: list[dict[str, Any]] = []
    for index, server in enumerate(result):
        if isinstance(server, str):
            try:
                server = json.loads(server)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"MCP server entry {index} is not a valid JSON object"
                ) from exc
        if not isinstance(server, dict):
            raise ValueError(f"MCP server entry {index} must be a JSON object")
        servers.append(server)
    return servers


@dataclass(slots=True)
class CapabilitiesConfig:
    """RBAC capability system settings."""

    enabled: bool = False
    policy_path: str = ""
    default_deny: bool = False


@dataclass(slots=True)
class SecurityConfig:
    """Security guardrails settings."""

    enabled: bool = True
    scan_input: bool = True
    scan_output: bool = True
    mode: str = "redact"  # "redact" | "warn" | "block"
    secret_scanner: bool = True
    pii_scanner: bool = True
    audit_log_path: str = field(
        default_factory=lambda: str(get_config_dir() / "audit.db")
    )
    enforce_tool_confirmation: bool = True
    merkle_audit: bool = True
    signing_key_path: str = ""
    ssrf_protection: bool = True
    rate_limit_enabled: bool = True
    rate_limit_rpm: int = 60
    rate_limit_burst: int = 10
    local_engine_bypass: bool = False
    local_tool_bypass: bool = False
    # "personal" (single user on this machine, loopback only) is the safe
    # default; "shared" and "server" tighten it; "" opts out of profiles.
    profile: str = "personal"
    vault_key_path: str = field(
        default_factory=lambda: str(get_config_dir() / ".vault_key")
    )
    capabilities: CapabilitiesConfig = field(default_factory=CapabilitiesConfig)


# ---------------------------------------------------------------------------
# Security profile presets
# ---------------------------------------------------------------------------

_SECURITY_PROFILES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "personal": {
        "security": {
            "mode": "redact",
            "rate_limit_enabled": True,
            "local_engine_bypass": False,
            "local_tool_bypass": False,
        },
        "server": {
            "host": "127.0.0.1",
        },
    },
    "shared": {
        "security": {
            "mode": "redact",
            "rate_limit_enabled": True,
            "local_engine_bypass": False,
            "local_tool_bypass": False,
            "capabilities": {"enabled": True, "default_deny": True},
        },
        "server": {
            "host": "127.0.0.1",
        },
    },
    "server": {
        "security": {
            "mode": "block",
            "rate_limit_enabled": True,
            "rate_limit_rpm": 30,
            "rate_limit_burst": 5,
            "local_engine_bypass": False,
            "local_tool_bypass": False,
            "capabilities": {"enabled": True, "default_deny": True},
        },
        "server": {
            "host": "0.0.0.0",
        },
    },
}


def apply_security_profile(
    security_cfg: "SecurityConfig",
    server_cfg: "ServerConfig | None",
    *,
    overrides: "set[str] | None" = None,
    server_overrides: "set[str] | None" = None,
) -> None:
    """Expand a named security profile into config fields.

    Fields in *overrides* (explicitly set by the user in ``[security]``)
    and *server_overrides* (set in ``[server]``) are not overwritten by the
    profile, so a user who binds ``host = "0.0.0.0"`` keeps it.
    """
    profile = security_cfg.profile
    if not profile:
        return

    if profile not in _SECURITY_PROFILES:
        raise ValueError(
            f"Unknown security profile '{profile}'. "
            f"Valid profiles: {', '.join(_SECURITY_PROFILES)}"
        )

    _overrides = overrides or set()
    pdef = _SECURITY_PROFILES[profile]

    for key, value in pdef.get("security", {}).items():
        if key == "capabilities" and isinstance(value, dict):
            # Preserve explicitly selected fields while inheriting the
            # profile's remaining defaults. A policy_path alone must not
            # silently disable the profile's capability gate.
            if "capabilities" in _overrides:
                continue
            for cap_key, cap_value in value.items():
                if f"capabilities.{cap_key}" not in _overrides and hasattr(
                    security_cfg.capabilities, cap_key
                ):
                    setattr(security_cfg.capabilities, cap_key, cap_value)
            continue
        if key not in _overrides and hasattr(security_cfg, key):
            setattr(security_cfg, key, value)

    _server_overrides = server_overrides or set()
    if server_cfg is not None:
        for key, value in pdef.get("server", {}).items():
            if key not in _server_overrides and hasattr(server_cfg, key):
                setattr(server_cfg, key, value)


@dataclass
class JarvisConfig:
    """Top-level configuration for OpenJarvis."""

    installed_at: str = ""
    installer_version: str = ""
    hardware: HardwareInfo = field(default_factory=HardwareInfo)
    engine: EngineConfig = field(default_factory=EngineConfig)
    intelligence: IntelligenceConfig = field(default_factory=IntelligenceConfig)
    deep_research: DeepResearchConfig = field(default_factory=DeepResearchConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    traces: TracesConfig = field(default_factory=TracesConfig)
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    sessions: SessionConfig = field(default_factory=SessionConfig)
    a2a: A2AConfig = field(default_factory=A2AConfig)
    operators: OperatorsConfig = field(default_factory=OperatorsConfig)
    speech: SpeechConfig = field(default_factory=SpeechConfig)
    optimize: OptimizeConfig = field(default_factory=OptimizeConfig)
    agent_manager: AgentManagerConfig = field(default_factory=AgentManagerConfig)
    memory_files: MemoryFilesConfig = field(default_factory=MemoryFilesConfig)
    system_prompt: SystemPromptConfig = field(default_factory=SystemPromptConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    digest: DigestConfig = field(default_factory=DigestConfig)
    proactive: ProactiveConfig = field(default_factory=ProactiveConfig)
    extensions: ExtensionsConfig = field(default_factory=ExtensionsConfig)
    phone: PhoneConfig = field(default_factory=PhoneConfig)
    tunnel: TunnelConfig = field(default_factory=TunnelConfig)
    cowork: CoworkConfig = field(default_factory=CoworkConfig)
    mining: Optional["MiningConfig"] = None

    @property
    def _config_dir(self) -> Path:
        """Directory containing the loaded config, or the env-aware default."""
        return self.__dict__.get("_config_source_dir", get_config_dir())

    @_config_dir.setter
    def _config_dir(self, value: Path) -> None:
        self.__dict__["_config_source_dir"] = Path(value)

    @property
    def memory(self) -> StorageConfig:
        """Backward-compatible accessor — canonical location is tools.storage."""
        return self.tools.storage

    @memory.setter
    def memory(self, value: StorageConfig) -> None:
        """Backward-compatible setter."""
        self.tools.storage = value


# ---------------------------------------------------------------------------
# Config key validation
# ---------------------------------------------------------------------------

# Sections that users may set via ``jarvis config set``.
# ``hardware`` is auto-detected and not user-settable.
_SETTABLE_SECTIONS = frozenset(JarvisConfig.__dataclass_fields__.keys()) - {
    "hardware",
    "mining",
}


# ---------------------------------------------------------------------------
# TOML loading
# ---------------------------------------------------------------------------


def _migrate_toml_data(data: Dict[str, Any], cfg: "JarvisConfig") -> None:
    """Migrate old-format TOML keys to new structure in-place.

    Handles cross-section moves that can't be solved by backward-compat
    properties alone (e.g. ``agent.temperature`` → ``intelligence.temperature``).
    """
    # agent.temperature / agent.max_tokens → intelligence.*
    if "agent" in data:
        agent_data = data["agent"]
        intel_data = data.setdefault("intelligence", {})
        for moved_key in ("temperature", "max_tokens"):
            if moved_key in agent_data:
                intel_data.setdefault(moved_key, agent_data.pop(moved_key))

    # context_injection from memory / tools.storage → agent.context_from_memory
    for src_section in ("memory",):
        src = data.get(src_section, {})
        if isinstance(src, dict) and "context_injection" in src:
            data.setdefault("agent", {}).setdefault(
                "context_from_memory",
                src.pop("context_injection"),
            )

    if "tools" in data:
        tools_data = data["tools"]
        if isinstance(tools_data, dict):
            storage_sub = tools_data.get("storage", {})
            if isinstance(storage_sub, dict) and "context_injection" in storage_sub:
                data.setdefault("agent", {}).setdefault(
                    "context_from_memory",
                    storage_sub.pop("context_injection"),
                )


def _parse_mining_section(data: dict) -> Optional["MiningConfig"]:
    """Parse the ``[mining]`` TOML section into a ``MiningConfig``.

    Returns None if the section is absent. Resolves the ``submit_target``
    string into a ``SoloTarget`` or ``PoolTarget`` tagged union.
    """
    if "mining" not in data:
        return None

    # Lazy runtime import to break the import cycle: ``mining/_stubs.py``
    # imports ``HardwareInfo`` from this module at its top level. By the
    # time ``_parse_mining_section`` is called, ``core.config`` is already
    # fully initialized in ``sys.modules``, so the cycle is harmless.
    from openjarvis.mining._stubs import MiningConfig, PoolTarget, SoloTarget

    section = data["mining"]
    extra = section.get("extra", {}) or {}

    target_str = section.get("submit_target", "solo")
    submit_target: Any
    if target_str == "solo":
        submit_target = SoloTarget(
            pearld_rpc_url=extra.get("pearld_rpc_url", "http://localhost:44107")
        )
    elif isinstance(target_str, str) and target_str.startswith("pool:"):
        submit_target = PoolTarget(url=target_str[len("pool:") :])
    else:
        raise ValueError(
            f"[mining].submit_target must be 'solo' or 'pool:<url>', got {target_str!r}"
        )

    return MiningConfig(
        provider=section["provider"],
        wallet_address=section["wallet_address"],
        submit_target=submit_target,
        fee_bps=int(section.get("fee_bps", 0)),
        fee_payout_address=section.get("fee_payout_address") or None,
        extra={k: v for k, v in extra.items()},
    )


@functools.lru_cache(maxsize=1)
def load_config(path: Optional[Path] = None) -> JarvisConfig:
    """Detect hardware, build defaults, overlay TOML overrides.

    Parameters
    ----------
    path:
        Explicit config file. If not set, uses ``OPENJARVIS_CONFIG`` when set,
        otherwise ``~/.openjarvis/config.toml``.
    """
    _ensure_config_dir()
    hw = detect_hardware()
    cfg = JarvisConfig(hardware=hw)
    cfg.engine.default = recommend_engine(hw)

    if path is not None:
        config_path = Path(path).expanduser().resolve()
    elif os.environ.get("OPENJARVIS_CONFIG"):
        config_path = Path(os.environ["OPENJARVIS_CONFIG"]).expanduser().resolve()
    else:
        config_path = get_config_path()
    cfg._config_dir = config_path.parent
    if config_path.exists():
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)

        # Run backward-compat migrations before applying
        _migrate_toml_data(data, cfg)

        # All top-level sections — recursive _apply_toml_section handles
        # nested sub-configs (engine.ollama, learning.routing, channel.*, etc.)
        top_sections = (
            "engine",
            "intelligence",
            "deep_research",
            "learning",
            "agent",
            "server",
            "telemetry",
            "analytics",
            "traces",
            "security",
            "channel",
            "tools",
            "sandbox",
            "scheduler",
            "workflow",
            "sessions",
            "a2a",
            "operators",
            "speech",
            "optimize",
            "agent_manager",
            "digest",
            "proactive",
            "memory_files",
            "system_prompt",
            "compression",
            "skills",
            "extensions",
            "phone",
            "tunnel",
            "cowork",
        )
        for section_name in top_sections:
            if section_name in data:
                _apply_toml_section(
                    getattr(cfg, section_name),
                    data[section_name],
                )

        # Memory: accept [memory] (old) → maps to tools.storage
        if "memory" in data:
            _apply_toml_section(cfg.tools.storage, data["memory"])

        # Top-level install provenance (installed_at, installer_version)
        for key in ("installed_at", "installer_version"):
            if key in data:
                setattr(cfg, key, data[key])

        # Expand security profile (user TOML overrides take precedence)
        _security_data = data.get("security", {})
        _user_security_keys = set(_security_data)
        if isinstance(_security_data.get("capabilities"), dict):
            _user_security_keys.discard("capabilities")
            _user_security_keys.update(
                f"capabilities.{key}" for key in _security_data["capabilities"]
            )
        _server_data = data.get("server", {})
        apply_security_profile(
            cfg.security,
            cfg.server,
            overrides=_user_security_keys,
            server_overrides=set(_server_data)
            if isinstance(_server_data, dict)
            else set(),
        )

        # Mining: dedicated parser for tagged-union submit_target
        cfg.mining = _parse_mining_section(data)

    # Apply profile even without a config file (in case defaults set one)
    if not config_path.exists() and cfg.security.profile:
        apply_security_profile(cfg.security, cfg.server)

    return cfg


# ---------------------------------------------------------------------------
# Default TOML generation (for ``jarvis init``)
# ---------------------------------------------------------------------------


def generate_minimal_toml(
    hw: HardwareInfo, engine: str | None = None, *, host: str | None = None
) -> str:
    """Render a minimal TOML config with only essential settings."""
    engine = engine or recommend_engine(hw)
    model = recommend_model(hw, engine)
    gpu_comment = ""
    if hw.gpu:
        mem_label = "unified memory" if hw.gpu.vendor == "apple" else "VRAM"
        gpu_comment = f"\n# GPU: {hw.gpu.name} ({hw.gpu.vram_gb} GB {mem_label})"
    if host:
        engine_host_section = f'\n[engine.{engine}]\nhost = "{host}"\n'
    else:
        engine_host_section = (
            f"\n[engine.{engine}]\n"
            f'# host = "http://localhost:11434"  '
            f"# set to remote URL if engine runs elsewhere\n"
        )
    return f"""\
# OpenJarvis configuration
# Hardware: {hw.cpu_brand} ({hw.cpu_count} cores, {hw.ram_gb} GB RAM){gpu_comment}
# Full reference config: jarvis init --full

[engine]
default = "{engine}"
{engine_host_section}
[intelligence]
default_model = "{model}"

[agent]
default_agent = "simple"

[tools]
enabled = ["code_interpreter", "web_search", "file_read", "shell_exec"]
"""


__all__ = [
    "A2AConfig",
    "AgentConfig",
    "AgentManagerConfig",
    "OperatorsConfig",
    "AgentLearningConfig",
    "BlueBubblesChannelConfig",
    "BrowserConfig",
    "CapabilitiesConfig",
    "ChannelConfig",
    "ConfigurationError",
    "DEFAULT_CONFIG_DIR",
    "DEFAULT_CONFIG_PATH",
    "DiscordChannelConfig",
    "DeepResearchConfig",
    "get_cache_dir",
    "get_config_dir",
    "get_config_path",
    "get_data_dir",
    "EmailChannelConfig",
    "EngineConfig",
    "FeishuChannelConfig",
    "GoogleChatChannelConfig",
    "GpuInfo",
    "HardwareInfo",
    "IRCChannelConfig",
    "IntelligenceConfig",
    "IntelligenceLearningConfig",
    "JarvisConfig",
    "LearningConfig",
    "LMStudioEngineConfig",
    "LlamaCppEngineConfig",
    "MCPConfig",
    "MLXEngineConfig",
    "MatrixChannelConfig",
    "MattermostChannelConfig",
    "MemoryConfig",
    "MetricsConfig",
    "OllamaEngineConfig",
    "OptimizeConfig",
    "RoutingLearningConfig",
    "SGLangEngineConfig",
    "SandboxConfig",
    "SchedulerConfig",
    "SecurityConfig",
    "ServerConfig",
    "SessionConfig",
    "SignalChannelConfig",
    "SlackChannelConfig",
    "SpeechConfig",
    "StorageConfig",
    "TeamsChannelConfig",
    "TelegramChannelConfig",
    "TelemetryConfig",
    "ToolsConfig",
    "TracesConfig",
    "VLLMEngineConfig",
    "WebChatChannelConfig",
    "WebhookChannelConfig",
    "WeatherToolConfig",
    "WhatsAppBaileysChannelConfig",
    "WhatsAppChannelConfig",
    "WorkflowConfig",
    "detect_hardware",
    "generate_default_toml",
    "generate_minimal_toml",
    "load_config",
    "recommend_engine",
    "recommend_model",
    "validate_config_key",
]


# Moved to their own module; they look their helpers up here.
from openjarvis.core import config_hardware as _hardware  # noqa: E402,I001

_available_memory_gb = _hardware._available_memory_gb
_detect_amd_gpu = _hardware._detect_amd_gpu
_detect_apple_gpu = _hardware._detect_apple_gpu
_detect_cpu_brand = _hardware._detect_cpu_brand
_detect_nvidia_gpu = _hardware._detect_nvidia_gpu
_run_cmd = _hardware._run_cmd
_total_ram_gb = _hardware._total_ram_gb
detect_hardware = _hardware.detect_hardware
estimated_download_gb = _hardware.estimated_download_gb
recommend_engine = _hardware.recommend_engine
recommend_model = _hardware.recommend_model
from openjarvis.core.config_toml import _apply_toml_section as _apply_toml_section  # noqa: E402,I001
from openjarvis.core.config_toml import generate_default_toml as generate_default_toml  # noqa: E402,I001
from openjarvis.core.config_toml import resolve_json_or_file as resolve_json_or_file  # noqa: E402,I001
from openjarvis.core.config_toml import validate_config_key as validate_config_key  # noqa: E402,I001

# Only the moved code uses these; it looks them up on this module.
from dataclasses import is_dataclass as is_dataclass  # noqa: E402,I001
from typing import get_args as get_args  # noqa: E402,I001
from typing import get_origin as get_origin  # noqa: E402,I001
from typing import get_type_hints as get_type_hints  # noqa: E402,I001

# Moved to their own module; they look their helpers up here.
