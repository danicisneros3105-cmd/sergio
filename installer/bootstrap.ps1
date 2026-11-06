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
if ($Repo -cne "https://github.com/danicisneros3105-cmd/sergio" -or $Branch -cnotmatch "^[A-Za-z0-9][A-Za-z0-9._/-]*$") {
    throw "Repositorio o rama de instalación no válidos."
}
$home_ = Join-Path $env:LOCALAPPDATA "Sergio"
New-Item -ItemType Directory -Force -Path $home_ | Out-Null
$log = Join-Path $home_ "instalacion.log"
function Say($m) { Write-Output $m; Add-Content -Path $log -Value ("{0:u}  {1}" -f (Get-Date), $m) }
function Wsl([string]$cmd, [string]$user = "") {
    $args_ = @("-d", "Ubuntu")
    if ($user) { $args_ += @("-u", $user) }
    $out = & wsl.exe @args_ -- bash -lc $cmd 2>&1
    $code = $LASTEXITCODE
    $out | ForEach-Object { Add-Content -Path $log -Value $_ }
    return $code
}

# -- 1. WSL and Ubuntu ------------------------------------------------------------
Say "Preparando Ubuntu dentro de Windows…"
$distros = try { (& { $ErrorActionPreference = "Continue"; wsl.exe -l -q 2>&1 }) -join "`n" -replace "`0", "" } catch { "" }
if (-not ($distros -match "Ubuntu")) {
    & wsl.exe --install -d Ubuntu --no-launch 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ }
    $distros = try { (& { $ErrorActionPreference = "Continue"; wsl.exe -l -q 2>&1 }) -join "`n" -replace "`0", "" } catch { "" }
    if (-not ($distros -match "Ubuntu")) {
        Say "Si Windows pidió reiniciar, reinícielo. Abra Ubuntu, configure su usuario y después vuelva a abrir el instalador."
        exit 3
    }
}
# Use the Ubuntu account chosen by the owner. Do not reset its WSL settings,
# grant permanent sudo access, or stop other running distributions.
if ((Wsl 'test "$(id -u)" -ne 0 && systemctl --user show-environment >/dev/null 2>&1') -ne 0) {
    Say "Abra Ubuntu, termine la configuración de su usuario y active systemd si hace falta. Después vuelva a abrir este instalador."
    exit 3
}
Say "Instalando los paquetes necesarios en Ubuntu…"
if ((Wsl "apt-get update && apt-get install -y git curl build-essential libssl-dev libyaml-dev zlib1g-dev libffi-dev pkg-config unzip ca-certificates" "root") -ne 0) {
    Say "No se pudieron instalar los paquetes de Ubuntu. Detalles: $log"
    exit 3
}

# -- 2. Git for Windows: its Credential Manager signs in to GitHub in a window --
Say "Preparando el acceso seguro a GitHub…"
$gcm = "C:\Program Files\Git\mingw64\bin\git-credential-manager.exe"
if (-not (Test-Path $gcm)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget install -e --id Git.Git --silent --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    }
}
# Only this checkout gets the credential helper.
$gcmArg = ""
if (Test-Path $gcm) {
    $gcmArg = "-c 'credential.helper=/mnt/c/Program\ Files/Git/mingw64/bin/git-credential-manager.exe'"
}

# -- 3. Sergio itself -------------------------------------------------------------------
Say "Descargando Sergio…"
if ((Wsl "test -d ~/sergio/.git || git $gcmArg clone -b '$Branch' '$Repo' ~/sergio") -ne 0) {
    Say "No pude descargar Sergio: inicie sesión en GitHub con una cuenta que tenga acceso y vuelva a abrir el instalador."
    exit 2
}
if ((Wsl 'cd ~/sergio && case "$(git remote get-url origin)" in https://github.com/danicisneros3105-cmd/sergio|https://github.com/danicisneros3105-cmd/sergio.git|git@github.com:danicisneros3105-cmd/sergio.git) exit 0 ;; *) exit 1 ;; esac') -ne 0) {
    Say "La carpeta ~/sergio existe pero no apunta al repositorio esperado. No se modificó."
    exit 2
}
if ($gcmArg) {
    Wsl "git -C ~/sergio config --local credential.helper '/mnt/c/Program\ Files/Git/mingw64/bin/git-credential-manager.exe'" | Out-Null
}
Say "Instalando Sergio (unos minutos la primera vez)…"
if ((Wsl "cd ~/sergio && ./scripts/install-todo-en-uno.sh --paquetes-listos") -ne 0) {
    Say "Algo falló al instalar. Vuelva a abrir el instalador: retoma donde quedó. Detalles: $log"
    exit 4
}
Say "Dejando Sergio siempre encendido…"
if ((Wsl 'export PATH="$HOME/.local/share/mise/shims:$HOME/.local/bin:$HOME/.cargo/bin:$PATH"; cd ~/sergio && uv run --no-sync sergio servicio instalar </dev/null') -ne 0) {
    Say "El servicio de Sergio no pudo iniciar. Detalles: $log"
    exit 6
}
$auto = Join-Path $PSScriptRoot "windows-autoarranque.ps1"
if (Test-Path $auto) { & $auto -Activar 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ } }

# -- 4. The desktop app (voice, companion, notch, screen control) --------------------------
Say "Instalando la app de escritorio…"
if ((Wsl 'export PATH="$HOME/.local/share/mise/shims:$HOME/.local/bin:$HOME/.cargo/bin:$PATH"; cd ~/sergio && uv run --no-sync sergio escritorio instalar') -ne 0) {
    Say "La app de escritorio no terminó de instalarse; Sergio en el navegador ya funciona. Detalles: $log"
    exit 5
}
Say "Listo, señor."
exit 0
