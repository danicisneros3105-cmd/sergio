"""Plugins in Claude's format, from Claude's own marketplaces.

A marketplace is a git repository with ``.claude-plugin/marketplace.json``
listing plugins; a plugin is a folder with ``.claude-plugin/plugin.json`` and
any of ``skills/<name>/SKILL.md``, ``commands/*.md``, ``agents/*.md`` and
``.mcp.json``. Installing one in Sergio:

* its skills (and its commands and agents, written as skills) go into
  ``~/.openjarvis/skills/plugin-<name>/`` where Sergio loads skills from;
* its MCP servers become connectors (``mcp/hub.py``), ready to «Conectar»;
* hooks are listed but not run (Sergio does not execute plugin hooks).

``sergio plugin marketplace add anthropics/knowledge-work-plugins`` and
``sergio plugin install design@knowledge-work-plugins`` work as in Claude.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MARKETPLACES = [
    "anthropics/claude-plugins-official",
    "anthropics/knowledge-work-plugins",
]
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


class ClaudePluginError(RuntimeError):
    """Something the owner can act on (plain Spanish)."""


def _home() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir()


def _git(*args: str, cwd: Optional[Path] = None, timeout: int = 180) -> None:
    try:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except FileNotFoundError as exc:
        raise ClaudePluginError("Falta git en el equipo.") from exc
    except subprocess.CalledProcessError as exc:
        raise ClaudePluginError(
            f"git falló: {(exc.stderr or exc.stdout or '').strip()[:200]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ClaudePluginError("git tardó demasiado (¿hay internet?).") from exc


def _git_url(source: str) -> str:
    source = source.strip()
    if re.match(r"^[\w.-]+/[\w.-]+$", source):
        return f"https://github.com/{source}.git"
    if source.startswith(("https://", "git@", "file://")) or Path(source).exists():
        return source
    raise ClaudePluginError(
        "Indique «propietario/repositorio» de GitHub o la URL git del marketplace."
    )


def _frontmatter(text: str) -> tuple[Dict[str, str], str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not match:
        return {}, text
    meta: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip("'\"")
    return meta, match.group(2)


class ClaudePlugins:
    def __init__(self, home: Optional[Path] = None, *, hub: Any = None) -> None:
        self.home = Path(home) if home else _home()
        self.markets_dir = self.home / "marketplaces"
        self.plugins_dir = self.home / "claude-plugins"
        self.skills_dir = self.home / "skills"
        self.state_path = self.home / "claude-plugins.json"
        self._hub = hub
        self._lock = threading.RLock()

    # -- state ----------------------------------------------------------------
    def _state(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("marketplaces", {})
        data.setdefault("installed", {})
        return data

    def _save(self, state: Dict[str, Any]) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self.state_path)

    def hub(self) -> Any:
        if self._hub is None:
            from openjarvis.mcp.hub import get_hub

            self._hub = get_hub()
        return self._hub

    # -- marketplaces ---------------------------------------------------------
    def add_marketplace(self, source: str) -> Dict[str, Any]:
        url = _git_url(source)
        self.markets_dir.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="mkt-", dir=self.markets_dir))
        try:
            if Path(url).exists():
                shutil.copytree(url, tmp, dirs_exist_ok=True)
            else:
                _git("clone", "--depth", "1", url, str(tmp))
            manifest = self._manifest(tmp)
            name = str(manifest.get("name") or "").strip()
            if not NAME_RE.match(name):
                raise ClaudePluginError("El marketplace no tiene un nombre válido.")
            final = self.markets_dir / name
            if final.exists():
                shutil.rmtree(final)
            tmp.rename(final)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        with self._lock:
            state = self._state()
            state["marketplaces"][name] = {
                "source": source,
                "url": url,
                "added": time.time(),
            }
            self._save(state)
        return {"name": name, "plugins": len(manifest.get("plugins") or [])}

    @staticmethod
    def _manifest(folder: Path) -> Dict[str, Any]:
        path = folder / ".claude-plugin" / "marketplace.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise ClaudePluginError(
                "Ese repositorio no es un marketplace de plugins."
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
            raise ClaudePluginError("El marketplace no lista plugins.")
        return data

    def update_marketplace(self, name: str) -> Dict[str, Any]:
        state = self._state()
        if name not in state["marketplaces"]:
            raise ClaudePluginError(f"No hay un marketplace «{name}».")
        return self.add_marketplace(state["marketplaces"][name]["source"])

    def remove_marketplace(self, name: str) -> None:
        if not NAME_RE.fullmatch(name):
            raise ClaudePluginError("Nombre de marketplace inválido.")
        with self._lock:
            state = self._state()
            if name not in state["marketplaces"]:
                raise ClaudePluginError(f"No hay un marketplace «{name}».")
            target = self.markets_dir / name
            if (
                target.is_symlink()
                or target.resolve().parent != self.markets_dir.resolve()
            ):
                raise ClaudePluginError("El marketplace apunta fuera de su carpeta.")
            if target.exists():
                shutil.rmtree(target)
            state["marketplaces"].pop(name)
            self._save(state)

    def ensure_defaults(self) -> List[str]:
        """The two official marketplaces, the first time (as Claude ships them)."""
        added = []
        state = self._state()
        if state.get("defaults_done"):
            return added
        for source in DEFAULT_MARKETPLACES:
            try:
                added.append(self.add_marketplace(source)["name"])
            except ClaudePluginError:
                continue
        with self._lock:
            state = self._state()
            state["defaults_done"] = bool(added)
            self._save(state)
        return added

    def marketplaces(self) -> List[Dict[str, Any]]:
        out = []
        for name, info in self._state()["marketplaces"].items():
            try:
                count = len(
                    self._manifest(self.markets_dir / name).get("plugins") or []
                )
            except ClaudePluginError:
                count = 0
            out.append(
                {"name": name, "source": info.get("source", ""), "plugins": count}
            )
        return out

    # -- browsing -------------------------------------------------------------
    def available(self, query: str = "", marketplace: str = "") -> List[Dict[str, Any]]:
        installed = self._state()["installed"]
        query = query.lower().strip()
        out = []
        for market in self._state()["marketplaces"]:
            if marketplace and market != marketplace:
                continue
            try:
                manifest = self._manifest(self.markets_dir / market)
            except ClaudePluginError:
                continue
            for entry in manifest["plugins"]:
                name = str(entry.get("name") or "")
                if not NAME_RE.match(name):
                    continue
                text = f"{name} {entry.get('displayName', '')} {entry.get('description', '')}".lower()
                if query and query not in text:
                    continue
                key = f"{name}@{market}"
                out.append(
                    {
                        "id": key,
                        "name": name,
                        "display_name": entry.get("displayName")
                        or name.replace("-", " ").capitalize(),
                        "description": entry.get("description", ""),
                        "category": entry.get("category", ""),
                        "marketplace": market,
                        "installed": key in installed,
                        "enabled": bool(installed.get(key, {}).get("enabled")),
                    }
                )
        return out

    # -- installing -----------------------------------------------------------
    def _fetch_source(self, market: str, entry: Dict[str, Any], into: Path) -> Path:
        """Copy the plugin folder named by a marketplace entry into *into*."""
        source = entry.get("source")
        base = self.markets_dir / market
        if isinstance(source, str):
            folder = (base / source).resolve()
            if not folder.is_relative_to(base.resolve()) or not folder.is_dir():
                raise ClaudePluginError("El plugin apunta a una carpeta que no existe.")
            shutil.copytree(folder, into)
            return into
        if not isinstance(source, dict):
            raise ClaudePluginError("Origen del plugin desconocido.")
        kind = source.get("source")
        if kind == "github":
            url, sub, ref = (
                f"https://github.com/{source.get('repo')}.git",
                "",
                source.get("ref", ""),
            )
        elif kind in ("url", "git"):
            url, sub, ref = str(source.get("url") or ""), "", source.get("ref", "")
        elif kind == "git-subdir":
            url, sub, ref = (
                str(source.get("url") or ""),
                str(source.get("path") or ""),
                source.get("ref", ""),
            )
        else:
            raise ClaudePluginError(f"Origen «{kind}» no admitido.")
        checkout = Path(tempfile.mkdtemp(prefix="plg-", dir=self.plugins_dir))
        try:
            args = (
                ["clone", "--depth", "1"]
                + (["--branch", ref] if ref else [])
                + [url, str(checkout / "repo")]
            )
            _git(*args)
            folder = (checkout / "repo" / sub).resolve() if sub else checkout / "repo"
            if (
                not folder.is_relative_to((checkout / "repo").resolve())
                or not folder.is_dir()
            ):
                raise ClaudePluginError("La subcarpeta del plugin no existe.")
            shutil.copytree(folder, into, ignore=shutil.ignore_patterns(".git"))
        finally:
            shutil.rmtree(checkout, ignore_errors=True)
        return into

    def install(self, plugin_id: str) -> Dict[str, Any]:
        """``nombre@marketplace`` (or just ``nombre`` if only one has it)."""
        name, _, market = plugin_id.partition("@")
        matches = [
            p
            for p in self.available()
            if p["name"] == name and (not market or p["marketplace"] == market)
        ]
        if not matches:
            raise ClaudePluginError(
                f"No encuentro el plugin «{plugin_id}» en sus marketplaces."
            )
        if len(matches) > 1:
            raise ClaudePluginError(
                "Hay varios plugins con ese nombre; indique nombre@marketplace."
            )
        market = matches[0]["marketplace"]
        key = f"{name}@{market}"
        previous = self._state()["installed"].get(key, {})
        entry = next(
            e
            for e in self._manifest(self.markets_dir / market)["plugins"]
            if e.get("name") == name
        )
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        target = self.plugins_dir / market / name
        staging = self.plugins_dir / f".{name}-{int(time.time() * 1000)}"
        try:
            self._fetch_source(market, entry, staging)
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        info = self._read_plugin(target, entry)
        info.update(
            {
                "id": key,
                "name": name,
                "marketplace": market,
                "path": str(target),
                "installed": time.time(),
                "skill_root": f"plugin-{name}-{hashlib.sha256(market.encode()).hexdigest()[:12]}",
            }
        )
        info["skills"] = self._place_skills(name, target, info)
        if (
            previous
            and not previous.get("skill_root")
            and not any(
                k != key and v.get("name") == name and not v.get("skill_root")
                for k, v in self._state()["installed"].items()
            )
        ):
            shutil.rmtree(self.skills_dir / f"plugin-{name}", ignore_errors=True)

        info["connector_errors"] = []
        info["connectors"] = self._add_connectors(
            name, target, entry, info["connector_errors"]
        )
        info["enabled"] = True
        with self._lock:
            state = self._state()
            state["installed"][key] = info
            self._save(state)
        return info

    @staticmethod
    def _read_plugin(folder: Path, entry: Dict[str, Any]) -> Dict[str, Any]:
        try:
            manifest = json.loads(
                (folder / ".claude-plugin" / "plugin.json").read_text("utf-8")
            )
        except (OSError, ValueError):
            manifest = {}
        author = manifest.get("author") or entry.get("author") or {}
        return {
            "display_name": entry.get("displayName")
            or manifest.get("name")
            or folder.name,
            "description": manifest.get("description") or entry.get("description", ""),
            "version": manifest.get("version", ""),
            "author": author.get("name", "")
            if isinstance(author, dict)
            else str(author),
            "commands": sorted(p.stem for p in (folder / "commands").glob("*.md")),
            "agents": sorted(p.stem for p in (folder / "agents").glob("*.md")),
            "hooks": (folder / "hooks" / "hooks.json").exists()
            or (folder / "hooks.json").exists(),
        }

    def _place_skills(self, name: str, folder: Path, info: Dict[str, Any]) -> List[str]:
        """Skills, commands and agents → ``skills/plugin-<name>/<skill>/SKILL.md``."""
        root = self.skills_dir / info.get("skill_root", f"plugin-{name}")
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        (root / ".sergio-plugin.json").write_text(
            json.dumps({"id": info.get("id", name)}), "utf-8"
        )
        placed: List[str] = []
        for skill_md in sorted((folder / "skills").glob("*/SKILL.md")):
            dest = root / skill_md.parent.name
            shutil.copytree(
                skill_md.parent, dest, ignore=shutil.ignore_patterns("scripts", ".git")
            )
            placed.append(skill_md.parent.name)
        for kind in ("commands", "agents"):
            for md in sorted((folder / kind).glob("*.md")):
                meta, body = _frontmatter(md.read_text("utf-8", errors="replace"))
                skill = f"{md.stem}" if kind == "commands" else f"agente-{md.stem}"
                if skill in placed or not NAME_RE.match(skill):
                    continue
                what = (
                    meta.get("description")
                    or f"{'Orden' if kind == 'commands' else 'Agente'} «{md.stem}» del plugin {name}."
                )
                dest = root / skill
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text(
                    f"---\nname: {skill}\ndescription: {json.dumps(what, ensure_ascii=False)}\n---\n\n{body.strip()}\n",
                    "utf-8",
                )
                placed.append(skill)
        return placed

    def _add_connectors(
        self,
        name: str,
        folder: Path,
        entry: Dict[str, Any],
        errors: Optional[List[str]] = None,
    ) -> List[str]:
        servers: Dict[str, Any] = {}
        try:
            data = json.loads((folder / ".mcp.json").read_text("utf-8"))
            servers.update(data.get("mcpServers") or {})
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError):
            if errors is not None:
                errors.append("No se pudo leer .mcp.json; revise su formato.")
        if isinstance(entry.get("mcpServers"), dict):
            servers.update(entry["mcpServers"])
        added: List[str] = []
        hub = self.hub()
        existing = {s.get("url") for s in hub.list() if s.get("url")}
        root = str(folder)
        for label, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            try:
                if cfg.get("url"):
                    if cfg["url"] in existing:
                        continue
                    server = hub.add_remote(
                        label.title(),
                        cfg["url"],
                        source=f"plugin:{name}",
                        headers=cfg.get("headers"),
                        transport=cfg.get("type", ""),
                    )
                elif cfg.get("command"):
                    command = [
                        str(cfg["command"]),
                        *[str(a) for a in cfg.get("args") or []],
                    ]
                    command = [
                        part.replace("${CLAUDE_PLUGIN_ROOT}", root) for part in command
                    ]
                    env = {
                        k: str(v).replace("${CLAUDE_PLUGIN_ROOT}", root)
                        for k, v in (cfg.get("env") or {}).items()
                    }
                    server = hub.add_local(
                        label.title(), command, env=env, source=f"plugin:{name}"
                    )
                else:
                    continue
            except Exception:  # noqa: BLE001 - one bad server never blocks the plugin
                if errors is not None:
                    errors.append(
                        f"No se pudo añadir el conector «{label}»; revise su configuración."
                    )
                continue
            added.append(server["id"])
        return added

    # -- the installed ones ---------------------------------------------------
    def installed(self) -> List[Dict[str, Any]]:
        return list(self._state()["installed"].values())

    def set_enabled(self, plugin_id: str, enabled: bool) -> Dict[str, Any]:
        with self._lock:
            state = self._state()
            info = state["installed"].get(plugin_id)
            if info is None:
                raise ClaudePluginError(f"«{plugin_id}» no está instalado.")
            if enabled:
                info["skills"] = self._place_skills(
                    info["name"], Path(info["path"]), info
                )
            else:
                shutil.rmtree(
                    self.skills_dir / info.get("skill_root", f"plugin-{info['name']}"),
                    ignore_errors=True,
                )
            for server_id in info.get("connectors") or []:
                try:
                    self.hub().set_enabled(server_id, enabled)
                except Exception:  # noqa: BLE001 - the connector may be gone
                    pass
            info["enabled"] = bool(enabled)
            self._save(state)
            return info

    def remove(self, plugin_id: str) -> None:
        with self._lock:
            state = self._state()
            info = state["installed"].pop(plugin_id, None)
            self._save(state)
        if info is None:
            raise ClaudePluginError(f"«{plugin_id}» no está instalado.")
        shutil.rmtree(
            self.skills_dir / info.get("skill_root", f"plugin-{info['name']}"),
            ignore_errors=True,
        )
        shutil.rmtree(info.get("path", ""), ignore_errors=True)
        for server_id in info.get("connectors") or []:
            try:
                self.hub().remove(server_id)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["ClaudePluginError", "ClaudePlugins", "DEFAULT_MARKETPLACES"]
