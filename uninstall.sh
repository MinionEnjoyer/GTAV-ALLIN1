#!/usr/bin/env bash
set -e

echo "============================================================"
echo "  GTA V ALLIN1 - Uninstaller"
echo "============================================================"
echo
echo "This will restore your original GTA V files from backup."
echo

read -p "Are you sure you want to uninstall? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Cancelled."
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "[ERROR] Virtual environment not found. Was ALLIN1 installed?"
    exit 1
fi

source .venv/bin/activate
echo
echo "Restoring original game files..."
echo
allin1 uninstall

echo
echo "============================================================"
echo "  Uninstall complete! Original files have been restored."
echo "============================================================"
