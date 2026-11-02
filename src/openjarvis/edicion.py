"""Personal or public edition (owner, 2 Nov 2026: Sergio becomes an international
product, like OpenAI, and sells to people who are not the owner).

What the owner decides for himself (clips from the web and from films with
yt-dlp, prompt collections with GPL or no licence, non-commercial data) is not
Sergio's to sell. ``SERGIO_EDICION=publica`` turns those off for every customer:

* clips of the web and of films, and songs «by name» (yt-dlp: the sites' terms
  forbid downloading, and a film clip is the studio's);
* the downloaded prompt collections (GPL-3.0 and unlicensed repositories);
* Jamendo's free API (non-commercial: music needs its commercial licence);
* OpenSky (non-commercial licence).

Nothing is removed from the owner's own copy (``personal``, the default).
Each piece also keeps its own switch (``SERGIO_CLIPS_WEB`` …): in the public
edition those switches cannot turn the risky pieces back on.
Why each piece is on this list: ``docs/LEGAL-TERCEROS.md``.
"""

from __future__ import annotations

import os


def publica() -> bool:
    return os.environ.get("SERGIO_EDICION", "personal").strip().lower() in (
        "publica",
        "pública",
        "public",
    )


def allowed(env_name: str, default: str = "1") -> bool:
    """A risky piece is on when its own switch says so, and never in the
    public edition."""
    if publica():
        return False
    return os.environ.get(env_name, default).strip().lower() not in (
        "0",
        "no",
        "false",
        "off",
    )


__all__ = ["allowed", "publica"]
