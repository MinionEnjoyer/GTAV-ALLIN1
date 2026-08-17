#!/usr/bin/env bash
set -e

# Change to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Initialize log
LOGFILE="allin1.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOGFILE"; }

echo "" >> "$LOGFILE"
log "uninstall.sh started"

echo "============================================================"
echo "  GTA V ALLIN1 - Uninstaller"
echo "============================================================"
echo
echo "This will restore your original GTA V files from backup."
echo

read -p "Are you sure you want to uninstall? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Cancelled."
    log "Uninstall cancelled by user"
    exit 0
fi

if [ ! -d ".venv" ]; then
    echo "[ERROR] Virtual environment not found. Was ALLIN1 installed?"
    log "ERROR: .venv not found"
    exit 1
fi

source .venv/bin/activate
echo
echo "Restoring original game files..."
echo
log "Running allin1 uninstall..."
allin1 uninstall

if [ $? -ne 0 ]; then
    echo
    echo "[ERROR] Uninstall failed. Check the error above."
    echo "See allin1.log for details."
    log "ERROR: allin1 uninstall failed"
    exit 1
fi

log "Uninstall completed successfully"
echo
echo "============================================================"
echo "  Uninstall complete! Original files have been restored."
echo "  Full log saved to: allin1.log"
echo "============================================================"
