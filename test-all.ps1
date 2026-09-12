$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "The project environment is missing. Run install.bat once before test-all.ps1."
}

# This is an already-generated artifact check only. The harness records its
# hash separately and never rebuilds or publishes a distribution archive.
Get-Item -LiteralPath "script/dist/ALLIN1.ReactorBridge.contract.json" | Out-Null
& $python tools\hardening_harness.py --python $python
if ($LASTEXITCODE -ne 0) { throw "Off-game hardening checks failed; inspect build\hh evidence." }
Write-Host "Off-game hardening checks passed. Packaged and live-game checks were not run." -ForegroundColor Green
