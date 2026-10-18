"""Data source connectors for Deep Research."""

import logging as _logging

from openjarvis.connectors._stubs import (
    Attachment,
    BaseConnector,
    Document,
    SyncStatus,
)
from openjarvis.connectors.store import KnowledgeStore

__all__ = ["Attachment", "BaseConnector", "Document", "KnowledgeStore", "SyncStatus"]

# Auto-register built-in connectors
import openjarvis.connectors.obsidian  # noqa: F401

try:
    import openjarvis.connectors.gmail  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.gmail): %s", _exc
    )

try:
    import openjarvis.connectors.gmail_imap  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.gmail_imap): %s", _exc
    )

try:
    import openjarvis.connectors.gdrive  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.gdrive; httpx may not be installed): %s",
        _exc,
    )

try:
    import openjarvis.connectors.notion  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.notion): %s", _exc
    )

try:
    import openjarvis.connectors.granola  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.granola): %s", _exc
    )

try:
    import openjarvis.connectors.gcontacts  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.gcontacts): %s", _exc
    )

try:
    import openjarvis.connectors.imessage  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.imessage): %s", _exc
    )

try:
    import openjarvis.connectors.apple_notes  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.apple_notes): %s", _exc
    )

try:
    import openjarvis.connectors.apple_music  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.apple_music): %s", _exc
    )

try:
    import openjarvis.connectors.apple_contacts  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.apple_contacts): %s", _exc
    )

try:
    import openjarvis.connectors.apple_calendar  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.apple_calendar): %s", _exc
    )

try:
    import openjarvis.connectors.slack_connector  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.slack_connector): %s", _exc
    )

try:
    import openjarvis.connectors.outlook  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.outlook): %s", _exc
    )

try:
    import openjarvis.connectors.imap  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.imap): %s", _exc
    )

try:
    import openjarvis.connectors.gcalendar  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.gcalendar): %s", _exc
    )

try:
    import openjarvis.connectors.dropbox  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.dropbox; httpx may not be installed): %s",
        _exc,
    )

try:
    import openjarvis.connectors.whatsapp  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.whatsapp): %s", _exc
    )

try:
    import openjarvis.connectors.oura  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.oura): %s", _exc
    )

try:
    import openjarvis.connectors.apple_health  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.apple_health): %s", _exc
    )

try:
    import openjarvis.connectors.garmin_connect  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.garmin_connect): %s", _exc
    )

try:
    import openjarvis.connectors.strava  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.strava): %s", _exc
    )

try:
    import openjarvis.connectors.spotify  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.spotify): %s", _exc
    )

try:
    import openjarvis.connectors.google_tasks  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.google_tasks): %s", _exc
    )

try:
    import openjarvis.connectors.weather  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.weather): %s", _exc
    )

try:
    import openjarvis.connectors.github_notifications  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.github_notifications): %s", _exc
    )

try:
    import openjarvis.connectors.hackernews  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.hackernews): %s", _exc
    )

try:
    import openjarvis.connectors.news_rss  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.connectors.news_rss): %s", _exc
    )
