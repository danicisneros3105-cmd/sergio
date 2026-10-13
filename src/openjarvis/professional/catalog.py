"""Reviewed upstream programs. Detection describes this host, never the user's PC."""

from __future__ import annotations

import platform
import shutil
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Program:
    id: str
    name: str
    group: str
    description: str
    repository: str
    license: str
    binaries: tuple[str, ...] = ()
    winget: str = ""
    adapter: str = "desktop"
    note: str = ""

    @property
    def source(self) -> str:
        return "https://github.com/" + self.repository

    @property
    def opens_window(self) -> bool:
        return self.adapter == "desktop" and self.id not in {
            "git",
            "gh",
            "uv",
            "rg",
            "fd",
            "bat",
            "just",
            "node",
        }


PROGRAMS = (
    Program(
        "codium",
        "VSCodium",
        "Código",
        "Editor completo, extensiones y depuración.",
        "VSCodium/vscodium",
        "MIT",
        ("codium",),
        "VSCodium.VSCodium",
    ),
    Program(
        "git",
        "Git",
        "Código",
        "Versiones, ramas y revisión de cambios.",
        "git-for-windows/git",
        "GPL-2.0",
        ("git",),
        "Git.Git",
    ),
    Program(
        "gh",
        "GitHub CLI",
        "Código",
        "Repositorios, pull requests y acciones desde terminal.",
        "cli/cli",
        "MIT",
        ("gh",),
        "GitHub.cli",
    ),
    Program(
        "terminal",
        "Windows Terminal",
        "Código",
        "PowerShell, Ubuntu y terminales en pestañas.",
        "microsoft/terminal",
        "MIT",
        ("wt",),
        "Microsoft.WindowsTerminal",
    ),
    Program(
        "powertoys",
        "PowerToys",
        "Código",
        "Ventanas, búsqueda y utilidades de escritorio.",
        "microsoft/PowerToys",
        "MIT",
        (),
        "Microsoft.PowerToys",
    ),
    Program(
        "uv",
        "uv",
        "Código",
        "Entornos y dependencias de Python.",
        "astral-sh/uv",
        "MIT / Apache-2.0",
        ("uv",),
        "astral-sh.uv",
    ),
    Program(
        "rg",
        "ripgrep",
        "Código",
        "Búsqueda rápida dentro del código.",
        "BurntSushi/ripgrep",
        "MIT / Unlicense",
        ("rg",),
        "BurntSushi.ripgrep.MSVC",
    ),
    Program(
        "fd",
        "fd",
        "Código",
        "Localizar archivos y carpetas.",
        "sharkdp/fd",
        "MIT / Apache-2.0",
        ("fd", "fdfind"),
        "sharkdp.fd",
    ),
    Program(
        "bat",
        "bat",
        "Código",
        "Leer archivos con sintaxis resaltada.",
        "sharkdp/bat",
        "MIT / Apache-2.0",
        ("bat", "batcat"),
        "sharkdp.bat",
    ),
    Program(
        "just",
        "just",
        "Código",
        "Tareas reproducibles de proyecto.",
        "casey/just",
        "CC0-1.0",
        ("just",),
        "Casey.Just",
    ),
    Program(
        "node",
        "Node.js LTS",
        "Código",
        "JavaScript y herramientas de frontend.",
        "nodejs/node",
        "MIT y licencias incluidas",
        ("node",),
        "OpenJS.NodeJS.LTS",
    ),
    Program(
        "freecad",
        "FreeCAD",
        "Arquitectura",
        "CAD paramétrico, piezas, planos y banco BIM.",
        "FreeCAD/FreeCAD",
        "LGPL-2.1",
        ("FreeCAD", "freecad", "FreeCADCmd"),
        "FreeCAD.FreeCAD",
    ),
    Program(
        "blender",
        "Blender",
        "Arquitectura",
        "Modelado, materiales, render y los hologramas de Sergio.",
        "blender/blender",
        "GPL-3.0",
        ("blender",),
        "BlenderFoundation.Blender",
    ),
    Program(
        "bonsai",
        "Bonsai · BlenderBIM",
        "Arquitectura",
        "BIM nativo IFC dentro de Blender.",
        "IfcOpenShell/IfcOpenShell",
        "GPL-3.0 add-on / LGPL library",
        adapter="addon",
        note="Instalar la extensión Bonsai en Blender. Tener Blender no confirma que el add-on esté activo.",
    ),
    Program(
        "librecad",
        "LibreCAD",
        "Arquitectura",
        "Dibujo técnico 2D, DXF y planos.",
        "LibreCAD/LibreCAD",
        "GPL-2.0",
        ("librecad",),
        "LibreCAD.LibreCAD",
    ),
    Program(
        "artcraft",
        "ArtCraft",
        "Creatividad",
        "Estudio completo de composición 2D/3D y generación de imagen y vídeo.",
        "storytold/artcraft",
        "Apache-2.0",
        ("artcraft",),
        note="Algunos modelos del estudio requieren cuenta, API o créditos del proveedor.",
    ),
    *(
        Program(
            slug,
            name,
            "Creatividad",
            purpose,
            "storytold/" + slug,
            "Apache-2.0",
            (slug,),
            note="Aplicación independiente de ArtCraft; revisar su release. Varias están en desarrollo o alpha.",
        )
        for slug, name, purpose in (
            ("photocraft", "PhotoCraft", "Imagen, capas, máscaras y PSD."),
            ("lightcraft", "LightCraft", "Biblioteca fotográfica y revelado RAW."),
            ("vectorcraft", "VectorCraft", "Ilustración vectorial y tipografía."),
            ("filmcraft", "FilmCraft", "Montaje de vídeo en una línea de tiempo."),
            ("effectcraft", "EffectCraft", "Motion graphics y composición de efectos."),
            ("designcraft", "DesignCraft", "Maquetación, publicaciones y páginas."),
            ("pdfcraft", "PdfCraft", "Organizar, combinar y trabajar con PDF."),
            ("wordcraft", "WordCraft", "Documentos y procesamiento de texto."),
            ("soundcraft", "SoundCraft", "Grabación, mezcla y edición de audio."),
            ("deckcraft", "DeckCraft", "Presentaciones y diapositivas."),
            ("cadcraft", "CADCraft", "Dibujo y diseño asistido por computadora."),
            ("gridcraft", "GridCraft", "Hojas de cálculo y análisis de datos."),
        )
    ),
    Program(
        "kdenlive",
        "Kdenlive",
        "Creatividad",
        "Edición de vídeo multipista; complemento de FilmCraft.",
        "KDE/kdenlive",
        "GPL-3.0",
        ("kdenlive",),
        "KDE.Kdenlive",
    ),
    Program(
        "opendesign",
        "OpenDesign",
        "Diseño",
        "Editor completo de lienzos, páginas y marcas; API de plantillas conectada a Sergio.",
        "clawnify/OpenDesign",
        "MIT",
        adapter="service",
        note="Servicio local independiente. Conectar su API en Ajustes del estudio.",
    ),
    Program(
        "lidojs",
        "LidoJS",
        "Diseño",
        "Editor de lienzos y plantillas con React.",
        "lidojs/canva-clone",
        "Licencia no declarada en el repo revisado",
        adapter="reference",
        note="Dependencias @lidojs y derechos pendientes de verificar; no redistribuido ni activado automáticamente.",
    ),
    Program(
        "kronos",
        "Kronos",
        "Mercados",
        "Modelo de escenarios OHLCV; adaptador con validación de datos y pesos locales.",
        "shiyu-coder/Kronos",
        "MIT",
        adapter="model",
        note="Requiere PyTorch, el repo y pesos locales. No coloca órdenes ni garantiza rendimientos.",
    ),
)
BY_ID = {program.id: program for program in PROGRAMS}


def catalog() -> dict:
    items = []
    for p in PROGRAMS:
        found = next((path for b in p.binaries if (path := shutil.which(b))), None)
        items.append(
            {
                **asdict(p),
                "source": p.source,
                "detected": bool(found),
                "opens_window": p.opens_window,
                "installable": bool(p.winget),
                "download": p.source + "/releases",
            }
        )
    return {"host": platform.system(), "scope": "server_path", "programs": items}


def installer(ids: list[str]) -> str:
    if not ids or len(ids) > len(PROGRAMS):
        raise ValueError("Seleccione al menos una aplicación compatible con WinGet.")
    selected = []
    for key in dict.fromkeys(ids):
        item = BY_ID.get(key)
        if item is None or not item.winget:
            raise ValueError("Aplicación sin instalador WinGet revisado: " + key)
        selected.append(item.winget)
    # These are reviewed identifiers, never interpolated user input or commands.
    lines = [
        "# Sergio: instalar únicamente las aplicaciones seleccionadas.",
        "$ErrorActionPreference = 'Stop'",
        "if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { "
        "throw 'Instale App Installer de Microsoft para usar WinGet.' }",
        "$packages = @(" + ", ".join("'" + x + "'" for x in selected) + ")",
        "foreach ($package in $packages) {",
        "    Write-Host ('Preparando ' + $package)",
        "    & winget.exe list --exact --id $package --source winget --disable-interactivity | Out-Null",
        "    if ($LASTEXITCODE -eq 0) { Write-Host 'Ya instalado.'; continue }",
        "    & winget.exe install --exact --id $package --source winget "
        "--accept-source-agreements --accept-package-agreements --disable-interactivity",
        "    if ($LASTEXITCODE -ne 0) { throw ('No se pudo instalar ' + $package + '. Revise el mensaje de WinGet.') }",
        "}",
        "Write-Host 'Selección completada. Reinicie las terminales para refrescar PATH.'",
    ]
    return "\r\n".join(lines) + "\r\n"
