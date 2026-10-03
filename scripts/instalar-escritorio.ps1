# Instala "Sergio Escritorio" en Windows: ventana propia, icono junto al reloj,
# atajos, voz y control de la pantalla. No necesita administrador.
# Se ejecuta desde Ubuntu con:  sergio escritorio instalar
param([Parameter(Mandatory = $true)][string]$Fuente)
$ErrorActionPreference = "Stop"
function Say($m) { Write-Host "`n== $m" -ForegroundColor Cyan }

$token = $env:SERGIO_DESKTOP_TOKEN
if (-not $token) { throw "Falta el token: ejecuta 'sergio escritorio instalar' desde Ubuntu." }
$dest = Join-Path $env:LOCALAPPDATA "SergioEscritorio"
$app = Join-Path $dest "app"
$venv = Join-Path $dest "venv"
$pyw = Join-Path $venv "Scripts\pythonw.exe"

Say "1/4 uv (Python para Windows)"
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) { $uv = $uvCmd.Source } else {
    powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
}

Say "2/4 Copiando Sergio Escritorio"
# Cierra la versión anterior si está abierta.
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.ExecutablePath -like "$venv*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
New-Item -ItemType Directory -Force $app | Out-Null
robocopy $Fuente $app /MIR /XD __pycache__ .venv /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "No pude copiar los archivos (robocopy $LASTEXITCODE)." }
@{ token = $token; server_url = "http://localhost:8000"; port = 8765 } |
    ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $dest "config.json")

Say "3/4 Instalando lo que necesita (1-3 minutos la primera vez)"
$env:UV_PROJECT_ENVIRONMENT = $venv
& $uv sync --project $app --python 3.12 --quiet
if ($LASTEXITCODE -ne 0) { throw "No pude instalar las dependencias (uv sync)." }

Say "4/4 Accesos directos y arranque con Windows"
$ico = Join-Path $dest "sergio.ico"
& (Join-Path $venv "Scripts\python.exe") -c "from sergio_escritorio.app import make_icon; make_icon('idle').save(r'$ico', sizes=[(16,16),(32,32),(48,48),(64,64)])"
$shell = New-Object -ComObject WScript.Shell
$places = @(
    [Environment]::GetFolderPath("Startup"),
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs")
)
foreach ($dir in $places) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "Sergio.lnk"))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = "-m sergio_escritorio"
    $lnk.WorkingDirectory = $dest
    $lnk.IconLocation = $ico
    $lnk.Description = "Sergio, tu asistente"
    $lnk.Save()
}
Start-Process $pyw -ArgumentList "-m", "sergio_escritorio" -WorkingDirectory $dest
Write-Host "Sergio Escritorio instalado y abierto." -ForegroundColor Green
