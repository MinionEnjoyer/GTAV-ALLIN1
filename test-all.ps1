$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -m pip install -e ".[test]"
python -m pytest --cov=allin1 --cov-report=term-missing --cov-report=html
dotnet restore script/ALLIN1.csproj
dotnet build script/ALLIN1.csproj -c Release --no-restore

Write-Host "All available automated test layers passed." -ForegroundColor Green
