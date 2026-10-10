# Builds NexoraOrderManagement.exe with the .NET Framework 4.x compiler already
# present on Windows -- no SDK, no Visual Studio, no vendored DLLs. JSON uses the
# in-box System.Web.Extensions (JavaScriptSerializer), so the output is a single
# self-contained exe that runs on any Windows with .NET Framework 4.x (7 SP1+).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$csc  = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$fw   = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$out  = Join-Path $root 'bin'
New-Item -ItemType Directory -Force $out | Out-Null

if (-not (Test-Path $csc)) { throw "csc not found at $csc" }

# System.Web.Extensions (JavaScriptSerializer, our JSON engine) and the common
# BCL assemblies are already in csc's default response file (csc.rsp), so they
# are auto-referenced -- we only add the extra assemblies the default set omits
# (System.Net.Http, WinForms, Drawing, and the DataVisualization chart control
# that the VB form uses).
$fwRefs = 'System.Net.Http.dll','System.Windows.Forms.dll','System.Drawing.dll',
          'System.Windows.Forms.DataVisualization.dll' |
          ForEach-Object { "/r:$(Join-Path $fw $_)" }

# Embed the blue background image (same wallpaper the VB form uses) so the exe
# stays a single self-contained file. Loaded at runtime via the manifest name
# "NexoraOrderManagement.vb_bg.png".
$bg = Join-Path $root 'assets\vb_bg.png'
$res = @()
if (Test-Path $bg) { $res = @("/resource:$bg,NexoraOrderManagement.vb_bg.png") }

$exe = Join-Path $out 'NexoraOrderManagement.exe'
$src = Get-ChildItem (Join-Path $root 'src') -Filter *.cs | ForEach-Object { $_.FullName }

& $csc /nologo /target:winexe /platform:anycpu /optimize+ /warn:2 `
    "/out:$exe" $fwRefs $res $src
if ($LASTEXITCODE -ne 0) { throw "compile failed ($LASTEXITCODE)" }
Write-Host "Built $exe"
