"""A browser of Sergio's own that works in the background.

The owner (3 Nov 2026): «estás viendo una película y le dices: Sergio, revisa la
plataforma de mi colegio, ¿tengo alguna tarea pendiente? … lo hace en segundo
plano mientras ves la película en el mismo dispositivo».

``desktop_action operate`` uses the real screen, mouse and keyboard: it would
interrupt the film. This browser runs **without a window** and keeps its own
profile (``~/.openjarvis/navegador/perfil``): the person signs in to a site
**once**, in a window opened for that (:func:`open_to_sign_in`), and from then
on Sergio reads it in the background with that session.

Rules that do not bend:

* Passwords are never typed by Sergio: the person types them in the sign-in
  window. A step that would type into a password field is refused.
* Sending, paying, buying, booking, publishing or deleting is never done here:
  a step that clicks such a button stops and returns ``espera_su_si``; the
  agent asks and the person decides.
* It is a plain browser that says what it is: no disguise, no bot-evasion.

How fast: a page that is already signed in reads in ~2–8 s; one that needs a
sign-in says so at once. «Under 3 seconds» is not promised: it depends on the site.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

TEXT_LIMIT = 12_000
NAV_TIMEOUT_MS = 20_000
_LOCK = threading.Lock()  # one profile = one browser at a time

# A click on one of these words is a final step: it waits for the person's yes.
FINAL = re.compile(
    r"\b(enviar|env[ií]a|mandar|pagar|paga|comprar|compra|reservar|confirmar|"
    r"confirma|publicar|publica|eliminar|borrar|suscrib|donar|transferir|"
    r"send|pay|buy|purchase|order|place order|checkout|book|confirm|publish|"
    r"post|delete|remove|subscribe|transfer|submit)\b",
    re.I,
)
_SMALL = {"del", "los", "las", "mis", "una", "uno", "para", "por", "con", "the", "my"}
LOGIN = re.compile(r"(login|signin|sign-in|iniciar|acceder|auth|sso|cas/)", re.I)


class NavegadorError(RuntimeError):
    pass


def home() -> Path:
    from openjarvis.core.config import get_config_dir

    path = Path(get_config_dir()) / "navegador"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def profile() -> Path:
    path = home() / "perfil"
    path.mkdir(parents=True, exist_ok=True)
    return path


# -- saved sites («mi colegio» → its address) -------------------------------------


def _sites_file() -> Path:
    return home() / "sitios.json"


def sites() -> Dict[str, Dict[str, str]]:
    try:
        data = json.loads(_sites_file().read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _key(name: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", name.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:60]


def save_site(name: str, url: str, note: str = "") -> Dict[str, str]:
    if not re.match(r"^https?://", url or ""):
        raise NavegadorError("La dirección debe empezar con https://")
    data = sites()
    item = {"nombre": name.strip(), "url": url.strip(), "nota": note.strip()[:300]}
    data[_key(name)] = item
    path = _sites_file()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(path, 0o600)
    return item


def forget_site(name: str) -> bool:
    data = sites()
    if data.pop(_key(name), None) is None:
        return False
    _sites_file().write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    return True


def resolve(target: str) -> str:
    """A saved site's address (by name, loosely), or the address itself."""
    target = (target or "").strip()
    if re.match(r"^https?://", target):
        return target
    data = sites()
    key = _key(target)
    if key in data:
        return data[key]["url"]
    # «la plataforma de mi colegio» → «Plataforma del colegio»: shared words
    want = {w for w in key.split("-") if len(w) > 2 and w not in _SMALL}
    best, score = None, 0.0
    for k, v in data.items():
        have = {w for w in k.split("-") if len(w) > 2 and w not in _SMALL}
        if not have:
            continue
        s = len(want & have) / len(have)
        if s > score:
            best, score = v, s
    if best and score >= 0.5:
        return best["url"]
    raise NavegadorError(
        f"No tengo guardado «{target}». Dígame su dirección una vez y la recuerdo."
    )


# -- the browser ------------------------------------------------------------------


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # installed by the update (extra «browser»)
        raise NavegadorError(
            "Falta el navegador de Sergio. Se instala con la actualización; "
            "o en Ubuntu: uv sync --extra browser && uv run playwright install chromium"
        ) from exc
    return sync_playwright


def _exe() -> Dict[str, Any]:
    """``SERGIO_CHROMIUM``: a Chromium or Edge already installed, if wanted."""
    path = os.environ.get("SERGIO_CHROMIUM", "").strip()
    return {"executable_path": path} if path else {}


def open_to_sign_in(target: str) -> Dict[str, Any]:
    """A visible window with Sergio's profile so the person signs in once.
    The window stays until they close it; the session is kept."""
    url = resolve(target)

    def run() -> None:
        with _LOCK, _playwright()() as pw:
            ctx = pw.chromium.launch_persistent_context(
                str(profile()), headless=False, **_exe()
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, timeout=NAV_TIMEOUT_MS)
            try:
                page.wait_for_event("close", timeout=0)
            finally:
                ctx.close()

    if not (
        os.environ.get("DISPLAY")
        or os.environ.get("WAYLAND_DISPLAY")
        or os.name == "nt"
    ):
        raise NavegadorError(
            "No hay pantalla para abrir la ventana de inicio de sesión aquí. "
            "En Windows 11 con WSL se abre sola; si no, inicie sesión desde el PC."
        )
    threading.Thread(target=run, daemon=True, name="sergio-inicio-sesion").start()
    return {
        "estado": "ventana_abierta",
        "url": url,
        "nota": "Inicie sesión usted en la ventana y ciérrela. Sergio guarda la sesión, nunca la contraseña.",
    }


def _visible_text(page: Any) -> str:
    text = page.evaluate("() => (document.body && document.body.innerText) || ''")
    text = re.sub(r"[ \t]+", " ", str(text))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:TEXT_LIMIT]


def _needs_sign_in(page: Any) -> bool:
    try:
        if page.locator("input[type=password]").first.is_visible(timeout=500):
            return True
    except Exception:  # noqa: BLE001 — no such field
        pass
    return bool(LOGIN.search(page.url or ""))


def _step(page: Any, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One step. Returns a stop (dict) when the step must wait for a person."""
    if "ir" in step:
        page.goto(resolve(str(step["ir"])), timeout=NAV_TIMEOUT_MS)
    elif "clic" in step:
        label = str(step["clic"])
        if FINAL.search(label):
            return {"estado": "espera_su_si", "paso": f"Pulsar «{label}»"}
        page.get_by_text(label, exact=False).first.click(timeout=8000)
    elif "escribir" in step:
        field = str(step.get("campo", ""))
        box = (
            page.get_by_label(field).first
            if field
            else page.locator("input:not([type=hidden]), textarea").first
        )
        try:
            if (box.get_attribute("type", timeout=2000) or "").lower() == "password":
                return {
                    "estado": "contrasena",
                    "paso": "Las contraseñas las escribe usted.",
                }
        except Exception:  # noqa: BLE001
            pass
        box.fill(str(step["escribir"]), timeout=8000)
    elif "tecla" in step:
        key = str(step["tecla"])
        if key.lower() == "enter" and step.get("envia"):
            return {"estado": "espera_su_si", "paso": "Enviar el formulario"}
        page.keyboard.press(key)
    elif "esperar" in step:
        page.wait_for_timeout(min(10_000, int(float(step["esperar"]) * 1000)))
    page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
    return None


def check(
    target: str, steps: Optional[List[Dict[str, Any]]] = None, *, launcher: Any = None
) -> Dict[str, Any]:
    """Opens a site in the background (no window), follows simple steps
    (``ir``, ``clic``, ``escribir``, ``tecla``, ``esperar``) and returns the
    visible text for the model to answer from. Never sends, pays or deletes."""
    url = resolve(target)
    start = time.monotonic()
    launch = launcher or _playwright()
    with _LOCK, launch() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(profile()), headless=True, **_exe()
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, timeout=NAV_TIMEOUT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:  # noqa: BLE001 — busy pages never go idle
                pass
            if _needs_sign_in(page):
                return {
                    "estado": "necesita_sesion",
                    "url": page.url,
                    "segundos": round(time.monotonic() - start, 1),
                    "nota": "Hace falta iniciar sesión una vez (acción iniciar_sesion).",
                }
            for step in steps or []:
                stop = _step(page, step)
                if stop:
                    stop.update(url=page.url, texto=_visible_text(page)[:3000])
                    return stop
            return {
                "estado": "leido",
                "url": page.url,
                "titulo": page.title(),
                "texto": _visible_text(page),
                "segundos": round(time.monotonic() - start, 1),
            }
        finally:
            ctx.close()


__all__ = [
    "FINAL",
    "NavegadorError",
    "check",
    "forget_site",
    "open_to_sign_in",
    "resolve",
    "save_site",
    "sites",
]
