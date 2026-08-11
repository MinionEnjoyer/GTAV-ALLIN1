#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
python3 -m pip install -e '.[test]'
python3 -m pytest --cov=allin1 --cov-report=term-missing --cov-report=html
dotnet restore script/ALLIN1.csproj
dotnet build script/ALLIN1.csproj -c Release --no-restore

echo "All available automated test layers passed."
