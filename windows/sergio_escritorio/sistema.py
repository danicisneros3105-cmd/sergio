"""The device itself, from a fixed list (owner, 4 Nov 2026: «que Sergio tenga
más control del dispositivo»).

``desktop_action system`` runs one of these operations. Each is either keys or
a **fixed** PowerShell script whose only input is a number or a choice from a
list (never text the model wrote), so they run at once, without the Visage
check that free commands (``terminal``) need. What reaches other people or
cannot be undone is not here.

``plan(op, value)`` is pure (tested): it says which keys or which script.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

OPS = (
    "volume", "mute", "media", "brightness", "theme", "window", "desktop",
    "clipboard_get", "clipboard_set", "lock", "battery", "wifi", "windows",
    "notify", "screenshot", "night_light", "settings",
)  # fmt: skip

WINDOW = {
    "maximize": "win+up", "minimize": "win+down", "left": "win+left", "right": "win+right",
    "fullscreen": "f11", "switch": "alt+tab", "next_desktop": "win+ctrl+right",
    "prev_desktop": "win+ctrl+left", "new_desktop": "win+ctrl+d", "task_view": "win+tab",
}  # fmt: skip
MEDIA = {"play": "playpause", "pause": "playpause", "playpause": "playpause",
         "next": "nexttrack", "previous": "prevtrack", "prev": "prevtrack"}  # fmt: skip
SETTINGS = {
    "wifi": "ms-settings:network-wifi", "bluetooth": "ms-settings:bluetooth",
    "display": "ms-settings:display", "sound": "ms-settings:sound",
    "battery": "ms-settings:batterysaver", "notifications": "ms-settings:notifications",
    "update": "ms-settings:windowsupdate", "apps": "ms-settings:appsfeatures",
    "privacy": "ms-settings:privacy", "storage": "ms-settings:storagesense",
    "night_light": "ms-settings:nightlight", "focus": "ms-settings:quiethours",
}  # fmt: skip

BRIGHTNESS_PS = (
    "$n=[Math]::Max(0,[Math]::Min(100,{level}));"
    "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
    "Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness=[byte]$n}} | Out-Null;$n"
)
THEME_PS = (
    "$k='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize';"
    "Set-ItemProperty $k -Name AppsUseLightTheme -Value {v};"
    "Set-ItemProperty $k -Name SystemUsesLightTheme -Value {v}"
)
BATTERY_PS = (
    "$b=Get-CimInstance Win32_Battery;if(-not $b){'sin bateria'}else{"
    "'{0}|{1}' -f $b.EstimatedChargeRemaining,$b.BatteryStatus}"
)
WIFI_PS = "netsh wlan show interfaces"
NOTIFY_PS = (
    "Add-Type -AssemblyName System.Windows.Forms;$n=New-Object System.Windows.Forms.NotifyIcon;"
    "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
    "$n.ShowBalloonTip(6000,'Sergio',[IO.File]::ReadAllText($env:SERGIO_AVISO),'None');Start-Sleep 7;$n.Dispose()"
)
LOCK_PS = "rundll32.exe user32.dll,LockWorkStation"


class SistemaError(ValueError):
    pass


@dataclass
class Plan:
    keys: str = ""  # a key chord to press
    repeat: int = 1
    then: str = ""  # a second chord after the first (exact volume)
    then_repeat: int = 0
    script: str = ""  # a fixed PowerShell script
    open: str = ""  # a settings page or folder
    special: str = ""  # done by the backend itself (clipboard, windows, screenshot)
    say: str = ""


def _level(value: Any) -> int:
    try:
        n = int(float(str(value).strip().rstrip("%")))
    except (TypeError, ValueError) as exc:
        raise SistemaError("El nivel es un número de 0 a 100.") from exc
    return max(0, min(100, n))


def plan(op: str, value: Any = None) -> Plan:
    """What *op* does, without doing it (pure)."""
    op = str(op or "").strip().lower()
    v = str(value or "").strip().lower()
    if op not in OPS:
        raise SistemaError(
            f"Operación desconocida: {op!r}. Use una de: {', '.join(OPS)}."
        )
    if op == "volume":
        level = _level(value)
        # to zero (2 % a press), then up to the level: exact on any PC
        return Plan("volumedown", 50, "volumeup" if level >= 2 else "", round(level / 2),
                    say=f"Volumen al {level} %.")  # fmt: skip
    if op == "mute":
        return Plan("volumemute", say="Sonido silenciado o devuelto.")
    if op == "media":
        key = MEDIA.get(v or "playpause")
        if not key:
            raise SistemaError("media: play, pause, next o previous.")
        return Plan(
            key,
            say={"nexttrack": "Siguiente.", "prevtrack": "Anterior."}.get(
                key, "Listo."
            ),
        )
    if op == "brightness":
        level = _level(value)
        return Plan(
            script=BRIGHTNESS_PS.format(level=level), say=f"Brillo al {level} %."
        )
    if op == "theme":
        if v not in ("dark", "light", "oscuro", "claro"):
            raise SistemaError("theme: dark o light.")
        light = 1 if v in ("light", "claro") else 0
        return Plan(
            script=THEME_PS.format(v=light),
            say="Modo claro." if light else "Modo oscuro.",
        )
    if op == "window":
        key = WINDOW.get(v)
        if not key:
            raise SistemaError("window: " + ", ".join(WINDOW) + ".")
        return Plan(key, say="Listo.")
    if op == "desktop":
        return Plan("win+d", say="Escritorio a la vista (otra vez para volver).")
    if op == "lock":
        return Plan(script=LOCK_PS, say="Equipo bloqueado.")
    if op == "battery":
        return Plan(script=BATTERY_PS)
    if op == "wifi":
        return Plan(script=WIFI_PS)
    if op == "notify":
        if not v:
            raise SistemaError("notify: el texto del aviso.")
        return Plan(special="notify", say="Aviso mostrado.")
    if op == "settings":
        page = SETTINGS.get(v)
        if not page:
            raise SistemaError("settings: " + ", ".join(SETTINGS) + ".")
        return Plan(open=page, say="Abierto.")
    if op == "night_light":
        return Plan(
            open=SETTINGS["night_light"],
            say="Abrí la luz nocturna: actívela con el interruptor.",
        )
    return Plan(special=op)  # clipboard_get, clipboard_set, windows, screenshot


def battery_line(out: str) -> str:
    text = (out or "").strip().splitlines()[-1:] or [""]
    line = text[0]
    if "sin bateria" in line:
        return "Este equipo no tiene batería (va enchufado)."
    pct, _, status = line.partition("|")
    charging = status.strip() in ("2", "6", "7", "8", "9")
    return (
        f"Batería al {pct.strip()} %" + (", cargando." if charging else ".")
        if pct.strip().isdigit()
        else "No pude leer la batería."
    )


def wifi_line(out: str) -> str:
    fields: dict[str, str] = {}
    for line in (out or "").splitlines():
        key, sep, val = line.partition(":")
        if sep:
            fields.setdefault(key.strip().lower(), val.strip())
    state = fields.get("state") or fields.get("estado") or ""
    ssid = fields.get("ssid", "")
    signal = fields.get("signal") or fields.get("señal") or ""
    if not state:
        return "No hay Wi-Fi en este equipo o está apagado."
    if "disconnected" in state.lower() or "desconectado" in state.lower():
        return "El Wi-Fi está desconectado."
    return f"Conectado a «{ssid}»" + (f", señal {signal}." if signal else ".")


def run(op: str, value: Any, backend: Any, press: Callable[[str, int], None]) -> str:
    """Do *op* on this computer; returns what to say."""
    p = plan(op, value)
    if p.keys:
        press(p.keys, p.repeat)
        if p.then and p.then_repeat:
            press(p.then, p.then_repeat)
        return p.say
    if p.open:
        backend.open_target(p.open)
        return p.say
    if p.script:
        ran = backend.shell(p.script, 20)
        if int(ran.get("exit_code", 1)) != 0:
            if op == "brightness":
                return "Esta pantalla no deja cambiar el brillo desde Windows (pasa con monitores externos)."
            return "No pude hacerlo en este equipo."
        if op == "battery":
            return battery_line(ran.get("stdout", ""))
        if op == "wifi":
            return wifi_line(ran.get("stdout", ""))
        return p.say
    special = getattr(backend, "system_special", None)
    if special is None:
        raise SistemaError("Este equipo no permite esa operación.")
    return str(special(p.special or op, "" if value is None else str(value)))


__all__ = ["OPS", "Plan", "SistemaError", "battery_line", "plan", "run", "wifi_line"]
