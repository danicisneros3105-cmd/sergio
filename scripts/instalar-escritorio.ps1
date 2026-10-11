# Instala a Sergio en Windows como compañero del cursor: sin ventana, una
# esfera junto al puntero, voz ("Sergio, ..." o Ctrl+Espacio) y control de la
# pantalla. No necesita administrador.
# Se ejecuta desde Ubuntu con:  sergio escritorio instalar
param([Parameter(Mandatory = $true)][string]$Fuente, [switch]$Gpu)
$ErrorActionPreference = "Stop"
function Say($m) { Write-Host "`n== $m" -ForegroundColor Cyan }

$token = $env:SERGIO_DESKTOP_TOKEN
if (-not $token) { throw "Falta el token: ejecuta 'sergio escritorio instalar' desde Ubuntu." }
$dest = Join-Path $env:LOCALAPPDATA "SergioEscritorio"
$app = Join-Path $dest "app"
$venv = Join-Path $dest "venv-python313"
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
if (-not (Test-Path $python)) { throw "Instala Python oficial primero: winget install --exact --id Python.Python.3.13 --source winget --scope user --accept-source-agreements --accept-package-agreements" }
if ((Get-AuthenticodeSignature $python).Status -ne "Valid") { throw "La firma de Python oficial no es válida; instalación detenida." }
& $python -c "import decimal, bz2, ssl; print('Python oficial: OK')"
if ($LASTEXITCODE -ne 0) { throw "Windows bloqueó módulos del Python oficial. Revisa el registro de integridad de código." }
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
    Where-Object { $_.ExecutablePath -like "$dest\venv*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
New-Item -ItemType Directory -Force $app | Out-Null
robocopy $Fuente $app /MIR /XD __pycache__ .venv /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "No pude copiar los archivos (robocopy $LASTEXITCODE)." }
# Conserva los ajustes del usuario (palabra "Sergio", mostrar junto al cursor).
$cfgPath = Join-Path $dest "config.json"
$cfg = @{ wake_word = $true; show_companion = $true }
if (Test-Path $cfgPath) {
    try {
        $old = Get-Content $cfgPath -Raw | ConvertFrom-Json
        foreach ($p in $old.PSObject.Properties) { $cfg[$p.Name] = $p.Value }
    } catch { }
}
$cfg.token = $token
$cfg.server_url = "http://localhost:8000"
$cfg.port = 8765
$cfg | ConvertTo-Json | Set-Content -Encoding UTF8 $cfgPath

Say "3/4 Instalando lo que necesita (verás el progreso; la primera vez tarda unos minutos)"
$env:UV_PROJECT_ENVIRONMENT = $venv
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & $python -m venv --without-pip $venv
    if ($LASTEXITCODE -ne 0) { throw "No pude crear el entorno con Python oficial." }
}
$env:UV_HTTP_TIMEOUT = "120"
# --inexact keeps the optional NVIDIA extra if it was installed before.
& $uv sync --project $app --python $python --inexact
if ($LASTEXITCODE -ne 0) {
    Start-Sleep -Seconds 5
    & $uv sync --project $app --python $python --inexact
}
if ($LASTEXITCODE -ne 0) { throw "No pude instalar las dependencias (uv sync). Revisa tu internet y vuelve a intentar." }
Write-Host "   Ojos y manos (objetos, caras y hologramas con la cámara)…"
& $uv sync --project $app --python $python --inexact --extra manos
if ($LASTEXITCODE -ne 0) { Write-Host "   No pude instalar la visión con las manos ahora; lo demás funciona." -ForegroundColor Yellow }
& $uv sync --project $app --python $python --inexact --extra manos --extra llamada
if ($LASTEXITCODE -ne 0) { Write-Host "   No pude instalar el cancelador de eco; en llamadas usa audífonos o habla fuerte para interrumpir." -ForegroundColor Yellow }
& $uv sync --project $app --python $python --inexact --extra manos --extra llamada --extra oido
if ($LASTEXITCODE -ne 0) { Write-Host "   No pude instalar el oído instantáneo; Sergio te oye igual, un poco más lento." -ForegroundColor Yellow }
Write-Host "   Actas de reuniones y videollamadas (audio de la computadora)…"
& $uv sync --project $app --python $python --inexact --extra manos --extra llamada --extra oido --extra reuniones
if ($LASTEXITCODE -ne 0) { Write-Host "   No pude instalar la grabación del audio de la computadora; las actas usarán solo el micrófono." -ForegroundColor Yellow }
Write-Host "   Posproducción de video (auto-editor y MoviePy)…"
& $uv sync --project $app --python $python --inexact --extra posproduccion
if ($LASTEXITCODE -ne 0) { Write-Host "   No pude instalar la posproducción ahora; el editor de video funciona sin cortar silencios." -ForegroundColor Yellow }
Write-Host "   Visión moderna (YOLO11 + YOLOE: objetos y personas sin confundir tu mano)… puede tardar"
$env:UV_HTTP_TIMEOUT = "900"
$visionOk = $false
$gpuCap = 0.0
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    try {
        $capText = (& nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>$null | Select-Object -First 1)
        $gpuCap = [double]::Parse("$capText".Trim(), [Globalization.CultureInfo]::InvariantCulture)
    } catch { $gpuCap = 7.5 }  # an old driver without the query: try the GPU
}
if ($gpuCap -gt 0 -and $gpuCap -lt 7.5) {
    Write-Host "   Tu tarjeta NVIDIA es anterior a las GTX 16/RTX 20: la visión usará el procesador."
}
if ($gpuCap -ge 7.5) {
    Write-Host "   Tarjeta NVIDIA: la visión usará la GPU (descarga grande, ~2,5 GB, solo la primera vez)"
    & $uv sync --project $app --python $python --inexact --extra manos --extra llamada --extra oido --extra reuniones --extra vision-gpu
    $visionOk = ($LASTEXITCODE -eq 0)
}
if (-not $visionOk) {
    & $uv sync --project $app --python $python --inexact --extra manos --extra llamada --extra oido --extra reuniones --extra vision
    if ($LASTEXITCODE -ne 0) { Write-Host "   No pude instalar la visión moderna ahora; uso la anterior." -ForegroundColor Yellow }
}
if ($Gpu) {
    Say "Extra: oído con la tarjeta NVIDIA (~1 GB, puede tardar)"
    $env:UV_HTTP_TIMEOUT = "900"
    & $uv sync --project $app --python $python --inexact --extra gpu
    if ($LASTEXITCODE -ne 0) { Write-Host "   No pude bajarlo ahora; Sergio sigue funcionando con el procesador." -ForegroundColor Yellow }
}

Write-Host "   Limpiando versiones viejas (caché, Pythons reemplazados, restos de Blender)…"
& (Join-Path $venv "Scripts\python.exe") -m sergio_escritorio.limpieza $uv

& (Join-Path $venv "Scripts\python.exe") -c "import decimal, bz2; from PySide6.QtWidgets import QApplication; import sergio_escritorio.app; print('Módulos de escritorio: OK')"
if ($LASTEXITCODE -ne 0) { throw "El escritorio no pasó la prueba de módulos nativos. No se modificaron los accesos directos." }
Say "4/4 Arranque con Windows"
$ico = Join-Path $dest "sergio.ico"
& (Join-Path $venv "Scripts\python.exe") -c "from sergio_escritorio.app import make_icon; make_icon('idle').save(r'$ico', sizes=[(16,16),(32,32),(48,48),(64,64)])"
$shell = New-Object -ComObject WScript.Shell
# Sin icono en el escritorio: arranca con Windows y queda en el menú Inicio
# por si lo cierras. Quita el acceso directo de versiones anteriores.
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "Sergio.lnk") -ErrorAction SilentlyContinue
$places = @(
    [Environment]::GetFolderPath("Startup"),
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
$started = Start-Process $pyw -ArgumentList "-m", "sergio_escritorio" -WorkingDirectory $dest -PassThru
Start-Sleep -Seconds 3
$started.Refresh()
if ($started.HasExited) { throw "El escritorio se cerró al arrancar. Revisa $dest\sergio.log; no puedo confirmar que esté visible." }
Write-Host "Proceso de escritorio iniciado (PID $($started.Id)). Comprueba el personaje junto al cursor; Ctrl+Espacio abre el panel." -ForegroundColor Green
