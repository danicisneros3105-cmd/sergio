"""The laptop itself, by voice and at once: windows, editing keys,
brightness, light/dark mode, Settings pages, folders, exact volume, typing.

``parse_device`` turns a plain sentence into a :class:`Step` (pure, tested);
``run_device`` does it through the control server's actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

# Window and editing orders -> keys
KEYS: dict[str, tuple[str, str]] = {
    "maximiza la ventana": ("win+up", "Ventana maximizada."),
    "maximiza esta ventana": ("win+up", "Ventana maximizada."),
    "maximizala": ("win+up", "Ventana maximizada."),
    "maximiza": ("win+up", "Ventana maximizada."),
    "pantalla completa": ("f11", "Pantalla completa."),
    "ponlo en pantalla completa": ("f11", "Pantalla completa."),
    "minimiza la ventana": ("win+down", "Ventana minimizada."),
    "minimiza esta ventana": ("win+down", "Ventana minimizada."),
    "minimizala": ("win+down", "Ventana minimizada."),
    "minimiza": ("win+down", "Ventana minimizada."),
    "ventana a la izquierda": ("win+left", "A la izquierda."),
    "pon la ventana a la izquierda": ("win+left", "A la izquierda."),
    "ventana a la derecha": ("win+right", "A la derecha."),
    "pon la ventana a la derecha": ("win+right", "A la derecha."),
    "cambia de ventana": ("alt+tab", "Listo."),
    "siguiente ventana": ("alt+tab", "Listo."),
    "ventana anterior": ("alt+tab", "Listo."),
    "muestra las ventanas": ("win+tab", "Aquí están tus ventanas."),
    "muestrame las ventanas": ("win+tab", "Aquí están tus ventanas."),
    "cierra esta ventana": ("alt+f4", "Cerrada."),
    "cierra la ventana": ("alt+f4", "Cerrada."),
    "cierra esto": ("alt+f4", "Cerrado."),
    "nueva pestana": ("ctrl+t", "Nueva pestaña."),
    "abre una pestana nueva": ("ctrl+t", "Nueva pestaña."),
    "abre una nueva pestana": ("ctrl+t", "Nueva pestaña."),
    "cierra la pestana": ("ctrl+w", "Pestaña cerrada."),
    "cierra esta pestana": ("ctrl+w", "Pestaña cerrada."),
    "recarga la pagina": ("f5", "Recargada."),
    "actualiza la pagina": ("f5", "Recargada."),
    "copia": ("ctrl+c", "Copiado."),
    "copialo": ("ctrl+c", "Copiado."),
    "copia eso": ("ctrl+c", "Copiado."),
    "pega": ("ctrl+v", "Pegado."),
    "pegalo": ("ctrl+v", "Pegado."),
    "pega eso": ("ctrl+v", "Pegado."),
    "corta": ("ctrl+x", "Cortado."),
    "deshaz": ("ctrl+z", "Deshecho."),
    "deshacer": ("ctrl+z", "Deshecho."),
    "rehaz": ("ctrl+y", "Rehecho."),
    "guarda": ("ctrl+s", "Guardado."),
    "guardalo": ("ctrl+s", "Guardado."),
    "guarda el archivo": ("ctrl+s", "Guardado."),
    "selecciona todo": ("ctrl+a", "Todo seleccionado."),
    "imprime": ("ctrl+p", "Imprimir."),
    "busca en la pagina": ("ctrl+f", "Escriba lo que busca."),
    "acercar": ("ctrl+add", "Más grande."),
    "haz zoom": ("ctrl+add", "Más grande."),
    "alejar": ("ctrl+subtract", "Más pequeño."),
    "aleja el zoom": ("ctrl+subtract", "Más pequeño."),
    "abre el portapapeles": ("win+v", "El portapapeles."),
    "abre los emojis": ("win+.", "Los emojis."),
    "nuevo escritorio": ("win+ctrl+d", "Escritorio nuevo."),
    "escritorio siguiente": ("win+ctrl+right", "Listo."),
    "escritorio anterior": ("win+ctrl+left", "Listo."),
    "abre el centro de notificaciones": ("win+n", "Notificaciones."),
    "abre la configuracion rapida": ("win+a", "Configuración rápida."),
    "dictado": ("win+h", "Dicte."),
    # Browser and pages
    "atras": ("alt+left", ""),
    "ve atras": ("alt+left", ""),
    "vuelve atras": ("alt+left", ""),
    "regresa": ("alt+left", ""),
    "pagina anterior": ("alt+left", ""),
    "adelante": ("alt+right", ""),
    "ve adelante": ("alt+right", ""),
    "pagina siguiente": ("alt+right", ""),
    "siguiente pestana": ("ctrl+tab", ""),
    "pestana siguiente": ("ctrl+tab", ""),
    "pestana anterior": ("ctrl+shift+tab", ""),
    "reabre la pestana": ("ctrl+shift+t", "Pestaña recuperada."),
    "abre la pestana que cerre": ("ctrl+shift+t", "Pestaña recuperada."),
    "ve a la barra de direcciones": ("ctrl+l", ""),
    "ve al final": ("end", ""),
    "baja hasta el final": ("end", ""),
    "ve al inicio": ("home", ""),
    "ve arriba del todo": ("home", ""),
    "sube hasta arriba": ("home", ""),
    "historial": ("ctrl+h", ""),
    "abre el historial": ("ctrl+h", ""),
    "descargas del navegador": ("ctrl+j", ""),
    "modo incognito": ("ctrl+shift+n", ""),
    "ventana de incognito": ("ctrl+shift+n", ""),
    "nueva ventana": ("ctrl+n", ""),
    "zoom normal": ("ctrl+0", ""),
    "restablece el zoom": ("ctrl+0", ""),
    "abre el administrador de tareas": ("ctrl+shift+esc", ""),
    "administrador de tareas": ("ctrl+shift+esc", ""),
    "abre el explorador": ("win+e", ""),
    "abre ejecutar": ("win+r", ""),
    "recorte de pantalla": ("win+shift+s", ""),
    "haz un recorte": ("win+shift+s", ""),
}

# "presiona enter", "dale tab dos veces", "flecha abajo"
KEY_NAMES: dict[str, str] = {
    "enter": "enter", "intro": "enter", "entrar": "enter",
    "escape": "esc", "esc": "esc", "tab": "tab", "tabulador": "tab",
    "espacio": "space", "barra espaciadora": "space",
    "borrar": "backspace", "retroceso": "backspace", "suprimir": "delete",
    "flecha arriba": "up", "flecha abajo": "down",
    "flecha izquierda": "left", "flecha derecha": "right",
    "arriba": "up", "abajo": "down", "izquierda": "left", "derecha": "right",
    "inicio": "home", "fin": "end", "re pag": "pageup", "av pag": "pagedown",
    "pagina arriba": "pageup", "pagina abajo": "pagedown",
}  # fmt: skip
for _n in range(1, 13):
    KEY_NAMES[f"f{_n}"] = f"f{_n}"
_TIMES = {"una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
          "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}  # fmt: skip
_PRESS = re.compile(
    r"(?:presiona|pulsa|dale|aprieta|oprime|teclea|toca)(?: a)?(?: la tecla| el)? "
    r"(?P<key>" + "|".join(sorted(map(re.escape, KEY_NAMES), key=len, reverse=True)) + r")"
    r"(?: (?P<n>\d+|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez) (?:vez|veces))?"
)
_SCROLL_DOWN = {
    "baja", "mas abajo", "sigue bajando", "baja la pagina", "baja un poco",
    "desplazate hacia abajo", "desplazate abajo", "scroll abajo", "haz scroll",
    "baja mas", "bajale a la pagina",
}  # fmt: skip
_SCROLL_UP = {
    "sube", "mas arriba", "sigue subiendo", "sube la pagina", "sube un poco",
    "desplazate hacia arriba", "desplazate arriba", "scroll arriba", "sube mas",
}  # fmt: skip
# "cambia a Chrome", "pasa a Word", "trae Spotify al frente"
_FOCUS = re.compile(
    r"(?:cambia a|cambiate a|pasa a|pasate a|ve a la ventana de|muestrame la ventana de)"
    r" (?:la ventana de |el |la )?(?P<name>.+)"
    r"|trae (?:a |el |la )?(?P<name2>.+?) al frente"
)
# "haz clic en Suscribirse", "pulsa el botón Enviar", "dale a Aceptar"
_CLICK = re.compile(
    r"(?P<verb>haz doble clic|haz doble click|doble clic|doble click|haz clic derecho|"
    r"clic derecho|haz clic|haz click|da clic|da click|dale clic|dale click|"
    r"clic|click|pulsa|presiona|oprime|aprieta|toca|selecciona|dale)"
    r"(?: (?:en|a|sobre|al|el|la|los|las|boton|opcion|enlace|link|pestana|menu|icono|de))*"
    r" (?P<name>.+)"
)

SETTINGS: dict[str, str] = {
    "wifi": "ms-settings:network-wifi",
    "red": "ms-settings:network",
    "internet": "ms-settings:network",
    "bluetooth": "ms-settings:bluetooth",
    "pantalla": "ms-settings:display",
    "sonido": "ms-settings:sound",
    "bateria": "ms-settings:batterysaver",
    "energia": "ms-settings:powersleep",
    "actualizaciones": "ms-settings:windowsupdate",
    "windows update": "ms-settings:windowsupdate",
    "fondo de pantalla": "ms-settings:personalization-background",
    "fondo": "ms-settings:personalization-background",
    "colores": "ms-settings:colors",
    "impresoras": "ms-settings:printers",
    "mouse": "ms-settings:mousetouchpad",
    "touchpad": "ms-settings:devices-touchpad",
    "teclado": "ms-settings:typing",
    "idioma": "ms-settings:regionlanguage",
    "hora": "ms-settings:dateandtime",
    "fecha": "ms-settings:dateandtime",
    "privacidad": "ms-settings:privacy",
    "camara": "ms-settings:privacy-webcam",
    "microfono": "ms-settings:privacy-microphone",
    "aplicaciones": "ms-settings:appsfeatures",
    "almacenamiento": "ms-settings:storagesense",
    "notificaciones": "ms-settings:notifications",
    "no molestar": "ms-settings:quiethours",
    "cuentas": "ms-settings:yourinfo",
}

FOLDERS: dict[str, str] = {
    "descargas": "shell:Downloads",
    "documentos": "shell:Personal",
    "escritorio": "shell:Desktop",
    "imagenes": "shell:My Pictures",
    "fotos": "shell:My Pictures",
    "musica": "shell:My Music",
    "videos": "shell:My Video",
    "papelera": "shell:RecycleBinFolder",
    "papelera de reciclaje": "shell:RecycleBinFolder",
}

BRIGHTNESS = (
    "$c=(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness;"
    "$n=[Math]::Max(0,[Math]::Min(100,{expr}));"
    "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
    "Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness=[byte]$n}} | Out-Null;"
    "$n"
)
THEME = (
    "$k='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize';"
    "Set-ItemProperty $k -Name AppsUseLightTheme -Value {v};"
    "Set-ItemProperty $k -Name SystemUsesLightTheme -Value {v}"
)

# "escribe ..." that asks the AI to compose something is not dictation.
_COMPOSE = re.compile(
    r"^(un|una|el|la|mi|me|nos|le|les)?\s*(correo|mensaje|email|mail|carta|ensayo|"
    r"codigo|programa|script|historia|cuento|poema|resumen|articulo|post|tweet|"
    r"respuesta|informe|parrafo|texto sobre|lista de)\b"
)
_NUMBERS = {
    "cero": 0, "diez": 10, "veinte": 20, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
    "noventa": 90, "cien": 100, "maximo": 100, "minimo": 0, "la mitad": 50,
}  # fmt: skip


@dataclass
class Step:
    kind: str  # key | brightness | theme | open | type | volume_set | scroll | focus | click
    arg: str = ""
    say: str = ""


def _level(text: str) -> int | None:
    m = re.search(r"(\d{1,3})", text)
    if m:
        return max(0, min(100, int(m.group(1))))
    for word, value in _NUMBERS.items():
        if re.search(rf"\b{word}\b", text):
            return value
    return None


def parse_device(t: str, raw: str = "") -> Step | None:
    """*t*: the plain (lower case, no accents) sentence; *raw*: as said."""
    if t in KEYS:
        keys, say = KEYS[t]
        return Step("key", keys, say)
    if t in _SCROLL_DOWN:
        return Step("scroll", "-6")
    if t in _SCROLL_UP:
        return Step("scroll", "6")
    m = _PRESS.fullmatch(t)
    if m:
        n = m.group("n") or "1"
        times = int(n) if n.isdigit() else _TIMES.get(n, 1)
        return Step("key", f"{KEY_NAMES[m.group('key')]}*{min(times, 30)}")
    # Brightness
    if re.search(r"\b(brillo|luminosidad)\b", t):
        level = _level(t)
        if re.search(r"\b(sube|subir|subele|aumenta|aumentar|mas)\b", t):
            return Step("brightness", "$c+20", "Más brillo.")
        if re.search(r"\b(baja|bajar|bajale|reduce|reducir|disminuye|disminuir|menos)\b", t) and level is None:
            return Step("brightness", "$c-20", "Menos brillo.")
        if level is not None:
            return Step("brightness", str(level), f"Brillo al {level}%.")
    # Light / dark mode
    if re.search(r"\b(modo|tema) (oscuro|nocturno)\b", t):
        return Step("theme", "0", "Modo oscuro.")
    if re.search(r"\b(modo|tema) (claro|de dia)\b", t):
        return Step("theme", "1", "Modo claro.")
    # Exact volume: "pon el volumen al 30"
    m = re.fullmatch(r"(?:pon|poner|deja|dejar|sube|subir|baja|bajar)? ?(?:el )?volumen (?:al|a|en) (.+)", t)
    if m:
        level = _level(m.group(1))
        if level is not None:
            return Step("volume_set", str(level), f"Volumen al {level}%.")
    # Settings pages: "abre la configuración del wifi", "ajustes de pantalla"
    m = re.fullmatch(
        r"(?:abre |muestrame |ve a |ir a )?(?:la |los )?(?:configuracion|ajustes|opciones)"
        r" (?:de |del |de la |de los )?(.+)",
        t,
    )
    if m and m.group(1).strip() in SETTINGS:
        page = m.group(1).strip()
        return Step("open", SETTINGS[page], f"Abriendo la configuración de {page}.")
    # Folders: "abre descargas", "abre la carpeta de documentos"
    m = re.fullmatch(
        r"(?:abre|muestrame|ve a) (?:la |mis |mi |los |las )?(?:carpeta )?(?:de |del )?(?:mis |las |los )?(.+)",
        t,
    )
    if m and m.group(1).strip() in FOLDERS:
        name = m.group(1).strip()
        return Step("open", FOLDERS[name], f"Abriendo {name}.")
    # Dictation: "escribe hola, ¿cómo estás?" (not "escribe un correo...")
    m = re.match(r"(?:escribe|teclea|escribi|escribelo)[:,]? (.+)", t)
    if m and not _COMPOSE.match(m.group(1)) and len(m.group(1)) <= 400:
        said = raw.strip()
        cut = re.match(r"\s*(?:sergio[,\s]+)?\S+[:,]?\s+", said, re.I)
        text = said[cut.end():] if cut else m.group(1)
        text = text.strip().strip("«»\"")
        enter = re.search(r"\s+y (?:dale|presiona|pulsa) (?:a )?(?:enter|intro)[.!]*$", text, re.I)
        if enter:  # "escribe hola y dale enter"
            text = text[: enter.start()] + "\n"
        return Step("type", text, "")
    m = _FOCUS.fullmatch(t)
    if m:
        name = (m.group("name") or m.group("name2") or "").strip()
        if name and name not in ("atras", "adelante", "inicio", "arriba", "abajo", "siguiente", "anterior", "otra"):
            return Step("focus", name)
    m = _CLICK.fullmatch(t)
    if m:
        name = m.group("name").strip()
        verb = m.group("verb")
        how = "double" if "doble" in verb else ("right" if "derecho" in verb else "left")
        if name and len(name) <= 60 and name not in ("todo", "eso", "esto", "aqui", "ahi"):
            # The name as said (accents, capitals): its last words.
            words = raw.strip().rstrip(".!?¡¿").split()
            count = len(name.split())
            shown = " ".join(words[-count:]) if len(words) >= count else name
            shown = shown.strip('«»"')
            return Step("click", f"{how}:{shown}")
    return None


def run_device(step: Step, act: Callable[[dict], Any]) -> str:
    """Do *step* with the control server's actions; returns what to say."""
    if step.kind == "key":
        keys, _, times = step.arg.partition("*")
        act({"action": "key", "keys": keys, "repeat": int(times or 1)})
    elif step.kind == "scroll":
        act({"action": "scroll", "amount": int(step.arg)})
    elif step.kind == "focus":
        try:
            act({"action": "focus", "target": step.arg})
        except Exception:  # noqa: BLE001 — not open: open it
            act({"action": "open_app", "target": step.arg})
            return f"Abriendo {step.arg}."
    elif step.kind == "click":
        how, _, name = step.arg.partition(":")
        act({"action": "click_name", "target": name, "button": how})
    elif step.kind == "open":
        act({"action": "open", "target": step.arg})
    elif step.kind == "type":
        act({"action": "type", "text": step.arg})
    elif step.kind == "volume_set":
        level = int(step.arg)
        act({"action": "key", "keys": "volumedown", "repeat": 50})  # to zero (2 % a press)
        if level >= 2:
            act({"action": "key", "keys": "volumeup", "repeat": round(level / 2)})
    elif step.kind == "brightness":
        expr = step.arg if step.arg.startswith("$c") else step.arg
        out = str(act({"action": "terminal", "command": BRIGHTNESS.format(expr=expr), "seconds": 20}) or "")
        if "exit code 0" not in out:
            return "Esta pantalla no deja cambiar el brillo desde Windows (pasa con monitores externos)."
        got = re.search(r"output:\s*(\d+)", out)
        return f"Brillo al {got.group(1)}%." if got else step.say
    elif step.kind == "theme":
        out = str(act({"action": "terminal", "command": THEME.format(v=step.arg), "seconds": 20}) or "")
        if "exit code 0" not in out:
            return "No pude cambiar el tema."
    return step.say


__all__ = ["FOLDERS", "KEYS", "SETTINGS", "Step", "parse_device", "run_device"]
