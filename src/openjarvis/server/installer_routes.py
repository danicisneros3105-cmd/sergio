"""Plug-and-Play Downloadable App Portal & One-Click Launcher Engine.

Delivers a friction-free, zero-command desktop and mobile experience:
1. GET /descargar/windows: 1-click Windows desktop launcher (.bat) running quietly in frameless app mode.
2. GET /descargar/macos: 1-click macOS .command launcher.
3. GET /descargar/linux: 1-click Linux desktop launcher.
4. GET /portal and /app: Complete web application with account management,
   autonomous permission cards, payment gateway checkout, and live conversational voice/chat.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

log = logging.getLogger("openjarvis.server.installer_routes")

router = APIRouter(tags=["descargas_y_portal"])

STATIC_PORTAL_PATH = Path(__file__).parent / "static" / "portal.html"


def generate_windows_launcher_bat(server_url: str) -> str:
    """Generate a clean, zero-command Windows launcher that runs silently in native app mode."""
    return f"""@echo off
:: ============================================================================
:: Sergio AI - Lanzador Plug and Play para Windows
:: No requiere comandos ni configuraciones manuales.
:: ============================================================================
title Sergio AI - Conectando...
set "SERVER_URL={server_url}"

:: 1. Comprobar si Microsoft Edge esta disponible para abrir en modo App Nativa
set "EDGE_X86=%PROGRAMFILES(X86)%\\Microsoft\\Edge\\Application\\msedge.exe"
if exist "%EDGE_X86%" (
    start "" "%EDGE_X86%" --app="%SERVER_URL%/portal" --window-size=1200,850
    exit /b 0
)

set "EDGE_PROG=%PROGRAMFILES%\\Microsoft\\Edge\\Application\\msedge.exe"
if exist "%EDGE_PROG%" (
    start "" "%EDGE_PROG%" --app="%SERVER_URL%/portal" --window-size=1200,850
    exit /b 0
)

:: 2. Comprobar Google Chrome en modo App
set "CHROME_PROG=%PROGRAMFILES%\\Google\\Chrome\\Application\\chrome.exe"
if exist "%CHROME_PROG%" (
    start "" "%CHROME_PROG%" --app="%SERVER_URL%/portal" --window-size=1200,850
    exit /b 0
)

:: 3. Navegador predeterminado si no se encuentra Edge o Chrome
start "" "%SERVER_URL%/portal"
exit /b 0
"""


def generate_macos_launcher_command(server_url: str) -> str:
    """Generate a 1-click macOS .command script to launch Sergio in frameless app mode."""
    return f"""#!/bin/bash
# ============================================================================
# Sergio AI - Lanzador Plug and Play para macOS
# ============================================================================
open -na "Google Chrome" --args --app="{server_url}/portal" 2>/dev/null || \\
open -na "Microsoft Edge" --args --app="{server_url}/portal" 2>/dev/null || \\
open "{server_url}/portal"

osascript -e 'tell application "Terminal" to close (every window whose name contains "Sergio")' &>/dev/null &
exit 0
"""


def generate_linux_launcher_sh(server_url: str) -> str:
    """Generate a 1-click Linux desktop launcher."""
    return f"""#!/bin/bash
# ============================================================================
# Sergio AI - Lanzador Plug and Play para Linux
# ============================================================================
google-chrome --app="{server_url}/portal" 2>/dev/null || \\
chromium --app="{server_url}/portal" 2>/dev/null || \\
xdg-open "{server_url}/portal" 2>/dev/null
exit 0
"""


@router.get("/descargar/windows", response_class=Response)
async def download_windows_app(request: Request) -> Response:
    """Download the zero-command Windows 1-click desktop app (.bat)."""
    base_url = str(request.base_url).rstrip("/")
    script_content = generate_windows_launcher_bat(base_url)
    headers = {
        "Content-Disposition": 'attachment; filename="Iniciar_Sergio_AI.bat"',
        "Content-Type": "application/x-bat",
    }
    return Response(content=script_content, media_type="application/x-bat", headers=headers)


@router.get("/descargar/macos", response_class=Response)
async def download_macos_app(request: Request) -> Response:
    """Download the zero-command macOS 1-click desktop app (.command)."""
    base_url = str(request.base_url).rstrip("/")
    script_content = generate_macos_launcher_command(base_url)
    headers = {
        "Content-Disposition": 'attachment; filename="Iniciar_Sergio_AI.command"',
        "Content-Type": "application/x-sh",
    }
    return Response(content=script_content, media_type="application/x-sh", headers=headers)


@router.get("/descargar/linux", response_class=Response)
async def download_linux_app(request: Request) -> Response:
    """Download the zero-command Linux 1-click desktop app (.sh)."""
    base_url = str(request.base_url).rstrip("/")
    script_content = generate_linux_launcher_sh(base_url)
    headers = {
        "Content-Disposition": 'attachment; filename="Iniciar_Sergio_AI.sh"',
        "Content-Type": "application/x-sh",
    }
    return Response(content=script_content, media_type="application/x-sh", headers=headers)


@router.get("/descargar/info", response_model=Dict[str, Any])
async def download_info(request: Request) -> Dict[str, Any]:
    """Retrieve metadata and download instructions for all supported operating systems."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "status": "success",
        "app_name": "Sergio AI Plug & Play",
        "version": "2.4.0-sovereign",
        "portales": {
            "web_portal": f"{base_url}/portal",
            "pwa_manifest": f"{base_url}/manifest.webmanifest",
        },
        "descargas_directas": {
            "windows": f"{base_url}/descargar/windows",
            "macos": f"{base_url}/descargar/macos",
            "linux": f"{base_url}/descargar/linux",
        },
        "instrucciones": {
            "windows": "Descargue Iniciar_Sergio_AI.bat y haga doble clic. Se abrirá como app de escritorio nativa.",
            "macos": "Descargue Iniciar_Sergio_AI.command y ejecútelo con doble clic.",
            "iphone": "Abra la URL en Safari y seleccione 'Añadir a pantalla de inicio' para tener la PWA.",
            "android": "Abra la URL en Chrome y seleccione 'Instalar aplicación' en el menú.",
        },
    }


@router.get("/portal", response_class=HTMLResponse)
@router.get("/app", response_class=HTMLResponse)
async def serve_sergio_web_portal(_request: Request) -> Response:
    """Serve the complete, modern, reactive Plug-and-Play Sergio App Portal."""
    if STATIC_PORTAL_PATH.is_file():
        return FileResponse(STATIC_PORTAL_PATH, media_type="text/html; charset=utf-8")
    return HTMLResponse(
        "<h1>Sergio Web Portal</h1><p>Archivo portal.html no encontrado en static/.</p>",
        status_code=404,
    )


__all__ = [
    "generate_windows_launcher_bat",
    "generate_macos_launcher_command",
    "generate_linux_launcher_sh",
    "download_windows_app",
    "download_macos_app",
    "download_linux_app",
    "download_info",
    "serve_sergio_web_portal",
    "router",
]
