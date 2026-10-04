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
}

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
    kind: str  # key | brightness | theme | open | type | volume_set
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
        return Step("type", text.strip().strip("«»\""), "Escrito.")
    return None


def run_device(step: Step, act: Callable[[dict], Any]) -> str:
    """Do *step* with the control server's actions; returns what to say."""
    if step.kind == "key":
        act({"action": "key", "keys": step.arg})
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
