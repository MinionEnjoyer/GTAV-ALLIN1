$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "The project environment is missing. Run install.bat once before test-all.ps1."
}

& $python -m pip install -e ".[test]"
if ($LASTEXITCODE -ne 0) { throw "Installing the test environment failed." }
& $python -m pytest --cov=allin1 --cov-report=term-missing --cov-report=html --cov-fail-under=91
if ($LASTEXITCODE -ne 0) { throw "Python tests or coverage qualification failed." }
dotnet restore script/tests/ALLIN1.Tests.csproj
if ($LASTEXITCODE -ne 0) { throw "Restoring the C# client failed." }
dotnet test script/tests/ALLIN1.Tests.csproj -c Release --no-restore
if ($LASTEXITCODE -ne 0) { throw "C# client tests failed." }
Get-Item -LiteralPath "script/dist/ALLIN1.dll", "script/dist/ALLIN1.ReactorBridge.plugin", "script/dist/ALLIN1.ReactorBridge.contract.json" | Out-Null

if (-not (Test-Path -LiteralPath "tools/RpfPatcher/RpfPatcher.exe")) {
    throw "RpfPatcher runtime is missing. Run runtools.ps1 before release qualification."
}

$version = (& $python -c "from allin1 import __version__; print(__version__)").Trim()
$archive = Join-Path $root "output\GTAV-ALLIN1-$version.zip"
& $python -m allin1.cli build-release --output $archive
if ($LASTEXITCODE -ne 0) { throw "Building the public release failed." }
& $python -m allin1.cli verify-release $archive
if ($LASTEXITCODE -ne 0) { throw "Verifying the public release failed." }

Write-Host "All automated layers and the public release archive passed." -ForegroundColor Green
