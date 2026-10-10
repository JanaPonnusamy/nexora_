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
# are auto-referenced -- we only add the extra assemblies the default set omits.
$fwRefs = 'System.Net.Http.dll','System.Windows.Forms.dll','System.Drawing.dll' |
          ForEach-Object { "/r:$(Join-Path $fw $_)" }

$exe = Join-Path $out 'NexoraOrderManagement.exe'
$src = Get-ChildItem (Join-Path $root 'src') -Filter *.cs | ForEach-Object { $_.FullName }

& $csc /nologo /target:winexe /platform:anycpu /optimize+ /warn:2 `
    "/out:$exe" $fwRefs $src
if ($LASTEXITCODE -ne 0) { throw "compile failed ($LASTEXITCODE)" }
Write-Host "Built $exe"
