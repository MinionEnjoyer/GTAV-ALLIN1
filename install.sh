#!/usr/bin/env bash
set -e

echo "============================================================"
echo "  GTA V ALLIN1 - Unlock All GTA Online Vehicles in SP"
echo "============================================================"
echo

# Find Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python is not installed."
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
    exit 1
fi
echo "[OK] Found Python $PYVER"

# Get script directory (works even if called from elsewhere)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set up virtual environment
if [ ! -d ".venv" ]; then
    echo
    echo "Setting up virtual environment..."
    $PYTHON -m venv .venv
    echo "[OK] Virtual environment created"
fi

# Activate and install
echo
echo "Installing dependencies..."
source .venv/bin/activate
pip install -e . --quiet 2>/dev/null
echo "[OK] Dependencies installed"

# Copy config if needed
if [ ! -f "config.toml" ]; then
    echo
    echo "Creating config.toml from example..."
    cp config.example.toml config.toml
    echo "[OK] Config created. Edit config.toml to customize settings."
else
    echo "[OK] Using existing config.toml"
fi

# Run installer (try auto-detection first)
echo
echo "============================================================"
echo "  Installing GTA Online vehicles into Single Player..."
echo "============================================================"
echo
allin1 install

if [ $? -ne 0 ]; then
    echo
    echo "[INFO] Auto-detection could not find GTA V."
    echo
    echo "Please enter the full path to your GTA V installation folder."
    echo "Example: /mnt/d/SteamLibrary/steamapps/common/Grand Theft Auto V"
    echo
    read -rp "GTA V path: " GTA_PATH

    if [ -z "$GTA_PATH" ]; then
        echo "[ERROR] No path entered. Exiting."
        exit 1
    fi

    # Write the path into config.toml
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

    echo
    echo "============================================================"
    echo "  Installing GTA Online vehicles into Single Player..."
    echo "============================================================"
    echo
    allin1 install

    if [ $? -ne 0 ]; then
        echo
        echo "[ERROR] Installation failed. Check the error above."
        echo "Make sure the path you entered contains GTA5.exe."
        exit 1
    fi
fi

echo
echo "============================================================"
echo "  Installation complete!"
echo
echo "  Prerequisites (if not already installed):"
echo "  - ASI Loader (dinput8.dll) in your GTA V folder"
echo "  - OpenIV.asi (or OpenRPF for Enhanced Edition)"
echo
echo "  These redirect the game to read from the mods/ folder."
echo "  Download OpenIV from openiv.com if you haven't already."
echo "============================================================"
