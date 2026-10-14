# Sergio's one-click install, run by Sergio-Instalador.exe (already as
# administrator: Windows asked once). No window of its own: every line it
# prints appears in the installer's progress list. It can run again at any
# time (after a reboot, or to repair): each step skips what is already done.
#
# Exit codes: 0 done · 3010 Windows must restart (the installer continues by
# itself after the restart) · anything else: a step failed (see the log).
param([string]$Repo = "https://github.com/danicisneros3105-cmd/sergio", [string]$Branch = "main")
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$home_ = Join-Path $env:LOCALAPPDATA "Sergio"
New-Item -ItemType Directory -Force -Path $home_ | Out-Null
$log = Join-Path $home_ "instalacion.log"
function Say($m) { Write-Output $m; Add-Content -Path $log -Value ("{0:u}  {1}" -f (Get-Date), $m) }
function Wsl([string]$cmd, [string]$user = "") {
    $args_ = @("-d", "Ubuntu")
    if ($user) { $args_ += @("-u", $user) }
    $out = & wsl.exe @args_ -- bash -lc $cmd 2>&1
    $out | ForEach-Object { Add-Content -Path $log -Value $_ }
    return $LASTEXITCODE
}

# -- 1. WSL and Ubuntu ------------------------------------------------------------
Say "Preparando Ubuntu dentro de Windows…"
$distros = try { (& { $ErrorActionPreference = "Continue"; wsl.exe -l -q 2>&1 }) -join "`n" -replace "`0", "" } catch { "" }
if (-not ($distros -match "Ubuntu")) {
    & wsl.exe --install -d Ubuntu --no-launch 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ }
    $distros = try { (& { $ErrorActionPreference = "Continue"; wsl.exe -l -q 2>&1 }) -join "`n" -replace "`0", "" } catch { "" }
    if (-not ($distros -match "Ubuntu")) {
        $ubuntu = Get-Command ubuntu.exe -ErrorAction SilentlyContinue
        if (-not $ubuntu) {
            Say "Windows necesita reiniciarse para terminar de activar Ubuntu. El instalador seguirá solo después."
            exit 3010
        }
        & ubuntu.exe install --root 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ }
    }
}
# A user like yours, with sudo and without asking for a password (nobody types
# anything in a black window).
$user = ($env:USERNAME.ToLower() -replace "[^a-z0-9_-]", "")
if (-not $user -or $user -match "^[0-9-]") { $user = "sergio" }
Wsl "id -u $user >/dev/null 2>&1 || useradd -m -s /bin/bash -G sudo $user; echo '$user ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-sergio; chmod 440 /etc/sudoers.d/90-sergio; printf '[boot]\nsystemd=true\n[user]\ndefault=$user\n' > /etc/wsl.conf" "root" | Out-Null
$wslcfg = Join-Path $env:USERPROFILE ".wslconfig"
if (-not (Test-Path $wslcfg) -or -not (Select-String -Path $wslcfg -Pattern "networkingMode" -Quiet)) {
    Add-Content $wslcfg "`n[wsl2]`nnetworkingMode=mirrored"
}
& wsl.exe --shutdown 2>&1 | Out-Null

# -- 2. Git for Windows: its Credential Manager signs in to GitHub in a window --
Say "Preparando el acceso seguro a GitHub…"
$gcm = "C:\Program Files\Git\mingw64\bin\git-credential-manager.exe"
if (-not (Test-Path $gcm)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget install -e --id Git.Git --silent --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    }
}
if (Test-Path $gcm) {
    $wslGcm = "/mnt/c/Program\ Files/Git/mingw64/bin/git-credential-manager.exe"
    Wsl "git config --global credential.helper '$wslGcm'" | Out-Null
}

# -- 3. Sergio itself -------------------------------------------------------------------
Say "Descargando Sergio…"
if ((Wsl "test -d ~/sergio/.git || git clone -b '$Branch' '$Repo' ~/sergio") -ne 0) {
    Say "No pude descargar Sergio: inicie sesión en GitHub cuando se lo pida y vuelva a abrir el instalador."
    exit 2
}
Say "Instalando Sergio (unos minutos la primera vez)…"
if ((Wsl "cd ~/sergio && ./scripts/install-todo-en-uno.sh --permanente") -ne 0) {
    Say "Algo falló al instalar. Vuelva a abrir el instalador: retoma donde quedó. Detalles: $log"
    exit 4
}
& wsl.exe --shutdown 2>&1 | Out-Null
Say "Dejando Sergio siempre encendido…"
Wsl "cd ~/sergio && uv run sergio servicio instalar </dev/null" | Out-Null
$auto = Join-Path $PSScriptRoot "windows-autoarranque.ps1"
if (Test-Path $auto) { & $auto -Activar 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ } }

# -- 4. The desktop app (voice, companion, notch, screen control) --------------------------
Say "Instalando la app de escritorio…"
if ((Wsl "cd ~/sergio && uv run sergio escritorio instalar") -ne 0) {
    Say "La app de escritorio no terminó de instalarse; Sergio en el navegador ya funciona. Detalles: $log"
    exit 5
}
Say "Listo, señor."
exit 0
