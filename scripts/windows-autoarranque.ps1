# Arranque automático de Sergio en Windows 11 (sin ventanas).
#
# WSL no se enciende solo al iniciar Windows. Esta tarea programada lo
# despierta al iniciar sesión y lo mantiene encendido; dentro de Ubuntu,
# systemd arranca Sergio (instalado con `sergio servicio instalar`).
#
#   .\scripts\windows-autoarranque.ps1 -Activar      # arrancar con Windows
#   .\scripts\windows-autoarranque.ps1 -Desactivar   # dejar de arrancar
#   .\scripts\windows-autoarranque.ps1 -Estado
param(
    [switch]$Activar,
    [switch]$Desactivar,
    [switch]$Estado,
    [string]$Distro = "Ubuntu"
)
$ErrorActionPreference = "Stop"
$TaskName = "Sergio (WSL)"

if ($Activar) {
    # conhost --headless evita que aparezca una consola; `sleep infinity`
    # mantiene viva la distribución para que los servicios sigan corriendo.
    $action = New-ScheduledTaskAction -Execute "conhost.exe" `
        -Argument "--headless wsl.exe -d $Distro --exec /bin/sh -c `"exec sleep infinity`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Description "Mantiene WSL encendido para Sergio" -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Listo: Sergio arrancará cada vez que inicies sesión." -ForegroundColor Green
    Write-Host "Ábrelo en http://localhost:8000"
}
elseif ($Desactivar) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    Write-Host "Sergio ya no arrancará con Windows (para apagarlo ahora: wsl --shutdown)."
}
elseif ($Estado) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) { Write-Host "Arranque automático: activado ($($task.State))" }
    else { Write-Host "Arranque automático: desactivado" }
}
else {
    Write-Host "Usa -Activar, -Desactivar o -Estado"
}
