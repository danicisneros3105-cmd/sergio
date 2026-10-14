; Sergio-Instalador.exe — one download, one "Sí" to the administrator
; question, and Sergio is installed: Ubuntu (WSL), the server, the desktop
; app and its shortcuts. Build: bash scripts/build-instalador.sh

Unicode true
ManifestDPIAware true
SetCompressor /SOLID lzma
RequestExecutionLevel admin

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP "Sergio"
!ifndef VERSION
  !define VERSION "1.0.0"
!endif

Name "${APP}"
Caption "${APP}"
BrandingText " "
OutFile "Sergio-Instalador.exe"
InstallDir "$LOCALAPPDATA\Sergio"
ShowInstDetails show
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileDescription" "Instalador de ${APP}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Apache-2.0"

!define MUI_ICON "sergio.ico"
!define MUI_UNICON "sergio.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Sergio"
!define MUI_WELCOMEPAGE_TEXT " "
!define MUI_FINISHPAGE_TITLE "Listo"
!define MUI_FINISHPAGE_TEXT " "
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Abrir Sergio"
!define MUI_FINISHPAGE_RUN_FUNCTION OpenSergio

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"

Section "Sergio" Main
  SetOutPath "$INSTDIR"
  File "bootstrap.ps1"
  File "..\scripts\windows-autoarranque.ps1"
  File "sergio.ico"
  ; A copy of this installer, so it can continue by itself after a restart.
  CopyFiles /SILENT "$EXEPATH" "$INSTDIR\Sergio-Instalador.exe"
  DetailPrint "Empezando…"
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "$INSTDIR\bootstrap.ps1"'
  Pop $0
  ${If} $0 == "3010"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\RunOnce" "SergioInstalar" '"$INSTDIR\Sergio-Instalador.exe"'
    SetRebootFlag true
    DetailPrint "Reinicie Windows: la instalación continuará sola."
  ${ElseIf} $0 != "0"
    MessageBox MB_ICONEXCLAMATION|MB_OK "La instalación no terminó (paso $0). Vuelva a abrir el instalador: retoma donde quedó.$\r$\nDetalles: $INSTDIR\instalacion.log"
    Abort
  ${EndIf}
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sergio" "DisplayName" "${APP}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sergio" "DisplayIcon" "$INSTDIR\sergio.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sergio" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sergio" "UninstallString" '"$INSTDIR\Desinstalar.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sergio" "NoModify" 1
SectionEnd

Function OpenSergio
  ; The desktop app's own shortcut (made by its installer).
  IfFileExists "$SMPROGRAMS\Sergio.lnk" 0 +3
    ExecShell "open" "$SMPROGRAMS\Sergio.lnk"
    Return
  ExecShell "open" "http://localhost:8000"
FunctionEnd

Section "Uninstall"
  ; Your data stays (Ubuntu keeps ~/.openjarvis); only Sergio on Windows goes.
  nsExec::ExecToLog 'schtasks.exe /Delete /TN "Sergio (WSL)" /F'
  Delete "$SMPROGRAMS\Sergio.lnk"
  Delete "$DESKTOP\Sergio.lnk"
  RMDir /r "$LOCALAPPDATA\SergioEscritorio"
  Delete "$INSTDIR\*.*"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sergio"
SectionEnd
