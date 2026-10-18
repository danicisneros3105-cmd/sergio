"""Prompt library: public system and persona prompt collections, downloaded whole
to the owner's computer, indexed, and used on every turn as technique references.

``sergio prompts sincronizar`` downloads the sources in :mod:`.sources` into
``~/.openjarvis/prompt_library`` and builds a local full-text index; nothing is
copied into this repository (some sources are GPL or carry no license).

On every turn :func:`guidance_for` adds a short block to the system prompt: the
distilled working principles plus the few passages that best match the request.
It changes how Sergio works, never who it is: names of other assistants are
removed, jailbreak-style passages are dropped and Sergio's own rules win.
"""

from openjarvis.prompt_library.guidance import (
    PRINCIPLES,
    guidance_for,
    principles_block,
)
from openjarvis.prompt_library.index import library_dir, search, status
from openjarvis.prompt_library.sources import SOURCES, Source
from openjarvis.prompt_library.sync import sync

__all__ = [
    "PRINCIPLES",
    "SOURCES",
    "Source",
    "guidance_for",
    "library_dir",
    "principles_block",
    "search",
    "status",
    "sync",
]
