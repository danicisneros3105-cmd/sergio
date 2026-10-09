"""The smaller ``config.toml`` sections: storage, tools, agent, server,
telemetry, extensions, sandbox, scheduler, speech, skills, digest …
Split out of ``config.py``, which re-exports every name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from openjarvis.core.paths import (
    get_config_dir,
)


@dataclass(slots=True)
class StorageConfig:
    """Storage (memory) backend settings.

    Covers both the retrieval/document store (``default_backend``, ``db_path``,
    chunking, context injection) and the automatic long-term memory service
    (``enabled``, ``backend``, ``extraction_model``, ``max_facts``,
    ``facts_path``) configured under ``[memory]`` in ``config.toml``.
    """

    default_backend: str = "sqlite"
    db_path: str = field(default_factory=lambda: str(get_config_dir() / "memory.db"))
    context_top_k: int = 5
    context_min_score: float = 0.0
    context_max_tokens: int = 2048
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Automatic memory service — extracts durable facts from conversations in
    # the background and persists them across sessions (see openjarvis.memory).
    enabled: bool = False  # start the memory service with serve/chat
    backend: str = "local"  # fact-store backend ("local" = on-disk JSONL)
    extraction_model: str = ""  # model for fact extraction ("" = active model)
    max_facts: int = 1000  # cap on stored facts (oldest evicted past the cap)
    facts_path: str = field(
        default_factory=lambda: str(get_config_dir() / "memory_facts.jsonl")
    )


@dataclass(slots=True)
class MCPConfig:
    """MCP (Model Context Protocol) settings."""

    enabled: bool = True
    servers: str = ""  # JSON list of MCP server configs


@dataclass(slots=True)
class BrowserConfig:
    """Browser automation settings (Playwright)."""

    headless: bool = True
    timeout_ms: int = 30000
    viewport_width: int = 1280
    viewport_height: int = 720


@dataclass(slots=True)
class WeatherToolConfig:
    """Native weather tool settings (credentials stay outside config.toml)."""

    provider: str = "openweathermap"
    default_location: str = ""
    units: str = "metric"
    lang: str = "en"


@dataclass(slots=True)
class ToolsConfig:
    """Tools primitive settings — wraps storage and MCP configuration."""

    storage: StorageConfig = field(default_factory=StorageConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    weather: WeatherToolConfig = field(default_factory=WeatherToolConfig)
    enabled: str = ""  # comma-separated default tools


@dataclass
class AgentConfig:
    """Agent harness settings — orchestration, tools, system prompt."""

    default_agent: str = "simple"
    max_turns: int = 10
    tools: str = ""  # comma-separated tool names
    objective: str = ""  # concise purpose for routing/learning/docs
    system_prompt: str = ""  # inline system prompt (takes precedence if set)
    system_prompt_path: str = ""  # path to system prompt file (.txt, .md)
    context_from_memory: bool = True  # inject relevant memory context into prompts
    default_system_prompt: str = (
        "You are Sergio, a helpful personal AI assistant running locally on "
        "the user's own computer. You are not a cloud service, and you are not "
        "Claude, ChatGPT, Gemini, or any other branded assistant. If asked "
        "who or what you are, identify yourself as Sergio. Reply in the "
        "user's language, helpfully, concisely, and accurately."
    )

    # Backward-compat property for old field name
    @property
    def default_tools(self) -> str:
        """Deprecated: use ``agent.tools``."""
        return self.tools

    @default_tools.setter
    def default_tools(self, value: str) -> None:
        self.tools = value


@dataclass(slots=True)
class ServerConfig:
    """API server settings."""

    host: str = "127.0.0.1"
    port: int = 8000
    agent: str = "orchestrator"
    model: str = ""
    workers: int = 1
    cors_origins: list = field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            # Tauri 2 production webview origins.
            # macOS / Linux / iOS use the custom scheme; Windows /
            # Android use http(s)://tauri.localhost. All three must
            # be allowed so the desktop app's chat-completions stream
            # is not blocked by CORS in production builds.
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ]
    )


@dataclass(slots=True)
class TelemetryConfig:
    """Telemetry persistence settings."""

    enabled: bool = True
    db_path: str = field(default_factory=lambda: str(get_config_dir() / "telemetry.db"))
    gpu_metrics: bool = False
    gpu_poll_interval_ms: int = 50
    energy_vendor: str = ""  # auto-detect or force "nvidia"/"amd"/"apple"/"cpu_rapl"
    # Permit a modelled energy estimate when no hardware counters are
    # readable. Off by default: an estimate written to the telemetry DB is
    # indistinguishable from a measurement at query time except via
    # `energy_method`, and on Apple Silicon the estimate is a function of
    # wall-clock alone, so it cannot tell an idle window from a busy one.
    allow_energy_estimates: bool = False
    warmup_samples: int = 0
    steady_state_window: int = 5
    steady_state_threshold: float = 0.05


@dataclass(slots=True)
class AnalyticsConfig:
    """External anonymous usage analytics (PostHog).

    Separate concern from :class:`TelemetryConfig`, which stores local
    FLOPs/energy/inference metrics in SQLite. This controls anonymized
    usage events sent to the OpenJarvis team's PostHog instance to
    measure setup success, retention, feature usage, and churn.

    No chat content, prompts, model outputs, file paths, emails, IPs,
    or hardware identifiers are ever sent. See ``docs/telemetry.md``.
    """

    enabled: bool = True
    host: str = "https://34.231.106.201.sslip.io"
    key: str = "phc_ysKu72QaxzYNmDpHFcesD2ZZAe68zkdWJEKoYYkc5e3n"
    anon_id_path: str = field(default_factory=lambda: str(get_config_dir() / "anon_id"))
    flush_interval_seconds: int = 30
    flush_at_size: int = 100


@dataclass(slots=True)
class TracesConfig:
    """Trace system settings."""

    enabled: bool = True
    db_path: str = field(default_factory=lambda: str(get_config_dir() / "traces.db"))


@dataclass(slots=True)
class ClackyExtensionConfig:
    """OpenClacky: the hands-on agent (terminal, files, the user's real Chrome)."""

    enabled: bool = True
    port: int = 7070
    path: str = ""  # Override for the extensions/clacky checkout
    timeout_seconds: float = 900.0  # Max time for one delegated task
    approval_wait_seconds: float = 300.0  # Wait for the user's approval click


@dataclass(slots=True)
class GlobeExtensionConfig:
    """God's Eye View: the live 3D globe."""

    enabled: bool = True
    port: int = 4173
    path: str = ""  # Override for the extensions/globe checkout


@dataclass(slots=True)
class PhoneConfig:
    """Voice calls (Twilio + Pipecat) and phone-number based channels.

    Secrets come from the environment: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER (and WHATSAPP_* for WhatsApp).
    """

    enabled: bool = False
    # Only these numbers may talk to Sergio by WhatsApp/SMS/phone, and calls
    # or messages to them need no approval. E.164, e.g. "+593991234567".
    owner_numbers: List[str] = field(default_factory=list)
    owner_name: str = ""  # Used in "calling on behalf of …"
    public_url: str = ""  # https URL of the tunnel that reaches this server
    language: str = "es"
    stt_model: str = "small"  # faster-whisper model for calls
    tts_voice: str = "em_alex"  # Kokoro voice (es: em_alex, em_santa, ef_dora)
    max_call_minutes: int = 10
    approval_wait_seconds: float = 300.0


@dataclass(slots=True)
class TunnelConfig:
    """Public tunnel so Twilio/WhatsApp can reach the local server."""

    provider: str = ""  # "ngrok" | "cloudflare" | "" (disabled)
    domain: str = ""  # ngrok static domain, e.g. "sergio-abc.ngrok-free.app"


@dataclass(slots=True)
class CoworkConfig:
    """Cowork mode: describe an outcome, step away, Sergio does the rest."""

    max_actions: int = 50  # hard cap on tool calls per run (1-500)
    autonomy: str = "normal"  # cauteloso | normal | autonomo
    approval_timeout_minutes: int = 120  # unanswered approvals count as "no"
    # Progress to the owner's own chat: a channel type ("telegram", "whatsapp",
    # "discord" …) and the owner's id on it. Phone channels only accept the
    # numbers in [phone] owner_numbers. Empty = only the app and the CLI.
    notify_channel: str = ""
    notify_to: str = ""


@dataclass(slots=True)
class BackupConfig:
    """Encrypted backups of ~/.openjarvis (``sergio respaldo``)."""

    # A folder, s3://bucket/prefix?endpoint=…&region=… (S3, Backblaze B2,
    # R2, Wasabi, MinIO) or sftp://user@host/path. Empty = not configured.
    target: str = ""
    keep_full: int = 4  # complete chains kept on the target
    with_secrets: bool = True  # include sergio.env and connector tokens


@dataclass(slots=True)
class SyncConfig:
    """Zero-knowledge sync of memory, skills and notes between devices."""

    target: str = ""  # same kinds of target as backup (a different prefix)
    with_secrets: bool = False  # also sync sergio.env (API keys)
    interval_minutes: int = 0  # 0 = only when you run `sergio sync ahora`


@dataclass(slots=True)
class ExtensionsConfig:
    """Bundled extensions that run next to OpenJarvis as one product."""

    autostart: bool = True  # Start them together with ``jarvis gui``
    clacky: ClackyExtensionConfig = field(default_factory=ClackyExtensionConfig)
    globe: GlobeExtensionConfig = field(default_factory=GlobeExtensionConfig)


@dataclass(slots=True)
class ProactiveConfig:
    """Proactive agent — autonomous action scheduling and approval routing."""

    enabled: bool = False
    schedule: str = "0 5 * * *"  # cron expression (default: 5am daily)
    hours_back: int = 24  # how many hours of unacted items to scan
    timezone: str = "America/Los_Angeles"
    # Channel to send approval notifications and receive yes/no replies.
    # Format: "{type}:{id}", e.g. "imessage:+15551234567" or "telegram:123456789"
    notification_channel: str = ""


@dataclass(slots=True)
class SandboxConfig:
    """Container sandbox settings."""

    enabled: bool = False
    image: str = "openjarvis-sandbox:latest"
    timeout: int = 300
    workspace: str = ""
    mount_allowlist_path: str = ""
    max_concurrent: int = 5
    runtime: str = "docker"
    wasm_fuel_limit: int = 1_000_000
    wasm_memory_limit_mb: int = 256


@dataclass(slots=True)
class SchedulerConfig:
    """Task scheduler settings."""

    enabled: bool = False
    poll_interval: int = 60
    db_path: str = ""  # Defaults to ~/.openjarvis/scheduler.db


@dataclass(slots=True)
class WorkflowConfig:
    """Workflow engine settings."""

    enabled: bool = False
    max_parallel: int = 4
    default_node_timeout: int = 300


@dataclass(slots=True)
class SessionConfig:
    """Cross-channel session settings."""

    enabled: bool = False
    max_age_hours: float = 24.0
    consolidation_threshold: int = 100
    db_path: str = field(default_factory=lambda: str(get_config_dir() / "sessions.db"))


@dataclass(slots=True)
class A2AConfig:
    """Agent-to-Agent protocol settings."""

    enabled: bool = False
    # Bearer token required for inbound A2A requests. Empty = unauthenticated
    # (only safe on a trusted network). See ``A2AServer(auth_token=...)``.
    auth_token: str = ""


@dataclass(slots=True)
class OperatorsConfig:
    """Operator lifecycle settings."""

    enabled: bool = False
    manifests_dir: str = field(
        default_factory=lambda: str(get_config_dir() / "operators")
    )
    auto_activate: str = ""  # Comma-separated operator IDs


@dataclass(slots=True)
class SpeechConfig:
    """Speech-to-text settings."""

    backend: str = "auto"  # "auto", "faster-whisper", "openai", "deepgram"
    model: str = "base"  # Whisper model size: tiny, base, small, medium, large-v3
    language: str = ""  # Empty = auto-detect
    # CPU by default: on WSL/laptops "auto" picks a GPU whose CUDA libraries
    # are often missing (libcublas), which breaks hearing. "cuda" to opt in.
    device: str = "cpu"  # "auto", "cpu", "cuda"
    compute_type: str = "int8"  # "float16", "int8", "float32"
    # Text-to-speech. ``voice_id`` is interpreted by ``tts_backend`` only --
    # voice IDs are not portable between backends, so if voice output falls
    # back to a different backend that backend's own default voice is used.
    # Kokoro IDs: bm_george / bm_lewis (British male), bf_emma / bf_isabella
    # (British female), af_* / am_* (American).
    tts_backend: str = "kokoro"  # "kokoro", "openai_tts", "cartesia"
    voice_id: str = "bm_george"
    voice_speed: float = 1.0


@dataclass(slots=True)
class OptimizeConfig:
    """Configuration optimization settings."""

    max_trials: int = 20
    early_stop_patience: int = 5
    optimizer_model: str = "claude-sonnet-4-6"
    optimizer_provider: str = "anthropic"
    benchmark: str = ""
    max_samples: int = 50
    judge_model: str = "gpt-5-mini-2025-08-07"
    db_path: str = field(default_factory=lambda: str(get_config_dir() / "optimize.db"))


@dataclass(slots=True)
class AgentManagerConfig:
    """Persistent agent manager settings."""

    enabled: bool = True
    db_path: str = field(default_factory=lambda: str(get_config_dir() / "agents.db"))


@dataclass(slots=True)
class MemoryFilesConfig:
    """Persistent memory-file paths and nudge settings."""

    soul_path: str = field(default_factory=lambda: str(get_config_dir() / "SOUL.md"))
    memory_path: str = field(
        default_factory=lambda: str(get_config_dir() / "MEMORY.md")
    )
    user_path: str = field(default_factory=lambda: str(get_config_dir() / "USER.md"))
    nudge_interval: int = 10
    persona_name: str = ""  # named persona dir under <config-dir>/personas/<name>/


@dataclass(slots=True)
class SystemPromptConfig:
    """Limits and strategy for system-prompt assembly."""

    prefix: str = ""
    soul_max_chars: int = 4000
    memory_max_chars: int = 2500
    user_max_chars: int = 1500
    skill_desc_max_chars: int = 60
    truncation_strategy: str = "head_tail"


@dataclass(slots=True)
class CompressionConfig:
    """Configuration for context compression."""

    enabled: bool = True
    threshold: float = 0.50
    strategy: str = "session_consolidation"
    # Token saver: compress long outputs of the tools below with LLMLingua-2
    # (``pip install llmlingua``) before they reach the model.
    tool_output: bool = False
    tool_output_min_chars: int = 6000
    tool_output_rate: float = 0.4  # fraction of tokens to keep
    tool_output_model: str = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank"
    tool_output_tools: List[str] = field(
        default_factory=lambda: [
            "web_search",
            "http_request",
            "browser_extract",
            "pdf_extract",
            "knowledge_search",
            "retrieval",
            "digest_collect",
        ]
    )


@dataclass(slots=True)
class SkillSourceConfig:
    """Configuration for a single skill source (Hermes, OpenClaw, GitHub)."""

    source: str = ""  # "hermes", "openclaw", or "github"
    url: str = ""  # required when source = "github"
    filter: Dict[str, Any] = field(default_factory=dict)
    auto_update: bool = False


@dataclass(slots=True)
class SkillsConfig:
    """Configuration for agent-authored procedural skills."""

    enabled: bool = True
    skills_dir: str = field(default_factory=lambda: str(get_config_dir() / "skills"))
    active: str = "*"
    auto_discover: bool = True
    auto_sync: bool = False
    nudge_interval: int = 15
    index_repo: str = "https://github.com/openjarvis/skill-index.git"
    index_dir: str = field(
        default_factory=lambda: str(get_config_dir() / "skill-index")
    )
    max_depth: int = 5
    sandbox_dangerous: bool = True
    sources: List[SkillSourceConfig] = field(default_factory=list)


@dataclass
class DigestSectionConfig:
    """Configuration for a single digest section."""

    sources: List[str] = field(default_factory=list)
    max_items: int = 10
    priority_contacts: List[str] = field(default_factory=list)


@dataclass
class DigestConfig:
    """Configuration for the morning digest feature."""

    enabled: bool = False
    schedule: str = "0 6 * * *"
    timezone: str = "America/Los_Angeles"
    persona: str = "jarvis"
    sections: List[str] = field(
        default_factory=lambda: ["messages", "calendar", "health", "world"]
    )
    optional_sections: List[str] = field(
        default_factory=lambda: ["github", "financial", "music", "fitness"]
    )
    honorific: str = "sir"
    voice_id: str = ""
    voice_speed: float = 1.0
    tts_backend: str = "cartesia"
    messages: DigestSectionConfig = field(
        default_factory=lambda: DigestSectionConfig(
            sources=["gmail", "slack", "google_tasks"]
        )
    )
    calendar: DigestSectionConfig = field(
        default_factory=lambda: DigestSectionConfig(sources=["gcalendar"])
    )
    health: DigestSectionConfig = field(
        default_factory=lambda: DigestSectionConfig(sources=["oura", "apple_health"])
    )
    world: DigestSectionConfig = field(
        default_factory=lambda: DigestSectionConfig(sources=[])
    )


__all__ = [
    "A2AConfig",
    "AgentConfig",
    "AgentManagerConfig",
    "AnalyticsConfig",
    "BrowserConfig",
    "ClackyExtensionConfig",
    "CompressionConfig",
    "BackupConfig",
    "CoworkConfig",
    "DigestConfig",
    "DigestSectionConfig",
    "ExtensionsConfig",
    "GlobeExtensionConfig",
    "MCPConfig",
    "MemoryFilesConfig",
    "OperatorsConfig",
    "OptimizeConfig",
    "PhoneConfig",
    "ProactiveConfig",
    "SandboxConfig",
    "SchedulerConfig",
    "ServerConfig",
    "SessionConfig",
    "SkillsConfig",
    "SyncConfig",
    "SkillSourceConfig",
    "SpeechConfig",
    "StorageConfig",
    "SystemPromptConfig",
    "TelemetryConfig",
    "ToolsConfig",
    "TracesConfig",
    "TunnelConfig",
    "WeatherToolConfig",
    "WorkflowConfig",
]
