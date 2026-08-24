#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
python3 -m pip install -e '.[test]'
python3 -m pytest --cov=allin1 --cov-report=term-missing --cov-report=html
dotnet restore script/tests/ALLIN1.Tests.csproj
dotnet test script/tests/ALLIN1.Tests.csproj -c Release --no-restore
dotnet restore mods/realistic-suppressors/tests/RealisticSuppressors.Tests.csproj
dotnet test mods/realistic-suppressors/tests/RealisticSuppressors.Tests.csproj -c Release --no-restore

echo "All available automated test layers passed."
