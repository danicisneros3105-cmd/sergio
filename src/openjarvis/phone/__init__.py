"""Phone features for Sergio: voice calls (Twilio + Pipecat) and number helpers.

The heavy voice stack (Pipecat, faster-whisper, Kokoro) is optional
(``uv sync --extra phone``) and imported lazily by :mod:`openjarvis.phone.bot`.
"""

from openjarvis.phone.numbers import digits, is_owner, owner_numbers, to_e164

__all__ = ["digits", "is_owner", "owner_numbers", "to_e164"]
