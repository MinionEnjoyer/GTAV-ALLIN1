"""Freeze the SDK CPU preview renderer without bundling its desktop application."""
from pathlib import Path
import subprocess
import sys


def build(root: Path, sdk: Path | None = None):
    sdk = sdk or root.parent/'ALLIN1-SDK'
    if not (sdk/'src/allin1_sdk/native_assets.py').is_file():
        raise FileNotFoundError('Building the preview worker requires an ALLIN1-SDK source checkout')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--console', '--onefile',
        '--name', 'WeaponPreview', '--distpath', str(root/'tools/WeaponPreview'),
        '--workpath', str(root/'build/weapon-preview-freeze'), '--specpath', str(root/'build'),
        '--paths', str(root/'src'), '--paths', str(sdk/'src'),
        '--exclude-module', 'tkinter', '--exclude-module', 'PIL.ImageTk',
        str(root/'tools/weapon_preview_entry.py')], check=True, cwd=root)
    return root/'tools/WeaponPreview/WeaponPreview.exe'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, help='SDK source checkout used to freeze the renderer')
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[1], args.sdk)
