"""Blocking: apps, websites and searches you decide to keep away (focus,
study, or a child using the PC), switched off only with the owner's face.

* Websites: the browsers' own per-user blocklist policy (Chrome, Edge,
  Brave: ``HKCU\\Software\\Policies\\…\\URLBlocklist``). No admin rights, and
  the browser shows its normal "blocked" page. Removed when blocking stops.
* Apps: while blocking is on, Sergio closes the listed programs when they
  open (never Windows itself, the Task Manager or Sergio).
* Settings: "configuración" in the app list blocks the Windows Settings app.
* Searches: a word in the list closes the browser tab whose title shows it
  (search pages put the words in the title).

Windows' own lock screen (Win+L) stays the way to lock the whole PC.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

NEVER_CLOSE = {
    "explorer.exe", "taskmgr.exe", "winlogon.exe", "csrss.exe", "lsass.exe", "services.exe",
    "svchost.exe", "dwm.exe", "python.exe", "pythonw.exe", "sergio.exe", "system", "smss.exe",
    "wininit.exe", "fontdrvhost.exe", "logonui.exe", "securityhealthsystray.exe",
}  # fmt: skip
ALIASES = {  # what people say -> the program
    "configuracion": "systemsettings.exe", "configuración": "systemsettings.exe", "ajustes": "systemsettings.exe",
    "settings": "systemsettings.exe", "panel de control": "control.exe", "tiktok": "tiktok.exe",
    "discord": "discord.exe", "steam": "steam.exe", "spotify": "spotify.exe", "whatsapp": "whatsapp.exe",
    "telegram": "telegram.exe", "epic games": "epicgameslauncher.exe", "roblox": "robloxplayerbeta.exe",
    "minecraft": "minecraft.exe", "netflix": "netflix.exe", "instagram": "instagram.exe",
}  # fmt: skip
BROWSERS = {
    "Chrome": r"Software\Policies\Google\Chrome\URLBlocklist",
    "Edge": r"Software\Policies\Microsoft\Edge\URLBlocklist",
    "Brave": r"Software\Policies\BraveSoftware\Brave\URLBlocklist",
}


def program(name: str) -> str:
    """«Discord» -> 'discord.exe' (what the process is called)."""
    low = " ".join(name.lower().split())
    if low in ALIASES:
        return ALIASES[low]
    low = re.sub(r"[^\w.-]", "", low)
    return low if low.endswith(".exe") else f"{low}.exe" if low else ""


def site(text: str) -> str:
    """«www.YouTube.com/» -> 'youtube.com' (blocks the site and its pages)."""
    low = text.strip().lower()
    low = re.sub(r"^[a-z]+://", "", low)
    low = low.removeprefix("www.").strip("/ ")
    if low and "." not in low:
        low += ".com"
    return low


@dataclass
class Blocklist:
    apps: list[str] = field(default_factory=list)
    sites: list[str] = field(default_factory=list)
    words: list[str] = field(default_factory=list)
    on: bool = False

    def add(self, kind: str, value: str) -> str:
        value = {"apps": program, "sites": site}.get(kind, lambda v: " ".join(v.lower().split()))(value)
        items = getattr(self, kind)
        if value and value not in items and value not in NEVER_CLOSE:
            items.append(value)
            return value
        return ""

    def remove(self, kind: str, value: str) -> None:
        items = getattr(self, kind)
        if value in items:
            items.remove(value)


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.list = self._load()

    def _load(self) -> Blocklist:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return Blocklist(**{k: data.get(k, v) for k, v in asdict(Blocklist()).items()})
        except (OSError, ValueError, TypeError):
            return Blocklist()

    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(asdict(self.list), ensure_ascii=False, indent=1), encoding="utf-8")


# -- websites: the browsers' own policy ---------------------------------------------
def write_policies(sites: list[str], registry: Any = None) -> list[str]:
    """Write the blocklist for every browser; returns the browsers set."""
    if registry is None:
        import winreg as registry  # noqa: N813 — Windows only
    done = []
    for browser, key_path in BROWSERS.items():
        try:
            key = registry.CreateKey(registry.HKEY_CURRENT_USER, key_path)
            # Clear old numbered values, then write the new list (1, 2, 3…).
            i = 0
            while True:
                try:
                    name = registry.EnumValue(key, 0)[0]
                except OSError:
                    break
                registry.DeleteValue(key, name)
                i += 1
                if i > 500:
                    break
            for n, value in enumerate(sites, start=1):
                registry.SetValueEx(key, str(n), 0, registry.REG_SZ, value)
            registry.CloseKey(key)
            done.append(browser)
        except OSError:
            continue
    return done


def clear_policies(registry: Any = None) -> None:
    write_policies([], registry)


# -- apps and searches: a light watchdog ---------------------------------------------
class Guard:
    """Every 1.5 s while on: close blocked programs; close tabs with blocked words."""

    def __init__(
        self,
        store: Store,
        processes: Callable[[], list[Any]] | None = None,
        title: Callable[[], str] | None = None,
        close_tab: Callable[[], None] = lambda: None,
        told: Callable[[str], None] = lambda _t: None,
    ) -> None:
        self.store = store
        self.processes = processes or _processes
        self.title = title or (lambda: "")
        self.close_tab = close_tab
        self.told = told
        self._stop = threading.Event()
        self._last_note = 0.0

    def check(self) -> list[str]:
        """One pass; returns what it closed."""
        bl = self.store.list
        closed: list[str] = []
        if not bl.on:
            return closed
        apps = {a.lower() for a in bl.apps} - NEVER_CLOSE
        if apps:
            for proc in self.processes():
                try:
                    name = str(proc.info.get("name") or "").lower()
                    if name in apps:
                        proc.terminate()
                        closed.append(name)
                except Exception:  # noqa: BLE001 — gone or protected
                    continue
        words = [w for w in bl.words if w]
        if words:
            title = self.title().lower()
            if any(w in title for w in words):
                self.close_tab()
                closed.append("búsqueda")
        if closed and time.time() - self._last_note > 20:
            self._last_note = time.time()
            self.told(f"Bloqueado: {', '.join(sorted(set(closed)))}.")
        return closed

    def run(self) -> None:
        while not self._stop.wait(1.5):
            try:
                self.check()
            except Exception:  # noqa: BLE001 — never stop guarding over one error
                continue

    def start(self) -> None:
        threading.Thread(target=self.run, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def _processes() -> list[Any]:
    import psutil

    return list(psutil.process_iter(["name"]))


def switch_on(store: Store, registry: Any = None) -> str:
    store.list.on = True
    store.save()
    browsers = write_policies(store.list.sites, registry) if store.list.sites else []
    parts = []
    if store.list.apps:
        parts.append(f"{len(store.list.apps)} apps")
    if store.list.sites:
        parts.append(f"{len(store.list.sites)} webs ({', '.join(browsers) or 'sin navegador compatible'})")
    if store.list.words:
        parts.append(f"{len(store.list.words)} búsquedas")
    return "Bloqueo activado: " + (", ".join(parts) or "la lista está vacía") + "."


def switch_off(store: Store, approved: bool, registry: Any = None) -> str:
    if not approved:
        return "Solo el dueño puede quitar el bloqueo: mírame a la cámara."
    store.list.on = False
    store.save()
    clear_policies(registry)
    return "Bloqueo desactivado."


PARSE = re.compile(
    r"\bbloquea(?:r|me)?\s+(?:la |el |las |los )?(?P<kind>app|aplicaci[oó]n|programa|p[aá]gina|web|sitio|"
    r"b[uú]squedas? de|b[uú]squeda)?\s*(?P<what>.+)$",
    re.I,
)


def parse_block(text: str) -> tuple[str, str] | None:
    """«bloquea youtube.com» -> ('sites', 'youtube.com'); «bloquea discord» -> ('apps', …)."""
    found = PARSE.search(text.strip().rstrip(".!"))
    if not found:
        return None
    what = found.group("what").strip()
    kind = (found.group("kind") or "").lower()
    if not what or what.lower() in ("computadora", "pc", "computador", "compu", "pantalla", "la pantalla"):
        return None
    if kind.startswith("b"):
        return "words", what
    if kind in ("pagina", "página", "web", "sitio") or re.search(r"\.[a-z]{2,}\b", what):
        return "sites", what
    return "apps", what


__all__ = [
    "BROWSERS", "Blocklist", "Guard", "NEVER_CLOSE", "Store", "clear_policies", "parse_block",
    "program", "site", "switch_off", "switch_on", "write_policies",
]  # fmt: skip
