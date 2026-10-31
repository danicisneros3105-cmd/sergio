"""Where the web app the server shows lives.

The update builds the web into ``static_local`` (ignored by git), so a
build never leaves tracked files changed and the next update never stops
on «local changes» (owner, 29 Oct 2026: «la app no abre»). The copy kept in
git (``static``) is the fallback for a checkout that was never built.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent


def local_dir() -> Path:
    """Where the update builds the web (git ignores it)."""
    return HERE / "static_local"


def web_dir(local: Path | None = None, tracked: Path | None = None) -> Path:
    """The freshest web build there is (paths worked out when asked)."""
    local = local or HERE / "static_local"
    if (local / "index.html").is_file():
        return local
    return tracked or HERE / "static"


__all__ = ["local_dir", "web_dir"]
