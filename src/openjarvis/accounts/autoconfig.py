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
# What the last autoconfig did, in plain words, for the sign-in page (owner,
# 1 Nov 2026: «no funciona lo que te registras y en segundo plano se crean
# todas las APIs»: failures only reached the server log).
_LAST: Dict[str, Any] = {}


def _key(name: str) -> str:
    """A key from the environment or from the keys file Sergio writes
    (``cloud-keys.env``), which a restart did not load back before: the owner
    key was then created again at every sign-in."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        from openjarvis.server.cloud_router import _owner_keys

        value = str(_owner_keys().get(name) or "").strip()
    except Exception:  # noqa: BLE001
        value = ""
    if value:
        os.environ[name] = value  # engine/cloud.py reads the environment
    return value


def ready() -> Dict[str, Any]:
    """What is configured (no secrets): for the sign-in page and «Uso»."""
    return {
        "openrouter": bool(_key("OPENROUTER_API_KEY")),
        "gestion": bool(_key("OPENROUTER_MANAGEMENT_KEY")),
        "gemini": bool(_key("GEMINI_API_KEY") or _key("GOOGLE_API_KEY")),
        "modelos": len(_CATALOG),
        "ultimo": dict(_LAST),
    }


def _save_env(name: str, value: str) -> None:
    from openjarvis import tiers
    from openjarvis.server.cloud_router import _CLOUD_ENV_FILE

    lines = _CLOUD_ENV_FILE.read_text().splitlines() if _CLOUD_ENV_FILE.exists() else []
    kept = [ln for ln in lines if ln.partition("=")[0].strip() != name]
    kept.append(f"{name}={value}")  # comments and other keys stay as they were
    tiers.write_private(_CLOUD_ENV_FILE, "\n".join(kept) + "\n")
    os.environ[name] = value


def owner_key(http: Any = None) -> bool:
    """The owner's own OpenRouter key, created once from the management key."""
    if _key("OPENROUTER_API_KEY"):
        return True
    from openjarvis.accounts import provision

    if not provision.enabled():
        return False
    with _LOCK:
        if _key("OPENROUTER_API_KEY"):
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
    key = _key("OPENROUTER_API_KEY")
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
        from openjarvis.server.customer_gate import plan_of

        # the customer's own plan, not always Free's $0.50 cap
        done["cliente"] = provision.ensure(user["id"], plan_of(user["id"]), http=http)
    done["modelos"] = len(catalog(http))
    done["motivo"] = _why(user, done)
    _LAST.clear()
    _LAST.update(done)
    return done


def _why(user: Dict[str, Any], done: Dict[str, Any]) -> str:
    """One sentence for the sign-in page about what was configured."""
    from openjarvis.accounts import provision

    if done.get("dueño") or done.get("cliente"):
        return f"Listo: la IA quedó configurada ({done.get('modelos', 0)} modelos disponibles)."
    if not provision.enabled() and not _key("OPENROUTER_API_KEY"):
        return (
            "Aún no hay IA conectada: toque «Conectar la IA con un clic» en el chat "
            "(inicia sesión en OpenRouter y Sergio guarda la clave solo)."
        )
    if user.get("role") != "dueño" and provision.key_for(user["id"]):
        return "Su IA ya estaba configurada."
    return "OpenRouter no aceptó crear la clave; revise que la de gestión sea de tipo «provisioning»."


def in_background(user: Dict[str, Any]) -> None:
    threading.Thread(
        target=lambda: _safe(user), name="ia-autoconfig", daemon=True
    ).start()


def _safe(user: Dict[str, Any], http: Optional[Any] = None) -> None:
    try:
        on_sign_in(user, http)
    except Exception as exc:  # noqa: BLE001
        log.warning("AI autoconfig failed", exc_info=True)
        _LAST.clear()
        _LAST.update({"motivo": f"No pude configurar la IA: {str(exc)[:160]}"})


def at_start() -> None:
    """At server start: the owner's keys too, not only at the next sign-in
    (a saved session or «seguir sin cuenta» never signed in again)."""
    in_background({"id": "dueño", "role": "dueño"})


__all__ = ["at_start", "catalog", "in_background", "on_sign_in", "owner_key", "ready"]
