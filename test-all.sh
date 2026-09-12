#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
python3 tools/hardening_harness.py --python python3
echo "Off-game hardening checks passed. Packaged and live-game checks were not run."
