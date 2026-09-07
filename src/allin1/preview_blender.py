"""Lightweight per-user Blender discovery. Never imported from the SDK in IPC."""
import hashlib
import json
import os
from pathlib import Path
import shutil


def settings_path():
    return Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))/'ALLIN1'/'preview-tools.json'


def select_blender(project):
    config = settings_path()
    saved = json.loads(config.read_text(encoding='utf-8')) if config.is_file() else {}
    explicit = os.environ.get('BLENDER_EXECUTABLE') or saved.get('blender_executable')
    if explicit:
        path = Path(explicit)
        if not path.is_file() or path.name.casefold() != 'blender.exe':
            raise ValueError('Invalid Blender override in '+str(config)+'; select an existing blender.exe')
        return path.resolve()
    candidates = []
    on_path = shutil.which('blender')
    if on_path: candidates.append(Path(on_path))
    # Development SDK portable dependency. Packaged installations can reference
    # the same executable through per-user settings, never a shipped local path.
    candidates += sorted((Path(project).parent/'ALLIN1-SDK/build/dependencies').glob('blender-*-windows-x64/blender.exe'), reverse=True)
    candidates += sorted((Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Blender Foundation').glob('Blender */blender.exe'), reverse=True)
    for path in candidates:
        if path.is_file(): return path.resolve()
    raise ValueError('Catalog previews require Blender. Set BLENDER_EXECUTABLE or blender_executable in '+str(config)+'. Existing artwork is retained.')


def identity(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()
