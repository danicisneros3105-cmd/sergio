"""Every AI configured by itself when someone signs up or signs in.

The owner (28 Oct 2026): «el núcleo de Sergio no es Gemini; con la key de
OpenRouter se autoconfiguran todas las IAs al mismo tiempo cuando creas
cuenta o inicias sesión». OpenRouter is one key for every big lab's models,
so with it nothing else is needed:

* **The owner** signs in: if there is a management key
  (``OPENROUTER_MANAGEMENT_KEY``) but no ``OPENROUTER_API_KEY`` yet, Sergio
  creates the owner's own key inside the owner's OpenRouter account and keeps
  it in ``sergio.env`` (0600), like any other key. From then on every model
  whose own company has no key here (Gemini, Claude, GPT, DeepSeek…) goes
  through OpenRouter by itself (``engine.cloud.through_openrouter``).
* **A customer** signs in: their sub-key inside the owner's account, with the
  monthly cap of their plan (``provision.ensure``), as before.
* Either way, the list of OpenRouter models is read again so the model picker
  shows what exists today.

Nothing blocks a sign-in: all of it runs in the background, and a failure is
only written to the log.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

KEYS_API = "https://openrouter.ai/api/v1/keys"
MODELS_API = "https://openrouter.ai/api/v1/models"
_LOCK = threading.Lock()
_CATALOG: List[str] = []


def ready() -> Dict[str, Any]:
    """What is configured (no secrets): for the sign-in page and «Uso»."""
    return {
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY", "").strip()),
        "gestion": bool(os.environ.get("OPENROUTER_MANAGEMENT_KEY", "").strip()),
        "gemini": bool(
            os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        ),
        "modelos": len(_CATALOG),
    }


def _save_env(name: str, value: str) -> None:
    from openjarvis import tiers
    from openjarvis.server.cloud_router import _CLOUD_ENV_FILE

    existing: Dict[str, str] = {}
    if _CLOUD_ENV_FILE.exists():
        for line in _CLOUD_ENV_FILE.read_text().splitlines():
            key, sep, val = line.partition("=")
            if sep and not key.startswith("#"):
                existing[key] = val
    existing[name] = value
    tiers.write_private(
        _CLOUD_ENV_FILE, "".join(f"{k}={v}\n" for k, v in existing.items())
    )
    os.environ[name] = value


def owner_key(http: Any = None) -> bool:
    """The owner's own OpenRouter key, created once from the management key."""
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        return True
    from openjarvis.accounts import provision

    if not provision.enabled():
        return False
    with _LOCK:
        if os.environ.get("OPENROUTER_API_KEY", "").strip():
            return True
        try:
            out = provision._call("POST", KEYS_API, {"name": "sergio-dueño"}, http)
        except Exception as exc:  # noqa: BLE001 — never block a sign-in
            log.warning("owner OpenRouter key not created: %s", exc)
            return False
        key = str(out.get("key") or "").strip()
        if not key:
            return False
        _save_env("OPENROUTER_API_KEY", key)
        return True


def catalog(http: Any = None) -> List[str]:
    """Every model OpenRouter serves today (ids like «anthropic/claude-…»)."""
    global _CATALOG
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return _CATALOG
    try:
        client = http
        if client is None:
            import httpx

            client = httpx.Client(timeout=20)
        resp = client.get(MODELS_API, headers={"Authorization": f"Bearer {key}"})
        data = resp.json().get("data") or []
        ids = [str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id")]
        if ids:
            _CATALOG = ids
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenRouter models not read: %s", exc)
    return _CATALOG


def on_sign_in(user: Dict[str, Any], http: Any = None) -> Dict[str, Any]:
    """Configure every AI for *user* (called in the background)."""
    from openjarvis.accounts import provision

    done: Dict[str, Any] = {}
    if user.get("role") == "dueño":
        done["dueño"] = owner_key(http)
    elif provision.enabled() and not provision.key_for(user["id"]):
        done["cliente"] = provision.ensure(user["id"], http=http)
    done["modelos"] = len(catalog(http))
    return done


def in_background(user: Dict[str, Any]) -> None:
    threading.Thread(
        target=lambda: _safe(user), name="ia-autoconfig", daemon=True
    ).start()


def _safe(user: Dict[str, Any], http: Optional[Any] = None) -> None:
    try:
        on_sign_in(user, http)
    except Exception:  # noqa: BLE001
        log.warning("AI autoconfig failed", exc_info=True)


__all__ = ["catalog", "in_background", "on_sign_in", "owner_key", "ready"]
