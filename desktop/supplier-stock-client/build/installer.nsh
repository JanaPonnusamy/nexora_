; Custom NSIS install step for Nexora Supplier Stock.
; Runs the display-resolution lock at install time: set the highest available
; resolution and hide the Display settings so the store user can't change it.
; The script (packaged via build.extraResources) does what it can without admin
; (current-user lock + resolution); machine-wide lock applies if the installer
; was run elevated.
!macro customInstall
  DetailPrint "Setting maximum display resolution and locking Display settings..."
  nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\resources\tools\lock-display-resolution.ps1"'
  Pop $0
  DetailPrint "Resolution lock finished (exit $0)."
!macroend
