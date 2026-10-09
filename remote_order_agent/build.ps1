# Builds NMVSyncAgent.exe with the .NET Framework 4.x compiler already present on Windows (no installs).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$csc  = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$fw   = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$out  = Join-Path $root 'bin'
$json = Join-Path $root 'lib\Newtonsoft.Json.dll'
New-Item -ItemType Directory -Force $out | Out-Null
Copy-Item $json $out -Force
$refs = 'System.dll','System.Core.dll','System.Data.dll','System.Xml.dll','System.Xml.Linq.dll','System.ServiceProcess.dll',
        'System.Security.dll','System.Runtime.Serialization.dll','System.Numerics.dll','System.Windows.Forms.dll','System.Drawing.dll' | ForEach-Object { "/r:$(Join-Path $fw $_)" }
$src = Get-ChildItem (Join-Path $root 'src') -Filter *.cs | ForEach-Object { $_.FullName }
& $csc /nologo /target:exe /platform:anycpu /optimize+ /warn:4 "/out:$(Join-Path $out 'NMVSyncAgent.exe')" $refs "/r:$json" $src
if ($LASTEXITCODE -ne 0) { throw "compile failed ($LASTEXITCODE)" }
Write-Host "Built $(Join-Path $out 'NMVSyncAgent.exe')"
