[CmdletBinding(SupportsShouldProcess)]
param([switch]$Execute)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$knownDirectories = @(
    '.antigravity-clean-test',
    '.antigravity-empty-extensions',
    '.antigravity-postrepair-test',
    '.antigravity-repair',
    '.pytest_cache',
    'frontend\node_modules\.vite',
    'desktop\supplier-stock-client\node_modules\.vite'
)

$targets = foreach ($relativePath in $knownDirectories) {
    $candidate = Join-Path $repoRoot $relativePath
    if (Test-Path -LiteralPath $candidate -PathType Container) {
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        if (-not $resolved.StartsWith($repoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean path outside repository: $resolved"
        }
        $bytes = (Get-ChildItem -LiteralPath $resolved -Recurse -Force -File -ErrorAction SilentlyContinue |
            Measure-Object Length -Sum).Sum
        [pscustomobject]@{ Path = $resolved; Bytes = [long]$bytes }
    }
}

$targets | Sort-Object Bytes -Descending | ForEach-Object {
    [pscustomobject]@{
        Path = $_.Path
        SizeMB = [math]::Round($_.Bytes / 1MB, 2)
        Action = if ($Execute) { 'remove' } else { 'preview' }
    }
} | Format-Table -AutoSize

$totalBytes = ($targets | Measure-Object Bytes -Sum).Sum
Write-Host ("Total reclaimable: {0:N2} MB" -f ($totalBytes / 1MB))
if (-not $Execute) {
    Write-Host 'Dry run only. Re-run with -Execute to remove these generated caches/test profiles.'
    return
}

$removedBytes = 0L
$failures = @()
foreach ($target in $targets) {
    if ($PSCmdlet.ShouldProcess($target.Path, 'Remove generated cache/test profile')) {
        try {
            Remove-Item -LiteralPath $target.Path -Recurse -Force -ErrorAction Stop
            $removedBytes += $target.Bytes
        }
        catch {
            $failures += $target.Path
            Write-Warning "Could not remove $($target.Path): $($_.Exception.Message)"
        }
    }
}
Write-Host ("Reclaimed approximately {0:N2} MB." -f ($removedBytes / 1MB))
if ($failures.Count) {
    throw "Cleanup incomplete; $($failures.Count) path(s) could not be removed."
}
