#!/usr/bin/env bash
set -e

# Change to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Initialize log
LOGFILE="allin1.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOGFILE"; }

echo "" >> "$LOGFILE"
log "================================================================"
log "install.sh started"
log "================================================================"

echo "============================================================"
echo "  GTA V ALLIN1 - Unlock All GTA Online Vehicles in SP"
echo "============================================================"
echo

# Find Python
log "Checking for Python..."
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python is not installed."
    log "ERROR: Python not found in PATH"
    echo
    echo "Install Python 3.10+ from https://www.python.org/downloads/"
    echo "  macOS:  brew install python3"
    echo "  Linux:  sudo apt install python3 python3-venv"
    exit 1
fi

# Check version
PYVER=$($PYTHON --version 2>&1 | awk '{print $2}')
PYMAJOR=$(echo "$PYVER" | cut -d. -f1)
PYMINOR=$(echo "$PYVER" | cut -d. -f2)

if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 10 ]; }; then
    echo "[ERROR] Python 3.10+ is required. You have Python $PYVER."
    log "ERROR: Python $PYVER too old (need 3.10+)"
    exit 1
fi
echo "[OK] Found Python $PYVER"
log "Found Python $PYVER"

# Set up virtual environment
if [ ! -d ".venv" ]; then
    echo
    echo "Setting up virtual environment..."
    log "Creating virtual environment..."
    $PYTHON -m venv .venv
    echo "[OK] Virtual environment created"
    log "Virtual environment created"
else
    log "Using existing virtual environment"
fi

# Activate and install
echo
echo "Installing dependencies..."
log "Installing dependencies..."
source .venv/bin/activate
pip install -e . --quiet 2>/dev/null
echo "[OK] Dependencies installed"
log "Dependencies installed"

# Copy config if needed
if [ ! -f "config.toml" ]; then
    echo
    echo "Creating config.toml from example..."
    cp config.example.toml config.toml
    echo "[OK] Config created. Edit config.toml to customize settings."
    log "Created config.toml from example"
else
    echo "[OK] Using existing config.toml"
    log "Using existing config.toml"
fi

# Check for cached GTA path
if [ -f ".gta_path" ]; then
    CACHED_PATH=$(cat .gta_path)
    echo "[OK] Using cached GTA V path: $CACHED_PATH"
    log "Found cached GTA V path: $CACHED_PATH"
fi

# Run installer (try auto-detection first)
echo
echo "============================================================"
echo "  Installing GTA Online vehicles into Single Player..."
echo "============================================================"
echo
log "Running allin1 install..."
allin1 install

if [ $? -ne 0 ]; then
    echo
    echo "[INFO] Auto-detection could not find GTA V."
    log "Auto-detection failed, prompting for manual path"
    echo
    echo "Please enter the full path to your GTA V installation folder."
    echo "Example: /mnt/d/SteamLibrary/steamapps/common/Grand Theft Auto V"
    echo
    read -rp "GTA V path: " GTA_PATH

    if [ -z "$GTA_PATH" ]; then
        echo "[ERROR] No path entered. Exiting."
        log "ERROR: No manual path entered"
        exit 1
    fi

    log "User entered path: $GTA_PATH"

    # Write the path into config.toml and cache file
    echo
    echo "Updating config.toml with your GTA V path..."
    $PYTHON -c "
import re, sys
path = sys.argv[1]
with open('config.toml') as f:
    content = f.read()
content = re.sub(r'gta_path\s*=\s*\"[^\"]*\"', 'gta_path = \"' + path.replace('\\\\', '\\\\\\\\') + '\"', content)
with open('config.toml', 'w') as f:
    f.write(content)
" "$GTA_PATH"
    echo "$GTA_PATH" > .gta_path
    log "Wrote path to config.toml and .gta_path"

    echo
    echo "============================================================"
    echo "  Installing GTA Online vehicles into Single Player..."
    echo "============================================================"
    echo
    log "Retrying allin1 install with manual path..."
    allin1 install

    if [ $? -ne 0 ]; then
        echo
        echo "[ERROR] Installation failed. Check the error above."
        echo "Make sure the path you entered contains GTA5.exe."
        echo "See allin1.log for details."
        log "ERROR: Installation failed after manual path entry"
        exit 1
    fi
fi

log "Installation completed successfully"
echo
echo "============================================================"
echo "  Installation complete!"
echo
echo "  ALLIN1 has:"
echo "  - Modified popgroups.ymt, dlclist.xml, gameconfig.xml"
echo "  - Deployed ALLIN1.asi (DLC vehicle despawn fix)"
echo
echo "  Prerequisite (if not already installed):"
echo "  - ASI Loader (dinput8.dll) + OpenIV.asi in your GTA V folder"
echo "    (Download OpenIV from openiv.com)"
echo
echo "  Full log saved to: allin1.log"
echo "============================================================"
