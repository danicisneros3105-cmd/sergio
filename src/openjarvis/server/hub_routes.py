"""Extensiones: plugins, skills and connectors in one place.

The web's «Extensiones» space reads everything Sergio can add to itself
from here. Connectors keep their own API (``/v1/connectors``) because they
need sign-in flows; this module covers plugins (code from others, always
installed with an explicit permission confirmation) and skills (manuals
that load by themselves when a request matches).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/hub", tags=["hub"])


def _store() -> Any:
    from openjarvis.plugins.store import PluginStore

    return PluginStore()


def plugins() -> List[Dict[str, Any]]:
    from openjarvis.plugins import index
    from openjarvis.plugins.manifest import PERMISSIONS_ES

    installed = _store().installed()
    out: Dict[str, Dict[str, Any]] = {}
    for entry in index.search(""):
        out[entry.name] = {
            "name": entry.name,
            "version": entry.version,
            "description": entry.description,
            "permissions": [PERMISSIONS_ES.get(p, p) for p in entry.permissions],
            "installed": False,
            "enabled": False,
        }
    for name, state in installed.items():
        row = out.setdefault(
            name,
            {"name": name, "description": "", "permissions": []},
        )
        row.update(
            installed=True,
            enabled=bool(state.get("enabled", True)),
            version=str(state.get("version") or row.get("version") or ""),
        )
    return sorted(out.values(), key=lambda r: (not r["installed"], r["name"]))


def skills() -> List[Dict[str, Any]]:
    from openjarvis.coach.skills import all_skills

    return [
        {"name": s["nombre"], "keys": list(s["claves"][:8])}
        for s in all_skills()
        if s.get("nombre") != "anatomy"  # hidden: Sergio uses it on its own
    ]


@router.get("")
async def hub() -> Dict[str, Any]:
    plug, sk = await asyncio.gather(
        asyncio.to_thread(plugins), asyncio.to_thread(_safe_skills)
    )
    return {"plugins": plug, "skills": sk}


def _safe_skills() -> List[Dict[str, Any]]:
    try:
        return skills()
    except Exception:  # noqa: BLE001 — skills folder missing or unreadable
        return []


class Confirm(BaseModel):
    accept_permissions: bool = False


@router.post("/plugins/{name}/install")
async def install(name: str, body: Confirm) -> Dict[str, Any]:
    """Install from the indexes; refused unless the owner saw the permissions."""
    from openjarvis.plugins import index
    from openjarvis.plugins.loader import load_enabled
    from openjarvis.plugins.store import PluginError

    entry = index.find(name)
    if entry is None:
        raise HTTPException(status_code=404, detail="No encuentro ese plugin.")
    if entry.permissions and not body.accept_permissions:
        raise HTTPException(
            status_code=409, detail="Confirme los permisos antes de instalarlo."
        )
    if entry.premium:
        from openjarvis.tiers import require

        try:
            require("premium_skills")
        except PermissionError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from None
    try:
        data = await asyncio.to_thread(index.fetch, entry)
        await asyncio.to_thread(
            _store().install, data, source=entry.source, expected_sha256=entry.sha256
        )
    except (PluginError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    tools = load_enabled().get(name, [])
    return {"name": name, "installed": True, "tools": tools}


class Toggle(BaseModel):
    enabled: bool


@router.post("/plugins/{name}/enabled")
async def toggle(name: str, body: Toggle) -> Dict[str, Any]:
    from openjarvis.plugins.loader import forget, load_enabled
    from openjarvis.plugins.store import PluginError

    try:
        _store().set_enabled(name, body.enabled)
    except PluginError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    if body.enabled:
        load_enabled()
    else:
        forget(name)
    return {"name": name, "enabled": body.enabled}


@router.delete("/plugins/{name}")
async def uninstall(name: str) -> Dict[str, Any]:
    from openjarvis.plugins.loader import forget
    from openjarvis.plugins.store import PluginError

    try:
        _store().uninstall(name)
    except PluginError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    forget(name)
    return {"name": name, "installed": False}


# -- plugins in Claude's format, from Claude's marketplaces -------------------
def _claude() -> Any:
    from openjarvis.plugins.claude_format import ClaudePlugins

    return ClaudePlugins()


def _claude_call(fn: Any, *args: Any) -> Any:
    from openjarvis.plugins.claude_format import ClaudePluginError

    try:
        return fn(*args)
    except ClaudePluginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/marketplaces")
async def marketplaces() -> Dict[str, Any]:
    plugins_ = _claude()
    if not plugins_.marketplaces():
        # The first time, the two official marketplaces (as Claude ships them).
        await asyncio.to_thread(plugins_.ensure_defaults)
    return {"marketplaces": plugins_.marketplaces()}


class MarketSource(BaseModel):
    source: str


@router.post("/marketplaces")
async def add_marketplace(body: MarketSource) -> Dict[str, Any]:
    return await asyncio.to_thread(_claude_call, _claude().add_marketplace, body.source)


@router.post("/marketplaces/{name}/update")
async def update_marketplace(name: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_claude_call, _claude().update_marketplace, name)


@router.delete("/marketplaces/{name}")
async def remove_marketplace(name: str) -> Dict[str, Any]:
    await asyncio.to_thread(_claude().remove_marketplace, name)
    return {"ok": True}


@router.get("/claude-plugins")
async def claude_plugins(q: str = "", marketplace: str = "") -> Dict[str, Any]:
    plugins_ = _claude()
    return {
        "available": await asyncio.to_thread(plugins_.available, q, marketplace),
        "installed": plugins_.installed(),
    }


class PluginId(BaseModel):
    id: str


@router.post("/claude-plugins/install")
async def install_claude_plugin(body: PluginId) -> Dict[str, Any]:
    return {"plugin": await asyncio.to_thread(_claude_call, _claude().install, body.id)}


@router.post("/claude-plugins/enabled")
async def toggle_claude_plugin(body: PluginId, enabled: bool = True) -> Dict[str, Any]:
    return {
        "plugin": await asyncio.to_thread(
            _claude_call, _claude().set_enabled, body.id, enabled
        )
    }


@router.post("/claude-plugins/remove")
async def remove_claude_plugin(body: PluginId) -> Dict[str, Any]:
    await asyncio.to_thread(_claude_call, _claude().remove, body.id)
    return {"ok": True}


__all__ = ["router", "plugins", "skills"]
