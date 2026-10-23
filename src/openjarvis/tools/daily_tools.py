"""Tools: everyday jobs on the owner's Windows laptop.

«Sergio, mi PC está muy lenta» and «organiza mi galería y borra las fotos
duplicadas» are jobs the agent could already do by writing PowerShell or
Python by hand. They are done here once, carefully, so every model gets them
right: first a look that changes nothing, then, only after the owner agrees,
the change, and always a way back.

* Nothing is deleted for good. Duplicate photos go to a folder
  «Duplicados (Sergio)» next to the gallery; startup apps are switched off
  with a copy kept to switch them back on. The only thing removed is the
  temporary files folder (files older than a day), and only when asked.
* Each change goes through Sergio Escritorio, which asks the owner to confirm
  in Windows (``python`` and ``terminal`` actions).
"""

from __future__ import annotations

import json
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import ToolSpec
from openjarvis.tools.desktop_tools import _DesktopTool

DUPLICATES_FOLDER = "Duplicados (Sergio)"
MANIFEST = "_sergio_duplicados.json"
STARTUP_BACKUP = "inicio-desactivado.json"  # in Documents\Sergio

# -- slow computer ---------------------------------------------------------------

_DIAGNOSE = r"""
$ErrorActionPreference = 'SilentlyContinue'
$os = Get-CimInstance Win32_OperatingSystem
'Memoria: {0:N1} GB libres de {1:N1} GB' -f ($os.FreePhysicalMemory/1MB), ($os.TotalVisibleMemorySize/1MB)
$cpu = (Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average
"Procesador: $cpu % en uso"
Get-PSDrive -PSProvider FileSystem | Where-Object Used | ForEach-Object {
  'Disco {0}: {1:N1} GB libres de {2:N1} GB' -f $_.Name, ($_.Free/1GB), (($_.Used + $_.Free)/1GB)
}
'Encendido desde: ' + $os.LastBootUpTime
''
'--- Lo que más memoria usa ---'
Get-Process | Group-Object ProcessName | ForEach-Object {
  [pscustomobject]@{
    N = $_.Name
    MB = [math]::Round(($_.Group | Measure-Object WorkingSet64 -Sum).Sum / 1MB)
    CPU = [math]::Round(($_.Group | Measure-Object CPU -Sum).Sum)
    K = $_.Count
  }
} | Sort-Object MB -Descending | Select-Object -First 12 | ForEach-Object {
  '{0} ({3} ventanas o procesos): {1} MB, {2} s de procesador' -f $_.N, $_.MB, $_.CPU, $_.K
}
''
'--- Se abren solos al encender ---'
Get-CimInstance Win32_StartupCommand | ForEach-Object { '{0} | {1}' -f $_.Name, $_.Location }
''
'--- Archivos temporales ---'
$t = (Get-ChildItem $env:TEMP -Recurse -Force -File | Measure-Object Length -Sum).Sum
'{0:N2} GB en {1}' -f ($t/1GB), $env:TEMP
$bin = (New-Object -ComObject Shell.Application).NameSpace(10).Items() | Measure-Object -Property Size -Sum
'Papelera: {0:N2} GB' -f ($bin.Sum/1GB)
"""

_CLEAN_TEMP = r"""
$ErrorActionPreference = 'SilentlyContinue'
$old = Get-ChildItem $env:TEMP -Recurse -Force -File | Where-Object LastWriteTime -lt (Get-Date).AddDays(-1)
$size = ($old | Measure-Object Length -Sum).Sum
$n = 0
foreach ($f in $old) {
  Remove-Item -LiteralPath $f.FullName -Force
  if (-not (Test-Path -LiteralPath $f.FullName)) { $n++ }
}
'Borré {0} archivos temporales ({1:N2} GB). Los que estaban en uso se quedaron.' -f $n, ($size/1GB)
"""

# HKCU Run values and Startup-folder shortcuts: the ones the owner's account
# controls without administrator rights. A copy of each one goes to
# Documents\Sergio so «startup_on» puts it back.
_STARTUP = r"""
$ErrorActionPreference = 'Stop'
$names = ConvertFrom-Json @'
__NAMES__
'@
$on = __ON__
$dir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Sergio'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$backup = Join-Path $dir '__BACKUP__'
$saved = @()
if (Test-Path $backup) { $saved = @(Get-Content $backup -Raw | ConvertFrom-Json) }
$run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$folder = [Environment]::GetFolderPath('Startup')
$parked = Join-Path $dir 'inicio-desactivado'
$done = @()
foreach ($name in $names) {
  if ($on) {
    foreach ($item in @($saved | Where-Object { $_.name -like "*$name*" })) {
      if ($item.kind -eq 'run') { Set-ItemProperty -Path $run -Name $item.name -Value $item.value }
      else { Move-Item -LiteralPath (Join-Path $parked $item.name) -Destination $folder -Force }
      $saved = @($saved | Where-Object { $_.name -ne $item.name })
      $done += $item.name
    }
  } else {
    $props = Get-ItemProperty -Path $run
    foreach ($p in $props.PSObject.Properties) {
      if ($p.Name -like 'PS*' -or $p.Name -notlike "*$name*") { continue }
      $saved += [pscustomobject]@{ kind = 'run'; name = $p.Name; value = $p.Value }
      Remove-ItemProperty -Path $run -Name $p.Name
      $done += $p.Name
    }
    New-Item -ItemType Directory -Force -Path $parked | Out-Null
    foreach ($f in Get-ChildItem -LiteralPath $folder -File | Where-Object Name -like "*$name*") {
      Move-Item -LiteralPath $f.FullName -Destination $parked -Force
      $saved += [pscustomobject]@{ kind = 'folder'; name = $f.Name; value = '' }
      $done += $f.Name
    }
  }
}
ConvertTo-Json -InputObject @($saved) | Set-Content -Path $backup -Encoding UTF8
if ($done.Count -eq 0) {
  'No encontré nada con ese nombre en el inicio de su cuenta ' +
  '(lo del sistema se cambia en el Administrador de tareas).'
}
elseif ($on) { 'Vuelven a abrirse al encender: ' + ($done -join ', ') }
else { 'Ya no se abren al encender: ' + ($done -join ', ') + '. Se pueden volver a activar.' }
"""


def startup_script(names: list[str], on: bool) -> str:
    clean = [n.replace("'", "").replace('"', "").strip() for n in names]
    clean = [n for n in clean if len(n) >= 2]
    return (
        _STARTUP.replace("__NAMES__", json.dumps(clean))
        .replace("__ON__", "$true" if on else "$false")
        .replace("__BACKUP__", STARTUP_BACKUP)
    )


@ToolRegistry.register("pc_checkup")
class PcCheckupTool(_DesktopTool):
    tool_id = "pc_checkup"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="pc_checkup",
            description=(
                "When the user's Windows laptop is slow. mode='diagnose' (changes "
                "nothing) reports free memory, processor and disk, the programs "
                "using the most memory, what opens by itself at startup, and the "
                "size of temporary files and the recycle bin. Explain in plain "
                "words what slows it down and propose the fixes. Only after the "
                "user agrees: mode='clean_temp' deletes temporary files older than "
                "a day; mode='startup_off' with 'names' stops those apps opening "
                "at startup (a copy is kept; mode='startup_on' puts them back). "
                "To close a running program use desktop_action close_app. Never "
                "uninstall programs or empty the recycle bin without the user "
                "naming them."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["diagnose", "clean_temp", "startup_off", "startup_on"],
                    },
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Startup apps (part of the name is enough).",
                    },
                },
                "required": ["mode"],
            },
            category="desktop",
            timeout_seconds=300,
        )

    def execute(self, **params: Any) -> ToolResult:
        mode = str(params.get("mode") or "diagnose")
        if mode == "diagnose":
            command = _DIAGNOSE
        elif mode == "clean_temp":
            command = _CLEAN_TEMP
        elif mode in {"startup_off", "startup_on"}:
            names = [str(n) for n in params.get("names") or []]
            if not names:
                return self._fail("Dígame qué programas: 'names'.")
            command = startup_script(names, mode == "startup_on")
        else:
            return self._fail(f"Modo desconocido: {mode}")
        action = {"action": "terminal", "command": command, "seconds": 240}
        try:
            data = self._call("POST", "/act", json=action, timeout=300)
        except RuntimeError as exc:
            return self._fail(f"No pude revisar el equipo: {exc}")
        result = str(data.get("result", ""))
        return ToolResult(
            tool_name=self.tool_id,
            content=result,
            success=result.startswith("exit code 0"),
        )


# -- duplicate photos ------------------------------------------------------------

# Runs on the laptop with its own Python (Pillow is there). Plain Python, no
# Windows calls, so the tests run the very same program.
_PHOTOS = r'''
import hashlib, json, os, shutil, sys, time
from pathlib import Path

ARGS = json.loads(__ARGS__)
EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
SKIP = ARGS["folder_name"]
MANIFEST = ARGS["manifest"]


def gallery(target):
    home = Path.home()
    words = {"", "fotos", "galeria", "galería", "imagenes", "imágenes", "pictures"}
    if target.strip().lower() in words:
        for p in (home / "Pictures", home / "OneDrive" / "Pictures",
                  home / "OneDrive" / "Imágenes", home / "Imágenes"):
            if p.is_dir():
                return p
        return home / "Pictures"
    p = Path(os.path.expandvars(os.path.expanduser(target)))
    return p if p.is_absolute() else home / p


root = gallery(ARGS["target"])
bin_dir = root / SKIP
manifest = bin_dir / MANIFEST

if ARGS["undo"]:
    moved = json.loads(manifest.read_text("utf-8")) if manifest.exists() else []
    back = 0
    for item in moved:
        src, dst = Path(item["now"]), Path(item["was"])
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            back += 1
    if manifest.exists():
        manifest.unlink()
    print(json.dumps({"undone": back, "folder": str(root)}))
    sys.exit(0)

try:
    from PIL import Image
except ImportError:
    Image = None


def dhash(path):
    with Image.open(path) as im:
        w, h = im.size
        rgb = im.convert("RGB")
        small = rgb.convert("L").resize((9, 8))
        px = list(small.getdata())
        tone = rgb.resize((1, 1)).getpixel((0, 0))
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits, w / h, w * h


def thumb(path):
    with Image.open(path) as im:
        return list(im.convert("RGB").resize((24, 24)).getdata())


def same_picture(a, b):
    """A second, closer look: the same picture differs by a few levels at most."""
    if Image is None:
        return True  # grouped by the file's exact bytes
    try:
        ta, tb = thumb(a), thumb(b)
    except Exception:
        return False
    diff = sum(abs(x - y) for p, q in zip(ta, tb) for x, y in zip(p, q))
    return diff / (len(ta) * 3) < 12


files = []
for dirpath, dirnames, names in os.walk(root):
    dirnames[:] = [d for d in dirnames if d != SKIP and not d.startswith(".")]
    for n in names:
        if Path(n).suffix.lower() in EXT:
            files.append(Path(dirpath) / n)
    if len(files) >= ARGS["limit"]:
        break

# Pictures whose fingerprints differ in at most 3 of 64 bits share at least
# one exact quarter: only those are compared, so 30 000 photos stay quick.
info, by_bytes, buckets = [], {}, {}
for f in files[: ARGS["limit"]]:
    try:
        st = f.stat()
        bits = None
        if Image is not None:
            try:
                bits, ratio, pixels = dhash(f)
            except Exception:
                bits = None
        if bits is None:
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            by_bytes.setdefault(digest, []).append(len(info))
            ratio, pixels = 0.0, 0
        info.append((pixels, st.st_size, -st.st_mtime, f, bits, ratio))
        if bits is not None:
            for part in range(4):
                key = (part, (bits >> (16 * part)) & 0xFFFF)
                buckets.setdefault(key, []).append(len(info) - 1)
    except OSError:
        continue

parent = list(range(len(info)))


def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def join(i, j):
    parent[find(i)] = find(j)


for same in by_bytes.values():
    for j in same[1:]:
        join(same[0], j)
seen = set()
for members in buckets.values():
    for x in range(len(members)):
        for y in range(x + 1, len(members)):
            i, j = members[x], members[y]
            if (i, j) in seen or find(i) == find(j):
                continue
            seen.add((i, j))
            a, b = info[i], info[j]
            close = bin(a[4] ^ b[4]).count("1") <= 3 and abs(a[5] - b[5]) < 0.02
            if close and same_picture(a[3], b[3]):
                join(i, j)

groups = {}
for i in range(len(info)):
    groups.setdefault(find(i), []).append(info[i][:4])

plan = []
for items in groups.values():
    if len(items) < 2:
        continue
    # keep the sharpest, then the heaviest file, then the oldest
    items.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    plan.append({"keep": str(items[0][3]), "extra": [str(t[3]) for t in items[1:]]})

extra = sum(len(g["extra"]) for g in plan)
size = sum(Path(p).stat().st_size for g in plan for p in g["extra"])
out = {"folder": str(root), "photos": len(files), "groups": len(plan),
       "duplicates": extra, "mb": round(size / 1e6, 1), "applied": False,
       "examples": plan[:5], "moved_to": str(bin_dir)}
if ARGS["apply"] and plan:
    bin_dir.mkdir(exist_ok=True)
    moved = json.loads(manifest.read_text("utf-8")) if manifest.exists() else []
    stamp = time.strftime("%Y%m%d%H%M%S")
    for g in plan:
        for p in g["extra"]:
            src = Path(p)
            dst = bin_dir / src.name
            if dst.exists():
                dst = bin_dir / f"{src.stem}-{stamp}-{len(moved)}{src.suffix}"
            shutil.move(str(src), str(dst))
            moved.append({"was": str(src), "now": str(dst), "same_as": g["keep"]})
    manifest.write_text(json.dumps(moved, ensure_ascii=False, indent=1), "utf-8")
    out["applied"] = True
print(json.dumps(out, ensure_ascii=False))
'''


def photos_script(
    target: str = "", *, apply: bool = False, undo: bool = False, limit: int = 30000
) -> str:
    args = {
        "target": target,
        "apply": apply,
        "undo": undo,
        "limit": int(limit),
        "folder_name": DUPLICATES_FOLDER,
        "manifest": MANIFEST,
    }
    return _PHOTOS.replace("__ARGS__", repr(json.dumps(args, ensure_ascii=False)))


def describe_photos(raw: str) -> str:
    """The program's last JSON line, said in plain Spanish."""
    line = next(
        (x for x in reversed(raw.splitlines()) if x.strip().startswith("{")), ""
    )
    try:
        data = json.loads(line)
    except ValueError:
        return raw
    if "undone" in data:
        return f"Devolví {data['undone']} fotos a su sitio en {data['folder']}."
    if not data["duplicates"]:
        return f"Revisé {data['photos']} fotos en {data['folder']}: no hay duplicadas."
    text = (
        f"Revisé {data['photos']} fotos en {data['folder']}: hay {data['duplicates']} "
        f"duplicadas en {data['groups']} grupos ({data['mb']} MB). "
    )
    if data["applied"]:
        return text + (
            f"Las moví a «{DUPLICATES_FOLDER}» ({data['moved_to']}); de cada grupo "
            "quedó la de mejor calidad. Revíselas y vacíe esa carpeta cuando quiera, "
            "o pídame deshacerlo."
        )
    sample = "; ".join(
        f"{g['keep']} se queda, sobran {len(g['extra'])}" for g in data["examples"][:3]
    )
    return text + f"Ejemplos: {sample}. Todavía no moví nada."


@ToolRegistry.register("photos_duplicates")
class PhotosDuplicatesTool(_DesktopTool):
    tool_id = "photos_duplicates"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="photos_duplicates",
            description=(
                "Find duplicate photos in the user's gallery on the Windows "
                "laptop (same picture, even resized or saved again). 'target' is "
                "a folder or empty for the Pictures gallery. ALWAYS call first "
                "with apply=false (changes nothing), tell the user how many and "
                "which, and only with their OK call apply=true: the extra copies "
                "move to a «Duplicados (Sergio)» folder (the best one of each "
                "stays), nothing is deleted for good; undo=true puts them back. "
                "To sort the gallery into folders by month afterwards use "
                "files_organize with by='month'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Folder."},
                    "apply": {"type": "boolean"},
                    "undo": {"type": "boolean"},
                },
            },
            category="desktop",
            timeout_seconds=960,
        )

    def execute(self, **params: Any) -> ToolResult:
        code = photos_script(
            str(params.get("target") or ""),
            apply=bool(params.get("apply")),
            undo=bool(params.get("undo")),
        )
        action = {"action": "python", "code": code, "seconds": 900}
        try:
            data = self._call("POST", "/act", json=action, timeout=960)
        except RuntimeError as exc:
            return self._fail(f"No pude revisar las fotos: {exc}")
        result = str(data.get("result", ""))
        if not result.startswith("exit code 0"):
            return self._fail(result)
        return self._ok(describe_photos(result))


__all__ = [
    "PcCheckupTool",
    "PhotosDuplicatesTool",
    "describe_photos",
    "photos_script",
    "startup_script",
]
