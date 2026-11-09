; Custom NSIS install steps for Nexora Supplier Stock.
;
; 1. Display: set the highest available resolution and keep Display settings
;    ENABLED (clears the NoDispCPL lock that older installers set). The script
;    (packaged via build.extraResources) clears the current user without admin;
;    HKLM is cleared too when run elevated.
; 2. Nexora Device Controller: install/upgrade the SYSTEM service that lets HO
;    start/stop/update the Nexora apps on this PC and replaces the old
;    watchdogs. It enrolls itself the first time a user signs in to this app.
;    Left installed on uninstall: it also manages the Store Agent / HO backend.
!macro customInstall
  DetailPrint "Setting maximum display resolution..."
  nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\resources\tools\lock-display-resolution.ps1"'
  Pop $0
  DetailPrint "Display resolution step finished (exit $0)."

  IfFileExists "$INSTDIR\resources\controller\NexoraDeviceController.exe" 0 +4
    DetailPrint "Installing Nexora Device Controller..."
    nsExec::ExecToLog '"$INSTDIR\resources\controller\NexoraDeviceController.exe" install-service'
    Pop $0
  DetailPrint "Device Controller step finished (exit $0)."
!macroend
