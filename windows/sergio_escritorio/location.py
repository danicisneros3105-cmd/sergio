"""Where the laptop is right now, for "¿qué avión pasa encima?".

Windows' own location service first (GPS if the laptop has one, otherwise
Wi-Fi positioning: tens of metres), then the internet address (city level),
then a place the user set by hand. It is refreshed in the background every
few minutes so asking about the plane overhead never waits for it.

To allow it: Configuración > Privacidad y seguridad > Ubicación > activa
"Servicios de ubicación" y "Permitir que las aplicaciones de escritorio
accedan a tu ubicación".
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)

REFRESH_SECONDS = 300.0
PS_LOCATION = r"""
Add-Type -AssemblyName System.Device
$w = New-Object System.Device.Location.GeoCoordinateWatcher([System.Device.Location.GeoPositionAccuracy]::High)
$w.Start()
$deadline = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $deadline -and ($w.Position.Location.IsUnknown) -and $w.Permission -ne 'Denied') {
  Start-Sleep -Milliseconds 200
}
$l = $w.Position.Location
$out = @{ permission = "$($w.Permission)"; status = "$($w.Status)" }
if (-not $l.IsUnknown) {
  $out.lat = $l.Latitude; $out.lon = $l.Longitude
  $out.alt = $l.Altitude; $out.accuracy = $l.HorizontalAccuracy
}
$w.Stop()
$out | ConvertTo-Json -Compress
"""
IP_SOURCES = ("https://ipapi.co/json/", "https://ipwho.is/")


@dataclass(frozen=True)
class Fix:
    lat: float
    lon: float
    accuracy_m: float  # how far off it may be
    source: str  # "windows" | "ip" | "config"
    alt: float | None = None  # metres above sea level, when known
    at: float = 0.0

    def describe(self) -> str:
        if self.source == "windows":
            return f"ubicación de Windows (±{self.accuracy_m:.0f} m)"
        if self.source == "ip":
            return (
                f"ubicación aproximada por internet (±{self.accuracy_m / 1000:.0f} km)"
            )
        return "ubicación configurada"


def parse_fixed(value: Any) -> Fix | None:
    """A place set by hand in the config: "lat,lon" or {"lat":..,"lon":..}."""
    try:
        if isinstance(value, dict):
            lat, lon = float(value["lat"]), float(value["lon"])
        elif isinstance(value, str) and "," in value:
            lat, lon = (float(x) for x in value.split(",")[:2])
        else:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return Fix(lat, lon, 50.0, "config")
    return None


def windows_fix(run: Callable[[str], str] | None = None) -> tuple[Fix | None, str]:
    """(fix, problem) from Windows' location service."""
    if run is None:
        import sys

        if sys.platform != "win32":
            return None, "solo en Windows"

        def run(script: str) -> str:
            done = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return done.stdout

    try:
        data = json.loads(run(PS_LOCATION) or "{}")
    except Exception as exc:  # noqa: BLE001
        return None, f"no pude preguntar a Windows ({exc})"
    if str(data.get("permission")) == "Denied":
        return None, (
            "Windows no me deja ver la ubicación: actívala en Configuración > "
            "Privacidad y seguridad > Ubicación (también para apps de escritorio)"
        )
    if data.get("lat") is None:
        return None, "Windows no supo la ubicación ahora (¿Wi-Fi apagado?)"
    alt = data.get("alt")
    alt = float(alt) if isinstance(alt, (int, float)) and alt not in (0, 0.0) else None
    accuracy = float(data.get("accuracy") or 100.0)
    return Fix(
        float(data["lat"]), float(data["lon"]), accuracy, "windows", alt, time.time()
    ), ""


def ip_fix(get: Callable[[str], dict] | None = None) -> Fix | None:
    if get is None:
        import httpx

        def get(url: str) -> dict:
            resp = httpx.get(url, timeout=5)
            resp.raise_for_status()
            return resp.json()

    for url in IP_SOURCES:
        try:
            data = get(url)
            lat, lon = float(data["latitude"]), float(data["longitude"])
            return Fix(lat, lon, 15_000.0, "ip", None, time.time())
        except Exception:  # noqa: BLE001 — try the next one
            continue
    return None


class Location:
    """The latest fix, kept fresh in the background."""

    def __init__(
        self,
        fixed: Any = None,
        *,
        windows: Callable[[], tuple[Fix | None, str]] = windows_fix,
        ip: Callable[[], Fix | None] = ip_fix,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.fixed = parse_fixed(fixed)
        self._windows = windows
        self._ip = ip
        self.clock = clock
        self.fix: Fix | None = None
        self.problem = ""
        self._at = -1e9
        self._lock = threading.Lock()

    def refresh(self) -> Fix | None:
        with self._lock:
            fix, problem = self._windows()
            if fix is None:
                fix = self._ip() or self.fixed
            if self.fixed is not None and (fix is None or fix.source == "ip"):
                fix = self.fixed  # a place set by hand beats a city-level guess
            self.fix, self.problem, self._at = fix, problem, self.clock()
            return fix

    def get(self, max_age: float = REFRESH_SECONDS) -> Fix | None:
        if self.fix is None or self.clock() - self._at > max_age:
            return self.refresh()
        return self.fix

    def keep_fresh(self) -> None:
        import sys

        if sys.platform != "win32":
            return  # asked when needed instead

        def loop() -> None:
            while True:
                try:
                    self.refresh()
                except Exception:  # noqa: BLE001
                    log.warning("location refresh failed", exc_info=True)
                time.sleep(REFRESH_SECONDS)

        threading.Thread(target=loop, daemon=True).start()


__all__ = ["Fix", "Location", "ip_fix", "parse_fixed", "windows_fix"]
