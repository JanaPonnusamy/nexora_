<#
    Lock the Windows display resolution on a store PC.

    What it does:
      1. Sets the display to its HIGHEST available resolution.
      2. Hides the "Screen Resolution" / Display settings page (NoDispCPL policy)
         so the day-to-day user can't change it back.

    Usage (run AS ADMINISTRATOR, while logged in as the store's normal user so
    the per-user policy applies to them):
        powershell -ExecutionPolicy Bypass -File lock-display-resolution.ps1
    To revert (admin):
        powershell -ExecutionPolicy Bypass -File lock-display-resolution.ps1 -Unlock

    Notes:
      - A local administrator can still undo this; it stops ordinary users, not admins.
      - Log off/on (or reboot) after running for the policy to take effect.
      - Tested pattern for Windows 7/8/10; try it on ONE PC first.
#>
param([switch]$Unlock)

$ErrorActionPreference = 'Stop'

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Please run this script as Administrator.'
    }
}
Assert-Admin

# Both hives: HKLM for machine-wide, HKCU for the currently logged-in store user.
$policyKeys = @(
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies\System',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System'
)

if ($Unlock) {
    foreach ($k in $policyKeys) {
        if (Test-Path $k) { Set-ItemProperty -Path $k -Name 'NoDispCPL' -Value 0 -Type DWord -Force }
    }
    Write-Host 'UNLOCKED: users can change the display resolution again. Log off/on to apply.'
    return
}

# --- 1) Set the highest available resolution -------------------------------
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class NexoraDisp {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Ansi)]
    public struct DEVMODE {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmDeviceName;
        public short dmSpecVersion; public short dmDriverVersion; public short dmSize; public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX; public int dmPositionY; public int dmDisplayOrientation; public int dmDisplayFixedOutput;
        public short dmColor; public short dmDuplex; public short dmYResolution; public short dmTTOption; public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmFormName;
        public short dmLogPixels; public int dmBitsPerPel; public int dmPelsWidth; public int dmPelsHeight;
        public int dmDisplayFlags; public int dmDisplayFrequency;
        public int dmICMMethod; public int dmICMIntent; public int dmMediaType; public int dmDitherType;
        public int dmReserved1; public int dmReserved2; public int dmPanningWidth; public int dmPanningHeight;
    }
    [DllImport("user32.dll")] public static extern int EnumDisplaySettings(string dev, int mode, ref DEVMODE dm);
    [DllImport("user32.dll")] public static extern int ChangeDisplaySettings(ref DEVMODE dm, int flags);
    public const int CDS_UPDATEREGISTRY = 0x01;
}
'@

$mode = New-Object 'NexoraDisp+DEVMODE'
$best = $null
$i = 0
while ([NexoraDisp]::EnumDisplaySettings($null, $i, [ref]$mode) -ne 0) {
    $area = [int64]$mode.dmPelsWidth * [int64]$mode.dmPelsHeight
    if ($null -eq $best) {
        $best = $mode
    } else {
        $bestArea = [int64]$best.dmPelsWidth * [int64]$best.dmPelsHeight
        if ($area -gt $bestArea -or ($area -eq $bestArea -and $mode.dmBitsPerPel -gt $best.dmBitsPerPel)) {
            $best = $mode
        }
    }
    $i++
}

if ($null -ne $best) {
    $result = [NexoraDisp]::ChangeDisplaySettings([ref]$best, [NexoraDisp]::CDS_UPDATEREGISTRY)
    Write-Host ("Set resolution to {0}x{1} @ {2}bpp (result {3}; 0 = success)." -f `
        $best.dmPelsWidth, $best.dmPelsHeight, $best.dmBitsPerPel, $result)
} else {
    Write-Host 'Could not enumerate display modes; resolution left unchanged.'
}

# --- 2) Lock the Display settings page -------------------------------------
foreach ($k in $policyKeys) {
    if (-not (Test-Path $k)) { New-Item -Path $k -Force | Out-Null }
    Set-ItemProperty -Path $k -Name 'NoDispCPL' -Value 1 -Type DWord -Force
}
Write-Host 'LOCKED: Screen Resolution / Display settings hidden (NoDispCPL=1). Log off/on (or reboot) to apply.'
