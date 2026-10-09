"""What the data-boundary audit looks for: cloud providers, local engines,
credential environment variables, local stores and the tool surfaces that
send data outside the machine. Split out of ``data_boundary_audit.py``.
"""

from __future__ import annotations

from typing import Literal

from openjarvis.core.credentials import TOOL_CREDENTIALS

Status = Literal["fail", "warn", "info"]


CLOUD_PROVIDER_KEYS = {
    "anthropic",
    "claude",
    "cloud",
    "codex",
    "deepseek",
    "gemini",
    "google",
    "litellm",
    "minimax",
    "openai",
    "openrouter",
}


LOCAL_ENGINE_KEYS = {
    # Apple Foundation Models, both the in-process engine and the shim. The
    # Python SDK has no Private Cloud Compute path, so inference is
    # unconditionally on-device.
    "afm",
    "apple_fm",
    "exo",
    "gemma_cpp",
    "lemonade",
    "llamacpp",
    "lmstudio",
    "mlx",
    "nexa",
    "ollama",
    "sglang",
    "uzu",
    "vllm",
}


API_KEY_ENV_VARS = {
    "ANTHROPIC_API_KEY": ("Anthropic cloud inference", {"anthropic", "claude"}),
    "CARTESIA_API_KEY": (
        "Cartesia cloud text-to-speech",
        {"cartesia", "text_to_speech"},
    ),
    "DEEPSEEK_API_KEY": ("DeepSeek cloud inference", {"deepseek"}),
    "MOONSHOT_API_KEY": ("Kimi (Moonshot) cloud inference", {"kimi", "moonshot"}),
    "GEMINI_API_KEY": ("Google/Gemini cloud inference", {"google", "gemini"}),
    "GOOGLE_API_KEY": ("Google/Gemini cloud inference", {"google", "gemini"}),
    "MINIMAX_API_KEY": ("MiniMax cloud inference", {"minimax"}),
    "OPENAI_API_KEY": ("OpenAI cloud inference", {"openai", "gpt"}),
    "OPENROUTER_API_KEY": ("OpenRouter cloud inference", {"openrouter"}),
    "OPENWEATHERMAP_API_KEY": (
        "OpenWeatherMap weather lookup",
        {"get_weather", "openweathermap", "weather"},
    ),
    "TAVILY_API_KEY": ("Tavily web search", {"tavily", "web_search"}),
    "YOUDOTCOM_API_KEY": ("You.com web search", {"youcom", "web_search"}),
    "SERPLY_API_KEY": ("Serply web search", {"serply", "web_search"}),
}


CHANNEL_SECRET_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("channel.telegram.bot_token", "Telegram bot token", "Telegram"),
    ("channel.discord.bot_token", "Discord bot token", "Discord"),
    ("channel.slack.bot_token", "Slack bot token", "Slack"),
    ("channel.slack.app_token", "Slack app token", "Slack"),
    ("channel.webhook.secret", "Webhook secret", "generic webhook"),
    ("channel.email.password", "Email password", "email"),
    ("channel.whatsapp.access_token", "WhatsApp access token", "WhatsApp"),
    ("channel.irc.password", "IRC password", "IRC"),
    ("channel.teams.app_password", "Teams app password", "Teams"),
    ("channel.matrix.access_token", "Matrix access token", "Matrix"),
    ("channel.mattermost.token", "Mattermost token", "Mattermost"),
    ("channel.feishu.app_secret", "Feishu app secret", "Feishu"),
    ("channel.bluebubbles.password", "BlueBubbles password", "BlueBubbles"),
)


CHANNEL_REFERENCE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("channel.webhook.url", "Webhook URL", "generic webhook"),
    ("channel.email.smtp_host", "Email SMTP host", "email"),
    ("channel.email.imap_host", "Email IMAP host", "email"),
    ("channel.email.username", "Email username", "email"),
    ("channel.whatsapp.phone_number_id", "WhatsApp phone number ID", "WhatsApp"),
    ("channel.signal.api_url", "Signal API URL", "Signal"),
    ("channel.signal.phone_number", "Signal phone number", "Signal"),
    ("channel.google_chat.webhook_url", "Google Chat webhook URL", "Google Chat"),
    ("channel.irc.server", "IRC server", "IRC"),
    ("channel.irc.nick", "IRC nick", "IRC"),
    ("channel.teams.app_id", "Teams app ID", "Teams"),
    ("channel.teams.service_url", "Teams service URL", "Teams"),
    ("channel.matrix.homeserver", "Matrix homeserver", "Matrix"),
    ("channel.mattermost.url", "Mattermost URL", "Mattermost"),
    ("channel.feishu.app_id", "Feishu app ID", "Feishu"),
    ("channel.bluebubbles.url", "BlueBubbles URL", "BlueBubbles"),
)


CHANNEL_SECRET_ENV_VARS = {
    "BLUEBUBBLES_PASSWORD": "BlueBubbles channel",
    "DISCORD_BOT_TOKEN": "Discord channel",
    "FEISHU_APP_SECRET": "Feishu channel",
    "MATTERMOST_TOKEN": "Mattermost channel",
    "MATRIX_ACCESS_TOKEN": "Matrix channel",
    "SLACK_APP_TOKEN": "Slack channel",
    "SLACK_BOT_TOKEN": "Slack channel",
    "TEAMS_APP_PASSWORD": "Teams channel",
    "TELEGRAM_BOT_TOKEN": "Telegram channel",
    "WHATSAPP_ACCESS_TOKEN": "WhatsApp channel",
}


CHANNEL_REFERENCE_ENV_VARS = {
    "BLUEBUBBLES_URL": "BlueBubbles channel",
    "FEISHU_APP_ID": "Feishu channel",
    "GOOGLE_CHAT_WEBHOOK_URL": "Google Chat channel",
    "MATTERMOST_URL": "Mattermost channel",
    "MATRIX_HOMESERVER": "Matrix channel",
    "SIGNAL_PHONE_NUMBER": "Signal channel",
    "TEAMS_APP_ID": "Teams channel",
    "WHATSAPP_PHONE_NUMBER_ID": "WhatsApp channel",
}


# Runtime tool/channel credential env keys from credentials.toml schema.
RUNTIME_CREDENTIAL_ENV_KEYS = {
    key for keys in TOOL_CREDENTIALS.values() for key in keys
}


# Specialized findings carry provider/channel semantics; remaining keys get a
# presence-only generic finding. Values are never read or printed.
_SPECIALIZED_CREDENTIAL_ENV_VARS = (
    set(API_KEY_ENV_VARS)
    | set(CHANNEL_SECRET_ENV_VARS)
    | set(CHANNEL_REFERENCE_ENV_VARS)
)


GENERIC_CREDENTIAL_ENV_VARS = frozenset(
    RUNTIME_CREDENTIAL_ENV_KEYS - _SPECIALIZED_CREDENTIAL_ENV_VARS
)


LOCAL_STORE_CANDIDATES: tuple[tuple[str, str, str, Status], ...] = (
    ("config-file", "Configuration file", "config.toml", "info"),
    ("credentials-toml", "Credentials file", "credentials.toml", "warn"),
    ("knowledge-db", "Knowledge and Deep Research database", "knowledge.db", "warn"),
    ("memory-db", "Memory index database", "memory.db", "warn"),
    ("memory-facts", "Persistent memory facts", "memory_facts.jsonl", "warn"),
    ("traces-db", "Trace database", "traces.db", "warn"),
    ("telemetry-db", "Telemetry database", "telemetry.db", "info"),
    ("audit-db", "Security audit database", "audit.db", "info"),
    ("sessions-db", "Session database", "sessions.db", "warn"),
    ("agents-db", "Agent manager database", "agents.db", "warn"),
    ("optimize-db", "Optimization database", "optimize.db", "warn"),
    ("scheduler-db", "Scheduler database", "scheduler.db", "warn"),
    ("skill-index", "Skill index directory", "skill-index", "info"),
    ("vault-key", "Vault encryption key", ".vault_key", "warn"),
    ("embeddings-store", "Embeddings store", "embeddings", "warn"),
    ("soul-file", "SOUL memory file", "SOUL.md", "warn"),
    ("memory-file", "MEMORY memory file", "MEMORY.md", "warn"),
    ("user-file", "USER memory file", "USER.md", "warn"),
)


_CONFIG_STORE_PATHS: tuple[tuple[str, str, str, Status], ...] = (
    ("memory-db", "Memory index database", "tools.storage.db_path", "warn"),
    ("memory-facts", "Persistent memory facts", "tools.storage.facts_path", "warn"),
    ("traces-db", "Trace database", "traces.db_path", "warn"),
    ("telemetry-db", "Telemetry database", "telemetry.db_path", "info"),
    ("audit-db", "Security audit database", "security.audit_log_path", "info"),
    ("sessions-db", "Session database", "sessions.db_path", "warn"),
    ("agents-db", "Agent manager database", "agents.db_path", "warn"),
    ("optimize-db", "Optimization database", "optimize.db_path", "warn"),
    ("vault-key", "Vault encryption key", "security.vault_key_path", "warn"),
    ("scheduler-db", "Scheduler database", "scheduler.db_path", "warn"),
    ("skill-index", "Skill index directory", "skills.index_dir", "info"),
)


PERSONAL_DIGEST_SOURCES = {
    "apple_health",
    "dropbox",
    "gcalendar",
    "gcontacts",
    "gdrive",
    "github",
    "gmail",
    "google_tasks",
    "imessage",
    "notion",
    "obsidian",
    "oura",
    "outlook",
    "slack",
    "spotify",
    "strava",
    "whatsapp",
}


WEB_SEARCH_TOOLS = {"web_search", "search", "tavily_search"}


BROWSER_TOOLS = {
    "browser",
    "browser_axtree",
    "browser_click",
    "browser_extract",
    "browser_navigate",
    "browser_open",
    "browser_screenshot",
    "browser_search",
    "browser_type",
    "web_browser",
}


GENERIC_NETWORK_TOOLS = {"http_request"}


WEATHER_TOOLS = {"get_weather"}


CHANNEL_OUTBOUND_TOOLS = {"channel_send"}


CLOUD_MEDIA_TOOLS = {"audio_transcribe", "image_generate", "text_to_speech"}


CLOUD_TTS_BACKENDS = {"cartesia", "openai", "openai_tts"}


# Local knowledge chunks scanned by an inference engine (Deep Research path).
KNOWLEDGE_ENGINE_TOOLS = {"scan_chunks"}


# External egress surfaces (web, browser, HTTP, channels, media, knowledge LM).
EXTERNAL_TOOL_SURFACES = (
    WEB_SEARCH_TOOLS
    | BROWSER_TOOLS
    | GENERIC_NETWORK_TOOLS
    | WEATHER_TOOLS
    | CHANNEL_OUTBOUND_TOOLS
    | CLOUD_MEDIA_TOOLS
    | KNOWLEDGE_ENGINE_TOOLS
)


# Narrower cloud inference / media API key surfaces (not browser-only egress).
CLOUD_API_SURFACES = CLOUD_MEDIA_TOOLS | WEB_SEARCH_TOOLS | WEATHER_TOOLS


OUTBOUND_TOOL_SURFACES = EXTERNAL_TOOL_SURFACES


LOCAL_ACCESS_TOOLS = {
    "apply_patch",
    "calendar_search",
    "calendar_upcoming",
    "channel_list",
    "channel_status",
    "code_interpreter",
    "code_interpreter_docker",
    "db_query",
    "docker_shell_exec",
    "file_read",
    "file_write",
    "git_commit",
    "git_diff",
    "git_log",
    "git_status",
    "kg_add_entity",
    "kg_add_relation",
    "kg_neighbors",
    "kg_query",
    "knowledge_sql",
    "memory_index",
    "memory_manage",
    "memory_retrieve",
    "memory_search",
    "memory_store",
    "pdf_extract",
    "repl",
    "retrieval",
    "shell_exec",
    "skill_manage",
    "user_profile_manage",
}
