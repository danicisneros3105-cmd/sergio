"""Messaging-channel configuration dataclasses (Telegram, Slack, WhatsApp,
email …) and the ``[channel]`` section. Split out of ``config.py``, which
re-exports every name.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TelegramChannelConfig:
    """Per-channel config for Telegram."""

    bot_token: str = ""
    allowed_chat_ids: str = ""
    parse_mode: str = "Markdown"


@dataclass(slots=True)
class DiscordChannelConfig:
    """Per-channel config for Discord."""

    bot_token: str = ""


@dataclass(slots=True)
class SlackChannelConfig:
    """Per-channel config for Slack."""

    bot_token: str = ""
    app_token: str = ""


@dataclass(slots=True)
class WebhookChannelConfig:
    """Per-channel config for generic webhooks."""

    url: str = ""
    secret: str = ""
    method: str = "POST"


@dataclass(slots=True)
class EmailChannelConfig:
    """Per-channel config for email (SMTP/IMAP)."""

    smtp_host: str = ""
    smtp_port: int = 587
    imap_host: str = ""
    imap_port: int = 993
    username: str = ""
    password: str = ""
    use_tls: bool = True


@dataclass(slots=True)
class WhatsAppChannelConfig:
    """Per-channel config for WhatsApp Cloud API."""

    access_token: str = ""
    phone_number_id: str = ""


@dataclass(slots=True)
class SignalChannelConfig:
    """Per-channel config for Signal (via signal-cli REST API)."""

    api_url: str = ""
    phone_number: str = ""


@dataclass(slots=True)
class GoogleChatChannelConfig:
    """Per-channel config for Google Chat webhooks."""

    webhook_url: str = ""


@dataclass(slots=True)
class IRCChannelConfig:
    """Per-channel config for IRC."""

    server: str = ""
    port: int = 6667
    nick: str = ""
    password: str = ""
    use_tls: bool = False


@dataclass(slots=True)
class WebChatChannelConfig:
    """Per-channel config for in-memory webchat."""

    pass


@dataclass(slots=True)
class TeamsChannelConfig:
    """Per-channel config for Microsoft Teams (Bot Framework)."""

    app_id: str = ""
    app_password: str = ""
    service_url: str = ""


@dataclass(slots=True)
class MatrixChannelConfig:
    """Per-channel config for Matrix."""

    homeserver: str = ""
    access_token: str = ""


@dataclass(slots=True)
class MattermostChannelConfig:
    """Per-channel config for Mattermost."""

    url: str = ""
    token: str = ""


@dataclass(slots=True)
class FeishuChannelConfig:
    """Per-channel config for Feishu (Lark)."""

    app_id: str = ""
    app_secret: str = ""


@dataclass(slots=True)
class BlueBubblesChannelConfig:
    """Per-channel config for BlueBubbles (iMessage bridge)."""

    url: str = ""
    password: str = ""


@dataclass(slots=True)
class WhatsAppBaileysChannelConfig:
    """Per-channel config for WhatsApp via Baileys protocol."""

    auth_dir: str = ""  # Defaults to ~/.openjarvis/whatsapp_auth
    assistant_name: str = "Jarvis"
    assistant_has_own_number: bool = False


@dataclass
class ChannelConfig:
    """Channel messaging settings."""

    enabled: bool = False
    default_channel: str = ""
    default_agent: str = "simple"
    telegram: TelegramChannelConfig = field(default_factory=TelegramChannelConfig)
    discord: DiscordChannelConfig = field(default_factory=DiscordChannelConfig)
    slack: SlackChannelConfig = field(default_factory=SlackChannelConfig)
    webhook: WebhookChannelConfig = field(default_factory=WebhookChannelConfig)
    email: EmailChannelConfig = field(default_factory=EmailChannelConfig)
    whatsapp: WhatsAppChannelConfig = field(default_factory=WhatsAppChannelConfig)
    signal: SignalChannelConfig = field(default_factory=SignalChannelConfig)
    google_chat: GoogleChatChannelConfig = field(
        default_factory=GoogleChatChannelConfig,
    )
    irc: IRCChannelConfig = field(default_factory=IRCChannelConfig)
    webchat: WebChatChannelConfig = field(default_factory=WebChatChannelConfig)
    teams: TeamsChannelConfig = field(default_factory=TeamsChannelConfig)
    matrix: MatrixChannelConfig = field(default_factory=MatrixChannelConfig)
    mattermost: MattermostChannelConfig = field(default_factory=MattermostChannelConfig)
    feishu: FeishuChannelConfig = field(default_factory=FeishuChannelConfig)
    bluebubbles: BlueBubblesChannelConfig = field(
        default_factory=BlueBubblesChannelConfig,
    )
    whatsapp_baileys: WhatsAppBaileysChannelConfig = field(
        default_factory=WhatsAppBaileysChannelConfig,
    )


__all__ = [
    "BlueBubblesChannelConfig",
    "ChannelConfig",
    "DiscordChannelConfig",
    "EmailChannelConfig",
    "FeishuChannelConfig",
    "GoogleChatChannelConfig",
    "IRCChannelConfig",
    "MatrixChannelConfig",
    "MattermostChannelConfig",
    "SignalChannelConfig",
    "SlackChannelConfig",
    "TeamsChannelConfig",
    "TelegramChannelConfig",
    "WebChatChannelConfig",
    "WebhookChannelConfig",
    "WhatsAppBaileysChannelConfig",
    "WhatsAppChannelConfig",
]
