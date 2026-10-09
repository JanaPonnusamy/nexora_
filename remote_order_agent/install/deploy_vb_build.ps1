# Deploys the guarded VB build (vb_build\OrderManagement.exe) to the folder staff run it from, with a backup.
#   powershell -ExecutionPolicy Bypass -File deploy_vb_build.ps1 -Target 'D:\VBDOTNET\OrderManagement\OrderManagement\bin\Debug'
#   powershell -ExecutionPolicy Bypass -File deploy_vb_build.ps1 -Target '...' -Rollback
# ClickOnce users (Start menu 'OrderManagement') need a ClickOnce re-publish from Visual Studio instead; the
# database trigger already blocks Process Order deletes for NMV from any older build.
param([Parameter(Mandatory = $true)][string]$Target, [switch]$Rollback)
$ErrorActionPreference = 'Stop'
$pkg = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exe = Join-Path $Target 'OrderManagement.exe'
$bak = Join-Path $pkg ('rollback\vb_exe_' + (Split-Path $Target -Leaf))
if (Get-Process OrderManagement -ErrorAction SilentlyContinue) { throw 'Close OrderManagement on this PC first.' }
if ($Rollback) {
    $last = Get-ChildItem $bak -Filter 'OrderManagement_*.exe' | Sort-Object Name | Select-Object -Last 1
    if (-not $last) { throw "No backup in $bak" }
    Copy-Item $last.FullName $exe -Force; Write-Host "Restored $($last.Name) -> $exe"; return
}
New-Item -ItemType Directory -Force $bak | Out-Null
if (Test-Path $exe) { Copy-Item $exe (Join-Path $bak ('OrderManagement_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.exe')) }
Copy-Item (Join-Path $pkg 'vb_build\OrderManagement.exe') $exe -Force
Write-Host "Deployed guarded build to $exe (backup in $bak)"
